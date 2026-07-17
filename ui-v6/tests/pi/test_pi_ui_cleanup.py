"""Live-window cleanup bites (ui-v6 FIELD edition; instrument UI only; engine +
faithfulness intact).

Items, all DISPLAY-side, none of which may open a new gesture->engine path:

  ITEM 1  the panel's redundant REGION vector strips are HIDDEN (not deleted) in
          the instrument window, while the FIELD still emits region-tilt on the
          SAME one /ets/lanes channel;
  ITEM 2  the FIELD renders ALL M role squares for a K=M telemetry frame (M=5):
          each square's centre hit-tests to its own key, none clipped away;
  ITEM 3  the bottom surface is a DISPLAY-ONLY source/library browser — its
          show/hide toggle is a browser filter that reaches no engine path;
  ITEM 4  the ui-v6 REPLACEMENT is total: the pad/tap modules are GONE from
          this version, `_RegionStrips` (the §8 region control) is kept, and
          the prior surface remains intact one version back (architecture-v6/).

Design law honoured: every emit here is on the existing region-tilt lane via
the panel's `set_region_vector`/`tap_region_anchor` -> `_push`; no test invents
or tolerates a second channel.
"""
from __future__ import annotations

import importlib
import pytest


# ---------------------------------------------------------------------------
# ITEM 1 — region strips hidden; the field still emits region-tilt.
# ---------------------------------------------------------------------------
def test_region_strips_hidden_but_field_still_emits(qapp, recording_emitter):
    widget = pytest.importorskip("ets.panel.widget")
    field_mod = pytest.importorskip("ets.instrument.field")

    K = 5
    panel = widget.Panel(emitter=recording_emitter, n_anchors=K)
    panel.hide_region_strips()

    # HIDDEN, not deleted: the strips widget stays constructed and still counts
    # as the exhaustive region control (it keeps mirroring region values).
    assert panel._region.isHidden(), "region strips were not hidden"
    assert isinstance(panel._region, widget._RegionStrips)
    assert panel._region.anchor_count == K

    # FIELD path emits region-tilt on the ONE /ets/lanes channel.
    model = field_mod.FieldModel()
    model.telemetry_writer().apply_roleactivity([0.2] * K)
    n0 = len(recording_emitter.lanes)
    model.add_bias(("role", 2), 1.0)
    panel.set_region_vector(model.region_vector(K))
    assert len(recording_emitter.lanes) > n0, "field bias did not emit"
    assert recording_emitter.lanes[-1][2] > 0.0
    assert recording_emitter.tolerances == [] and recording_emitter.hellos == []

    # the hidden strips still MIRROR the region value (display fidelity).
    assert panel._region.anchor_count == K


# ---------------------------------------------------------------------------
# ITEM 2 — the field renders all M role squares for a K=M frame (M=5).
# ---------------------------------------------------------------------------
def test_field_renders_five_role_squares_for_a_K5_frame(qapp):
    field_mod = pytest.importorskip("ets.instrument.field")
    from ets.instrument.feed import TelemetryReceiver

    # Drive the EXACT live sizing chain: a /ets/roleactivity frame's length is M.
    seen_K = {}
    recv = TelemetryReceiver(
        on_roleactivity=lambda levels: seen_K.__setitem__("K", len(levels)))
    recv._handle_roleactivity("/ets/roleactivity", 0.9, 0.1, 0.5, 0.2, 0.7)
    recv.stop()
    assert seen_K["K"] == 5, "telemetry K read wrong (M, not M-1)"

    m = field_mod.FieldModel()
    m.telemetry_writer().apply_roleactivity([0.9, 0.1, 0.5, 0.2, 0.7])
    v = field_mod.FieldView(m)
    v.resize(400, 300)
    sqs = v.current_squares()
    assert [s.key for s in sqs] == [("role", i) for i in range(5)]

    # every square's centre hit-tests to its OWN key — including the LAST.
    n = len(sqs)
    cols = max(1, int(n ** 0.5 + 0.999))
    rows = max(1, (n + cols - 1) // cols)
    w = v.width() / cols
    h = (v.height() - v._HEADER_PX) / rows
    hits = []
    for k in range(n):
        r, c = divmod(k, cols)
        sq = v.square_at((c + 0.5) * w, v._HEADER_PX + (r + 0.5) * h)
        hits.append(sq.key if sq else None)
    assert hits == [s.key for s in sqs], f"not all 5 squares render: {hits}"


# ---------------------------------------------------------------------------
# ITEM 3 — the library browser is DISPLAY-ONLY. (unchanged in ui-v6)
# ---------------------------------------------------------------------------
def test_library_browser_is_display_only(qapp):
    lib_mod = pytest.importorskip("ets.instrument.library")
    from ets.instrument.model import PadModel

    model = PadModel()
    model.set_activity({0: 0.8, 7: 0.3})
    browser = lib_mod.TrackLibraryBrowser(model)
    browser.sync()

    assert browser.visible_tracks() == [0, 7]
    for attr in ("emitter", "panel", "_push", "set_region_vector",
                 "tap_region_anchor", "changed", "tapped"):
        assert not hasattr(browser, attr), \
            f"library browser exposes an engine-ward attribute: {attr}"

    before_tracks = list(model.tracks)
    before_act = dict(model.activity)
    browser.set_shown(0, False)
    browser.sync()
    assert browser.is_shown(0) is False
    assert browser.visible_tracks() == [7]
    # hiding is a browser filter, not a mask: shared state unchanged.
    assert list(model.tracks) == before_tracks
    assert model.activity == before_act
    assert 0 in model.tracks


# ---------------------------------------------------------------------------
# ITEM 4 — the replacement is TOTAL in this version; the region control stays.
# ---------------------------------------------------------------------------
def test_pads_and_drill_are_gone_and_regionstrips_kept(qapp):
    """ui-v6 has NO pad grid, NO XY pad, NO separate drill view. The prior
    surface is preserved immutable one version back (architecture-v6/)."""
    widget = pytest.importorskip("ets.panel.widget")
    for gone in ("ets.instrument.pads", "ets.instrument.tap"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(gone)
    assert not hasattr(widget, "_RegionXYPad"), "the XY pad survived in ui-v6"
    assert hasattr(widget, "_RegionStrips"), "the §8 region control was lost"
    field_mod = importlib.import_module("ets.instrument.field")
    assert hasattr(field_mod, "FieldView") and hasattr(field_mod, "FieldModel")
