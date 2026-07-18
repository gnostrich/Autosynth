"""Anchors (spec §4): free-support barycenter measures in role space E_B, and
their SELF-SIZING by balanced truncation of the cross-track role-traffic operator.

All cross-track traffic factors through anchors — there is no direct pairwise
track coupling in the architecture. Each track reaches the anchors only by GW
(T1). The anchor object holds ONLY (D, a): support and mass. It carries NO
pressure accumulator, EMA, momentum, or any duplicate smoothing state
(invariant I-3), enforced by a structural check in tests/invariants.

Self-sizing (spec §4, verbatim): "anchor spawned when unabsorbable residual
HANKEL mass clears the calibrated noise floor; balanced-truncation prune below
floor. Claim under test (G1): anchor count tracks the corpus's role diversity
(McMillan degree of TRAFFIC), flat in N."

Reading, load-bearing: the sizing criterion is the spec's Hankel / McMillan /
balanced-truncation language — a SPECTRAL RANK of the cross-track TRAFFIC
operator, not a transport residual. (A transport-residual reading was tried and
REJECTED: it does not dissociate role-diverse from same-role corpora and it grows
with N; see the build report and PREREG G1.) The traffic operator is built ONLY
from pairwise GW role-distances (roles.role_distance), so no coordinate crosses a
track boundary (I-2). Its effective rank (participation ratio = balanced-
truncation effective mode count) is the self-sized anchor count. The F/solver
then settles the anchor SUPPORTS (D, a) as the GW barycenter at that count.
"""
from __future__ import annotations
from dataclasses import replace
import numpy as np

from . import f as ff
from . import solver as sv
from ..geometry import roles


# ---- traffic operator + balanced-truncation sizing ------------------------

def traffic_affinity(protos, sigma: float | None = None):
    """Cross-track role-traffic affinity A[s,t] = exp(-GW_dist(s,t)/sigma).

    Built only from pairwise GW role-distances (internal costs only, I-2). sigma
    is a single corpus-level scale (median off-diagonal distance); not a
    coordinate. Returns (A, D_role, sigma)."""
    D = roles.role_distance_matrix(protos)
    off = D[~np.eye(len(D), dtype=bool)]
    if sigma is None:
        sigma = float(np.median(off)) if off.size else 1.0
        sigma = sigma if sigma > 0 else 1.0
    A = np.exp(-D / sigma)
    return A, D, sigma


def effective_rank(A: np.ndarray) -> float:
    """Balanced-truncation effective mode count of the traffic operator: the
    participation ratio (sum w)^2 / sum w^2 of its (non-negative) spectrum. Modes
    below the noise floor contribute vanishing w^2, i.e. are truncated. This is
    the McMillan degree of the traffic, real-valued; the anchor count is its
    round."""
    w = np.maximum(np.linalg.eigvalsh(0.5 * (A + A.T)), 0.0)
    s1, s2 = float(w.sum()), float((w ** 2).sum())
    return (s1 * s1) / (s2 + 1e-12)


def gauge_copy(P: roles.Prototypes, transpose: int = 0, phase: int = 0,
               loud: float = 1.0) -> roles.Prototypes:
    """Apply a gauge action (spec §3: transposition x phase x loudness) to a
    prototype space. Because the cross-track cost is transposition-quotiented and
    circular, and mass is renormalised, the RESULT HAS AN IDENTICAL role geometry
    — a gauge copy carries the same intrinsic content. Used to build the strict
    flat-in-N arm (adding gauge copies must not add anchors) which doubles as a
    gauge-invariance check."""
    chroma = np.roll(P.chroma, transpose % 12, axis=1)
    slot = np.roll(P.slot_hist, phase % P.slot_hist.shape[1], axis=1)
    mass = P.mass * loud
    mass = mass / (mass.sum() + 1e-12)               # loudness is gauge -> renormalise
    return replace(P, chroma=chroma, slot_hist=slot, mass=mass)


def scramble_null(protos, seed: int = 0):
    """Role-scrambled null: independently permute each track's prototype geometry
    so NO shared cross-track role structure (traffic) survives. The effective rank
    on this null is the calibrated noise reference for the sizing."""
    rng = np.random.default_rng(seed)
    out = []
    for P in protos:
        K = P.mass.shape[0]
        perm = rng.permutation(K)
        out.append(replace(P, cost=P.cost[np.ix_(perm, perm)]))
    return out


# ---- barycenter supports at the self-sized count ---------------------------

