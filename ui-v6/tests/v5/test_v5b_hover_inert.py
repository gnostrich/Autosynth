"""V5-B — HOVER-INERT (B1/B2), carried into ui-v6. Passive hover (a mouse move
with no button and no wheel) over any control changes and emits NOTHING.

ui-v6 note: the XY pad is removed (the FIELD subsumes it). The invariant is
audited on the surviving surfaces:
  (1) THE FIELD: no mouse tracking, no move handler; a passive hover changes
      nothing and emits nothing — only an explicit scroll gesture biases.
  (2) the scalar/region sliders: press / drag / move are all inert (wheel-only).
  (3) the whole panel: passive hover/drag emits nothing on the wire.
"""
from __future__ import annotations

from tests.v5._fakeqt import FakeMouseEvent


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _fed_field():
    from ets.instrument.field import FieldModel, FieldView
    m = FieldModel()
    w = m.telemetry_writer()
    w.apply_roleactivity([0.9, 0.2, 0.5])
    w.apply_nowplaying({0: 0.8, 7: 0.3})
    w.apply_profiles({0: [0.7, 0.2, 0.1], 7: [0.1, 0.2, 0.7]})
    v = FieldView(m)
    v.resize(300, 240)
    return m, v


def test_field_has_no_hover_move_channel():
    """The field exposes no mouseMove handler and no mouse tracking, so a
    passive hover cannot bias a lane (B1 audit, field edition)."""
    from ets.instrument.field import FieldView
    _app()
    m, v = _fed_field()
    assert not v.hasMouseTracking(), "field tracks hover (B1 risk)"
    assert "mouseMoveEvent" not in FieldView.__dict__, \
        "field defines a hover-move handler (B1 risk)"


def test_field_passive_hover_changes_nothing():
    _app()
    m, v = _fed_field()
    emitted = []
    v.bias_changed.connect(lambda: emitted.append(1))
    before_bias = {s.key: s.bias for s in v.current_squares()}
    before_settled = [s.settled for s in v.current_squares()]
    # the only mouse handler is press (unit cue routing); on non-unit squares
    # it must change nothing:
    v.mousePressEvent(FakeMouseEvent(30, 60))
    v.mousePressEvent(FakeMouseEvent(250, 200))
    assert emitted == [], "hover/click biased the field (must be scroll-only)"
    assert {s.key: s.bias for s in v.current_squares()} == before_bias
    assert [s.settled for s in v.current_squares()] == before_settled


def test_scalar_slider_hover_and_drag_are_inert():
    _app()
    from ets.panel.widget import _ScrollSlider
    sl = _ScrollSlider()
    sl.setRange(0, 1000)
    sl.setValue(500)
    seen = []
    sl.valueChanged.connect(lambda v: seen.append(v))
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

    # drag a region strip — no emit at all (strips are wheel-only).
    strip = panel._region._strips[0]
    strip.mousePressEvent(FakeMouseEvent(3, 3))
    strip.mouseMoveEvent(FakeMouseEvent(3, 40))
    strip.mouseReleaseEvent(FakeMouseEvent(3, 80))
    assert em.calls == [], "a passive hover / drag over the panel emitted (B1)"
