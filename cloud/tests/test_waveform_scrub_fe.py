"""FE teeth for WAVEFORM SCRUB-TO-STEER (PREREG-waveform-scrub).

The TRACKS view is a SECOND FRONT-END onto the material surface's EXISTING two jacks
(channel_bias for a row/track roll-up, track_role_bias for a (track, role) cell). It
adds no jack, no decision channel and no new scaling constant: every lean it produces
is an entry in the SAME lean ledger the GRID gestures write, summed by the SAME
saturating accumulator (fieldAddBias) and cast by the SAME single payload builder
(fieldBiasPayload). These tests hold that construction to the directive's laws.

Teeth (each must BITE — the deliberate-violation variant is exercised inline):
  WS-5  switch-reset: after a view switch the payload is the NEUTRAL carrier,
        byte-for-byte; switching back does not resurrect the old leans.
  W-4   same-jack: scrub(i, t) payload == the equivalent manual GRID row+cell payload
        built from the same numbers (byte-identical JSON).
  WS-1  mapping honesty: w_r == the EXACT mass-weighted stored q of the selected
        slices; an intentionally smoothed variant FAILS the same assertion.
  WS-4  wall respect: a lane the grid omits (track absent from the channel roster) is
        omitted from the scrub payload identically, and the scrub never rides the
        SETTLEMENT lane (region_add stays all-zero, armed or disarmed).
  WS-7  not-a-playhead (static half): no audio element, no transport call, no seek and
        no unit id anywhere on the scrub path; the view's only fetch is the read-only
        wavemap GET (no method, no body).
  WS-6  grid-untouched: the GRID-view pure-logic block is byte-identical to the
        pre-directive extraction (sha256 pin), as is the DISPLAY block it reuses.
  W-1   the lane ROW HEADER is the grid's row square verbatim (same kind/key/telemetry),
        so the existing row-lean gesture drives it unchanged.
  V-4   default GRID; only the exact persisted "tracks" token selects the new view.
  FLAG  FIELD_TRACKS_VIEW false pins the surface to GRID (rollback).
"""
from __future__ import annotations

import hashlib
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


# --- extraction (the pattern of test_field_display_and_explore_fe.py) --------

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


def _field_block() -> str:
    return _block("/* ---------- pure logic", "===== END FIELD PURE LOGIC ===== */")


def _display_block() -> str:
    return _block("/* ===== FIELD DISPLAY PURE LOGIC",
                  "===== END FIELD DISPLAY PURE LOGIC ===== */")


def _tracks_block() -> str:
    return _block("/* ===== FIELD TRACKS PURE LOGIC",
                  "===== END FIELD TRACKS PURE LOGIC ===== */")


def _tracks_runtime() -> str:
    return _block("/* ---------- TRACKS VIEW runtime", "// ---- THE TELEMETRY APPLIERS")


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"//[^\n]*", " ", src)
    return src


