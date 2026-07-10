"""M3 — the memory kernel, and the experiment that decides everything.

Estimation (spec [locked: method] [open: order]):

1. Resolved trajectories ``a(t)`` = corpus windows projected to macro
   coordinates, per track.
2. Autocorrelation ``C(τ)`` per macro, τ up to 30 s, per-track then averaged.
3. Fit ``K(t) = Σ_j c_j e^{−γ_j t} cos(ω_j t + φ_j)`` with J = 2 then 3 modes.

Exact identity used (the "practical route" the spec allows and asks us to
document):

    We fit the *normalized resolved autocorrelation* C(t)/C(0) directly with a
    damped-oscillator basis Σ_j c_j e^{−γ_j t} cos(ω_j t + φ_j), and take the
    fitted parameters (c_j, γ_j, ω_j, φ_j) as the memory-kernel modes. This is
    the Markovian-embedding / mode-matching identity: a resolved coordinate
    whose autocorrelation is a sum of damped cosines is exactly the coordinate
    of a linear GLE whose memory kernel carries those same damped-cosine modes
    (each underdamped oscillator contributes one e^{−γt}cos(ωt+φ) term to both
    C and K). We therefore identify K with the fitted autocorrelation shape;
    the overall amplitude is absorbed into the orbit's memory-strength knob κ.

Order (J) is chosen by track-held-out cross-validation. The kernel's ω_j are
cross-checked against the corpus's beat/bar/phrase periods; mismatches are
reported (in LEDGER), never forced.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.optimize


@dataclass
class KernelFit:
    """A fitted memory kernel over the macro coordinates."""

    modes: list              # [n_macros] of list-of-(c, gamma, omega, phi)
    order: int               # J actually used
    step_s: float
    max_lag_steps: int
    Kvals: np.ndarray        # [n_macros, max_lag_steps+1] sampled kernel (lag 0..L)
    cv_error: float          # track-held-out CV error at the chosen order
    omega_hz: list           # [n_macros] fitted frequencies in Hz
    tempo_hz: dict           # {'beat','bar','phrase'} reference frequencies
    tempo_check: list        # per-mode note on rational relation to tempo
    clamped: bool = False

    def memory_knob(self, history_a: list) -> np.ndarray:
        """Memory integral Σ_s K(t−s)·a(s) as a macro-coordinate knob.

        ``history_a`` is the orbit's list of resolved coordinates a(0..t); the
        return is a vector over macros (later projected onto charts via ψ).
        """
        hist = np.asarray(history_a)                 # [T, n_macros]
        if hist.ndim != 2 or hist.shape[0] == 0:
            return np.zeros(self.Kvals.shape[0])
        T, M = hist.shape
        L = self.Kvals.shape[1] - 1
        d = min(T, L + 1)
        # lag 0 uses the current sample, lag d uses hist[T-1-d]
        K = self.Kvals[:, :d]                        # [M, d]
        recent = hist[T - d:][::-1].T                # [M, d] aligned to lags
        return np.sum(K * recent, axis=1)

    def clamp_spectral_radius(self, bound: float = 1.0) -> None:
        """Scale each macro's kernel so Σ_τ |K(τ)| ≤ bound (outcome-(c) guard)."""
        mass = np.sum(np.abs(self.Kvals), axis=1, keepdims=True)
        scale = np.minimum(1.0, bound / np.maximum(mass, 1e-9))
        self.Kvals = self.Kvals * scale
        self.clamped = bool(np.any(scale < 1.0))


# ---------------------------------------------------------------------------
# Resolved trajectories + autocorrelation
# ---------------------------------------------------------------------------

def resolved_trajectories(memberships: np.ndarray, psi: np.ndarray,
                          track_bounds: list) -> list:
    """Per-track macro-coordinate trajectories ``a(t) = m(t) @ ψ``."""
    a_full = memberships @ psi                       # [n_windows, n_macros]
    return [a_full[s:e] for (s, e) in track_bounds if e - s >= 2]


