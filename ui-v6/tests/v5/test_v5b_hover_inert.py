"""V5-B — HOVER-INERT (B1/B2). Passive hover (a mouse move with no button and no
wheel) over any control changes and emits NOTHING; the XY pad emits ONLY between
arm and drop.

Teeth:
  (1) the XY pad: a disarmed move emits nothing; it emits only while armed.
  (2) the scalar/region sliders: press / drag / move are all inert (wheel-only).
  (3) the tap surface (instrument): a passive move emits nothing (no move
      handler, no mouse tracking) — audited alongside the panel controls.
"""
from __future__ import annotations

import numpy as np
import pytest

from tests.v5._fakeqt import FakeMouseEvent, Recorder


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_pad_passive_hover_is_inert_and_only_emits_between_arm_and_drop():
    _app()
    from ets.panel.widget import _RegionXYPad
    pad = _RegionXYPad()
    pad.resize(200, 200)
    pad.set_anchor_count(4)
    rec = Recorder()
    pad.changed.connect(rec)

    # DISARMED passive hover across the pad — nothing emitted.
    for x in range(40, 160, 10):
        pad.mouseMoveEvent(FakeMouseEvent(x, 100))
    assert rec.vectors == [], "a passive hover over the disarmed pad emitted"
    assert not pad.is_armed

    # ARM (click) → emits; MOVE while armed → emits; each emit is a live value.
    pad.mousePressEvent(FakeMouseEvent(150, 60))
    assert pad.is_armed
    n_after_arm = len(rec.vectors)
    assert n_after_arm >= 1, "arming did not emit a live value"
    pad.mouseMoveEvent(FakeMouseEvent(140, 70))
    pad.mouseMoveEvent(FakeMouseEvent(130, 80))
    assert len(rec.vectors) == n_after_arm + 2, "armed moves did not emit live"

    # DROP (click) → parks + emits once more, then hover is inert again.
    pad.mousePressEvent(FakeMouseEvent(130, 80))
    assert not pad.is_armed
    n_after_drop = len(rec.vectors)
    for x in range(40, 160, 10):
        pad.mouseMoveEvent(FakeMouseEvent(x, 100))
    assert len(rec.vectors) == n_after_drop, "the parked pad emitted on hover"


def test_scalar_slider_hover_and_drag_are_inert():
    _app()
    from ets.panel.widget import _ScrollSlider
    sl = _ScrollSlider()
    sl.setRange(0, 1000)
    sl.setValue(500)
    seen = []
    sl.valueChanged.connect(lambda v: seen.append(v))
    # press / move / release all inert (value changes on WHEEL only).
    sl.mousePressEvent(FakeMouseEvent(5, 5))
    sl.mouseMoveEvent(FakeMouseEvent(5, 50))
    sl.mouseReleaseEvent(FakeMouseEvent(5, 90))
    assert seen == [], "slider changed on click/drag/hover (must be wheel-only)"
    assert sl.value() == 500


def test_panel_passive_hover_emits_nothing_across_controls():
    _app()
    from ets.panel.widget import Panel

    class _RecEmitter:
        def __init__(self):
            self.calls = []
        def emit(self, u):
            self.calls.append(u.copy())

    em = _RecEmitter()
    panel = Panel(emitter=em, n_anchors=3)

    # hover the XY pad (disarmed) and drag a region strip — no emit at all.
    panel._xy.resize(200, 200)
    for x in range(30, 170, 10):
        panel._xy.mouseMoveEvent(FakeMouseEvent(x, 100))
    strip = panel._region._strips[0]
    strip.mousePressEvent(FakeMouseEvent(3, 3))
    strip.mouseMoveEvent(FakeMouseEvent(3, 40))
    strip.mouseReleaseEvent(FakeMouseEvent(3, 80))
    assert em.calls == [], "a passive hover / drag over the panel emitted (B1)"


def test_tap_surface_has_no_hover_move_channel():
    """The instrument tap surface exposes no mouseMove handler and no mouse
    tracking, so a passive hover cannot spike a lane (B1 audit)."""
    from ets.instrument.pads import RegionTapPads
    _app()
    pads = RegionTapPads(3)
    assert not pads.hasMouseTracking(), "tap surface tracks hover (B1 risk)"
    # its own class defines no mouseMoveEvent (only press/release = discrete tap).
    assert "mouseMoveEvent" not in RegionTapPads.__dict__
