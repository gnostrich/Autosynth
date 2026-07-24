"""FE pure-logic teeth for the DISPLAY/ADDITIVE Play-surface changes
(PREREG-field-fullscreen-remove-set): field fullscreen + scroll-fit + full-name
marquee, and the Explore owner-only "Remove my set".

These are DISPLAY-ONLY: none of the new logic touches fieldBias / fieldBiasPayload /
the steer wire. The load-bearing guarantee re-proven here at the FE boundary is that a
NEUTRAL field (empty bias) still emits the byte-identical neutral payload
(channel_bias all-zero, unit_bias {}, track_role_bias [], region_add all-zero) — the
exact precondition the engine byte-identity (test_channel_bias) rests on.

Teeth:
  FIT       fieldGridMinSize keeps a legible min cell (fits -> box; oversized -> scroll).
  MARQUEE   fieldMarqueeShift is 0 when the name fits, and travels in [0, over] over
            time when it overflows (gentle ping-pong; no trig/timer in the code).
  FS        fieldFsPlan picks API vs CSS-fallback by availability + active state.
  MINE      exploreRemovable is true ONLY for entry.mine === true (owner-only gate).
  NEUTRAL   fieldBiasPayload on an empty field is the byte-identical neutral payload.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_INDEX = _ROOT / "cloud" / "companion" / "static" / "index.html"
_NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(_NODE is None, reason="node not available")


def _inline_js() -> str:
    html = _INDEX.read_text()
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert blocks, "no inline <script> found in index.html"
    for b in blocks:
        if "FIELD PURE LOGIC" in b:
            return b
    return max(blocks, key=len)


def _block(begin: str, end: str) -> str:
    js = _inline_js()
    m = re.search(re.escape(begin) + r".*?" + re.escape(end), js, re.S)
    assert m, f"extractable block {begin!r}..{end!r} missing/renamed"
    return m.group(0)


def _display_block() -> str:
    return _block("/* ===== FIELD DISPLAY PURE LOGIC", "===== END FIELD DISPLAY PURE LOGIC ===== */")


def _explore_block() -> str:
    return _block("/* ===== EXPLORE PURE LOGIC", "===== END EXPLORE PURE LOGIC ===== */")


def _field_block() -> str:
    return _block("/* ---------- pure logic", "===== END FIELD PURE LOGIC ===== */")


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"//[^\n]*", " ", src)
    return src


def _run_node(script: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        r = subprocess.run([_NODE, path], capture_output=True, text=True, timeout=60)
    finally:
        Path(path).unlink(missing_ok=True)
    assert r.returncode == 0, f"node failed: {r.stdout}\n{r.stderr}"
    return r.stdout.strip()


# --- FIT : legible minimum + scroll when oversized ---------------------------

def test_grid_min_size_fits_then_scrolls():
    driver = _display_block() + """
    // small grid inside a big box -> just fill the box, no scroll on either axis.
    var a = fieldGridMinSize(2, 3, 1200, 800);
    if(a.w !== 1200 || a.h !== 800 || a.scrollX || a.scrollY){
      console.log('FAIL fits ' + JSON.stringify(a)); process.exit(1); }
    // many tracks x many roles in a small box -> grow beyond the box AND flag scroll.
    var b = fieldGridMinSize(40, 30, 600, 400);
    if(!(b.w > 600) || !(b.h > 400) || !b.scrollX || !b.scrollY){
      console.log('FAIL scroll ' + JSON.stringify(b)); process.exit(1); }
    // the grown size keeps at least the min cell per row/col (34x30 + headers/rail).
    if(b.w < 160 + 30*34 || b.h < 22 + 30 + 40*30){
      console.log('FAIL mincell ' + JSON.stringify(b)); process.exit(1); }
    console.log('OK');
    """
    assert _run_node(driver) == "OK"


# --- MARQUEE : full name reads over time, 0 when it fits ---------------------

def test_marquee_shift_zero_when_fits_and_travels_when_overflow():
    driver = _display_block() + """
    // name fits the box -> no scroll, ever.
    for(var t=0;t<5000;t+=137){
      if(fieldMarqueeShift(80, 120, t) !== 0){ console.log('FAIL fit ' + t); process.exit(1); }
    }
    // overflow: offset stays within [0, over] and actually reaches near `over`.
    var over = 200 - 60;               // textW 200, boxW 60
    var mx = 0, mn = 1e9;
    for(var u=0;u<40000;u+=50){
      var o = fieldMarqueeShift(200, 60, u);
      if(o < -1e-9 || o > over + 1e-9){ console.log('FAIL range ' + o); process.exit(1); }
      if(o > mx) mx = o; if(o < mn) mn = o;
    }
    if(mn > 1e-9){ console.log('FAIL start ' + mn); process.exit(1); }   // pauses at 0
    if(mx < over - 1.0){ console.log('FAIL reach ' + mx); process.exit(1); }  // reaches ~the end (within 1px of the sampling grid)
    console.log('OK');
    """
    assert _run_node(driver) == "OK"


def test_marquee_has_no_trig_timer_or_easing_in_code():
    """The gentle marquee is WEB-FAB clean: pure arithmetic, no procedural-art trig,
    no timer/easing library baked into the pure motion function."""
    src = _display_block()
    m = re.search(r"function\s+fieldMarqueeShift\s*\(.*?\n  \}", src, re.S)
    assert m, "fieldMarqueeShift missing"
    body = m.group(0)
    for banned in ("Math.sin", "Math.cos", "Math.tan", "Math.random",
                   "setTimeout", "setInterval", "lerp", "tween", "easing"):
        assert banned not in body, f"marquee motion must not use {banned!r}"


# --- FS : Fullscreen API vs CSS fallback ------------------------------------

def test_fullscreen_plan_branches():
    driver = _display_block() + """
    if(fieldFsPlan(true, false)  !== 'api-enter'){ console.log('FAIL ae'); process.exit(1); }
    if(fieldFsPlan(true, true)   !== 'api-exit'){  console.log('FAIL ax'); process.exit(1); }
    if(fieldFsPlan(false, false) !== 'css-enter'){ console.log('FAIL ce'); process.exit(1); }
    if(fieldFsPlan(false, true)  !== 'css-exit'){  console.log('FAIL cx'); process.exit(1); }
    console.log('OK');
    """
    assert _run_node(driver) == "OK"


# --- MINE : owner-only Remove gate ------------------------------------------

def test_explore_removable_owner_or_keyed_operator():
    """Removable = MY set, or ANY set when this session is the keyed OPERATOR
    (world.canTrain) — the operator curates the catalog (2026-07-24, requested:
    'i dont even see remove button for the other sets'). Server-enforced either
    way (owner-gated /api/share; owner-session-gated /api/admin/unshare)."""
    driver = _explore_block() + """
    var world = {};                              // visitor: strict owner flag only
    if(exploreRemovable({ mine:true, id:'x' })  !== true){  console.log('FAIL mine'); process.exit(1); }
    if(exploreRemovable({ mine:false, id:'x' }) !== false){ console.log('FAIL notmine'); process.exit(1); }
    if(exploreRemovable({ id:'x' })             !== false){ console.log('FAIL absent'); process.exit(1); }
    if(exploreRemovable(null)                   !== false){ console.log('FAIL null'); process.exit(1); }
    // a truthy-but-not-true `mine` (e.g. 1) must NOT unlock removal (strict owner flag).
    if(exploreRemovable({ mine:1 })             !== false){ console.log('FAIL loose'); process.exit(1); }
    // keyed OPERATOR (canTrain) may remove ANY set; strict-true only.
    world = { canTrain: true };
    if(exploreRemovable({ mine:false, id:'x' }) !== true){ console.log('FAIL op'); process.exit(1); }
    world = { canTrain: 1 };
    if(exploreRemovable({ mine:false, id:'x' }) !== false){ console.log('FAIL oploose'); process.exit(1); }
    if(exploreRemoveMsg('My Set') !== 'Remove My Set from Explore?'){ console.log('FAIL msg'); process.exit(1); }
    console.log('OK');
    """
    assert _run_node(driver) == "OK"


def test_remove_button_only_rendered_for_mine_and_uses_unshare():
    """The Remove control is display-gated on exploreRemovable(s) and its handler hits
    the EXISTING owner-gated unshare (POST /api/share {on:false, set_id}) — never a new
    route. Static wiring assertions on the served page."""
    js = _inline_js()
    assert "exploreRemovable(s)" in js, "Remove button must be gated on exploreRemovable(s)"
    m = re.search(r"function\s+removeMySet\s*\(.*?\n  \}", js, re.S)
    assert m, "removeMySet missing"
    body = m.group(0)
    assert '"/api/share"' in body and '"on":false' in body.replace(" ", "") \
        or ("on:false" in body.replace(" ", "")), "must POST the owner-gated unshare"
    assert "/api/share" in body and "set_id:id" in body.replace(" ", ""), \
        "removeMySet must unshare via /api/share with the set_id"
    assert "confirm(" in body, "removal must be behind a confirm (mis-tap guard)"


# --- NEUTRAL : the field's neutral payload is byte-identical ------------------

def test_neutral_field_payload_is_byte_identical():
    """A field with NO bias must emit the neutral payload the engine byte-identity
    contract (test_channel_bias) rests on: channel_bias all-zero, unit_bias {},
    track_role_bias [], region_add all-zero — and always ALL FOUR keys present."""
    driver = _field_block() + """
    // browser globals fieldBiasPayload reads (world + a settled region cap / arming).
    var world = { channels:[{track_id:0},{track_id:1}], M:3, regionCap:1, regionArmed:true };
    var p = fieldBiasPayload({ bias:{} });
    var keys = Object.keys(p).sort();
    if(JSON.stringify(keys) !== JSON.stringify(["channel_bias","region_add","track_role_bias","unit_bias"])){
      console.log('FAIL keys ' + JSON.stringify(keys)); process.exit(1); }
    if(JSON.stringify(p.channel_bias) !== JSON.stringify([0,0])){ console.log('FAIL cb'); process.exit(1); }
    if(JSON.stringify(p.region_add) !== JSON.stringify([0,0,0])){ console.log('FAIL ra'); process.exit(1); }
    if(JSON.stringify(p.track_role_bias) !== "[]"){ console.log('FAIL tr'); process.exit(1); }
    if(JSON.stringify(p.unit_bias) !== "{}"){ console.log('FAIL ub'); process.exit(1); }
    console.log('OK');
    """
    assert _run_node(driver) == "OK"


def test_display_logic_never_touches_the_bias_payload():
    """The DISPLAY block (fullscreen / scroll / marquee) must not read or write the
    steer path — no fieldBias, no fieldBiasPayload, no sendSteer. It is layout only."""
    disp = _strip_comments(_display_block())   # comments name the ban; code must not use it
    for banned in ("fieldBias", "sendSteer", "/api/steer",
                   "channel_bias", "region_add", "track_role_bias", "unit_bias"):
        assert banned not in disp, f"display pure-logic must not reference the steer path ({banned})"
