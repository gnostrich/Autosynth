"""Layer-0 tilt observables phi_i: hand-computed correctness (connector Layer 0).

Every value asserted below is computed by hand from the definitions in
ets/connector/phi.py, so the observable math (scheduled-mass attribution,
successor counting, 1/Delta recency, gauge group metrics) is pinned exactly.
"""
import numpy as np
import pytest

from ets.connector.phi import (LANE_PHI, PHI_NAMES, RoleMaps, phi_bars,
                               _circ_dist, _gauge_move_magnitude)
from ets.render.schedule import Schedule, Section, Gauge, PLACEMENT_DTYPE

S_PHASE = 4


def _maps():
    return RoleMaps(
        unit_role={(0, 0): 0, (0, 1): 0, (0, 2): 1, (0, 3): 2,
                   (1, 0): 1, (1, 1): 1},
        unit_band={(0, 0): 0, (0, 1): 0, (0, 2): 0, (0, 3): 0,
                   (1, 0): 1, (1, 1): 1},
        successor={(0, 0): (0, 1), (0, 1): (0, 2), (0, 2): (0, 3),
                   (1, 0): (1, 1)},
        M=3)


def _schedule(rows, n_slots=8, sections=None):
    p = np.zeros(len(rows), dtype=PLACEMENT_DTYPE)
    if sections is None:
        sections = (Section(0, 0, n_slots, Gauge()),)
    starts = np.array([s.out_slot_start for s in sections])
    for i, (slot, tid, uid, mass) in enumerate(rows):
        p[i]["out_slot"] = slot
        p[i]["src_track"] = tid
        p[i]["src_unit"] = uid
        p[i]["mass"] = mass
        p[i]["section"] = int(np.searchsorted(starts, slot, side="right") - 1)
    bounds = np.arange(n_slots + 1, dtype=np.int64) * 100
    return Schedule(sr=44100, slot_boundaries=bounds, placements=p,
                    sections=sections)


ROWS = [
    # bar 0
    (0, 0, 0, 0.5),   # role 0, band 0 (run head)
    (0, 1, 0, 1.0),   # role 1, band 1 (run head)
    (1, 0, 1, 2.0),   # successor of (0,0) -> continuity event, bar 0
    (2, 0, 3, 1.0),   # NOT successor of (0,1) -> run break
    # bar 1
    (4, 0, 0, 1.0),   # reuse of (0,0), last used bar 0 -> novelty 1/1
    (5, 0, 1, 1.0),   # successor of (0,0) -> continuity; reuse -> novelty 1/1
    (6, 1, 1, 0.5),   # successor of (1,0) -> continuity (band-1 thread)
]

SECTIONS = (Section(0, 0, 4, Gauge(transpose_semitones=2.0, phase_shift=0.1,
                                   loudness_scale=1.0)),
            Section(1, 4, 8, Gauge(transpose_semitones=13.0, phase_shift=0.9,
                                   loudness_scale=2.0)))


def test_lane_map_is_exhaustive_and_temperature_has_no_phi():
    assert sorted(LANE_PHI) == [1, 2, 3, 4, 5, 6]
    assert LANE_PHI[6] is None                      # T_s: sharpness, no phi
    assert tuple(LANE_PHI[i] for i in range(1, 6)) == PHI_NAMES


def test_phi_hand_computed_values():
    phis = phi_bars(_schedule(ROWS, sections=SECTIONS), _maps(), S_PHASE)

    # region: scheduled mass (mass^2) attributed to the PLACED unit's role.
    exp_region = np.array([[0.25 + 4.0, 1.0, 1.0],       # bar 0
                           [1.0 + 1.0, 0.25, 0.0]])      # bar 1
    assert np.allclose(phis["region"], exp_region, atol=0, rtol=0)

    # density == the region marginal, exactly.
    assert np.array_equal(phis["density"], phis["region"].sum(axis=1))
    assert np.allclose(phis["density"], [6.25, 2.25], atol=0, rtol=0)

    # continuity: source-successor continuation events per bar.
    assert np.array_equal(phis["continuity"], [1.0, 2.0])

    # novelty: 1/Delta recency-weighted reuse vs committed (earlier) bars.
    assert np.array_equal(phis["novelty"], [0.0, 2.0])

    # gauge: frame move at slot 4 (bar 1); group metrics per component.
    exp_move = (_circ_dist(11.0, 12.0) / 12.0        # 1/12
                + _circ_dist(0.8, 1.0)               # 0.2
                + float(np.log(2.0)))
    assert phis["gauge"][0] == 0.0
    assert abs(phis["gauge"][1] - exp_move) < 1e-15
    assert abs(exp_move - (1.0 / 12.0 + 0.2 + np.log(2.0))) < 1e-15


def test_same_bar_reuse_is_not_novelty():
    # the committed tape is strictly earlier bars: reuse WITHIN a bar adds 0.
    rows = [(0, 0, 0, 1.0), (2, 0, 0, 1.0)]
    phis = phi_bars(_schedule(rows), _maps(), S_PHASE)
    assert np.array_equal(phis["novelty"], [0.0, 0.0])


def test_recency_weight_is_one_over_delta():
    # unit used in bar 0, reused in bar 2 -> 1/2.
    rows = [(0, 0, 0, 1.0), (9, 0, 0, 1.0)]
    phis = phi_bars(_schedule(rows, n_slots=12), _maps(), S_PHASE)
    assert np.array_equal(phis["novelty"], [0.0, 0.0, 0.5])


def test_partial_bar_raises():
    with pytest.raises(ValueError, match="whole bars"):
        phi_bars(_schedule([(0, 0, 0, 1.0)], n_slots=6), _maps(), S_PHASE)


def test_unknown_unit_raises_not_defaults():
    rows = [(0, 7, 99, 1.0)]                        # unit unknown to the world
    with pytest.raises(KeyError):
        phi_bars(_schedule(rows), _maps(), S_PHASE)


def test_zero_loudness_section_is_outside_the_gauge_group():
    g0, g1 = Gauge(), Gauge(loudness_scale=0.0)
    with pytest.raises(ValueError, match="gauge group"):
        _gauge_move_magnitude(g0, g1)


def test_empty_schedule_bars_are_zero():
    phis = phi_bars(_schedule([]), _maps(), S_PHASE)
    for name in PHI_NAMES:
        assert np.all(np.asarray(phis[name]) == 0.0)