def autocorr(trajs: list, max_lag: int) -> np.ndarray:
    """Per-macro autocorrelation averaged over tracks. Returns ``[M, max_lag+1]``."""
    M = trajs[0].shape[1]
    acc = np.zeros((M, max_lag + 1))
    wsum = np.zeros(max_lag + 1)
    for a in trajs:
        a = a - a.mean(0, keepdims=True)
        T = a.shape[0]
        for lag in range(min(max_lag, T - 1) + 1):
            acc[:, lag] += np.sum(a[lag:] * a[:T - lag], axis=0)
            wsum[lag] += (T - lag)
    wsum[wsum < 1] = 1.0
    C = acc / wsum
    c0 = C[:, :1].copy()
    c0[c0 < 1e-12] = 1.0
    return C / c0                                    # normalized to C(0)=1


# ---------------------------------------------------------------------------
# Damped-oscillator fit
# ---------------------------------------------------------------------------

def _basis(t: np.ndarray, params: np.ndarray) -> np.ndarray:
    """Σ_j c_j e^{−γ_j t} cos(ω_j t + φ_j) with params flattened [c,γ,ω,φ]*J."""
    J = params.size // 4
    out = np.zeros_like(t)
    for j in range(J):
        c, g, w, p = params[4 * j:4 * j + 4]
        out += c * np.exp(-g * t) * np.cos(w * t + p)
    return out


def _fit_one(t: np.ndarray, C: np.ndarray, J: int):
    """Fit J damped cosines to one autocorrelation curve. Returns params, resid."""
    # frequency seeds from the autocorr spectrum
    spec = np.abs(np.fft.rfft(C - C.mean()))
    freqs = 2 * np.pi * np.fft.rfftfreq(len(C), d=1.0)   # rad / step
    order = np.argsort(-spec[1:]) + 1
    seeds = freqs[order[:J]] if order.size else np.linspace(0.1, 1.0, J)
    seeds = np.pad(seeds, (0, max(0, J - seeds.size)),
                   constant_values=0.3)[:J]

    p0, lo, hi = [], [], []
    for j in range(J):
        p0 += [1.0 / J, 0.05, max(1e-3, seeds[j]), 0.0]
        lo += [-2.0, 1e-4, 0.0, -np.pi]
        hi += [2.0, 5.0, np.pi, np.pi]

    def resid(p):
        return _basis(t, p) - C

    try:
        sol = scipy.optimize.least_squares(resid, p0, bounds=(lo, hi),
                                           max_nfev=4000)
        return sol.x, float(np.mean(sol.fun ** 2))
    except Exception:
        return np.array(p0), float(np.mean((_basis(t, np.array(p0)) - C) ** 2))


def _cv_error(trajs: list, max_lag: int, J: int) -> float:
    """Track-held-out CV error at order J, averaged over macros and folds."""
    if len(trajs) < 2:
        C = autocorr(trajs, max_lag)
        t = np.arange(max_lag + 1, dtype=float)
        errs = [_fit_one(t, C[m], J)[1] for m in range(C.shape[0])]
        return float(np.mean(errs))
    t = np.arange(max_lag + 1, dtype=float)
    fold_errs = []
    for held in range(len(trajs)):
        train = [a for i, a in enumerate(trajs) if i != held]
        Ctr = autocorr(train, max_lag)
        Cte = autocorr([trajs[held]], max_lag)
        for m in range(Ctr.shape[0]):
            p, _ = _fit_one(t, Ctr[m], J)
            fold_errs.append(np.mean((_basis(t, p) - Cte[m]) ** 2))
    return float(np.mean(fold_errs))


# ---------------------------------------------------------------------------
# Tempo cross-check
# ---------------------------------------------------------------------------

