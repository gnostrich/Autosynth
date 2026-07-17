"""F3.2 pad tap/hold behaviour (via the existing region lane) + the affordance-
honesty fixes (disarmed lanes render visibly disabled).

These are not one of the five neutrality nets (A..E) but they pin the two live
behaviours those nets bound: that a tap actually drives the region lane (and only
it), and that a disarmed lane is shown disabled.
"""
from __future__ import annotations

import numpy as np
import pytest

from ets.instrument.tap import RegionTapController, RegionTapEnvelope
from ets.panel.lanes import spec as lane_spec


def test_tap_is_a_transient_spike_that_eases_to_zero():
    env = RegionTapEnvelope(peak=3.0, lag_s=0.1)
    env.tap()
    assert env.value == 3.0 and env.state == "transient"
    # eases toward zero over the lane's constraint-lag.
    for _ in range(200):
        env.advance(0.02)
    assert env.value == 0.0 and env.state == "idle"


def test_hold_sustains_until_release_then_eases():
    env = RegionTapEnvelope(peak=3.0, lag_s=0.1)
    env.hold()
    for _ in range(50):
        env.advance(0.02)
    assert env.value == 3.0 and env.state == "held"     # sustained
    env.release()
    for _ in range(200):
        env.advance(0.02)
    assert env.value == 0.0                              # eases after release


def test_tap_controller_drives_only_the_region_lane_of_the_panel():
    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import Panel
    QApplication.instance() or QApplication([])
    panel = Panel(emitter=None, n_anchors=4)
    before = panel.u.copy()

    ctl = RegionTapController(4, region_sink=panel.tap_region_anchor)
    ctl.tap(1)
    # the tap landed on region anchor 1 (the sanctioned lane) at full scale.
    assert panel.u.u_region[1] == pytest.approx(lane_spec("region").hi)
    # NOTHING else moved: other anchors, the scalar leans, and T_s are untouched.
    assert panel.u.u_region[0] == 0.0 and panel.u.u_region[2] == 0.0
    assert (panel.u.u_density, panel.u.u_continuity, panel.u.u_gauge,
            panel.u.u_novelty, panel.u.T_s) == (
        before.u_density, before.u_continuity, before.u_gauge,
        before.u_novelty, before.T_s)

    # easing ticks bring the lane back toward zero (living loop, not a latch).
    for _ in range(400):
        ctl.advance(0.02)
    assert panel.u.u_region[1] == pytest.approx(0.0, abs=1e-3)


def test_disarmed_lanes_render_visibly_disabled():
    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import Panel
    QApplication.instance() or QApplication([])
    panel = Panel(emitter=None, n_anchors=3)

    panel.apply_disarmed(["region", "gauge"])          # engine-side ids
    assert not panel._strips["gauge"].isEnabled()
    assert not panel._region.isEnabled()
    assert not panel._xy.isEnabled()
    # a lane the engine reports as ARMED is live.
    panel.apply_disarmed(["gauge"])                     # region now armed
    assert panel._region.isEnabled()
    assert not panel._strips["gauge"].isEnabled()
    # 'cont' maps to the continuity strip (engine id vs panel id).
    panel.apply_disarmed(["cont"])
    assert not panel._strips["continuity"].isEnabled()
    assert panel._strips["gauge"].isEnabled()
