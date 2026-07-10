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


class Orbit:
    """Steerable walk over the transfer operator in chart-mixture space."""

    def __init__(self, P: np.ndarray, psi: np.ndarray, cfg: dict,
                 knob_vector: np.ndarray | None = None,
                 kernel=None, seed: int = 0):
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

        self.visitation = np.zeros(self.n_charts)
        self.visit_decay = 0.9
        self.history_a: list = []            # resolved macro coords a(t)
        self._m = None

    # -- initialisation -----------------------------------------------------

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
                    + self.kappa * self._memory_tilt())
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
        return OrbitState(m=m_new, a=a, a_pred=a_pred, top_charts=top)

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
