"""LAMBDA-free reference world for the corpus-time estimator (spec §6, step d).

The contrastive/NCE fit of the F-weights (spec §6) needs a FROZEN world to score
real tracks and their scrambles against. That world must NOT depend on LAMBDA, or
the fit would be circular (fitting the weights that shaped the world we score
with). This module builds such a world from the T1-only (transport) geometry plus
learned corpus occupancy marginals — every quantity here is LAMBDA-free:

  * anchor count M*  = round(effective_rank(traffic_affinity))   (spec §4; the G1
    instrument; does not reference LAMBDA — retro-audit F-1 scope).
  * anchor geometry D = free-support GW barycenter of the corpus prototype costs
    (the update_D formula: pure couplings + prototype costs, no LAMBDA).
  * couplings pi     = pure entropic GW prototype->anchor (transport only).
  * anchor masses a  = corpus-mean anchor occupancy marginal (learned).
  * slot profile theta = corpus-mean per-anchor slot distribution (learned; the
    role's characteristic metrical placement, NOT the solver's uniform prior).
  * band profile B   = coupling-weighted mean prototype band profile.

theta/a are LEARNED from the real corpus so that the estimator's T2 target is the
role's actual slot profile (mass conservation to the learned groove), not a flat
prior. See the step-d training report / PREREG for the separability analysis this
world was built to test.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from ..geometry import roles
from ..functional import anchors as an, ot


@dataclass(frozen=True)
class WorldFreeze:
    """A frozen, LAMBDA-free role world. All cross-track traffic factors through
    these anchors (spec §4); every field is gauge-invariant intrinsic structure
    (I-2)."""
    D: np.ndarray        # (M,M) anchor role-space cost (GW barycenter)
    a: np.ndarray        # (M,) anchor masses (learned occupancy marginal)
    B: np.ndarray        # (M,n_bands) anchor band profiles, rows on simplex
    theta: np.ndarray    # (M,S) anchor slot profiles, rows on simplex
    sigma: float         # frozen corpus affinity scale
    M: int               # anchor count M*

    def couple(self, P: roles.Prototypes, eps: float = 0.05) -> np.ndarray:
        """Pure entropic-GW coupling of a prototype space -> anchors (transport
        only; LAMBDA-free, gauge-invariant, I-2). Row marginal = P.mass."""
        pi, _ = ot.entropic_gw(P.cost, self.D, P.mass, self.a, eps)
        return pi


def _occ(pi: np.ndarray, P: roles.Prototypes) -> np.ndarray:
    """Anchor x slot occupancy from a coupling and a prototype slot histogram
    (mirrors f.occupancy at native gauge: per-role slot distribution, coupled)."""
    q = P.slot_hist / (P.slot_hist.sum(1, keepdims=True) + 1e-12)
    return pi.T @ q


def build_reference_world(protos, sigma: float | None = None,
                          bary_iters: int = 12) -> WorldFreeze:
    """Build the LAMBDA-free reference world from corpus prototype spaces."""
    D_role = roles.role_distance_matrix(protos)
    off = D_role[~np.eye(len(D_role), dtype=bool)]
    if sigma is None:
        sigma = float(np.median(off)) if off.size else 1.0
        sigma = sigma if sigma > 0 else 1.0
    M = max(1, int(round(an.effective_rank(np.exp(-D_role / sigma)))))

    # free-support GW barycenter geometry (update_D formula; LAMBDA-free)
    seed = protos[int(np.argmax([P.mass.max() for P in protos]))]
    idx = np.argsort(seed.mass)[::-1][:M]
    D = seed.cost[np.ix_(idx, idx)].copy()
    D = 0.5 * (D + D.T); np.fill_diagonal(D, 0.0)
    a = np.full(M, 1.0 / M)
    for _ in range(bary_iters):
        pis = [ot.entropic_gw(P.cost, D, P.mass, a, 0.05)[0] for P in protos]
        num = sum(pi.T @ P.cost @ pi for pi, P in zip(pis, protos))
        den = sum(np.outer(pi.sum(0), pi.sum(0)) for pi in pis)
        Dn = num / (den + 1e-12); Dn = 0.5 * (Dn + Dn.T); np.fill_diagonal(Dn, 0.0)
        if np.abs(Dn - D).max() < 1e-4:
            D = Dn; break
        D = Dn

    pis = [ot.entropic_gw(P.cost, D, P.mass, a, 0.05)[0] for P in protos]
    n_bands = protos[0].band_profile.shape[1]

    # learned occupancy marginals: a (anchor mass) + theta (per-anchor slot profile)
    Obar = np.mean([_occ(pi, P) for pi, P in zip(pis, protos)], axis=0)   # (M,S)
    a = Obar.sum(1); a = a / (a.sum() + 1e-12)
    theta = Obar / (Obar.sum(1, keepdims=True) + 1e-12)

    # coupling-weighted band profile per anchor
    Bw = np.zeros((M, n_bands)); wsum = np.zeros(M)
    for pi, P in zip(pis, protos):
        bp = P.band_profile / (P.band_profile.sum(1, keepdims=True) + 1e-12)
        Bw += pi.T @ bp; wsum += pi.sum(0)
    B = Bw / (wsum[:, None] + 1e-12)
    B = B / (B.sum(1, keepdims=True) + 1e-12)

    return WorldFreeze(D=D, a=a, B=B, theta=theta, sigma=float(sigma), M=int(M))
