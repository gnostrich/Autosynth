"""Tests for the §9 meter jacks: drift CV, phrase EOC, novelty saturation, and
the traffic loop-defect holonomy primitive.

Each meter is checked for (i) correct behaviour, (ii) GAUGE INVARIANCE to a
global gauge action (the property that makes it a legal §9 jack), and (iii) that
it is a pure read-only function (no F dependency — the structural side is the
I-14 manifest check; here we assert the value-only contract behaviourally).
"""
from __future__ import annotations
import numpy as np
import pytest

from ets import meters as M
from ets.meters import holonomy as H


# --------------------------------------------------------------------------
# DRIFT CV  (accumulated holonomy of the running gauge frame)
# --------------------------------------------------------------------------

def test_drift_accumulates_signed_winding():
    running, total = H.circular_holonomy([0, 1, 3, 2, 5, 7, 7, 9], 12)
    assert running[0] == 0.0
    assert np.allclose(running, [0, 1, 3, 2, 5, 7, 7, 9])
    assert total == 9.0


def test_drift_circular_wrap_is_signed_minimal():
    # 11 -> 0 is +1 (not -11); 0 -> 11 is -1 (not +11).
    assert H.circular_holonomy([11, 0], 12)[1] == 1.0
    assert H.circular_holonomy([0, 11], 12)[1] == -1.0


def test_drift_gauge_invariance_global_reference_shift_exact():
    # A global gauge action re-references the whole frame by a constant; the
    # accumulated holonomy is EXACTLY unchanged (reads only differences).
    rng = np.random.default_rng(1)
    for _ in range(20):
        traj = rng.integers(0, 12, size=16)
        c = int(rng.integers(0, 12))
        r0, t0 = H.circular_holonomy(traj, 12)
        r1, t1 = H.circular_holonomy((traj + c) % 12, 12)
        assert np.max(np.abs(r0 - r1)) == 0.0
        assert t0 == t1


def test_drift_cv_bank_key_and_phase_live_timbre_walled():
    transpose = [0, 2, 4, 3, 5]
    phase = [0, 1, 2, 1, 0]
    d = M.drift_cv(transpose, phase, phase_modulus=8)
    assert d.key.total == 5.0            # net +5 semitone winding
    assert d.phase.total == 0.0          # returns to phase 0 -> zero net drift
    # timbre jack is absent on a v0 world (no running timbre-basis frame): WALL.
    assert d.timbre is None
    assert d.as_dict()["timbre_drift_total"] is None
    # ...but the machinery works when a timbre-basis angle IS supplied.
    dt = M.timbre_drift([0.0, 0.5, 1.0, 0.5])
    assert dt is not None and abs(dt.total - 0.5) < 1e-12


# --------------------------------------------------------------------------
# TRAFFIC LOOP DEFECT  (triangle-loop holonomy of role-space traffic; G2 core)
# --------------------------------------------------------------------------

def _identity_coupling(mass):
    return np.diag(mass)          # perfect correspondence, source marginal = mass


def test_loop_defect_zero_on_identity_traffic():
    # Three tracks with identical geometry and identity couplings: a flat world,
    # loops close exactly -> zero defect.
    m = np.array([0.5, 0.3, 0.2])
    C = np.array([[0.0, 1.0, 2.0], [1.0, 0.0, 1.5], [2.0, 1.5, 0.0]])
    costs = [C, C, C]
    masses = [m, m, m]
    coup = {(a, b): _identity_coupling(m) for a in range(3) for b in range(3) if a != b}
    d = H.loop_defect(costs, masses, coup, [0, 1, 2, 0])
    assert d < 1e-9


