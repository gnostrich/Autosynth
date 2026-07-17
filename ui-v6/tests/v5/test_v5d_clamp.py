"""V5-D — CLAMP (B3.1), carried into ui-v6. No reachable control state emits a
per-anchor region lean above the safe-envelope cap. The clamp function is a
backstop even for an out-of-envelope vector arriving from anywhere.

ui-v6 note: the XY pad (and its dot/ring geometry tests) is removed — the FIELD
surface's cap coverage lives in tests/field/ (composite-bias clamp + slew-
bounded wire). The panel-wire clamp tests below are unchanged.
"""
from __future__ import annotations

import numpy as np
import pytest

from ets.panel.envelope import SAFE_REGION_MAGNITUDE, clamp_region


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
