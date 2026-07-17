"""Field bias behaviour (via the existing region lane) + the affordance-honesty
fixes (disarmed lanes render visibly disabled). ui-v6 FIELD edition: the pad
tap/hold envelope (ets.instrument.tap) is removed with the pad surface; the
bias accumulator replaces it as the gesture state.

These are not one of the five neutrality nets (A..E) but they pin the two live
behaviours those nets bound: that a bias actually drives the region lane (and
only it), and that a disarmed lane is shown disabled.
"""
from __future__ import annotations

import pytest

from ets.instrument.field import FieldModel


def test_bias_accumulates_and_unwinds_to_zero():
    m = FieldModel()
    m.telemetry_writer().apply_roleactivity([0.1, 0.1])
    k = ("role", 1)
    m.add_bias(k, 0.5)
    m.add_bias(k, 0.25)
    assert m.bias_of(k) == pytest.approx(0.75)
    # scrolling back down unwinds the lean symmetrically to exactly zero
    # (and a zero bias leaves no residue in the ledger).
    m.add_bias(k, -0.75)
    assert m.bias_of(k) == 0.0
    assert float(m.region_vector(2)[1]) == 0.0


def test_bias_drives_only_the_region_lane_of_the_panel():
    from PySide6.QtWidgets import QApplication
    from ets.panel.envelope import SAFE_REGION_MAGNITUDE
    from ets.panel.widget import Panel
    QApplication.instance() or QApplication([])
    panel = Panel(emitter=None, n_anchors=4)
    before = panel.u.copy()

    m = FieldModel()
    m.telemetry_writer().apply_roleactivity([0.1] * 4)
    m.add_bias(("role", 1), 1.0)
    panel.set_region_vector(m.region_vector(4))
    # the bias landed on region anchor 1 (the sanctioned lane) at the cap.
    assert panel.u.u_region[1] == pytest.approx(SAFE_REGION_MAGNITUDE)
    # NOTHING else moved: other anchors, the scalar leans, and T_s untouched.
    assert panel.u.u_region[0] == 0.0 and panel.u.u_region[2] == 0.0
    assert (panel.u.u_density, panel.u.u_continuity, panel.u.u_gauge,
            panel.u.u_novelty, panel.u.T_s) == (
        before.u_density, before.u_continuity, before.u_gauge,
        before.u_novelty, before.T_s)

    # unwinding the bias brings the lane back to zero (living loop, no latch).
    m.add_bias(("role", 1), -1.0)
    panel.set_region_vector(m.region_vector(4))
    assert panel.u.u_region[1] == pytest.approx(0.0, abs=1e-6)


def test_disarmed_lanes_render_visibly_disabled():
    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import Panel
    QApplication.instance() or QApplication([])
    panel = Panel(emitter=None, n_anchors=3)

    panel.apply_disarmed(["region", "gauge"])          # engine-side ids
    assert not panel._strips["gauge"].isEnabled()
    assert not panel._region.isEnabled()
    # a lane the engine reports as ARMED is live.
    panel.apply_disarmed(["gauge"])                     # region now armed
    assert panel._region.isEnabled()
    assert not panel._strips["gauge"].isEnabled()
    # 'cont' maps to the continuity strip (engine id vs panel id).
    panel.apply_disarmed(["cont"])
    assert not panel._strips["continuity"].isEnabled()
    assert panel._strips["gauge"].isEnabled()
