"""M1 operator + spectrum invariants."""

import numpy as np

from basin import operator


def test_P_row_stochastic(toy_memberships):
    m, bounds = toy_memberships
    P = operator.build_operator(m, bounds)
    sums = P.sum(1)
    # every non-dangling row sums to 1
    assert np.allclose(sums[sums > 1e-9], 1.0)
    assert (P >= 0).all()


def test_P_no_cross_track_transitions():
    # two length-2 tracks; the boundary pair (win 1 -> win 2) must NOT count
    m = np.zeros((4, 3))
    m[0, 0] = 1; m[1, 1] = 1; m[2, 2] = 1; m[3, 0] = 1
    P = operator.build_operator(m, [(0, 2), (2, 4)])
    # within track 0: chart0 -> chart1 ; within track 1: chart2 -> chart0
    assert P[0, 1] == 1.0
    assert P[2, 0] == 1.0
    # boundary chart1 -> chart2 would be a cross-track pair — forbidden
    assert P[1, 2] == 0.0


def test_spectrum_classification_and_macros(toy_memberships):
    m, bounds = toy_memberships
    P = operator.build_operator(m, bounds)
    sp = operator.eigendecompose(P)
    # eigenvalues sorted by |lambda| descending
    mags = np.abs(sp.eigvals)
    assert np.all(np.diff(mags) <= 1e-9)
    # every mode is classified
    kinds = {mo.kind for mo in sp.modes}
    assert kinds <= {"linear", "oscillatory", "alternation"}
    # psi standardized: unit-ish std per macro column
    if sp.psi.shape[1]:
        assert np.allclose(sp.psi.std(0), 1.0, atol=1e-6)
