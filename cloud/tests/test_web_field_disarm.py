"""WEB-FIELD role/unit-grain DISARM (OPEN_ENDS #22; Theorem A arming corollary).

On a world whose anchor band-profile B is degenerate (uniform — profile_armed False),
the field must disarm exactly the two controls that route through B's columns, and
NOTHING else:
  * ROLE->UNIT drill DISARMS — the server withholds the (false-attribution) unit
    pools, so role squares floor-gate to non-expandable and no unit squares render;
  * TRACK-square LEAN DISARMS — a scroll/drag on a track square emits nothing and
    names the wall (a degenerate T1 under uniform B);
while the honest surface STAYS live:
  * TRACK->ROLE drill stays OPEN — a flat profile still drills to all M roles by
    index (no false ranking);
  * ROLE-square bias stays LIVE — a well-typed T1 tilt through the role indicator.

Pure-ladder behaviour is checked in node; the imperative gate wiring + refusal
captions are checked by static read. Reuses the test_web_field harness.
"""
from __future__ import annotations

import re

import pytest

from cloud.tests.test_web_field import (
    _INDEX, _NODE, _inline_js, _js_functions, _pure_logic_block, _run_node,
)


# --- pure ladder: unit drill disarmed (empty pools), track->role stays open -------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_disarm_empty_pools_close_unit_drill_but_keep_track_role_drill():
    driver = _pure_logic_block() + """
    // DISARMED world: server serves EMPTY unit_pools + flat per-track profiles.
    var st = { roleact:[0.5,0.5], nowplaying:{0:0.4}, profiles:{0:[1,1]},
               unitPools:{}, names:{}, bias:{} };
    // ROLE->UNIT drill DISARMED: role squares floor-gate to non-expandable; no units.
    var role = fieldRoleSquare(st, 0);
    if(role.expandable){ console.log('FAIL role expandable under empty pools'); process.exit(1); }
    if(fieldUnitSquares(st, 0).length !== 0){ console.log('FAIL unit squares served'); process.exit(1); }
    // TRACK->ROLE drill STAYS OPEN: a flat profile drills to ALL M roles, index order.
    var tracks = fieldTrackSquares(st);
    if(!tracks[0].expandable){ console.log('FAIL track drill closed'); process.exit(1); }
    var roles = fieldRolesOfTrack(st, 0).map(function(s){ return s.key[1]; });
    if(roles.join(',') !== '0,1'){ console.log('FAIL roles ' + roles.join(',')); process.exit(1); }
    // the drilled role squares are themselves atomic (unit grain closed).
    if(roles.length && fieldRoleSquare(st, roles[0]).expandable){
      console.log('FAIL drilled role still expandable'); process.exit(1); }
    console.log('OK');
    """
    assert _run_node(driver) == "OK"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_track_lean_gate_predicate():
    """fieldTrackLeanDisarmed fires ONLY on track keys, ONLY when disarmed — role
    (and any other) bias is never gated by it. Reconstructed from the REAL function
    body (no drift) rather than executing the browser script (which has no DOM here)."""
    body = _js_functions(_inline_js()).get("fieldTrackLeanDisarmed", "")
    assert body, "fieldTrackLeanDisarmed helper missing"
    driver = "var fieldProfileArmed;\nfunction fieldTrackLeanDisarmed(keyArr){" + body + "}\n" + """
    fieldProfileArmed = false;
    if(fieldTrackLeanDisarmed(["track",0]) !== true){ console.log('FAIL track disarmed'); process.exit(1); }
    if(fieldTrackLeanDisarmed(["role",0]) !== false){ console.log('FAIL role gated'); process.exit(1); }
    if(fieldTrackLeanDisarmed(["unit",0,5,0]) !== false){ console.log('FAIL unit gated'); process.exit(1); }
    fieldProfileArmed = true;
    if(fieldTrackLeanDisarmed(["track",0]) !== false){ console.log('FAIL armed track'); process.exit(1); }
    console.log('OK');
    """
    assert _run_node(driver) == "OK"


# --- imperative wiring: the gates are actually consulted before emitting ----------

def _funcs():
    return _js_functions(_inline_js())


def test_applier_reads_measured_flag():
    body = _funcs().get("fieldApplyStatic", "")
    assert "profile_armed" in body and "fieldProfileArmed" in body, \
        "fieldApplyStatic must read the measured profile_armed flag"
    # default armed (informative-B / flag-absent worlds keep current behaviour).
    assert re.search(r"var\s+fieldProfileArmed\s*=\s*true", _inline_js()), \
        "fieldProfileArmed must default armed"


def test_wheel_bias_consults_track_lean_gate_before_emitting():
    body = _funcs().get("fieldOnWheel", "")
    assert "fieldTrackLeanDisarmed" in body and "fieldRefuseTrackLean" in body, \
        "the wheel bias path must consult the track-lean disarm gate"
    # the refusal + return must precede the fieldAddBias emit (emit nothing when disarmed).
    assert body.index("fieldTrackLeanDisarmed") < body.index("fieldAddBias"), \
        "the track-lean gate must run BEFORE any bias is added"


def test_touch_bias_consults_track_lean_gate_before_emitting():
    body = _funcs().get("fieldTouchMove", "")
    assert "fieldTrackLeanDisarmed" in body and "fieldRefuseTrackLean" in body, \
        "the touch bias path must consult the track-lean disarm gate"
    assert body.index("fieldTrackLeanDisarmed") < body.index("fieldAddBias"), \
        "the track-lean gate must run BEFORE any bias is added (touch)"


def test_zoom_names_the_unit_grain_wall_under_disarm():
    body = _funcs().get("fieldZoomInto", "")
    assert "fieldRefuseUnitGrain" in body and "fieldProfileArmed" in body, \
        "drilling a role under disarm must name the unit-grain wall, not the generic atomic refusal"


def test_refusal_functions_read_the_registered_caption_spans():
    funcs = _funcs()
    assert 'fieldTrackLeanMsg' in funcs.get("fieldRefuseTrackLean", ""), \
        "fieldRefuseTrackLean must read its caption from the registered span (single source)"
    assert 'fieldUnitGrainMsg' in funcs.get("fieldRefuseUnitGrain", ""), \
        "fieldRefuseUnitGrain must read its caption from the registered span (single source)"


def test_refusal_captions_present_verbatim_and_hidden():
    html = _INDEX.read_text()
    for cid, text in (
        ("fieldTrackLeanMsg",
         "track lean disarmed &mdash; anchor profiles carry no direction on this world"),
        ("fieldUnitGrainMsg",
         "unit grain disarmed &mdash; the anchor-band matrix carries no information on this world"),
    ):
        m = re.search(r'<span class="hint" id="%s"([^>]*)>(.*?)</span>' % cid, html)
        assert m, f"missing refusal caption span #{cid}"
        assert "hidden" in m.group(1), f"#{cid} must start hidden (shown only on refusal)"
        assert m.group(2) == text, f"#{cid} text drifted: {m.group(2)!r}"