def _tempo_reference(paths: list, sr: int, step_s: float) -> dict:
    """Beat / bar / phrase reference frequencies (rad/step) from librosa tempo."""
    import librosa
    tempos = []
    tempo_fn = getattr(librosa.feature, "tempo", None) or librosa.beat.tempo
    for p in paths[: min(len(paths), 8)]:            # a sample is enough
        try:
            y, _ = librosa.load(p, sr=sr, mono=True)
            tempos.append(float(np.atleast_1d(tempo_fn(y=y, sr=sr))[0]))
        except Exception:
            continue
    if not tempos:
        return {"beat": 0.0, "bar": 0.0, "phrase": 0.0}
    bpm = float(np.median(tempos))
    beat_hz = bpm / 60.0
    to_rad = 2 * np.pi * step_s                       # Hz → rad/step
    return {
        "beat": beat_hz * to_rad,
        "bar": (beat_hz / 4.0) * to_rad,              # 4-beat bar
        "phrase": (beat_hz / 32.0) * to_rad,          # 8-bar phrase
    }


def _tempo_note(omega: float, ref: dict) -> str:
    """Nearest rational relation of ``omega`` (rad/step) to a tempo reference."""
    if omega <= 1e-6:
        return "dc/near-zero mode"
    best, ratio = None, None
    for name, w in ref.items():
        if w <= 1e-6:
            continue
        r = omega / w
        # closeness to a small rational (n/m, n,m <= 4)
        cands = [n / m for n in range(1, 5) for m in range(1, 5)]
        near = min(cands, key=lambda c: abs(r - c))
        if best is None or abs(r - near) < ratio:
            best, ratio = f"{omega:.3f}≈{near:.2f}×{name}", abs(r - near)
    return best or "no reference"


# ---------------------------------------------------------------------------
# Top-level fit
# ---------------------------------------------------------------------------

def fit_kernel(memberships: np.ndarray, psi: np.ndarray, track_bounds: list,
               cfg: dict, track_paths: list) -> KernelFit:
    """Fit the memory kernel; pick order 2 vs 3 by held-out CV."""
    step_s = float(cfg["step_s"])
    sr = int(cfg["sr"])
    max_order = int(cfg.get("prony_order", 2))
    max_lag = max(2, int(round(30.0 / step_s)))       # τ up to 30 s

    trajs = resolved_trajectories(memberships, psi, track_bounds)
    if not trajs or psi.shape[1] == 0:
        M = max(psi.shape[1], 0)
        return KernelFit(modes=[[] for _ in range(M)], order=0, step_s=step_s,
                         max_lag_steps=max_lag, Kvals=np.zeros((M, max_lag + 1)),
                         cv_error=float("nan"), omega_hz=[],
                         tempo_hz={}, tempo_check=[])

    # choose order in {2, ..., max_order} (spec allows up to 3) by CV
    candidate_orders = list(range(2, max(2, min(3, max_order)) + 1))
    cv = {J: _cv_error(trajs, max_lag, J) for J in candidate_orders}
    order = min(cv, key=cv.get)

    C = autocorr(trajs, max_lag)                      # [M, L+1]
    t = np.arange(max_lag + 1, dtype=float)
    ref = _tempo_reference(track_paths, sr, step_s)

    modes, Kvals, omega_hz, checks = [], [], [], []
    for m in range(C.shape[0]):
        p, _ = _fit_one(t, C[m], order)
        Kvals.append(_basis(t, p))
        mode_list = []
        for j in range(order):
            c, g, w, ph = p[4 * j:4 * j + 4]
            mode_list.append((float(c), float(g), float(w), float(ph)))
            omega_hz.append(w / (2 * np.pi * step_s))
            checks.append(_tempo_note(w, ref))
        modes.append(mode_list)

    return KernelFit(
        modes=modes, order=order, step_s=step_s, max_lag_steps=max_lag,
        Kvals=np.asarray(Kvals), cv_error=float(cv[order]),
        omega_hz=omega_hz, tempo_hz=ref, tempo_check=checks,
    )