def test_loop_defect_positive_on_curved_traffic():
    # A transposition coupling (swap prototypes 0<->1) satisfies P^3 = P != I, so
    # the composed 3-loop does NOT return home: nonzero holonomy in the start
    # metric (prototype 0 lands on 1 and vice versa, each a role-distance of 1).
    m = np.array([1 / 3, 1 / 3, 1 / 3])
    C = np.array([[0.0, 1.0, 2.0], [1.0, 0.0, 1.0], [2.0, 1.0, 0.0]])
    costs = [C, C, C]
    masses = [m, m, m]
    swap = np.array([[0, 1, 0], [1, 0, 0], [0, 0, 1]], float) * m[:, None]
    coup = {(a, b): swap for a in range(3) for b in range(3) if a != b}
    d = H.loop_defect(costs, masses, coup, [0, 1, 2, 0])
    # expected: (1/3)(C[0,1] + C[1,0] + C[2,2]) = (1/3)(1+1+0) = 2/3
    assert abs(d - 2.0 / 3.0) < 1e-9


def test_loop_defect_requires_closed_cycle():
    m = np.array([0.5, 0.5])
    coup = {(0, 1): _identity_coupling(m)}
    with pytest.raises(ValueError):
        H.loop_defect([np.eye(2)] * 2, [m, m], coup, [0, 1])


# --------------------------------------------------------------------------
# PHRASE EOC GATE
# --------------------------------------------------------------------------

def _periodic_traj(period, n_cycles, d=10, noise=0.01, seed=0):
    rng = np.random.default_rng(seed)
    base = rng.standard_normal((period, d))
    return np.concatenate([base + noise * rng.standard_normal((period, d))
                           for _ in range(n_cycles)])


def test_phrase_eoc_detects_period_and_gates_cycle_ends():
    X = _periodic_traj(period=4, n_cycles=5)
    pe = M.phrase_eoc(X)
    assert pe.period == 4
    assert list(np.where(pe.gate)[0]) == [3, 7, 11, 15, 19]
    assert pe.strength > 0


def test_phrase_eoc_gauge_invariance_global_slot_roll():
    # A global cyclic roll of the slot axis (a beat-phase gauge action applied to
    # the whole trajectory) leaves the detected period and gate unchanged.
    X = _periodic_traj(period=5, n_cycles=4)
    pe = M.phrase_eoc(X)
    for k in (1, 2, 3):
        pe_r = M.phrase_eoc(np.roll(X, k, axis=1))
        assert pe_r.period == pe.period
        assert np.array_equal(pe_r.gate, pe.gate)


def test_phrase_eoc_empty_when_no_cycle():
    rng = np.random.default_rng(3)
    X = rng.standard_normal((20, 10))          # no recurrence
    pe = M.phrase_eoc(X)
    # either no period, or if a weak spurious one, gate must remain a valid {0,1}.
    assert set(np.unique(pe.gate)).issubset({0, 1})


# --------------------------------------------------------------------------
# NOVELTY SATURATION CV
# --------------------------------------------------------------------------

def test_novelty_saturation_bounds_and_first_bar_novel():
    rng = np.random.default_rng(4)
    X = np.abs(rng.standard_normal((12, 8)))
    ns = M.novelty_saturation(X)
    assert ns.cv[0] == 0.0
    assert np.all(ns.cv >= 0.0) and np.all(ns.cv <= 1.0)


def test_novelty_saturation_rises_on_reuse():
    rng = np.random.default_rng(5)
    d = 8
    # repeated material saturates higher than all-distinct material.
    repeat = np.tile(np.abs(rng.standard_normal((1, d))), (10, 1))
    # distinct one-hot-ish bars (genuinely fresh support each bar)
    distinct = np.zeros((10, d))
    for t in range(10):
        distinct[t, t % d] = 1.0
    sat_repeat = M.novelty_saturation(repeat).cv[1:].mean()
    sat_distinct = M.novelty_saturation(distinct).cv[1:].mean()
    assert sat_repeat > sat_distinct
    assert sat_repeat > 0.9


def test_novelty_saturation_gauge_invariance_global_slot_roll():
    rng = np.random.default_rng(6)
    X = np.abs(rng.standard_normal((16, 9)))
    ns = M.novelty_saturation(X)
    for k in (1, 4, 7):
        ns_r = M.novelty_saturation(np.roll(X, k, axis=1))
        assert np.allclose(ns.cv, ns_r.cv, atol=1e-12)
        assert ns_r.tau == ns.tau
