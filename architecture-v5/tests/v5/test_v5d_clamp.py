"""V5-D — CLAMP (B3.1). No reachable dot position emits a per-anchor region lean
above the safe-envelope cap; the ring is a real wall. The clamp function is a
backstop even for an out-of-envelope vector arriving from anywhere.
"""
from __future__ import annotations

import numpy as np
import pytest

from ets.panel.envelope import SAFE_REGION_MAGNITUDE, clamp_region
from tests.v5._fakeqt import FakeMouseEvent


def _pad(K=5, size=200):
    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import _RegionXYPad
    QApplication.instance() or QApplication([])
    pad = _RegionXYPad()
    pad.resize(size, size)
    pad.set_anchor_count(K)
    return pad


def test_no_reachable_dot_position_exceeds_the_cap():
    pad = _pad(K=5, size=200)
    worst = 0.0
    # sweep the whole widget rectangle (incl. far corners, well outside the ring)
    # arming at each point and asking for the emitted vector.
    for x in range(-40, 241, 8):
        for y in range(-40, 241, 8):
            pad._armed = False
            pad.mousePressEvent(FakeMouseEvent(x, y))   # arm/place at (x, y)
            v = pad._vector()
            worst = max(worst, float(np.max(np.abs(v))) if v.size else 0.0)
    assert worst <= SAFE_REGION_MAGNITUDE + 1e-6, (
        f"a reachable dot position emitted lean {worst} > cap "
        f"{SAFE_REGION_MAGNITUDE} — the ring is not a wall")


def test_dot_cannot_leave_the_ring():
    pad = _pad(K=4, size=200)
    cx, cy = pad._center()
    R = pad._ring_radius()
    pad.mousePressEvent(FakeMouseEvent(1000, 1000))     # far outside
    d = np.hypot(pad._dot.x() - cx, pad._dot.y() - cy)
    assert d <= R + 1e-6, "the dot escaped the safe ring"


def test_clamp_is_a_backstop_and_preserves_direction():
    over = np.array([3.0, -1.5, 0.0, 0.6], dtype=np.float32)   # peak 3.0 > cap
    c = clamp_region(over)
    assert float(np.max(np.abs(c))) <= SAFE_REGION_MAGNITUDE + 1e-6
    # direction preserved: ratios unchanged (uniform scale).
    scale = SAFE_REGION_MAGNITUDE / 3.0
    np.testing.assert_allclose(c, over * scale, atol=1e-6)
    # an in-envelope vector is returned unchanged.
    inside = np.array([0.4, -0.2, 0.0], dtype=np.float32)
    np.testing.assert_allclose(clamp_region(inside), inside, atol=1e-6)


def test_panel_never_emits_a_region_component_above_the_cap():
    """Even a full-scale tap (peak = lane hi = 3.0) is clamped on the WIRE while
    the raw target is preserved for the controls."""
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
    panel.tap_region_anchor(1, 3.0)             # full-scale region tap
    for _ in range(60):
        panel.tick_slew()
    for c in em.calls:
        assert float(np.max(np.abs(c.u_region))) <= SAFE_REGION_MAGNITUDE + 1e-6
    # the raw control TARGET is preserved (only the wire is clamped).
    assert panel.u.u_region[1] == pytest.approx(3.0)