def _js_functions(src: str):
    out = {}
    for m in re.finditer(r"function\s+([A-Za-z_$][\w$]*)\s*\(", src):
        name = m.group(1)
        i = src.index("{", m.end() - 1)
        depth, j = 0, i
        while j < len(src):
            ch = src[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out[name] = src[i + 1:j]
    return out


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


def _node_check(script: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        r = subprocess.run([_NODE, "--check", path], capture_output=True, text=True,
                           timeout=60)
    finally:
        Path(path).unlink(missing_ok=True)
    assert r.returncode == 0, f"node --check failed: {r.stderr}"


# --- the shared fixture world + wavemap --------------------------------------
#
# M = 3 roles. Track 7 carries four STORED slices; two of them OVERLAP at t=1.7 so the
# mass-weighted conditional really has to sum over a multi-slice selection:
#   slice 102  m=1.0  q=[0, .5, .5]   spans [1.0, 2.0)
#   slice 104  m=1.0  q=[1,  0,  0]   spans [1.5, 2.5)
#   => Sum m*q = [1.0, 0.5, 0.5], total 2.0  =>  w = [0.5, 0.25, 0.25]
# Track 9 is a second lane (its own slices) so per-lane isolation is visible.
_FIXTURE = """
var world = { channels:[{track_id:7},{track_id:9}], M:3, regionCap:1, regionArmed:true };
var WM = { ok:true, M:3, sr:48000, tracks:{
  "7": { name:"seven", duration_s:10, peaks:[0,0.5,1],
         slices:[ [0.0, 1.0, 101, 2.0, [1.0, 0.0, 0.0]],
                  [1.0, 2.0, 102, 1.0, [0.0, 0.5, 0.5]],
                  [1.5, 2.5, 104, 1.0, [1.0, 0.0, 0.0]],
                  [2.5, 3.0, 103, 3.0, [0.25, 0.75, 0.0]] ] },
  "9": { name:"nine", duration_s:4, peaks:[1,1],
         slices:[ [0.0, 4.0, 201, 5.0, [0.0, 0.0, 1.0]] ] }
} };
var W_EXPECT = [0.5, 0.25, 0.25];        // the exact stored conditional at t = 1.7
var MAG0 = 0.125;                        // fieldScrubMag(0) = ONE existing field step
var NEUTRAL = '{"channel_bias":[0,0],"unit_bias":{},"track_role_bias":[],"region_add":[0,0,0]}';
function payloadOf(bias){
  var p = fieldBiasPayload({ bias: bias });
  return JSON.stringify({ channel_bias:p.channel_bias, unit_bias:p.unit_bias,
                          track_role_bias:p.track_role_bias, region_add:p.region_add });
}
"""


def _driver(body: str) -> str:
    return _field_block() + _tracks_block() + _FIXTURE + body


# ============================ WS-1 : mapping honesty =========================

def test_scrub_weights_are_the_exact_stored_mass_weighted_conditional():
    """w_r == normalize(sum_j m_j * q_j[r]) over the STORED slices containing t —
    nothing else. The BITE: a smoothed variant of the same numbers (the classic
    'just add a little uniform prior' patch) is computed alongside and must NOT be
    what the code returns."""
    assert _run_node(_driver("""
    var got = fieldScrubWeights(WM.tracks["7"].slices, 1.7, 3);
    if(got.sel.length !== 2){ console.log('FAIL nsel ' + got.sel.length); process.exit(1); }
    for(var r=0;r<3;r++){
      if(Math.abs(got.w[r] - W_EXPECT[r]) > 1e-12){
        console.log('FAIL exact ' + JSON.stringify(got.w)); process.exit(1); }
    }
    // the deliberate violation: 90% signal + 10% uniform. If the code ever smooths,
    // the exact assertion above fails; this proves the two are distinguishable.
    var smoothed = W_EXPECT.map(function(v){ return 0.9*v + 0.1/3; });
    if(JSON.stringify(got.w) === JSON.stringify(smoothed)){
      console.log('FAIL smoothed'); process.exit(1); }
    // a single-slice selection is that slice's stored q, verbatim (mass cancels).
    var one = fieldScrubWeights(WM.tracks["7"].slices, 2.7, 3);
    if(JSON.stringify(one.w) !== JSON.stringify([0.25, 0.75, 0])){
      console.log('FAIL single ' + JSON.stringify(one.w)); process.exit(1); }
    console.log('OK');
    """)) == "OK"


def test_scrub_window_is_the_stored_slice_grid_half_open():
    """The window IS the world's own unit segmentation: half-open [t0, t1), and a t in
    a GAP between stored spans selects nothing at all (no nearest-slice fallback, no
    invented grid)."""
    assert _run_node(_driver("""
    var s = WM.tracks["9"].slices;
    if(fieldSlicesAt(s, 0.0).length !== 1){ console.log('FAIL t0'); process.exit(1); }
    if(fieldSlicesAt(s, 4.0).length !== 0){ console.log('FAIL t1 open'); process.exit(1); }
    if(fieldSlicesAt(s, 9.0).length !== 0){ console.log('FAIL beyond'); process.exit(1); }
    // a GAP in track 7 ([2.5,3.0) ends the stored spans; 3.4 is a gap) -> no lean AT ALL,
    // not even a row lean: the pointer is not over stored material.
    if(fieldScrubBiasMap({ track:7, t:3.4, travel:0 }, WM, 3) !== null){
      console.log('FAIL gap'); process.exit(1); }
    // ... and a lane the wavemap does not carry contributes nothing either.
    if(fieldScrubBiasMap({ track:42, t:0.5, travel:0 }, WM, 3) !== null){
      console.log('FAIL unknown lane'); process.exit(1); }
    console.log('OK');
    """)) == "OK"


def test_zero_stored_role_mass_yields_no_cell_lean_not_a_uniform():
    """Honest disarm at the finest grain: a selection whose stored q carries no mass
    gets ZERO cell weights (and therefore no cell entries) — never a fabricated
    uniform 1/M."""
    assert _run_node(_driver("""
    var wm = { ok:true, M:3, tracks:{ "7":{ duration_s:1, peaks:[],
      slices:[[0.0, 1.0, 501, 0.0, [0,0,0]]] } } };
    var w = fieldScrubWeights(wm.tracks["7"].slices, 0.5, 3);
    if(JSON.stringify(w.w) !== JSON.stringify([0,0,0])){
      console.log('FAIL ' + JSON.stringify(w.w)); process.exit(1); }
    var leans = fieldScrubBiasMap({ track:7, t:0.5, travel:0 }, wm, 3);
    // the ROW lean still stands (the roll-up does not route through q); NO cell entries.
    if(JSON.stringify(Object.keys(leans)) !== JSON.stringify(['["track",7]'])){
      console.log('FAIL keys ' + JSON.stringify(Object.keys(leans))); process.exit(1); }
    console.log('OK');
    """)) == "OK"


# ============================ W-4 : same-jack ================================

def test_scrub_payload_equals_the_manual_grid_row_and_cell_payload():
    """THE law: scrub(i, t) emits exactly what the operator would get by leaning the
    GRID's row i and its role cells by the same numbers — same keys, same builder,
    byte-identical JSON. The BITE: a payload built with any other key shape (e.g. the
    unit grain) is shown to differ."""
    assert _run_node(_driver("""
    var scrub = { track:7, t:1.7, travel:0 };
    var scrubPayload = payloadOf(fieldMergeLeans({}, fieldScrubBiasMap(scrub, WM, 3)));

    // the MANUAL grid gesture: row 7 leaned by MAG0, then its (7, r) cells leaned by
    // MAG0 * w_r — through the SAME accumulator the wheel/drag handlers call.
    var manual = {};
    fieldAddBias(manual, fieldKeyStr(["track", 7]), MAG0);
    for(var r=0;r<3;r++){
      var v = MAG0 * W_EXPECT[r];
      if(v > 0) fieldAddBias(manual, fieldKeyStr(["role", 7, r]), v);
    }
    var manualPayload = payloadOf(manual);
    if(scrubPayload !== manualPayload){
      console.log('FAIL\\n  scrub  ' + scrubPayload + '\\n  manual ' + manualPayload);
      process.exit(1); }
    if(scrubPayload === NEUTRAL){ console.log('FAIL inert'); process.exit(1); }
    // and it really is the two sanctioned grains, nothing else.
    var p = JSON.parse(scrubPayload);
    if(JSON.stringify(p.channel_bias) !== JSON.stringify([MAG0, 0])){
      console.log('FAIL cb ' + JSON.stringify(p.channel_bias)); process.exit(1); }
    if(JSON.stringify(p.track_role_bias) !==
       JSON.stringify([[7,0,0.0625],[7,1,0.03125],[7,2,0.03125]])){
      console.log('FAIL tr ' + JSON.stringify(p.track_role_bias)); process.exit(1); }
    // the BITE: the unit grain (a uid-keyed lean) would be a DIFFERENT payload.
    var wrong = {}; fieldAddBias(wrong, fieldKeyStr(["unit", 0, 102, 7]), MAG0);
    if(payloadOf(wrong) === scrubPayload){ console.log('FAIL bite'); process.exit(1); }
    console.log('OK');
    """)) == "OK"


def test_scrub_never_emits_a_unit_grain_for_any_pointer_position():
    """NOT-A-PLAYHEAD / no-injection at the payload boundary: whatever the pointer does,
    unit_bias stays empty — a unit id never becomes a lean."""
    assert _run_node(_driver("""
    for(var t=0; t<3.0; t+=0.05){
      for(var tv=0; tv<=200; tv+=37){
        var m = fieldScrubBiasMap({ track:7, t:t, travel:tv }, WM, 3);
        if(!m) continue;
        for(var k in m){
          var key = JSON.parse(k);
          if(key[0] !== "track" && key[0] !== "role"){
            console.log('FAIL grain ' + k); process.exit(1); }
        }
        var p = JSON.parse(payloadOf(fieldMergeLeans({}, m)));
        if(JSON.stringify(p.unit_bias) !== "{}"){
          console.log('FAIL ub ' + JSON.stringify(p.unit_bias)); process.exit(1); }
      }
    }
    console.log('OK');
    """)) == "OK"


def test_scrub_magnitude_is_the_fields_own_step_and_saturation_law():
    """No new scaling constant enters the outbound path: pointer-down is ONE
    FIELD_BIAS_STEP, further travel steps by the EXISTING px quantum, and the whole
    thing soft-saturates at the EXISTING FIELD_BIAS_LIMIT (never a mute, never > 1)."""
    assert _run_node(_driver("""
    if(fieldScrubMag(0) !== FIELD_BIAS_STEP){ console.log('FAIL down'); process.exit(1); }
    if(fieldScrubMag(FIELD_TOUCH_BIAS_PX) !== 2*FIELD_BIAS_STEP){ console.log('FAIL one'); process.exit(1); }
    if(fieldScrubMag(-3*FIELD_TOUCH_BIAS_PX) !== 4*FIELD_BIAS_STEP){ console.log('FAIL abs'); process.exit(1); }
    if(fieldScrubMag(1e6) !== FIELD_BIAS_LIMIT){ console.log('FAIL sat'); process.exit(1); }
    // monotone, never above the limit, for any travel.
    var prev = 0;
    for(var px=0; px<4000; px+=7){
      var m = fieldScrubMag(px);
      if(m < prev - 1e-12 || m > FIELD_BIAS_LIMIT){ console.log('FAIL mono ' + px); process.exit(1); }
      prev = m;
    }
    // the ledger sum saturates through the SAME accumulator (a standing row lean plus
    // a scrub can never exceed the field's own stop).
    var base = {}; fieldAddBias(base, fieldKeyStr(["track", 7]), 0.95);
    var merged = fieldMergeLeans(base, fieldScrubBiasMap({track:7,t:1.7,travel:1e6}, WM, 3));
    if(merged['["track",7]'] !== FIELD_BIAS_LIMIT){
      console.log('FAIL merge sat ' + merged['["track",7]']); process.exit(1); }
    console.log('OK');
    """)) == "OK"


# ============================ WS-5 : switch-reset ============================

def test_view_switch_publishes_the_byte_identical_neutral_carrier():
    """V-1..V-3. Leans applied in one view (row + column + cell + a held scrub) are ALL
    zeroed by the switch, and the published payload is the neutral carrier byte-for-byte
    — the same object the engine byte-identity contract rests on. Switching back does
    not resurrect anything (including the sub-step wheel remainder)."""
    assert _run_node(_driver("""
    // --- in GRID view: bias a row, a column and a cell; hold a scrub as well.
    var bias = {};
    fieldAddBias(bias, fieldKeyStr(["track", 7]), 0.5);
    fieldAddBias(bias, fieldKeyStr(["role", 7, 1]), -0.25);
    fieldAddBias(bias, fieldKeyStr(["col", 2]), 0.75);
    var scrub = { track:9, t:1.0, travel:400 };
    var wheel = { key:'["track",7]', acc: 23 };
    var loaded = payloadOf(fieldMergeLeans(bias, fieldScrubBiasMap(scrub, WM, 3)));
    if(loaded === NEUTRAL){ console.log('FAIL precondition'); process.exit(1); }

    // --- SWITCH: the whole material-surface lean state goes neutral.
    var n = fieldNeutralLeanState();
    bias = n.bias; scrub = n.scrub; wheel = n.wheel;
    if(wheel.key !== null || wheel.acc !== 0){ console.log('FAIL wheel'); process.exit(1); }
    if(scrub !== null){ console.log('FAIL scrub'); process.exit(1); }
    var after = payloadOf(fieldMergeLeans(bias, fieldScrubBiasMap(scrub, WM, 3)));
    if(after !== NEUTRAL){ console.log('FAIL neutral ' + after); process.exit(1); }

    // --- SWITCH BACK: still neutral (no carry-over, no resurrection, no mapping).
    var n2 = fieldNeutralLeanState();
    bias = n2.bias; scrub = n2.scrub;
    var back = payloadOf(fieldMergeLeans(bias, fieldScrubBiasMap(scrub, WM, 3)));
    if(back !== NEUTRAL){ console.log('FAIL back ' + back); process.exit(1); }
    // the neutral carrier is the SAME object the empty-field contract pins.
    if(payloadOf({}) !== NEUTRAL){ console.log('FAIL pin'); process.exit(1); }
    console.log('OK');
    """)) == "OK"


def test_a_released_scrub_leaves_no_residue_in_the_ledger():
    """Held = sustained; release = exactly 0, instantly, with nothing left behind (the
    codebase's held-gesture release law; V-3 bans any fade). The persistent ledger is
    never mutated by a scrub — it is summed with it at publish time."""
    assert _run_node(_driver("""
    var bias = {};
    fieldAddBias(bias, fieldKeyStr(["track", 9]), 0.375);   // a standing GRID row lean
    var held = payloadOf(fieldMergeLeans(bias, fieldScrubBiasMap({track:7,t:0.5,travel:90}, WM, 3)));
    var released = payloadOf(fieldMergeLeans(bias, fieldScrubBiasMap(null, WM, 3)));
    if(held === released){ console.log('FAIL held==released'); process.exit(1); }
    // release returns EXACTLY to the standing grid lean — not a decayed version of it.
    if(released !== payloadOf(bias)){ console.log('FAIL residue ' + released); process.exit(1); }
    if(JSON.stringify(Object.keys(bias)) !== JSON.stringify(['["track",9]'])){
      console.log('FAIL mutated ' + JSON.stringify(bias)); process.exit(1); }
    // no scrub => the effective ledger IS the ledger (identity; the GRID path unchanged).
    if(fieldMergeLeans(bias, null) !== bias){ console.log('FAIL identity'); process.exit(1); }
    console.log('OK');
    """)) == "OK"


# ============================ WS-4 : wall respect ============================

def test_scrub_omits_the_lanes_the_grid_omits_and_never_rides_settlement():
    """The scrub inherits the grid's walls because it IS the grid's builder: a track
    absent from the channel roster takes no row lean (there is no slot to lean), and
    the scrub never touches the SETTLEMENT lane — region_add stays all-zero whether the
    region is armed or honestly disarmed (a moment's profile leaning the column is
    explicitly OUT of scope)."""
    assert _run_node(_driver("""
    // lane 7 is NOT in the channel roster -> the grid drops its row lean; so must the scrub.
    world = { channels:[{track_id:9}], M:3, regionCap:1, regionArmed:true };
    var leans = fieldScrubBiasMap({ track:7, t:1.7, travel:0 }, WM, 3);
    var scrubPayload = payloadOf(fieldMergeLeans({}, leans));
    var manual = {};
    fieldAddBias(manual, fieldKeyStr(["track", 7]), MAG0);
    for(var r=0;r<3;r++){ var v = MAG0*W_EXPECT[r]; if(v>0) fieldAddBias(manual, fieldKeyStr(["role",7,r]), v); }
    if(scrubPayload !== payloadOf(manual)){
      console.log('FAIL parity ' + scrubPayload); process.exit(1); }
    var p = JSON.parse(scrubPayload);
    if(JSON.stringify(p.channel_bias) !== JSON.stringify([0])){
      console.log('FAIL roster ' + JSON.stringify(p.channel_bias)); process.exit(1); }
    if(JSON.stringify(p.region_add) !== JSON.stringify([0,0,0])){
      console.log('FAIL region armed ' + JSON.stringify(p.region_add)); process.exit(1); }

    // region honestly DISARMED: identical scrub payload, settlement still untouched.
    world = { channels:[{track_id:7},{track_id:9}], M:3, regionCap:1, regionArmed:false };
    var q = JSON.parse(payloadOf(fieldMergeLeans({}, fieldScrubBiasMap({track:7,t:1.7,travel:0}, WM, 3))));
    if(JSON.stringify(q.region_add) !== JSON.stringify([0,0,0])){
      console.log('FAIL region disarmed ' + JSON.stringify(q.region_add)); process.exit(1); }
    if(JSON.stringify(q.channel_bias) !== JSON.stringify([MAG0, 0])){
      console.log('FAIL cb disarmed'); process.exit(1); }
    // the BITE: a COLUMN lean DOES ride settlement on an armed world — so the all-zero
    // region_add above is a real fact about the scrub, not an inert assertion.
    world = { channels:[{track_id:7}], M:3, regionCap:1, regionArmed:true };
    var col = {}; fieldAddBias(col, fieldKeyStr(["col", 1]), 0.5);
    if(JSON.parse(payloadOf(col)).region_add[1] === 0){ console.log('FAIL bite'); process.exit(1); }
    console.log('OK');
    """)) == "OK"


def test_scrub_arming_predicate_refuses_a_foreign_role_basis():
    """The projection basis is the WORLD's: a wavemap whose stored role count is not the
    world's M is refused outright (no remap, no truncation). Static wiring assertion on
    the arming predicate + the honest lane note."""
    src = _strip_comments(_js_functions(_tracks_runtime())["fieldScrubArmed"])
    assert "fieldWave" in src and "world.M" in src and "fieldWave.M" in src, \
        "the scrub must arm only on a wavemap whose role count IS the world's"
    assert "fieldViewMode(fieldView)" in src, "the scrub must be inert outside TRACKS view"
    note = _js_functions(_tracks_runtime())["fieldLanesNote"]
    assert "scrub inactive" in note and "unavailable" in note, \
        "a missing/mismatched wavemap must be reported honestly, not faked"


# ============================ W-1 : the row header ===========================

def test_lane_row_header_is_the_grids_row_square_verbatim():
    """One lane per track over the SAME roster, and each lane's row header is the GRID's
    row square — same kind, same key, same label, same telemetry glow — so the existing
    row-lean gesture produces the SAME channel_bias row value in either view."""
    assert _run_node(_driver("""
    var st = { nowplaying:{ 7:0.4, 9:0.9 }, nowplayingTrackRole:{}, nowplayingUnit:{},
               profiles:{ 7:[1,0,0], 9:[0,1,1] }, names:{ 7:"seven", 9:"nine" }, bias:{} };
    var lanes = fieldLanesPlace(st, 800, 400);
    var grid  = fieldGridPlace(st, 800, 400);
    var gridRows = grid.placed.filter(function(s){ return s.kind === "track"; });
    if(lanes.placed.length !== gridRows.length || lanes.lanes.length !== gridRows.length){
      console.log('FAIL count'); process.exit(1); }
    for(var i=0;i<gridRows.length;i++){
      var a = lanes.placed[i], b = gridRows[i];
      if(a.kind !== b.kind || fieldKeyStr(a.key) !== fieldKeyStr(b.key)
         || a.label !== b.label || a.settled !== b.settled || a.track !== b.track){
        console.log('FAIL row ' + i + ' ' + JSON.stringify([a, b])); process.exit(1); }
    }
    // the row header and the wave area do not overlap, and only the header is a square.
    for(var j=0;j<lanes.lanes.length;j++){
      var hr = lanes.placed[j].rect, wr = lanes.lanes[j].rect;
      if(wr.x < hr.x + hr.w){ console.log('FAIL overlap'); process.exit(1); }
      if(fieldLaneAt(lanes.lanes, hr.x + 1, hr.y + 1) !== null){
        console.log('FAIL header is not a scrub surface'); process.exit(1); }
    }
    // a row lean written by the EXISTING gesture shows up on the lane header ring.
    var bias = {}; fieldAddBias(bias, fieldKeyStr(["track", 9]), 0.25);
    st.bias = bias;
    var l2 = fieldLanesPlace(st, 800, 400);
    if(l2.placed[1].bias !== 0.25){ console.log('FAIL ring'); process.exit(1); }
    console.log('OK');
    """)) == "OK"


def test_lane_time_map_is_bounded_and_reversible():
    """The x<->time map addresses the STORED slice grid and nothing else: clamped to
    the lane, and round-tripping a stored boundary lands back on it."""
    assert _run_node(_driver("""
    var rect = { x:100, y:0, w:400, h:60 };
    if(fieldLaneTime(rect, 100, 10) !== 0){ console.log('FAIL t0'); process.exit(1); }
    if(fieldLaneTime(rect, 500, 10) !== 10){ console.log('FAIL t1'); process.exit(1); }
    if(fieldLaneTime(rect, -50, 10) !== 0){ console.log('FAIL clampL'); process.exit(1); }
    if(fieldLaneTime(rect, 9999, 10) !== 10){ console.log('FAIL clampR'); process.exit(1); }
    if(fieldLaneTime(rect, 200, 0) !== 0){ console.log('FAIL zero dur'); process.exit(1); }
    for(var t=0;t<=10;t+=0.25){
      var back = fieldLaneTime(rect, fieldLaneX(rect, t, 10), 10);
      if(Math.abs(back - t) > 1e-9){ console.log('FAIL roundtrip ' + t); process.exit(1); }
    }
    console.log('OK');
    """)) == "OK"


# ============================ V-4 + rollback =================================

def test_default_view_is_grid_and_only_the_exact_token_selects_tracks():
    assert _run_node(_driver("""
    if(fieldViewPick(null) !== "grid"){ console.log('FAIL null'); process.exit(1); }
    if(fieldViewPick("") !== "grid"){ console.log('FAIL empty'); process.exit(1); }
    if(fieldViewPick("TRACKS") !== "grid"){ console.log('FAIL case'); process.exit(1); }
    if(fieldViewPick("junk") !== "grid"){ console.log('FAIL junk'); process.exit(1); }
    if(fieldViewPick("tracks") !== "tracks"){ console.log('FAIL tracks'); process.exit(1); }
    if(fieldViewMode("tracks") !== "tracks"){ console.log('FAIL mode on'); process.exit(1); }
    if(fieldViewMode("grid") !== "grid"){ console.log('FAIL mode grid'); process.exit(1); }
    // ROLLBACK: the flag off pins the surface to GRID whatever the stored view says.
    FIELD_TRACKS_VIEW = false;
    if(fieldViewMode("tracks") !== "grid"){ console.log('FAIL rollback'); process.exit(1); }
    console.log('OK');
    """)) == "OK"


def test_flag_ships_on_and_gates_every_tracks_entry_point():
    js = _inline_js()
    assert re.search(r"var FIELD_TRACKS_VIEW\s*=\s*true;", js), \
        "FIELD_TRACKS_VIEW must exist and ship on"
    rt = _strip_comments(_tracks_runtime())
    # the tab control, the wavemap read and the scrub all gate on the flag.
    assert "if(fieldViewsEl) fieldViewsEl.hidden = !FIELD_TRACKS_VIEW" in rt, \
        "the tab pair must be hidden outright when the flag is off (pre-directive surface)"
    assert "FIELD_TRACKS_VIEW" in _js_functions(rt)["fieldWaveEnsure"], \
        "the wavemap read must not happen at all when the flag is off"
    assert "FIELD_TRACKS_VIEW" in _js_functions(rt)["fieldScrubArmed"], \
        "the scrub must not arm when the flag is off"
    assert "if(!FIELD_TRACKS_VIEW) v = \"grid\";" in _js_functions(rt)["fieldSetView"], \
        "the view switch must pin GRID when the flag is off"


def test_switch_handler_zeroes_every_lean_and_publishes_before_rendering():
    """The runtime half of V-1/V-2: the switch assigns the neutral lean state (ledger,
    scrub, wheel remainder), publishes through the ONE steer call, and touches no
    outboard/eigen/transport state."""
    body = _strip_comments(_js_functions(_tracks_runtime())["fieldSetView"])
    assert "fieldNeutralLeanState()" in body, "the switch must use the neutral lean state"
    for assigned in ("fieldBias = n.bias", "fieldScrub = n.scrub",
                     "fieldWheelBiasState = n.wheel"):
        assert assigned in body, f"the switch must zero {assigned!r}"
    assert "sendSteerNow();" in body, "the switch must publish the neutral carrier"
    assert body.index("fieldBias = n.bias") < body.index("sendSteerNow();"), \
        "the leans must be zeroed BEFORE the publish"
    # V-2: nothing outboard/eigen/transport is named by the switch.
    for banned in ("radial", "scalar", "outboard", "temperature", "startPlayback",
                   "stopPlayback", "state ="):
        assert banned not in body, f"a view switch must not touch {banned!r} (V-2)"
    # V-3: no fade/tween theater on the reset.
    for banned in ("setTimeout", "setInterval", "requestAnimationFrame", "ease", "tween",
                   "lerp"):
        assert banned not in body, f"the reset must be instant, not {banned!r} (V-3)"


# ============================ WS-7 : not a playhead ==========================

_PLAYHEAD_BANNED = (
    "new Audio", "Audio(", "audioCtx", "audio.", "AudioContext", "audioWorklet",
    ".play(", ".pause(", "currentTime", "seek", "playbackRate", "startPlayback",
    "pausePlayback", "stopPlayback", "resumePlayback", "streamLoop", "openTelemetry",
    "/api/play", "/api/pause", "/api/stop", "/api/stream", "/api/steer",
)


def test_scrub_path_has_no_audio_transport_or_seek_call():
    """NOT-A-PLAYHEAD, static half: the pointer's entire footprint is the bias payload.
    Neither the pure mapping nor the runtime handlers may reference an audio element,
    the transport, a stream, a seek or the steer ROUTE (they publish through the ONE
    existing call site, sendSteerNow)."""
    pure = _strip_comments(_tracks_block())
    rt = _strip_comments(_tracks_runtime())
    for banned in _PLAYHEAD_BANNED:
        assert banned not in pure, f"the scrub mapping must not reference {banned!r}"
        assert banned not in rt, f"the TRACKS runtime must not reference {banned!r}"
    # the pure mapping is pure: no DOM, no network, no storage, no telemetry writes.
    for banned in ("document", "window.", "fetch(", "XMLHttpRequest", "EventSource",
                   "localStorage", "fieldNowPlaying", "fieldSettled"):
        assert banned not in pure, f"the scrub mapping must not reference {banned!r}"
    # ... and no procedural art anywhere in the view (WEB-FAB).
    for banned in ("Math.random", "Math.sin", "Math.cos", "Math.tan"):
        assert banned not in pure and banned not in rt, \
            f"no fabricated signal in the TRACKS view ({banned})"


def test_no_unit_id_ever_leaves_the_scrub_path():
    """WS-8 at the FE boundary: unit ids exist in the view ONLY as READ keys of the
    achieved heatmap's telemetry lookup. No scrub function names or carries one, and
    the lean keys it builds are strictly the row and cell grains."""
    fns = _js_functions(_strip_comments(_tracks_block()))
    fns.update(_js_functions(_strip_comments(_tracks_runtime())))
    leans = fns["fieldScrubLeans"]
    assert '["track", tid | 0]' in leans and '["role", tid | 0, r]' in leans, \
        "the scrub's lean keys must be the row and cell grains"
    for grain in ("unit", "uid", "unit_id"):
        assert grain not in leans, f"a scrub lean must never name {grain!r}"
    for name in ("fieldScrubWeights", "fieldSlicesAt", "fieldScrubBiasMap",
                 "fieldScrubMag", "fieldScrubPoint", "fieldScrubStart",
                 "fieldScrubMove", "fieldScrubEnd", "fieldScrubPublish"):
        body = fns[name]
        for grain in ("unit_bias", "uid", "unit_id", "set_unit_bias"):
            assert grain not in body, f"{name} must not carry a unit id ({grain})"
    # the ONLY uid read in the whole view is the heatmap's telemetry lookup (W-3).
    assert "nowplayingUnit" in fns["fieldDrawHeat"], \
        "the heatmap must glow from the per-unit placement telemetry"
    for other in ("fieldDrawWave", "fieldDrawScrubMark", "fieldLanesNote"):
        assert "nowplayingUnit" not in fns[other], \
            f"{other} must not double as a second telemetry consumer"


def test_the_views_only_request_is_the_read_only_wavemap_get():
    """No unit id (nor anything else) travels from the pointer toward a POST: the view
    issues exactly ONE request, a bodyless GET of the read-only wavemap."""
    rt = _strip_comments(_tracks_runtime())
    fetches = re.findall(r"fetch\((.*?)\)", rt, re.S)
    assert len(fetches) == 1, f"the TRACKS view must issue exactly one request: {fetches}"
    assert fetches[0].strip() == '"/api/wavemap"', \
        f"the only request must be the bodyless wavemap GET, got {fetches[0]!r}"
    for banned in ("method:", "body:", 'method: "POST"', "POST"):
        assert banned not in rt, \
            f"the TRACKS view must issue no POST and no request body ({banned})"
    # the only JSON.stringify in the view is the local idempotence key — nothing is
    # serialised toward the network.
    assert re.findall(r"JSON\.stringify\((.*?)\)", rt) == ["m"], \
        "the TRACKS view must serialise nothing but its local dedupe key"


def test_scrub_publishes_only_through_the_single_steer_call_site():
    """WS-3: the scrub reaches the engine through the EXISTING single entry point
    (sendSteerNow -> the one /api/steer POST), never a second one."""
    fns = _js_functions(_strip_comments(_tracks_runtime()))
    for name in ("fieldScrubPublish", "fieldScrubEnd", "fieldSetView"):
        assert "sendSteerNow()" in fns[name], f"{name} must publish via sendSteerNow"
    for name in ("fieldScrubStart", "fieldScrubMove"):
        assert "fieldScrubPublish()" in fns[name], f"{name} must publish via the one path"
        assert "sendSteer(" not in fns[name], f"{name} must not bypass sendSteerNow"
    js = _strip_comments(_inline_js())
    assert js.count('fetch("/api/steer"') == 1, \
        "there must remain exactly ONE /api/steer call site"


# ============================ WS-6 : grid untouched ==========================

# sha256 of the extracted blocks at the pre-directive HEAD (worktree base commit
# 27a6fa8). The GRID's pure logic — hit-testing, bias accumulation, the payload
# builder, the disarm predicates — is a REGRESSION PIN: the TRACKS view is built
# strictly on top of it, so a single byte of drift here is a directive violation.
_GRID_PURE_SHA256 = "6b13968f7b540199e57d73108feb7a69dde59877e8f410f3c6d32d127d1ba31b"
_DISPLAY_PURE_SHA256 = "d2715e472b348de4dec0baaa0e7a5a37eeb6305367ef01c76589468c4afe44eb"


def test_grid_pure_logic_block_is_byte_identical_to_pre_directive():
    got = hashlib.sha256(_field_block().encode()).hexdigest()
    assert got == _GRID_PURE_SHA256, (
        "the GRID pure-logic block changed (WS-6). The TRACKS view must be built ON TOP "
        "of it — never by editing it. If a change is genuinely required it needs its own "
        f"pre-registration and a new pin. got={got}")


def test_field_display_pure_logic_block_is_byte_identical_to_pre_directive():
    got = hashlib.sha256(_display_block().encode()).hexdigest()
    assert got == _DISPLAY_PURE_SHA256, (
        "the FIELD DISPLAY pure-logic block changed; the TRACKS view reuses "
        f"fieldGridMinSize/fieldMarqueeShift as-is. got={got}")


def test_grid_gesture_handlers_are_unchanged_by_the_directive():
    """The grid's INPUT path is untouched: the wheel/touch handlers still accumulate on
    the raw ledger through fieldAddBias, and the scrub is nowhere in them."""
    fns = _js_functions(_strip_comments(_inline_js()))
    for name in ("fieldOnWheel", "fieldTouchMove"):
        body = fns[name]
        assert "fieldAddBias(fieldBias" in body, f"{name} must still write the raw ledger"
        assert "fieldScrub" not in body, f"{name} must not know about the scrub"
    # the scrub is transient by construction: it never mutates the persistent ledger.
    rt = _strip_comments(_tracks_runtime())
    assert "fieldAddBias(fieldBias" not in rt, \
        "the scrub must never bake itself into the persistent ledger"


def test_tracks_view_is_reachable_only_through_the_shared_draw_and_hittest():
    """One surface, one canvas, one hit-test: the view branches inside the EXISTING
    fieldDraw / fieldSquareAt / fieldFitCanvas, so there is no second input surface."""
    fns = _js_functions(_strip_comments(_inline_js()))
    assert 'fieldViewMode(fieldView) === "tracks"' in fns["fieldDraw"], \
        "fieldDraw must branch on the view (one canvas)"
    assert 'fieldViewMode(fieldView) === "tracks"' in fns["fieldSquareAt"], \
        "fieldSquareAt must branch on the view (one hit-test)"
    assert 'fieldViewMode(fieldView) === "tracks"' in fns["fieldFitCanvas"], \
        "fieldFitCanvas must branch on the view (one sizing law)"
    assert "fieldGridMinSize" in fns["fieldFitCanvas"], \
        "the lanes must reuse the existing min-size/scroll helper"


def test_the_tab_pair_is_in_the_surface_header_and_ships_default_grid():
    html = _INDEX.read_text()
    m = re.search(r'<div class="pad-head">(.*?)</div>', html, re.S)
    assert m, "the material-surface header is missing"
    head = m.group(1)
    assert 'id="fieldViews"' in head, "the tab pair must live in the surface header"
    assert re.search(r'id="fieldViewGrid"[^>]*aria-pressed="true"', head, re.S), \
        "GRID must be the shipped default (V-4)"
    assert re.search(r'id="fieldViewTracks"[^>]*aria-pressed="false"', head, re.S), \
        "TRACKS must not be pre-selected"
    assert ">Grid<" in head and ">Tracks<" in head, "the tab pair reads [GRID][TRACKS]"


def test_operator_copy_is_present_on_the_lane_view():
    """W-5, verbatim."""
    rt = _tracks_runtime()
    assert ("point at a part you love — the instrument leans toward what that part "
            "is made of") in rt, "the W-5 copy must appear on the TRACKS view"


# ============================ syntax ========================================

def test_node_check_on_every_extracted_script():
    for name, src in (("inline", _inline_js()),
                      ("field", _field_block()),
                      ("display", _display_block()),
                      ("tracks", _tracks_block()),
                      ("tracks-runtime", _tracks_runtime())):
        _node_check(src if name != "tracks-runtime" else src + "\n")
