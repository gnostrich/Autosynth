"""NOVELTY SATURATION CV meter (spec §9; the OUTPUT dual of the §8 NOVELTY
PRESSURE input lane).

Novelty saturation measures how EXHAUSTED the material is: the recency-weighted
degree to which the current bar re-uses recently-used role-slot occupancy vs.
introducing fresh support (connector φ_novelty = "recency-weighted unit reuse vs
the committed tape"). It is a pure function (occupancy trajectory) -> CV in
[0,1]: 0 = fully novel (current bar lies outside the recent support), 1 = fully
saturated (current bar recycles recent material). It takes NO F-weights and feeds
NOTHING back into a solve; its sanctioned consumers are the planner and CV-lane
feedback (I-5, I-14).

Gauge-invariance basis: like the phrase meter it reads only cosine similarities
between (non-negative) occupancy vectors, which are invariant to a common cyclic
roll of the slot axis (orthogonal permutation), to transposition (does not touch
role×slot occupancy) and to loudness (renormalized). Machine-precision verified.

Derivation of the only constant (the recency timescale τ): DERIVED from the
trajectory's own dominant recurrence period (phrase.dominant_period) — the
natural memory length of the material — not hand-set. τ is returned for audit.

This module imports ONLY numpy + the sibling phrase meter (no functional/solver
dependency; I-14).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np

from .phrase import dominant_period


@dataclass(frozen=True)
class NoveltySaturation:
    cv: np.ndarray             # (T,) saturation in [0,1]; cv[0] = 0
    tau: float                 # recency timescale actually used (bars), derived


def novelty_saturation(occupancy_traj: np.ndarray,
                       tau: Optional[float] = None) -> NoveltySaturation:
    """NOVELTY SATURATION CV from an occupancy trajectory (T, d).

    For each bar t, the recency-weighted past support is
        past_t = Σ_{τ<t} exp(-(t-1-τ)/τ_len) · X_τ
    and saturation_t = cosine(X_t, past_t) ∈ [0,1] (non-negative occupancy).
    ``tau`` (recency length in bars) defaults to the trajectory's dominant
    recurrence period; if none is detected it falls back to max(1, T/4)
    (a derived fraction of the horizon, not a magic number)."""
    X = np.asarray(occupancy_traj, float)
    if X.ndim != 2:
        raise ValueError("occupancy_traj must be 2-D (T, d)")
    T = X.shape[0]
    if tau is None:
        period, _ = dominant_period(X)
        tau = float(period) if period is not None else max(1.0, T / 4.0)
    tau = max(float(tau), 1e-6)

    cv = np.zeros(T)
    Xn = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-12)
    for t in range(1, T):
        ages = (t - 1) - np.arange(t)            # 0 for the immediately-past bar
        w = np.exp(-ages / tau)
        past = w @ X[:t]                          # (d,)
        pn = past / (np.linalg.norm(past) + 1e-12)
        cv[t] = float(np.clip(Xn[t] @ pn, 0.0, 1.0))
    return NoveltySaturation(cv=cv, tau=float(tau))
