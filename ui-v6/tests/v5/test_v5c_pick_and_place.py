"""V5-C — PAD PICK-AND-PLACE (B2). Arm → move → drop emits the expected
position-based vector; a second click re-arms; a parked dot ignores the cursor.

Semantics under test (position IS the value):
  * angle selects which anchors (inverse-distance weighting toward the anchors
    on the ring), distance-from-centre is the magnitude;
  * dropping the dot on top of an anchor leans predominantly toward it;
  * dropping at the centre is zero lean;
  * the emitted target reaches the geometric value (the slew converges to it).
"""
from __future__ import annotations

import numpy as np
import pytest

from tests.v5._fakeqt import FakeMouseEvent, Recorder


def _pad(K=4, size=200):
    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import _RegionXYPad
    QApplication.instance() or QApplication([])
    pad = _RegionXYPad()
    pad.resize(size, size)
    pad.set_anchor_count(K)
    return pad


def test_place_on_an_anchor_leans_toward_that_anchor():
    pad = _pad(K=4)
    rec = Recorder()
    pad.changed.connect(rec)
    # anchor 0 sits at angle 0 → to the RIGHT of centre on the ring.
    ax, ay = pad._anchor_xy(0)
    pad.mousePressEvent(FakeMouseEvent(ax, ay))     # arm right on anchor 0
    v = rec.vectors[-1]
    assert int(np.argmax(np.abs(v))) == 0, f"dominant should be anchor 0, got {v}"
    assert v[0] > 0.5, f"placing on an anchor should lean hard toward it: {v}"
    # the parked/emitted value equals the geometric _vector() at that position.
    pad.mousePressEvent(FakeMouseEvent(ax, ay))     # drop
    np.testing.assert_allclose(rec.vectors[-1], pad._vector(), atol=1e-6)


def test_center_is_zero_lean():
    pad = _pad(K=4)
    rec = Recorder()
    pad.changed.connect(rec)
    cx, cy = pad._center()
    pad.mousePressEvent(FakeMouseEvent(cx, cy))     # arm at dead centre
    assert np.allclose(rec.vectors[-1], 0.0, atol=1e-6), "centre must be zero lean"


def test_second_click_rearms_and_parked_dot_ignores_cursor():
    pad = _pad(K=3)
    rec = Recorder()
    pad.changed.connect(rec)

    pad.mousePressEvent(FakeMouseEvent(150, 60))    # click 1: ARM
    assert pad.is_armed
    pad.mouseMoveEvent(FakeMouseEvent(140, 70))     # follows
    pad.mousePressEvent(FakeMouseEvent(140, 70))    # click 2: DROP (park)
    assert not pad.is_armed
    parked = rec.vectors[-1].copy()

    # a parked dot ignores the cursor entirely.
    n = len(rec.vectors)
    pad.mouseMoveEvent(FakeMouseEvent(30, 190))
    assert len(rec.vectors) == n, "parked dot followed the cursor"
    np.testing.assert_allclose(pad._vector(), parked, atol=1e-6)

    # click 3: RE-ARM — the dot follows again.
    pad.mousePressEvent(FakeMouseEvent(60, 60))     # click 3
    assert pad.is_armed
    pad.mouseMoveEvent(FakeMouseEvent(70, 70))
    assert not np.allclose(pad._vector(), parked, atol=1e-6), "re-arm did not move"


def test_through_panel_target_and_slewed_wire_reach_the_placed_vector():
    """The pad drives the ONE region path: the panel target (self.u.u_region) is
    the placed geometric vector, and the slewed wire value converges to it."""
    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import Panel
    QApplication.instance() or QApplication([])

    class _RecEmitter:
        def __init__(self):
            self.calls = []
        def emit(self, u):
            self.calls.append(u.copy())

    em = _RecEmitter()
    panel = Panel(emitter=em, n_anchors=4)
    panel._xy.resize(200, 200)
    ax, ay = panel._xy._anchor_xy(2)
    panel._xy.mousePressEvent(FakeMouseEvent(ax, ay))   # arm on anchor 2
    panel._xy.mousePressEvent(FakeMouseEvent(ax, ay))   # drop

    placed = panel._xy._vector()
    # panel TARGET == the placed geometric vector (the pad set the region lane).
    np.testing.assert_allclose(panel.u.u_region, placed, atol=1e-6)
    # let the slew converge; the last emitted region equals the target.
    for _ in range(60):
        panel.tick_slew()
    np.testing.assert_allclose(em.calls[-1].u_region, placed, atol=1e-3)
