"""PHRASE EOC GATE meter (spec §9, §1 GATE type; consumed by §10 mode-3b
feedback "EOC -> scene advance").

A phrase is the dominant recurrence CYCLE of an arrangement trajectory: the lag
at which the per-bar occupancy pattern most strongly repeats. The EOC gate fires
at the end of each such cycle. It is a pure function (occupancy trajectory) ->
gate in {0,1}, taking NO F-weights and feeding NOTHING back into a solve — its
only sanctioned consumers are the planner and CV-lane feedback (I-5, I-14).

Gauge-invariance basis: the meter reads ONLY cosine self-similarities between
bars of the trajectory. A global gauge action transforms every bar identically —
a common cyclic roll of the metrical-slot axis is a single permutation applied to
all bar vectors, and a permutation is orthogonal, so ⟨roll·a, roll·b⟩ = ⟨a,b⟩;
transposition does not touch role×slot occupancy; loudness is renormalized away.
Hence every pairwise similarity, the detected period, and the gate are invariant
(spec §3, I-2). Verified to machine precision by the meter gauge-invariance test.

Derivation of the only constant (the period): it is the arg-max of the
trajectory's OWN lagged self-similarity — a property measured from the data, not
a hand-set phrase length (spec: "every constant shows its derivation or dies").
When no positive recurrence exists the gate is empty (honest: no phrase detected).

This module imports ONLY numpy (no functional/solver dependency; I-14).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np


def _normalize_rows(X: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(X, axis=1, keepdims=True)
    return X / (n + 1e-12)


def dominant_period(X: np.ndarray) -> Tuple[Optional[int], float]:
    """Dominant recurrence period of a per-bar trajectory X (T, d), by lagged
    cosine self-similarity. Returns (period, strength). period is None (strength
    0.0) when T is too short or no lag has positive above-average self-similarity
    — i.e. no cycle is present. The period is DERIVED (arg-max over lags), never
    hand-set."""
    X = np.asarray(X, float)
    T = X.shape[0]
    if T < 4:
        return None, 0.0
    Xn = _normalize_rows(X)
    max_lag = T // 2
    scores = np.array([float(np.mean(np.sum(Xn[:-L] * Xn[L:], axis=1)))
                       for L in range(1, max_lag + 1)])
    # a genuine cycle: the best lag must beat the mean lag-similarity (else the
    # trajectory has no preferred recurrence).
    best = int(np.argmax(scores))
    period = best + 1
    strength = float(scores[best] - scores.mean())
    if strength <= 0.0:
        return None, 0.0
    return period, strength


@dataclass(frozen=True)
class PhraseEOC:
    gate: np.ndarray            # (T,) in {0,1}: 1 at each end-of-cycle bar
    period: Optional[int]       # detected dominant cycle length (bars), or None
    strength: float             # recurrence strength (self-similarity peak margin)


def phrase_eoc(occupancy_traj: np.ndarray) -> PhraseEOC:
    """PHRASE EOC gate from an occupancy trajectory.

    ``occupancy_traj`` is (T, d): one occupancy feature vector per bar (e.g. the
    flattened role×slot occupancy the machine already produces). Fires the gate at
    the last bar of every dominant-period cycle. If no cycle is detected the gate
    is all zeros (no phrase structure)."""
    X = np.asarray(occupancy_traj, float)
    if X.ndim != 2:
        raise ValueError("occupancy_traj must be 2-D (T, d)")
    T = X.shape[0]
    gate = np.zeros(T, dtype=np.int64)
    period, strength = dominant_period(X)
    if period is not None:
        # end-of-cycle bars: p-1, 2p-1, 3p-1, ...  (last bar of each cycle)
        idx = np.arange(period - 1, T, period)
        gate[idx] = 1
    return PhraseEOC(gate=gate, period=period, strength=strength)
