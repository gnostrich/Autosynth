"""Optimal-transport primitives for F (spec §5): entropic Sinkhorn and entropic
Gromov-Wasserstein. Hand-rolled (no third-party OT dependency) so the numerics
are auditable in-repo and the runtime stays lean.

These are the I-PROJECTION building blocks of the block-coordinate solver
(spec §5): a Sinkhorn iteration is the I-projection of a kernel onto the
transport polytope, and each entropic-GW outer step is a Sinkhorn on the
GW-linearized cost. Nothing here is a second objective — callers assemble these
into the single functional F.
"""
from __future__ import annotations
import numpy as np


def sinkhorn(cost: np.ndarray, r: np.ndarray, c: np.ndarray, eps: float,
             n_iter: int = 500, tol: float = 1e-9) -> np.ndarray:
    """Entropic OT plan minimising <pi,cost> - eps*H(pi) with marginals (r, c).

    Returns pi (len(r) x len(c)). Log-domain-free but stabilised by subtracting
    the cost min. This is a KL I-projection of the Gibbs kernel onto U(r, c).
    """
    r = np.asarray(r, float); c = np.asarray(c, float)
    K = np.exp(-(cost - cost.min()) / eps) + 1e-300
    u = np.ones_like(r)
    v = np.ones_like(c)
    for _ in range(n_iter):
        u_new = r / (K @ v + 1e-300)
        v = c / (K.T @ u_new + 1e-300)
        if np.max(np.abs(u_new - u)) < tol:
            u = u_new
            break
        u = u_new
    return u[:, None] * K * v[None, :]


def entropic_gw(Cx: np.ndarray, Cy: np.ndarray, mx: np.ndarray, my: np.ndarray,
                eps: float, n_outer: int = 100, n_inner: int = 200,
                tol: float = 1e-8):
    """Entropic Gromov-Wasserstein coupling between metric-measure spaces
    (Cx, mx) and (Cy, my). Returns (pi, distortion).

    GW couples via INTERNAL distances only — no shared coordinate system is ever
    required (spec §4/I-2: intrinsic geometry to anchors, no coordinate crosses a
    boundary). Uses the Peyre et al. squared-loss factorisation so each outer
    step is a Sinkhorn on the pseudo-cost L(pi) = const - 4 Cx pi Cy^T.
    """
    mx = np.asarray(mx, float); my = np.asarray(my, float)
    nx, ny = len(mx), len(my)
    pi = np.outer(mx, my)
    Cx2, Cy2 = Cx ** 2, Cy ** 2
    # constant part of the squared-loss tensor contraction
    A = Cx2 @ mx[:, None] @ np.ones((1, ny)) + np.ones((nx, 1)) @ (my[None, :] @ Cy2.T)
    dist_prev = np.inf
    for _ in range(n_outer):
        pseudo = A - 2.0 * (Cx @ pi @ Cy.T)
        pi = sinkhorn(pseudo, mx, my, eps, n_iter=n_inner)
        distortion = float(np.sum(pseudo * pi))  # <L(pi), pi>, up to the eps term
        if abs(dist_prev - distortion) < tol * (abs(dist_prev) + 1e-12):
            dist_prev = distortion
            break
        dist_prev = distortion
    return pi, gw_distortion(Cx, Cy, pi)


def gw_distortion(Cx: np.ndarray, Cy: np.ndarray, pi: np.ndarray) -> float:
    """Raw squared-loss GW distortion sum_{i,j,k,l}(Cx_ik - Cy_jl)^2 pi_ij pi_kl,
    computed in O(n^2 m + n m^2) via the factorisation. This is the exact T1
    contribution for a coupling (used by F; the entropic solve above only adds an
    entropy regulariser on top)."""
    mx = pi.sum(1); my = pi.sum(0)
    const = float(mx @ (Cx ** 2) @ mx)
    const2 = float(my @ (Cy ** 2) @ my)
    cross = float(np.sum((Cx @ pi @ Cy.T) * pi))
    return const + const2 - 2.0 * cross