def init_state(protos, M=1, seed=0):
    """Initial FState for the barycenter solve at a GIVEN anchor count M."""
    rng = np.random.default_rng(seed)
    S = protos[0].slot_hist.shape[1]
    n_bands = protos[0].band_profile.shape[1]
    P0 = protos[0]
    if M <= P0.cost.shape[0]:
        idx = np.argsort(P0.mass)[::-1][:M]
        D = P0.cost[np.ix_(idx, idx)].copy()
    else:
        D = rng.random((M, M))
    D = 0.5 * (D + D.T); np.fill_diagonal(D, 0.0)
    a = np.full(M, 1.0 / M)
    B = np.full((M, n_bands), 1.0 / n_bands)
    theta = np.full((M, S), 1.0 / S)
    pis = [np.outer(P.mass, a) for P in protos]
    phase_off = np.zeros(len(protos), dtype=int)
    transpose = np.zeros(len(protos), dtype=int)
    return ff.FState(D=D, a=a, B=B, theta=theta, pis=pis,
                     phase_off=phase_off, transpose=transpose)


def _prune(state, protos):
    """Balanced truncation on the settled supports: drop anchors whose coupled
    mass is below the mass floor (redundant support)."""
    O = ff.occupancy(state, protos)
    m = O.sum(1)
    keep = m >= 0.01 * (m.sum() + 1e-12)
    if keep.all() or keep.sum() == 0:
        return state
    idx = np.where(keep)[0]
    a = state.a[idx]; a = a / (a.sum() + 1e-12)
    return replace(state, D=state.D[np.ix_(idx, idx)], a=a,
                   B=state.B[idx], theta=state.theta[idx],
                   pis=[pi[:, idx] for pi in state.pis])


def coupling_weighted_B(pis, protos):
    """The coupling-weighted anchor band profile of a set of couplings — the
    fidelity readout of paper2 §2 ("same anchor-profile = same sound"). Each
    anchor's row is the mass-weighted (by coupled mass ``pi.sum(0)``) mean of its
    units' own simplex band profiles, itself renormalised onto the simplex. This
    is VERBATIM the form the LAMBDA-free NCE reference world already carries
    (``training/world.py`` "coupling-weighted band profile per anchor"); no new
    theory, hyperparameter, or library. Rows on the band simplex; (M, n_bands)."""
    M = pis[0].shape[1]
    n_bands = protos[0].band_profile.shape[1]
    Bw = np.zeros((M, n_bands)); wsum = np.zeros(M)
    for pi, P in zip(pis, protos):
        bp = P.band_profile / (P.band_profile.sum(1, keepdims=True) + 1e-12)
        Bw += pi.T @ bp; wsum += pi.sum(0)
    B = Bw / (wsum[:, None] + 1e-12)
    B = B / (B.sum(1, keepdims=True) + 1e-12)
    return B


def build_world(protos, seed=0, sweeps=8, sigma=None):
    """Self-size the anchors on `protos` and settle their supports.

    (1) SIZE: anchor count M* = round(effective_rank(traffic_affinity)) — balanced
        truncation of the cross-track traffic (Hankel) operator.
    (2) SETTLE: solve the single functional F (block-coordinate, Lyapunov-certified
        descent) for the free-support barycenter (D, a) at M*.
    (3) FREEZE B: replace the uniform band-blind fixed-point B with the coupling-
        weighted band profile of the SETTLED, PRUNED couplings (paper2 §2 fidelity;
        PREREG-informative-B.md §2). B becomes a derived freeze-time readout of the
        world's OWN couplings — data-coupled, deliberately NOT the F-argmin in the
        B direction (F is band-indifferent at the uniform fixed point). The solver's
        descent, settlement, and the settled D/a/theta/pi are UNCHANGED (update_B is
        a no-op on uniform B, so the settled state is bit-identical THROUGH the
        solve); only the FINAL frozen B differs. B stays FROZEN post-training (I-9).
        F_final is then recomputed on the FROZEN state, so the receipt certifies the
        world AS FROZEN with its informative B.
    `sigma` is the FROZEN corpus-level affinity scale (calibrate once on the
    reference corpus, then apply to every arm); None falls back to this set's
    median (standalone use only). Returns (state, info)."""
    A, D_role, sigma = traffic_affinity(protos, sigma=sigma)
    er = effective_rank(A)
    M = max(1, int(round(er)))
    state = init_state(protos, M=M, seed=seed)
    state, traj = sv.batch_solve(state, protos, max_sweeps=sweeps)
    state = _prune(state, protos)
    # (3) informative B at freeze — a data-coupled readout of the settled couplings.
    state = replace(state, B=coupling_weighted_B(state.pis, protos))
    F_final = float(ff.F(state, protos)[0])              # F of the FROZEN world
    F_init = float(ff.F(init_state(protos, M=M, seed=seed), protos)[0])
    info = {
        "effective_rank": float(er),
        "n_anchors": int(state.M),
        "sigma": float(sigma),
        "role_dist_mean": float(D_role[~np.eye(len(D_role), dtype=bool)].mean()),
        "F_init": F_init,
        "F_final": F_final,
        "seed": int(seed),
        "F_monotone": bool(np.all(np.diff(np.asarray(traj)) <= 1e-9)),
    }
    return state, info
