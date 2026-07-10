"""M2 — Markovian orbit (the K-less control condition), extended with M3 memory.

State is a soft chart-mixture ``m`` (a vector over charts). Each discrete step
(at the window rate, ``step_s``):

    m' ∝ (m @ P) * exp( β·bias_align − γ·visitation + κ·memory )
    m' ← sharpen(m', τ) ; renormalize ; keep top 8

* ``bias_align(chart) = knob_vector · ψ(chart)`` — knobs are a vector in
  diffusion (macro) coordinates; β scales lean strength.
* ``visitation`` is an exponentially-decaying recent-visit count; γ=0 exactly
  reproduces pure PULL.
* ``memory`` is the M3 kernel term ``Σ_s K(t−s)·a(s)`` projected onto charts
  via ψ — a time-varying knob computed from the orbit's own history. κ=0
  exactly reproduces M2.

``τ`` (temperature) is the drift knob: low = mode-following, high = diffuse.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class OrbitState:
    """One step of the orbit, retained for rendering and the co-moving panel."""

    m: np.ndarray            # chart mixture (rows sum 1)
    a: np.ndarray            # resolved macro coordinate  = m @ psi
    a_pred: np.ndarray       # PULL(+kernel) prediction of this step's a
    top_charts: np.ndarray   # indices of the kept charts
    m_full: np.ndarray = None  # untruncated tilted one-step mixture (region
    #                            gate for flow reads: the walk's own full
    #                            posterior — top-k truncation is an emission
    #                            device and would jitter the gate)


class Orbit:
    """Steerable walk over the transfer operator in chart-mixture space."""

    def __init__(self, P: np.ndarray, psi: np.ndarray, cfg: dict,
                 knob_vector: np.ndarray | None = None,
                 kernel=None, seed: int = 0, modes=None, basins=None):
        self.P = P
        self.psi = psi                       # [n_charts, n_macros]
        self.n_charts = P.shape[0]
        self.n_macros = psi.shape[1]
        self.beta = float(cfg.get("beta", 1.0))
        self.gamma = float(cfg.get("gamma", 0.3))
        self.tau = float(cfg.get("tau", 1.0))
        self.kappa = float(cfg.get("kappa", 1.0))
        self.top_k = int(cfg.get("top_memberships", 8))
        self.step_s = float(cfg.get("step_s", 0.75))
        self.knob = (np.zeros(self.n_macros) if knob_vector is None
                     else np.asarray(knob_vector, float))
        self.kernel = kernel                 # None → pure M2
        self.rng = np.random.default_rng(seed)

        # Momentum orbit v2 (eigenmode flywheel): momentum lives in the
        # transfer operator's own oscillatory eigenmodes. For each complex
        # pair λ_i, v_i, keep a flywheel ζ_i = Σ_s λ_i^{t−s}·z_i(s) — the
        # walk's history convolved with the mode's own damping+rotation, i.e.
        # the GLE memory integral evaluated in the operator's eigenbasis. The
        # tilt pushes toward the phase-advanced field Re[λ_i ζ_i v_i(chart)].
        # Everything (damping |λ|, frequency arg λ, mode shapes) is spectral
        # data of P itself; β_p is the only strength scalar. momentum=0
        # reproduces the memoryless walk bit-for-bit.
        self.beta_p = float(cfg.get("momentum", 0.0))
        self._fly = None
        # init the flywheel whenever modes are available (not just when β_p>0)
        # so momentum can be raised live from 0 mid-orbit (panel slider).
        if self.beta_p != 0.0 or modes is not None:
            self._init_modes(modes)

        # Territory-scale wanderlust: dwelling pressure accumulated per
        # DISCOVERED BASIN (differential — only relative over-occupancy
        # pushes), γ-gated, timescale = median track length (pure corpus
        # statistic, supplied by the caller as basin_halflife_steps). This is
        # the escape force for large traps (e.g. the quiet-material basin)
        # that chart-level visitation cannot build pressure against.
        self.chart_basin = np.asarray(basins) if basins is not None else None
        if self.chart_basin is not None:
            self.n_basins = int(self.chart_basin.max()) + 1
            self.basin_visit = np.zeros(self.n_basins)
            hl = float(cfg.get("basin_halflife_steps") or 0) or None
            self.basin_decay = (0.5 ** (1.0 / hl)) if hl else None
        else:
            self.basin_decay = None

        self.visitation = np.zeros(self.n_charts)
        self.visit_decay = 0.9
        self.history_a: list = []            # resolved macro coords a(t)
        self._m = None

    # -- initialisation -----------------------------------------------------

    def _init_modes(self, modes, k_modes: int = 4) -> None:
        """Select the top oscillatory eigenmodes of P for the flywheel.

        ``modes`` is an optional ``(eigvals, right_vecs)`` pair from the
        instrument file (sorted by |λ|); if absent, P is eigendecomposed here.
        One member of each conjugate pair is kept (positive imaginary part).
        """
        if modes is None:
            import scipy.linalg
            vals, vecs = scipy.linalg.eig(self.P)
            order = np.argsort(-np.abs(vals))
            vals, vecs = vals[order], vecs[:, order]
        else:
            vals, vecs = modes
        idx = [i for i in range(len(vals)) if np.imag(vals[i]) > 1e-9][:k_modes]
        if not idx:
            self._fly = np.zeros(0, dtype=complex)
            self._mode_vals = np.zeros(0, dtype=complex)
            self._mode_vecs = np.zeros((self.n_charts, 0), dtype=complex)
            self._mode_left = np.zeros((0, self.n_charts), dtype=complex)
            return
        self._mode_vals = np.asarray(vals)[idx]
        self._mode_vecs = np.asarray(vecs)[:, idx]           # [n_charts, K]
        # left eigen-rows (biorthogonal projections) via pseudo-inverse
        self._mode_left = np.linalg.pinv(np.asarray(vecs))[idx, :]
        self._fly = np.zeros(len(idx), dtype=complex)
        self.mode_weights = np.ones(len(idx))    # per-mode depth (panel LFO bank)

    def seed_state(self, chart: int | None = None) -> np.ndarray:
        """Start the orbit on a single chart (default: a random one)."""
        m = np.zeros(self.n_charts)
        c = self.rng.integers(self.n_charts) if chart is None else chart
        m[c] = 1.0
        self._m = m
        return m

    # -- tilt terms ---------------------------------------------------------

    def _bias_align(self) -> np.ndarray:
        return self.psi @ self.knob                    # [n_charts]

    def _memory_tilt(self) -> np.ndarray:
        """Kernel memory term projected onto charts, or zeros if κ=0/no kernel."""
        if self.kernel is None or self.kappa == 0.0 or not self.history_a:
            return np.zeros(self.n_charts)
        macro_knob = self.kernel.memory_knob(self.history_a)   # [n_macros]
        # Normalize to unit magnitude so κ is a well-scaled strength knob and the
        # windowed history sum can't snowball into a positive-feedback collapse
        # (the unnormalized term sums ~40 same-sign steps → runaway tilt).
        n = np.linalg.norm(macro_knob)
        if n > 1e-9:
            macro_knob = macro_knob / n
        return self.psi @ macro_knob

    def _basin_pressure(self) -> np.ndarray:
        """γ-scaled differential dwelling pressure over discovered basins."""
        if self.basin_decay is None or self.gamma == 0.0:
            return np.zeros(self.n_charts)
        diff = self.basin_visit - self.basin_visit.mean()
        return self.gamma * diff[self.chart_basin]

    def _momentum_tilt(self) -> np.ndarray:
        """Phase-advanced eigenmode field, standardized over charts.

        ``field(c) = Σ_i Re[λ_i·ζ_i·v_i(c)]`` — where each oscillatory mode's
        flywheel says the state should rotate to next. Smooth by construction:
        the field turns at arg λ per step and the flywheel integrates
        ~1/(1−|λ|) steps of history, so it steers drift, not per-step reads.
        """
        if self.beta_p == 0.0 or self._fly is None or not len(self._fly):
            return np.zeros(self.n_charts)
        field = np.real(self._mode_vecs
                        @ (self._mode_vals * self._fly * self.mode_weights))
        s = field.std()
        if s > 1e-12:
            field = field / s
        return self.beta_p * field

    def _predict(self, m: np.ndarray) -> np.ndarray:
        """PULL(+kernel) prediction of the next resolved coordinate.

        Used by the co-moving panel: innovation = actual a − this prediction.
        """
        pulled = m @ self.P
        s = pulled.sum()
        pulled = pulled / s if s > 1e-12 else pulled
        return pulled @ self.psi

    # -- stepping -----------------------------------------------------------

    def step(self) -> OrbitState:
        if self._m is None:
            self.seed_state()
        m = self._m

        a_pred = self._predict(m)

        pulled = m @ self.P                            # PULL
        log_tilt = (self.beta * self._bias_align()
                    - self.gamma * self.visitation
                    + self.kappa * self._memory_tilt()
                    + self._momentum_tilt()
                    - self._basin_pressure())
        # stabilise exp
        log_tilt = log_tilt - log_tilt.max()
        raw = pulled * np.exp(log_tilt)

        s = raw.sum()
        if s < 1e-12:                                  # dangling → restart diffuse
            raw = np.ones(self.n_charts) / self.n_charts
        else:
            raw = raw / s

        m_new = self._sharpen(raw)
        m_new = self._keep_top(m_new)          # emission mixture (for grain read)

        a = m_new @ self.psi
        self.history_a.append(a)
        self.visitation = self.visit_decay * self.visitation + m_new
        top = np.nonzero(m_new)[0]

        # flywheel update: rotate+damp by the mode's own eigenvalue, entrain
        # to the walk's actual state — ζ_i(t) = Σ_s λ_i^{t−s} z_i(s).
        if self._fly is not None and len(self._fly):
            z = self._mode_left @ m_new
            self._fly = self._mode_vals * self._fly + z

        # basin dwelling pressure (EMA of basin occupancy)
        if self.basin_decay is not None:
            bm = np.bincount(self.chart_basin, weights=m_new,
                             minlength=self.n_basins)
            self.basin_visit = (self.basin_decay * self.basin_visit
                                + (1.0 - self.basin_decay) * bm)

        # Re-localize to a concrete chart sampled from the emission mixture.
        # Propagating the full mixture through P instead converges to the
        # stationary distribution and freezes the orbit (argmax stuck on one
        # chart); sampling a position each step keeps it a *moving* walk while
        # still stepping through P and honoring every tilt term. γ=0 remains a
        # pure-PULL walk; κ=0 still reproduces M2 (identical rng draws).
        c = self.rng.choice(self.n_charts, p=m_new / m_new.sum())
        nxt = np.zeros(self.n_charts)
        nxt[c] = 1.0
        self._m = nxt
        return OrbitState(m=m_new, a=a, a_pred=a_pred, top_charts=top,
                          m_full=raw)

    def _sharpen(self, m: np.ndarray) -> np.ndarray:
        """Temperature sharpening: exponent 1/τ. Low τ → peaky (mode-follow)."""
        if self.tau <= 0:
            out = np.zeros_like(m)
            out[np.argmax(m)] = 1.0
            return out
        p = np.power(np.maximum(m, 0.0), 1.0 / self.tau)
        s = p.sum()
        return p / s if s > 1e-12 else m

    def _keep_top(self, m: np.ndarray) -> np.ndarray:
        k = min(self.top_k, self.n_charts)
        keep = np.argpartition(-m, k - 1)[:k]
        out = np.zeros_like(m)
        out[keep] = m[keep]
        s = out.sum()
        return out / s if s > 1e-12 else m

    def relocalize(self, m: np.ndarray) -> None:
        """Snap the walk's state to a given chart-membership (flow coupling).

        Used by flow-mode rendering: after a grain is actually emitted, the
        walk continues from where playback *is*, so walk and sound stay one
        trajectory instead of two.
        """
        s = m.sum()
        if s > 1e-12:
            self._m = m / s

    def run(self, n_steps: int) -> list:
        """Run ``n_steps`` and return the list of :class:`OrbitState`."""
        return [self.step() for _ in range(n_steps)]
