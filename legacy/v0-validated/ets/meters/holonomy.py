"""Holonomy primitives (spec §9 drift meter, §13-G2, §10 planner map).

Two DISTINCT holonomy objects live here, both pure functions of a trajectory /
of the frozen world's geometry, both READ-ONLY instruments (I-5, I-14):

1. CIRCULAR HOLONOMY of a running gauge frame — the accumulated signed winding
   of a per-bar gauge-section value (transposition on the pitch-class circle,
   beat-phase on the metrical circle, ...). This is the core of the DRIFT CV
   meter (spec §9 "accumulated holonomy of the running frame").

   Gauge-invariance basis (exact, by construction): the accumulator reads ONLY
   the CONSECUTIVE DIFFERENCES of the frame (the discrete connection 1-form).
   A global gauge action re-references the frame by a single constant offset c
   (choosing a different overall key / downbeat origin); consecutive differences
   are invariant under v -> v + c, so every output sample is unchanged to
   machine precision. The gauge group components used here (Z_12 transposition,
   the S-slot metrical circle) are ABELIAN, so the loop holonomy is exactly the
   sum of signed increments and carries no path/ordering ambiguity beyond the
   half-turn tie.

2. TRAFFIC LOOP DEFECT — the triangle-loop holonomy of role-space traffic
   (spec §13-G2, §16 "triangle loop defect", §10 "seams with drift prices").
   Composing the GW barycentric maps around a loop of tracks and comparing the
   result to the identity, IN THE START TRACK'S OWN normalized role metric,
   measures the curvature (non-integrability) of the cross-track role geometry.

   Gauge-invariance basis (I-2): the couplings are entropic Gromov-Wasserstein
   over INTERNAL distances only, and the start metric ``cost`` is within-track
   normalized / gauge-quotiented; a per-track gauge action leaves both the GW
   couplings and ``cost`` invariant, so the defect is invariant. No coordinate
   crosses a track boundary.

Neither object takes F-weights (LAMBDA) and neither feeds anything back into a
solve. This module imports ONLY numpy — it has ZERO dependency on the
functional/solver package (structurally enforced by the I-14 manifest check).
"""
from __future__ import annotations
from typing import Dict, Sequence, Tuple
import numpy as np


# --------------------------------------------------------------------------
# (1) circular holonomy of a running gauge frame  — DRIFT CV core
# --------------------------------------------------------------------------

def signed_increment(delta: np.ndarray, modulus: float) -> np.ndarray:
    """Map a raw frame difference to its signed minimal representative on a
    circle of circumference ``modulus``: the unique value in [-modulus/2,
    modulus/2). This is the discrete connection 1-form of the frame."""
    m = float(modulus)
    return (np.asarray(delta, float) + m / 2.0) % m - m / 2.0


def circular_holonomy(values: Sequence[float], modulus: float
                      ) -> Tuple[np.ndarray, float]:
    """Accumulated holonomy of a running frame trajectory on a circle.

    ``values`` is the per-bar gauge-section value (e.g. transposition in Z_12,
    beat-phase in Z_S). Returns (running, total) where ``running`` is the CV
    signal — running[t] = net signed winding accumulated up to bar t, running[0]
    = 0 — and ``total`` = running[-1] is the closed-trajectory holonomy.

    Reads only consecutive differences, so it is EXACTLY invariant to a global
    re-referencing of the frame (v -> v + c); this is the meter's gauge
    invariance (spec §9, I-2)."""
    v = np.asarray(values, float)
    if v.ndim != 1:
        raise ValueError("frame trajectory must be 1-D (one value per bar)")
    if len(v) == 0:
        return np.zeros(0), 0.0
    incr = signed_increment(np.diff(v), modulus)          # (T-1,)
    running = np.concatenate([[0.0], np.cumsum(incr)])     # (T,), running[0]=0
    return running, float(running[-1])


# --------------------------------------------------------------------------
# (2) traffic loop defect  — G2 / planner-map holonomy of role-space traffic
# --------------------------------------------------------------------------

def barycentric_map(pi: np.ndarray, mass_a: np.ndarray) -> np.ndarray:
    """Row-stochastic transport map a-prototypes -> distribution over
    b-prototypes induced by a coupling ``pi`` (K_a x K_b) with source marginal
    ``mass_a``. P[i,:] = pi[i,:]/mass_a[i] sums to 1 (the GW barycentric image
    of prototype i)."""
    ma = np.asarray(mass_a, float)
    return np.asarray(pi, float) / (ma[:, None] + 1e-12)


def loop_defect(costs: Sequence[np.ndarray], masses: Sequence[np.ndarray],
                couplings: Dict[Tuple[int, int], np.ndarray],
                cycle: Sequence[int]) -> float:
    """Holonomy (loop defect) of role-space traffic around ``cycle``.

    ``cycle`` is a sequence of track indices that RETURNS to its start
    (e.g. [s, t, u, s]). ``couplings[(a, b)]`` is the GW coupling K_a x K_b from
    track a to track b (source marginal = masses[a]). The composed row-stochastic
    map around the loop lands back in the start track's prototype space; the
    defect is the expected START-METRIC role-distance between a prototype and its
    loop image:  Σ_i m_s[i] Σ_j Q[i,j] cost_s[i,j] / Σ_i m_s[i].

    A perfectly integrable (flat) role geometry closes every loop up to the
    solver/entropy floor; genuine curvature shows up as excess defect. Measured
    in the start's own normalized metric, so gauge-invariant (I-2)."""
    if cycle[0] != cycle[-1]:
        raise ValueError("cycle must return to its start (cycle[0] == cycle[-1])")
    s = cycle[0]
    ms = np.asarray(masses[s], float)
    Q = np.eye(len(ms))
    for a, b in zip(cycle[:-1], cycle[1:]):
        pi = couplings[(a, b)]
        Q = Q @ barycentric_map(pi, masses[a])
    Cs = np.asarray(costs[s], float)
    per_i = np.einsum("ij,ij->i", Q, Cs)                  # Σ_j Q[i,j] cost_s[i,j]
    return float(ms @ per_i / (ms.sum() + 1e-12))
