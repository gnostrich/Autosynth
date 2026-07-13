"""Block-coordinate I-projection solver for F (spec §5).

Minimisation is by block-coordinate I-projections:
  - pi-blocks   : Sinkhorn on the GW-linearised + coupled-gradient cost.
  - B-blocks    : exponentiated-gradient (mirror descent on the band simplex).
  - mass-blocks : unbalanced multiplicative update on anchor masses a; free-support
                  GW-barycenter closed form on the anchor geometry D.
  - gauge-block : exact minimisation over the per-section phase/transposition set.

Batch termination is a LYAPUNOV F-DESCENT CERTIFICATE: every accepted block step
decreases the single functional F, so the F-trajectory is monotone non-increasing
and the run stops when |dF| < tol. There is NO second objective and NO separate
training loss (invariant I-4): the ONLY quantity any accept/reject decision reads
is F itself (see solver-reads-only-F structural check in tests/invariants).
"""
from __future__ import annotations
from dataclasses import replace
import numpy as np

from . import f as ff
from . import ot


# --------------------------------------------------------------------------
# block updates. Each returns a CANDIDATE FState; the driver accepts it only if
# F decreased (the Lyapunov guard). That guard is the whole termination theory.
# --------------------------------------------------------------------------

def _dF_dO(O, state):
    """Gradient of the O-marginal terms (T2+T3) w.r.t. occupancy O.

    (rev-r1) The O-aggregate role-continuation gradient (g4) was REMOVED: T4 is now
    the unit-successor term on pi's fiber (spec §5 rev-r1), which is inexpressible
    over O and does not enter the O-block gradient. T2 (mass conservation) and T3
    (masking) are the terms that provably factor through the marginal O."""
    L = ff.LAMBDA
    tgt = state.a[:, None] * state.theta + 1e-12
    g2 = L["T2"] * np.log((O + 1e-12) / tgt)                       # d gKL / dO
    E = O.T @ state.B
    g3 = L["T3"] * 2.0 * ((E @ state.B.T).T - O * (state.B ** 2).sum(1)[:, None])
    return g2 + g3


def update_pi(state, protos, eps=0.1):
    O = ff.occupancy(state, protos)
    gO = _dF_dO(O, state)                       # (M,S)
    new = list(state.pis)
    for t, P in enumerate(protos):
        q = P.slot_hist / (P.slot_hist.sum(1, keepdims=True) + 1e-12)
        q = np.roll(q, int(state.phase_off[t]) % 8, axis=1)
        # GW pseudo-cost (linearisation) + coupled-term gradient pulled to (K,M)
        A = (P.cost ** 2) @ P.mass[:, None] + (state.a[None, :] @ (state.D ** 2))
        gw_cost = A - 2.0 * (P.cost @ state.pis[t] @ state.D.T)
        coupled = q @ gO.T                       # (K,M)
        cost = gw_cost + coupled
        new[t] = ot.sinkhorn(cost, P.mass, state.a, eps, n_iter=200)
    return replace(state, pis=new)


def update_B(state, protos, eta=0.5):
    # exponentiated gradient (mirror descent on the per-role band simplex).
    # dT3/dB[k,b] = 2 L3 sum_s O[k,s] (E[s,b] - O[k,s] B[k,b]),  E = O^T B.
    O = ff.occupancy(state, protos)
    E = O.T @ state.B                                   # (S, n_bands)
    dB = np.zeros_like(state.B)
    for k in range(state.M):
        dB[k] = 2 * ff.LAMBDA["T3"] * (O[k] @ (E - O[k][:, None] * state.B[k][None, :]))
    Bnew = state.B * np.exp(-eta * dB)
    Bnew = Bnew / (Bnew.sum(1, keepdims=True) + 1e-12)
    return replace(state, B=Bnew)


def update_masses(state, protos, eta=0.5):
    O = ff.occupancy(state, protos)
    coupled = O.sum(1)                                   # mass routed to each role
    a_new = state.a * np.exp(-eta * (state.a - coupled) / (state.a + 1e-9))
    a_new = np.maximum(a_new, 1e-9)
    return replace(state, a=a_new)


def update_D(state, protos, damp=0.5):
    M = state.M
    num = np.zeros((M, M)); den = np.zeros((M, M))
    for t, P in enumerate(protos):
        pi = state.pis[t]
        num += pi.T @ P.cost @ pi
        col = pi.sum(0)
        den += np.outer(col, col)
    D_bary = num / (den + 1e-12)
    D_bary = 0.5 * (D_bary + D_bary.T)
    np.fill_diagonal(D_bary, 0.0)
    return replace(state, D=(1 - damp) * state.D + damp * D_bary)


def update_gauge(state, protos):
    S = protos[0].slot_hist.shape[1]
    off = state.phase_off.copy()
    for t in range(len(protos)):
        best_off, best_F = off[t], np.inf
        for cand in range(S):
            trial = replace(state, phase_off=_with(off, t, cand))
            val, _ = ff.F(trial, protos)
            if val < best_F:
                best_F, best_off = val, cand
        off = _with(off, t, best_off)
        state = replace(state, phase_off=off)
    return state


def _with(arr, i, v):
    a = arr.copy(); a[i] = v; return a


# --------------------------------------------------------------------------
# driver: Lyapunov-certified block-coordinate descent
# --------------------------------------------------------------------------

# theta (the per-role metrical slot reference) is a FIXED uniform prior, not a
# free variable — so T2 is a real mass-conservation constraint (occupancy is
# penalised for deviating from the role's mass spread evenly over slots) with
# genuine tension against T3/T4, rather than a target that chases O to zero.
_BLOCKS = [
    ("pi", update_pi),
    ("B", update_B),
    ("masses", update_masses),
    ("D", update_D),
    ("gauge", update_gauge),
]


def batch_solve(state, protos, max_sweeps=12, tol=1e-6, record=True):
    """Block-coordinate descent on the single F. Each block step is ACCEPTED
    only if it decreases F (the Lyapunov guard), so the returned trajectory is
    monotone non-increasing. Returns (state, trajectory)."""
    F_cur, _ = ff.F(state, protos)
    traj = [F_cur]
    for _ in range(max_sweeps):
        F_before_sweep = F_cur
        for name, upd in _BLOCKS:
            cand = upd(state, protos)
            F_cand, _ = ff.F(cand, protos)
            if F_cand <= F_cur + 1e-12:      # accept iff F did not increase
                state, F_cur = cand, F_cand
            # else: reject the candidate; F stays put (guard preserves monotonicity)
            if record:
                traj.append(F_cur)
        if abs(F_before_sweep - F_cur) < tol * (abs(F_before_sweep) + 1e-12):
            break
    return state, traj
