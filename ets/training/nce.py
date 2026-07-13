"""Corpus-time contrastive/NCE estimator of the F-weights LAMBDA (spec §6, step d).

Condition (spec §6): each real track is an equilibrium of F; its re-arrangements
are not. Estimator: a logistic/NCE fit over (real, scramble) pairs, with the
comparison class drawn INTERNALLY from the fixed pre-registered scramble family
(no external negatives, I-6). F is linear in the weights,

    F(x) = phi_1(x) + sum_i LAMBDA[Ti] * phi_i(x)   for i in {T2,T3,T4},

with T1 the reference scale (weight 1). The feature map phi = (T1,T2,T3,T4) is
computed at the frozen LAMBDA-free world (world.py) at native gauge, so the fit is
convex and its LAMBDA-gradient is exact — no circularity. (T5 is identically 0 at
native gauge for every member of the fixed family — a global section-gauge move is
orthogonal to every re-arrangement — so it carries no contrastive signal; see the
step-d report / PREREG for why lambda_5 is not corpus-time identifiable.)

The negatives are drawn ONLY through the registered fixed family: ``draw_pairs``
calls ``assert_family_fixed`` first and iterates ``scramble.family()`` — there is
no second, ad-hoc scrambler path (I-6, the auditor's step-(d) forward obligation).

Well-posedness is NOT assumed: ``separation`` is the pre-registered validity check
(PREREG "Training — real-tracks-are-equilibria"), with a KILL condition. On the v0
corpus it KILLS (F does not separate real from cross-track-swap / grid-shuffle for
any LAMBDA>=0). The estimator therefore does NOT emit an authoritative LAMBDA; the
wall is reported, not patched (WALL PROTOCOL). The fit routine is retained as the
instrument that establishes the kill; it must never be used to hand-force a split.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np

from ..geometry import roles
from ..functional import f as ff
from . import scramble as S
from .world import WorldFreeze, _occ


# ---- feature map phi = (T1, T2, T3, T4), LAMBDA-free ----------------------

def _track_arrangement(track, world: WorldFreeze) -> Tuple[np.ndarray, float]:
    """Occupancy + transport for a real (or Track-level scrambled) track: extract
    prototypes, couple to the frozen anchors (pure GW), read O and T1."""
    P = roles.extract_prototypes(track, seed=0)
    pi = world.couple(P)
    from ..functional import ot
    return _occ(pi, P), float(ot.gw_distortion(P.cost, world.D, pi))


def feature(O: np.ndarray, t1: float, world: WorldFreeze) -> np.ndarray:
    """phi = [T1, T2, T3, T4] via the SINGLE F-term implementation (raw_terms_O)."""
    c = ff.raw_terms_O(O, world.D, world.a, world.B, world.theta)
    return np.array([float(t1), c["T2"], c["T3"], c["T4"]], float)


def positive_features(tracks, world: WorldFreeze) -> np.ndarray:
    return np.array([feature(*_track_arrangement(t, world), world) for t in tracks])


# ---- negatives drawn ONLY through the registered fixed family -------------

def draw_pairs(tracks, world: WorldFreeze, seeds=(1, 2, 3)
               ) -> Dict[str, np.ndarray]:
    """Draw scramble features per family member, for every track and seed.

    Wires ``assert_family_fixed`` (the negatives come ONLY from the closed
    pre-registered family) and dispatches by op arity through the anchor channel.
    Returns {op_name: (n, 4) feature array}."""
    S.assert_family_fixed()                       # I-6: family fixed in PREREG
    real_ids = [int(t.track_id) for t in tracks]
    out: Dict[str, List[np.ndarray]] = {op.name: [] for op in S.family()}
    for op in S.family():
        for i, t in enumerate(tracks):
            for sd in seeds:
                if op.arity == "track":
                    scr = op.fn(t, seed=sd)
                    O, t1 = _track_arrangement(scr, world)
                elif op.arity == "role":
                    arr = op.fn(t, world, seed=sd)
                    S.assert_arrangement_real(arr, real_ids)
                    O, t1 = arr.O, arr.t1
                elif op.arity == "role_pair":
                    partner = tracks[(i + 1 + sd) % len(tracks)]
                    arr = op.fn([t, partner], world, seed=sd)
                    S.assert_arrangement_real(arr, real_ids)
                    O, t1 = arr.O, arr.t1
                else:
                    raise ValueError(f"unknown scramble arity {op.arity!r}")
                out[op.name].append(feature(O, t1, world))
    return {k: np.array(v) for k, v in out.items()}


# ---- logistic / NCE fit (T1 = reference scale 1) --------------------------

@dataclass
class FitResult:
    lam: np.ndarray            # (3,) fitted [T2, T3, T4] relative to T1=1
    loss: float                # final logistic loss
    grad_norm: float
    n_pairs: int


def _pair_deltas(pos: np.ndarray, negs: Dict[str, np.ndarray]):
    reps = {k: v.shape[0] // pos.shape[0] for k, v in negs.items()}
    D, op_of = [], []
    for k, v in negs.items():
        r = reps[k]
        base = np.repeat(pos, r, axis=0)[:v.shape[0]] if r >= 1 and r * pos.shape[0] == v.shape[0] \
            else pos[:v.shape[0]]
        D.append(v - base); op_of += [k] * len(v)
    return np.vstack(D), np.array(op_of)


def fit_lambda(pos: np.ndarray, negs: Dict[str, np.ndarray],
               lr: float = 0.5, iters: int = 4000) -> FitResult:
    """Convex logistic NCE fit: min_{lam>=0} mean -log sigmoid(margin), margin =
    dT1 + lam . dphi_{234}. T1 coefficient is FIXED at 1 (reference scale). This
    routine is the instrument that measures separability — it is NEVER a lever to
    hand-force a split (WALL PROTOCOL)."""
    Dp, _ = _pair_deltas(pos, negs)
    d1, d234 = Dp[:, 0], Dp[:, 1:]
    lam = np.ones(3)                              # neutral init (not the old hand-set)
    sig = lambda x: 1.0 / (1.0 + np.exp(-x))
    grad = np.zeros(3)
    for _ in range(iters):
        margin = d1 + d234 @ lam
        g = -(1.0 - sig(margin))
        grad = (g[:, None] * d234).mean(0)
        lam = np.maximum(lam - lr * grad, 0.0)
    margin = d1 + d234 @ lam
    loss = float(np.mean(np.log1p(np.exp(-margin))))
    return FitResult(lam=lam, loss=loss, grad_norm=float(np.linalg.norm(grad)),
                     n_pairs=len(margin))


# ---- pre-registered validity check (separation, with KILL) ----------------

def separation(pos: np.ndarray, negs: Dict[str, np.ndarray],
               lam: np.ndarray) -> dict:
    """Per-op separation rate + median margin under weights (1, lam). The
    pre-registered training-validity metric (distinct from the fit's logistic
    loss, so no fit metric is a gate metric, I-5)."""
    w = np.concatenate([[1.0], lam])
    per = {}
    for k, v in negs.items():
        r = v.shape[0] // pos.shape[0]
        base = np.repeat(pos, r, axis=0)[:v.shape[0]] if r >= 1 and r * pos.shape[0] == v.shape[0] \
            else pos[:v.shape[0]]
        m = (v - base) @ w
        per[k] = {"sep_rate": float((m > 0).mean()),
                  "median_margin": float(np.median(m)),
                  "n": int(len(m))}
    per["overall_min_sep"] = float(min(d["sep_rate"] for d in per.values()
                                       if isinstance(d, dict)))
    return per
