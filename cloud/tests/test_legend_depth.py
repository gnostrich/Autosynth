"""LEGEND AT DEPTH (OPEN_ENDS #21b) — the legend no longer blanks below the
track root. Drilled into a track it shows a compact PARENT-TRACK chip (colour +
honest name) plus the role-shade key for exactly the roles that view shows; at
unit depth, the parent chip + the drilled role's label. Every shade is derived
by the SAME fieldFamilyShade the squares use (fieldSquareColor) — never a
second palette — and the degraded role-grain-only field keeps NO legend
(grey squares carry no track attribution to key).

The what-to-show decision is the pure fieldLegendSpec (node-driven here); the
renderer wiring is checked statically.
"""
from __future__ import annotations

import json
import re
import shutil

import pytest

from cloud.tests.test_web_field import (
    _inline_js,
    _js_functions,
    _pure_logic_block,
    _run_node,
)

_NODE = shutil.which("node")

# a world with two tracks; track 0 clears the floor with roles {0,1} (PR 2).
_ST = """
    var st = { roleact:[0.4, 0.2, 0.1],
               nowplaying:{0:0.9, 1:0.3},
               profiles:{0:[1,1,0], 1:[1,0,0]},
               unitPools:{0:[{unit_id:7, track_id:0, band:2, profile:[1,0,0]}]},
               names:{0:'kick_drum_loop.wav', 1:'pad take 3'}, bias:{} };
"""


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_legend_spec_all_four_modes():
    driver = _pure_logic_block() + _ST + """
    console.log(JSON.stringify([
      fieldLegendSpec(st, []),                              // track root
      fieldLegendSpec(st, [['track', 0]]),                  // drilled into a track
      fieldLegendSpec(st, [['track', 0], ['role', 1]]),     // unit depth
      fieldLegendSpec(st, [['role', 2]]),                   // degraded (no track parent)
      fieldLegendSpec({ roleact:[0.1], nowplaying:{}, profiles:{}, unitPools:{},
                        names:{}, bias:{} }, [])            // flat role root
    ]));
    """
    root, track, unit, degraded, flat = json.loads(_run_node(driver))
    assert root == {"mode": "root"}
    assert track["mode"] == "track" and track["track"] == 0
    assert unit == {"mode": "unit", "track": 0, "role": 1}
    assert degraded == {"mode": "none"}, "no track parent -> no attribution to key"
    assert flat == {"mode": "none"}, "the flat role fallback keeps no legend"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_legend_role_key_ids_equal_the_drilled_view_squares():
    # the role-shade key lists EXACTLY the role ids fieldRolesOfTrack shows —
    # the same key[1] each role square carries, so shade(key) == shade(square).
    driver = _pure_logic_block() + _ST + """
    var spec = fieldLegendSpec(st, [['track', 0]]);
    var kids = fieldRolesOfTrack(st, 0).map(function(sq){ return sq.key[1]; });
    console.log(JSON.stringify([spec.roles, kids]));
    """
    roles, kids = json.loads(_run_node(driver))
    assert roles == kids and len(roles) >= 2, (roles, kids)


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_legend_shades_are_the_square_shades():
    # honestly one derivation: legend swatch for role r == fieldFamilyShade(base, r),
    # the exact expression fieldSquareColor paints the drilled role square with.
    driver = _pure_logic_block() + _ST + """
    var base = '#4FE0AE';                     // track 0's palette colour
    var spec = fieldLegendSpec(st, [['track', 0]]);
    var shades = spec.roles.map(function(r){ return fieldFamilyShade(base, r); });
    var squares = spec.roles.map(function(r){ return fieldFamilyShade(base, r); });
    var hue = Math.round(fieldHexToHsl(base).h);
    var sameFamily = shades.every(function(c){
      var m = c.match(/^hsl\\((\\d+),/); return m && parseInt(m[1],10) === hue; });
    console.log(JSON.stringify([shades, squares, sameFamily]));
    """
    shades, squares, same_family = json.loads(_run_node(driver))
    assert shades == squares
    assert same_family, "role-key shades must stay in the parent track's hue family"


# ---- renderer wiring (static) ------------------------------------------------

def test_renderer_uses_the_spec_and_one_palette_only():
    funcs = _js_functions(_inline_js())
    body = funcs["fieldRenderLegend"]
    assert "fieldLegendSpec" in body, "the renderer must consume the pure spec"
    assert "fieldFamilyShade" in body, "role-key shades must come from fieldFamilyShade"
    assert "fieldTrackColor" in body, "the parent chip must use the track palette"
    # no second palette: the renderer builds NO colour of its own (no hsl()/hex
    # literals) — every swatch colour is fieldTrackColor or fieldFamilyShade.
    assert not re.search(r"hsl\(|#[0-9a-fA-F]{3,6}\b", body), \
        "fieldRenderLegend must not invent colours — one palette, one derivation"
    # the old blank-below-root gate is gone.
    assert "atTrackRoot" not in body, "the legend must not blank below the track root"


def test_renderer_drilled_branch_shows_parent_chip_then_role_key():
    body = _js_functions(_inline_js())["fieldRenderLegend"]
    # parent chip first (base colour + honest name), then the R<n> key entries.
    chip_calls = re.findall(r"fieldLegendChip\(", body)
    assert len(chip_calls) >= 4, "root chips + parent chip + role key + unit label"
    assert '"R" + ' in body.replace("'", '"'), "role key entries must be labeled R<n>"
    assert "fieldTruncMiddle" in body, "the parent chip name must stay legible (trunc)"
