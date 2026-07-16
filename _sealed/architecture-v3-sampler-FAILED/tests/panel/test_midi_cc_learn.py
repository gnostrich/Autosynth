"""MIDI CC-learn: arm a lane, learn a hardware (channel, cc), then live CC
values drive that lane. Covers scalar lanes, the region vector lane (per-anchor
strip), value scaling into natural units, and rejection of a seventh target.
"""
import numpy as np
import pytest

from ets.panel.lanes import LaneVector, default_lane_vector, spec
from ets.panel.midi import CCMap, LaneTarget, cc_to_lane_value, apply_to_lane_vector


def test_learn_then_apply_scalar_lane():
    m = CCMap()
    m.arm(LaneTarget("density"))
    assert m.armed is not None
    bound = m.observe(channel=0, cc=21)          # the learned CC
    assert bound == LaneTarget("density")
    assert m.armed is None                        # learn consumed the arm
    assert m.target_for(0, 21) == LaneTarget("density")

    u = default_lane_vector(0)
    hit = m.apply(0, 21, value7=127, u=u)         # full-scale CC
    assert hit
    assert u.u_density == pytest.approx(spec("density").hi, abs=1e-6)

    hit = m.apply(0, 21, value7=0, u=u)           # zero CC → lane low
    assert u.u_density == pytest.approx(spec("density").lo, abs=1e-6)


def test_learn_region_anchor_strip():
    m = CCMap()
    m.arm(LaneTarget("region", anchor=2))
    m.observe(channel=1, cc=40)
    u = LaneVector(u_region=np.zeros(4, dtype=np.float32))
    m.apply(1, 40, value7=127, u=u)
    assert u.u_region[2] == pytest.approx(spec("region").hi, abs=1e-6)
    # other anchors untouched
    assert np.allclose(np.delete(u.u_region, 2), 0.0)


def test_temperature_maps_into_its_own_range():
    m = CCMap()
    m.bind(0, 7, LaneTarget("temperature"))
    u = default_lane_vector(0)
    m.apply(0, 7, value7=64, u=u)
    ts = spec("temperature")
    expected = ts.lo + (64 / 127.0) * (ts.hi - ts.lo)
    assert u.T_s == pytest.approx(expected, abs=1e-6)


def test_unmapped_cc_is_ignored():
    m = CCMap()
    u = default_lane_vector(0)
    before = u.copy()
    assert m.apply(5, 99, value7=100, u=u) is False
    assert u.u_density == before.u_density and u.T_s == before.T_s


def test_value_scaling_endpoints_and_midpoint():
    assert cc_to_lane_value("density", 0) == pytest.approx(spec("density").lo)
    assert cc_to_lane_value("density", 127) == pytest.approx(spec("density").hi)
    mid = cc_to_lane_value("density", 64)
    s = spec("density")
    assert mid == pytest.approx(s.lo + (64 / 127.0) * (s.hi - s.lo))


def test_cannot_learn_a_seventh_target():
    # A target outside the six lanes is rejected at construction — CC-learn
    # cannot smuggle in a seventh control.
    with pytest.raises(ValueError):
        LaneTarget("swing")


def test_region_target_requires_anchor_and_scalars_reject_anchor():
    with pytest.raises(ValueError):
        LaneTarget("region")                 # vector lane needs an anchor index
    with pytest.raises(ValueError):
        LaneTarget("density", anchor=0)      # scalar lane takes no anchor


def test_out_of_range_cc_value_rejected():
    with pytest.raises(ValueError):
        cc_to_lane_value("density", 128)


def test_panel_cc_learn_end_to_end():
    """Through the widget: arm CC-learn on the panel, learn a CC, then a live CC
    drives the lane, updates the control, and emits over OSC."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import Panel

    class _RecEmitter:
        def __init__(self):
            self.calls = []

        def emit(self, u):
            self.calls.append(u.copy())

    app = QApplication.instance() or QApplication([])
    emitter = _RecEmitter()
    panel = Panel(emitter=emitter, n_anchors=2)

    panel.arm_cc_learn(LaneTarget("novelty"))
    assert panel.handle_cc(0, 30, 0) is True          # learn (armed → bind)
    n0 = len(emitter.calls)
    assert panel.handle_cc(0, 30, 127) is True         # live drive
    assert panel.u.u_novelty == pytest.approx(spec("novelty").hi, abs=1e-6)
    assert len(emitter.calls) == n0 + 1                # a live CC emits once
    assert emitter.calls[-1].u_novelty == pytest.approx(spec("novelty").hi, abs=1e-6)
