"""M3 kernel fit + memory-term invariants."""

import numpy as np

from basin import operator
from basin.kernel import fit_kernel, autocorr, resolved_trajectories


CFG = dict(sr=22050, hop=1024, prony_order=2, step_s=0.75)


def _fitted(toy):
    m, bounds = toy
    P = operator.build_operator(m, bounds)
    sp = operator.eigendecompose(P)
    k = fit_kernel(m, sp.psi, bounds, CFG, track_paths=[])
    return m, sp, k


def test_autocorr_normalized_at_zero(toy_memberships):
    m, bounds = toy_memberships
    P = operator.build_operator(m, bounds)
    sp = operator.eigendecompose(P)
    trajs = resolved_trajectories(m, sp.psi, bounds)
    if not trajs:
        return
    C = autocorr(trajs, max_lag=5)
    assert np.allclose(C[:, 0], 1.0)


def test_memory_knob_shape_and_finite(toy_memberships):
    m, sp, k = _fitted(toy_memberships)
    n_macros = sp.psi.shape[1]
    if n_macros == 0:
        return
    hist = [np.random.default_rng(i).standard_normal(n_macros) for i in range(15)]
    knob = k.memory_knob(hist)
    assert knob.shape == (n_macros,)
    assert np.isfinite(knob).all()


def test_clamp_reduces_mass(toy_memberships):
    m, sp, k = _fitted(toy_memberships)
    if sp.psi.shape[1] == 0:
        return
    before = np.abs(k.Kvals).sum()
    k.clamp_spectral_radius(bound=0.1)
    after = np.abs(k.Kvals).sum()
    assert after <= before + 1e-9


def test_order_within_spec_bound(toy_memberships):
    _, _, k = _fitted(toy_memberships)
    assert k.order <= 3           # spec: Prony order stays <= 3
