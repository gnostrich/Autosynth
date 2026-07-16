"""Live-window cleanup bites (instrument UI only; engine + faithfulness intact).

Three items, all DISPLAY-side, none of which may open a new gesture->engine path:

  ITEM 1  the panel's redundant REGION vector strips are HIDDEN (not deleted) in
          the instrument window, while the ROLE pads + XY vector pad still emit
          region-tilt on the SAME one /ets/lanes channel;
  ITEM 2  the ROLE grid renders ALL M pads for a K=M telemetry frame (M=5), sized
          to M (not M-1), with a per-pad minimum so the last pad is never clipped;
  ITEM 3  the bottom surface is a DISPLAY-ONLY source/library browser — its
          show/hide toggle is a browser filter that reaches no engine path.

Design law honoured: every emit here is on the existing region-tilt lane via the
panel's `tap_region_anchor` / XY `_on_region_vector` -> `_push`; no test invents
or tolerates a second channel.
"""
from __future__ import annotations

import numpy as np
import pytest

from PySide6.QtCore import QPointF


class _FakeMouseEvent:
    """Minimal event stub: the widget handlers only touch position/accept/ignore."""

    def __init__(self, x: float, y: float) -> None:
        self._p = QPointF(float(x), float(y))

    def position(self) -> QPointF:
        return self._p

    def accept(self) -> None:
        pass

    def ignore(self) -> None:
        pass


# ---------------------------------------------------------------------------
# ITEM 1 — region strips hidden; XY + role still emit region-tilt.
# ---------------------------------------------------------------------------
def test_region_strips_hidden_but_xy_and_role_still_emit(qapp, recording_emitter):
    widget = pytest.importorskip("ets.panel.widget")
    from ets.panel.envelope import SAFE_REGION_MAGNITUDE

    K = 5
    panel = widget.Panel(emitter=recording_emitter, n_anchors=K)
    panel.hide_region_strips()

    # HIDDEN, not deleted: the strips widget stays constructed and still counts as
    # the exhaustive region control (it keeps mirroring region values).
    assert panel._region.isHidden(), "region strips were not hidden"
    assert isinstance(panel._region, widget._RegionStrips)
    assert panel._region.anchor_count == K

    # ROLE path still emits region-tilt on the ONE /ets/lanes channel.
    n0 = len(recording_emitter.lanes)
    panel.tap_region_anchor(2, float(SAFE_REGION_MAGNITUDE))
    assert len(recording_emitter.lanes) > n0, "role tap did not emit region-tilt"
    assert recording_emitter.lanes[-1][2] > 0.0
    assert recording_emitter.tolerances == [] and recording_emitter.hellos == []

    # XY vector pad still emits region-tilt: arm it off-centre, then let the panel
    # slew push the target onto the wire (same _push path).
    panel._xy.resize(200, 200)
    panel._xy.mousePressEvent(_FakeMouseEvent(170, 100))   # arm, dot off-centre
    n1 = len(recording_emitter.lanes)
    for _ in range(60):
        panel.tick_slew()
    assert len(recording_emitter.lanes) > n1, "XY vector pad did not emit region-tilt"
    assert recording_emitter.tolerances == [] and recording_emitter.hellos == []


# ---------------------------------------------------------------------------
# ITEM 2 — role grid renders all M pads for a K=M frame (M=5), sized to M.
# ---------------------------------------------------------------------------
def test_role_grid_renders_five_pads_for_a_K5_frame(qapp):
    pads_mod = pytest.importorskip("ets.instrument.pads")
    from ets.instrument.feed import TelemetryReceiver

    # Drive the EXACT live sizing chain: a /ets/roleactivity frame's length is M
    # (one level per anchor), and live.py sizes the grid to that M.
    seen_K = {}
    recv = TelemetryReceiver(
        on_roleactivity=lambda levels: seen_K.__setitem__("K", len(levels)))
    recv._handle_roleactivity("/ets/roleactivity", 0.9, 0.1, 0.5, 0.2, 0.7)  # M=5
    recv.stop()
    assert seen_K["K"] == 5, "telemetry K read wrong (M, not M-1)"

    pads = pads_mod.RegionTapPads(0)
    pads.set_anchor_count(seen_K["K"])       # the live path: set_anchor_count(M)
    assert pads._K == 5

    # Every one of the 5 pads renders: each pad's centre hit-tests to its OWN
    # index 0..4 — including the LAST pad (index 4), so none is clipped off.
    pads.resize(400, 90)
    w = pads.width() / 5.0
    hit = [pads._anchor_at((i + 0.5) * w) for i in range(5)]
    assert hit == [0, 1, 2, 3, 4], f"not all 5 pads render distinctly: {hit}"

    # Minimum width is keyed to M (not M-1): room for all 5 pads at MIN_PAD_W each.
    assert pads.minimumWidth() >= 5 * pads_mod.RegionTapPads.MIN_PAD_W


# ---------------------------------------------------------------------------
# ITEM 3 — the library browser is DISPLAY-ONLY.
# ---------------------------------------------------------------------------
def test_library_browser_is_display_only(qapp):
    lib_mod = pytest.importorskip("ets.instrument.library")
    from ets.instrument.model import PadModel

    model = PadModel()
    model.set_activity({0: 0.8, 7: 0.3})     # two loaded, now-playing source tracks
    browser = lib_mod.TrackLibraryBrowser(model)
    browser.sync()

    # a row per loaded source track (a list browser, not a tap grid).
    assert browser.visible_tracks() == [0, 7]

    # it owns NO engine handle — structurally it cannot reach an emitter/lane/panel.
    for attr in ("emitter", "panel", "_push", "set_region_vector",
                 "tap_region_anchor", "changed", "tapped"):
        assert not hasattr(browser, attr), \
            f"library browser exposes an engine-ward attribute: {attr}"

    # toggling the show/hide filter emits NOTHING and affects ONLY the browser.
    before_tracks = list(model.tracks)
    before_act = dict(model.activity)
    browser.set_shown(0, False)
    browser.sync()
    assert browser.is_shown(0) is False
    assert browser.visible_tracks() == [7], "hide changed more than the browser view"

    # the only shared state (the read-only PadModel) is UNCHANGED: the source track
    # is not muted, excluded, or removed — hiding is a browser filter, not a mask.
    assert list(model.tracks) == before_tracks
    assert model.activity == before_act
    assert 0 in model.tracks


def test_trackpadgrid_and_regionstrips_are_kept_not_deleted():
    """The re-role/collapse must not DELETE the widgets other tests depend on:
    TrackPadGrid stays in pads.py; _RegionStrips stays in the panel."""
    pads_mod = pytest.importorskip("ets.instrument.pads")
    widget = pytest.importorskip("ets.panel.widget")
    assert hasattr(pads_mod, "TrackPadGrid")
    assert hasattr(widget, "_RegionStrips")
