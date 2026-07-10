"""M2/M3 orbit invariants: the spec's γ=0 and κ=0 reproduction guarantees."""

import numpy as np

from basin import operator
from basin.orbit import Orbit
from basin.kernel import fit_kernel


CFG = dict(beta=1.0, gamma=0.3, tau=1.0, kappa=1.0, top_memberships=8, step_s=0.75)


def _orbit(P, psi, cfg, kernel=None, seed=0):
    o = Orbit(P, psi, cfg, kernel=kernel, seed=seed)
    o.seed_state(chart=0)
    return [s.m.copy() for s in o.run(30)]


def test_gamma_zero_is_pure_pull(toy_memberships):
    """γ=0 removes the wanderlust term entirely (spec: must reproduce PULL)."""
    m, bounds = toy_memberships
    P = operator.build_operator(m, bounds)
    sp = operator.eigendecompose(P)
    cfg0 = dict(CFG, gamma=0.0)
    a = _orbit(P, sp.psi, cfg0, seed=1)
    b = _orbit(P, sp.psi, cfg0, seed=1)
    # deterministic and identical run-to-run
    assert all(np.allclose(x, y) for x, y in zip(a, b))
    # and different once wanderlust is switched on
    c = _orbit(P, sp.psi, dict(CFG, gamma=1.0), seed=1)
    assert not all(np.allclose(x, y) for x, y in zip(a, c))


def test_kappa_zero_exactly_reproduces_m2(toy_memberships):
    """κ=0 must exactly reproduce M2 — kernel present but silent."""
    m, bounds = toy_memberships
    P = operator.build_operator(m, bounds)
    sp = operator.eigendecompose(P)
    cfg = dict(sr=22050, hop=1024, prony_order=2, step_s=0.75, beta=1.0,
               gamma=0.3, tau=1.0)
    kernel = fit_kernel(m, sp.psi, bounds, cfg, track_paths=[])

    with_k = _orbit(P, sp.psi, dict(CFG, kappa=0.0), kernel=kernel, seed=2)
    without_k = _orbit(P, sp.psi, dict(CFG, kappa=0.0), kernel=None, seed=2)
    assert all(np.allclose(x, y) for x, y in zip(with_k, without_k))


def test_memberships_stay_normalized_and_sparse(toy_memberships):
    m, bounds = toy_memberships
    P = operator.build_operator(m, bounds)
    sp = operator.eigendecompose(P)
    o = Orbit(P, sp.psi, CFG, seed=0)
    o.seed_state()
    for st in o.run(20):
        assert abs(st.m.sum() - 1.0) < 1e-9
        assert np.count_nonzero(st.m) <= CFG["top_memberships"]
