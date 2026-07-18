"""WEB-FIELD harness — the companion's FIELD steer surface honors the same law the
desktop field does (ui-v6/tests/field/test_field_inv.py), now at the FULL LADDER:
TRACK squares (root) -> the ROLES a track loads -> a role's UNIT pool (atomic).

The FIELD replaces the role pads + XY vector pad in cloud/companion/static/index.html.
Governing invariant: you push -> the engine re-settles -> the display shows the
ENGINE'S ANSWER. Fill brightness = settled telemetry only, never the echoed input.

Teeth (all must BITE):
  WEB-FIELD-INV  no input handler writes ANY telemetry-fed store (fieldSettled /
                 fieldNowPlaying / fieldProfiles / fieldUnitPools / fieldTrackNames),
                 TRANSITIVELY through helpers; an echo fixture MUST fail.
  WEB-FIELD-B    bias soft-saturates at +-1; the composite region vector (across all
                 grains, with overlap) never exceeds the safe envelope
                 (SAFE_REGION_MAGNITUDE); full down-bias re-weights, never mutes.
  WEB-FIELD-C    the JS participation-ratio equals anchors.effective_rank (value pin);
                 round(PR) >= 2 gates drill (atomic squares refuse).
  WEB-FIELD-D    the settlement inputs are the REGION lane PLUS the typed scalar
                 conjugate lanes (paper2 §2), EACH through its ONE setter, all inside
                 /api/steer — one endpoint, a richer force vector (the Phase-1A typing
                 table widened this from "region only"). The FE adds no new /api/
                 endpoint; /api/steer stays the single engine-control call.
  WEB-FIELD-E    every square/legend id comes from a telemetry/world payload (empty
                 payload -> empty field); the expanded view shows EXACTLY the real
                 child count (no padded/placeholder squares; empty cells not hit-able).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[2]
_INDEX = _ROOT / "cloud" / "companion" / "static" / "index.html"
_APP = _ROOT / "cloud" / "companion" / "app.py"
_ENVELOPE = _ROOT / "architecture-v6" / "ets" / "panel" / "envelope.py"

_NODE = shutil.which("node")


def _inline_js() -> str:
    html = _INDEX.read_text()
    # index.html carries more than one inline <script> (the ambient-chrome prism block
    # + the main app). Return the MAIN app script — the one holding the FIELD logic —
    # rather than a greedy span across both (which would swallow a literal </script>).
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert blocks, "no inline <script> found in index.html"
    for b in blocks:
        if "FIELD PURE LOGIC" in b:
            return b
    return max(blocks, key=len)


def _pure_logic_block() -> str:
    js = _inline_js()
    m = re.search(r"/\* ===== FIELD PURE LOGIC.*?/\* ===== END FIELD PURE LOGIC ===== \*/",
                  js, re.S)
    assert m, "the test-extractable FIELD PURE LOGIC block is missing/renamed"
    return m.group(0)


# ---- JS function-body extraction (brace matching) --------------------------

def _js_functions(src: str):
    """Map every `function NAME(...) { ... }` in `src` to its body text."""
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


def _called_names(body: str):
    return set(re.findall(r"([A-Za-z_$][\w$]*)\s*\(", body))


# every telemetry-fed store: a direct assignment to any of these from an input path
# would be a fill written from input (the exact FIELD-INV violation).
_STORE_RE = re.compile(
    r"(?:fieldSettled|fieldNowPlaying|fieldProfiles|fieldUnitPools|fieldTrackNames)"
    r"\s*(?:\[[^\]]*\])?\s*=(?!=)")


def _assigns_settled(body: str) -> bool:
    return bool(_STORE_RE.search(body))


# The fill/telemetry writers in the field: the two appliers (live frame + static
# world section), plus any direct assignment to a store (caught by _assigns_settled).
BRIGHTNESS_WRITERS = {"fieldApplySettled", "fieldApplyStatic"}
INPUT_HANDLERS = {"fieldOnWheel", "fieldOnMove", "fieldZoom", "fieldOnClick",
                  "fieldTouchStart", "fieldTouchMove", "fieldTouchEnd",
                  # mobile-UX chrome entry points (fullscreen snap ⛶/✕, the
                  # fullscreenchange collapse, the tutorial dismiss): user input
                  # too — none may reach a telemetry writer, transitively.
                  "fieldExpandToggle", "fieldExpandOpen", "fieldExpandClose",
                  "fieldOnFullscreenChange", "tutDismiss",
                  # the SCALAR FORCE LANE drag handlers (paper2 §2 conjugate
                  # controls): they DO reach the engine, but ONLY through the
                  # sanctioned scalar force path (sendSteerNow → sendSteer, the
                  # widened WEB-FIELD-D contract) — never a brightness/telemetry
                  # store. WEB-FIELD-INV proves that below.
                  "scalarOnDown", "scalarOnMove", "scalarOnUp"}


def _input_handler_violations(src: str):
    """Telemetry-store writers reachable from any input handler in `src`,
    TRANSITIVELY through same-source helpers (mirrors ui-v6 test_field_inv). Empty
    on the real module, non-empty on an echo fixture."""
    funcs = _js_functions(src)
    calls_of = {name: _called_names(body) for name, body in funcs.items()}

    def reachable(fn, seen=None):
        seen = set() if seen is None else seen
        if fn in seen:
            return set()
        seen.add(fn)
        out = set()
        body = funcs.get(fn, "")
        if _assigns_settled(body):
            out.add("store=")
        for called in calls_of.get(fn, ()):
            if called in BRIGHTNESS_WRITERS:
                out.add(called)
            if called in funcs:
                out |= reachable(called, seen)
        return out

    bad = []
    for h in INPUT_HANDLERS:
        if h in funcs:
            for w in sorted(reachable(h)):
                bad.append((h, w))
    return bad


# --- WEB-FIELD-INV : no input handler writes brightness ---------------------

def test_field_inv_no_input_handler_writes_brightness():
    src = _inline_js()
    funcs = _js_functions(src)
    assert INPUT_HANDLERS <= set(funcs), \
        f"missing field input handlers: {INPUT_HANDLERS - set(funcs)}"
    assert BRIGHTNESS_WRITERS <= set(funcs), \
        f"missing telemetry appliers: {BRIGHTNESS_WRITERS - set(funcs)}"
    assert _input_handler_violations(src) == [], \
        "WEB-FIELD-INV violated: an input handler reaches a telemetry store"


def test_field_inv_wheel_reaches_the_steer_post_not_the_fill():
    """The wheel handler MUST reach the steer POST (bias -> engine) and MUST NOT
    reach either telemetry applier — the two halves of the same claim."""
    src = _inline_js()
    funcs = _js_functions(src)
    seen, stack, reach = set(), ["fieldOnWheel"], set()
    while stack:
        fn = stack.pop()
        if fn in seen:
            continue
        seen.add(fn)
        for c in _called_names(funcs.get(fn, "")):
            reach.add(c)
            if c in funcs:
                stack.append(c)
    assert "sendSteer" in reach, "the wheel handler must route bias to /api/steer"
    assert not (reach & BRIGHTNESS_WRITERS), "the wheel handler must not write any fill"


def _reach(src, start):
    """All names reachable (transitively, same-source) from function `start`."""
    funcs = _js_functions(src)
    seen, stack, reach = set(), [start], set()
    while stack:
        fn = stack.pop()
        if fn in seen:
            continue
        seen.add(fn)
        for c in _called_names(funcs.get(fn, "")):
            reach.add(c)
            if c in funcs:
                stack.append(c)
    return reach


def test_field_inv_touch_drag_reaches_the_steer_post_not_the_fill():
    """MOBILE BIAS (one-finger vertical drag): the touch-move handler must reach the
    SAME steer POST the wheel uses (fieldAddBias -> sendSteer) and must not reach any
    telemetry applier — the touch lane is the wheel lane, not a second channel."""
    src = _inline_js()
    reach = _reach(src, "fieldTouchMove")
    assert "fieldAddBias" in reach, "touch drag must use the wheel's bias entry"
    assert "sendSteer" in reach, "touch drag must route bias to /api/steer"
    assert not (reach & BRIGHTNESS_WRITERS), "touch drag must not write any fill"


def test_touch_tap_never_zooms_in_and_synthetic_click_is_suppressed():
    """MOBILE TAP: touchend never drills IN (fieldZoomInto unreachable — a tap shows
    the tooltip only); the header tap-out affordance stays; and the click handler
    suppresses the touch-synthesized click so a tap cannot zoom through it."""
    src = _inline_js()
    funcs = _js_functions(src)
    reach = _reach(src, "fieldTouchEnd")
    assert "fieldZoomInto" not in reach, "a tap must NEVER zoom into a square"
    assert "fieldZoomOut" in reach, "the header tap = zoom-out affordance must stay"
    assert "sendSteer" not in reach and "fieldAddBias" not in reach, \
        "a tap must not emit anything"
    assert "fieldLastTouchEnd" in funcs.get("fieldOnClick", ""), \
        "fieldOnClick must suppress the synthetic click after a touch"
    assert "fieldLastTouchEnd" in funcs.get("fieldTouchEnd", ""), \
        "fieldTouchEnd must arm the synthetic-click suppressor"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_touch_drag_steps_pure():
    """~30px of vertical drag = one wheel-notch-equivalent bias step, through the
    SAME fieldAddBias clamp (saturating, never a mute)."""
    driver = _pure_logic_block() + """
    var a = fieldDragSteps(65);           // 2 steps + 5px remainder
    var b = fieldDragSteps(-35);          // -1 step + -5px remainder
    var c = fieldDragSteps(29);           // sub-threshold: no step yet
    if(a.steps !== 2 || Math.abs(a.rem - 5) > 1e-9){ console.log('FAIL a'); process.exit(1); }
    if(b.steps !== -1 || Math.abs(b.rem + 5) > 1e-9){ console.log('FAIL b'); process.exit(1); }
    if(c.steps !== 0 || c.rem !== 29){ console.log('FAIL c'); process.exit(1); }
    // a 90px upward drag consumed in 15px increments = exactly 3 bias steps
    var bias = {}, k = JSON.stringify(['role', 0]), acc = 0;
    for(var i=0;i<6;i++){
      acc += 15;
      var s = fieldDragSteps(acc); acc = s.rem;
      if(s.steps) fieldAddBias(bias, k, s.steps * FIELD_BIAS_STEP);
    }
    if(Math.abs(bias[k] - 3*FIELD_BIAS_STEP) > 1e-9){ console.log('FAIL acc ' + bias[k]); process.exit(1); }
    console.log('OK');
    """
    assert _run_node(driver) == "OK"


_ECHO_SRC = """
function echoWheel(ev){
  fieldApplySettled({roles:[ev.deltaY]});   // echo!
}
"""

_LAUNDERED_ECHO_SRC = """
function _echoApply(v){ fieldNowPlaying = {0:v}; }   // echo, one call deep
function fieldOnWheel(ev){ _echoApply(ev.deltaY); }
"""

_STATIC_ECHO_SRC = """
function fieldOnClick(ev){ fieldApplyStatic({profiles:{0:[ev.x]}}); }  // echo via static
"""


def test_field_inv_bites_on_direct_echo():
    src = _ECHO_SRC.replace("echoWheel", "fieldOnWheel")
    assert _input_handler_violations(src), \
        "the WEB-FIELD-INV checker failed to flag a direct input->brightness echo"


def test_field_inv_bites_transitively_through_a_helper():
    assert _input_handler_violations(_LAUNDERED_ECHO_SRC), \
        "the WEB-FIELD-INV checker missed a handler->helper->store-write chain"


def test_field_inv_bites_on_static_applier_from_input():
    assert _input_handler_violations(_STATIC_ECHO_SRC), \
        "the WEB-FIELD-INV checker missed a handler->fieldApplyStatic echo"


# --- node runtime helpers ---------------------------------------------------

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


def _run_tree(body: str) -> str:
    """Run a node driver with the extracted pure-ladder block in scope."""
    return _run_node(_pure_logic_block() + "\n" + body)


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_js_syntax_node_check():
    """A `node --check` pass on the whole inline script (syntax gate)."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(_inline_js())
        path = f.name
    try:
        r = subprocess.run([_NODE, "--check", path], capture_output=True, text=True)
    finally:
        Path(path).unlink(missing_ok=True)
    assert r.returncode == 0, r.stderr


# --- WEB-FIELD-B : soft saturation + envelope (composite, with overlap) -----

def _envelope_cap() -> float:
    txt = _ENVELOPE.read_text()
    m = re.search(r"SAFE_REGION_MAGNITUDE\s*:\s*float\s*=\s*([0-9.]+)", txt)
    assert m, "could not read SAFE_REGION_MAGNITUDE from the engine envelope"
    return float(m.group(1))


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_field_b_soft_saturation_and_envelope():
    cap = _envelope_cap()
    driver = _pure_logic_block() + f"""
    if(FIELD_SAFE_MAG !== {cap}){{ console.log('FAIL safe_mag ' + FIELD_SAFE_MAG); process.exit(1); }}
    var bias = {{}}, k = JSON.stringify(["role",0]);
    // drive the wheel step far past the up-stop: must saturate at exactly +1.
    for(var i=0;i<40;i++) fieldAddBias(bias, k, FIELD_BIAS_STEP);
    if(bias[k] !== FIELD_BIAS_LIMIT){{ console.log('FAIL up ' + bias[k]); process.exit(1); }}
    // and past the down-stop: exactly -1 (soft, finite — never -Infinity / a mute).
    for(var i=0;i<80;i++) fieldAddBias(bias, k, -FIELD_BIAS_STEP);
    if(bias[k] !== -FIELD_BIAS_LIMIT){{ console.log('FAIL down ' + bias[k]); process.exit(1); }}
    if(!isFinite(bias[k])){{ console.log('FAIL nonfinite'); process.exit(1); }}
    // composite across OVERLAPPING grains (a role axis AND a track profile that also
    // loads that axis) at full bias must still stay within the envelope everywhere.
    var st = {{ roleact:[0,0,0], nowplaying:{{}}, profiles:{{0:[1,0.8,0.2]}},
                unitPools:{{0:[{{unit_id:5, track_id:0, band:2,
                                 profile:[0.9,0.4,0.1]}}]}},
                names:{{}}, bias:{{}} }};
    // ALL THREE grains overlapping on the same axis at full bias
    // (auditor note 2: role + track + unit in one composite).
    st.bias[JSON.stringify(["role",0])]  = 1.0;
    st.bias[JSON.stringify(["track",0])] = 1.0;
    st.bias[JSON.stringify(["unit",0,5,0])] = 1.0;
    var reg = fieldRegionVector(st, 3);
    for(var i=0;i<reg.length;i++){{
      if(Math.abs(reg[i]) > {cap} + 1e-9){{ console.log('FAIL envelope ' + reg[i]); process.exit(1); }}
      if(!isFinite(reg[i])){{ console.log('FAIL nonfinite2'); process.exit(1); }}
    }}
    // the full down-stop is still a finite re-weight, never a mute.
    st.bias[JSON.stringify(["role",0])] = -1.0;
    var reg2 = fieldRegionVector(st, 3);
    for(var i=0;i<reg2.length;i++){{ if(!isFinite(reg2[i])){{ console.log('FAIL nonfinite3'); process.exit(1); }} }}
    console.log('OK');
    """
    assert _run_node(driver) == "OK"


# --- WEB-FIELD-C : PR pinned to effective_rank, and the floor gate ----------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_field_c_pr_pinned_to_effective_rank():
    from ets.functional.anchors import effective_rank
    vecs = [[1.0, 1.0], [1.0, 0.0, 0.0], [0.5, 0.3, 0.2, 0.05],
            [2.0, 2.0, 2.0], [1.0]]
    calls = "".join(
        f"console.log(fieldParticipationRatio({v}));\n" for v in vecs)
    js_out = _run_tree(calls)
    js_vals = [float(x) for x in js_out.splitlines()]
    for v, js in zip(vecs, js_vals):
        want = float(effective_rank(np.diag(np.asarray(v, dtype=float))))
        assert abs(js - want) < 1e-6, f"PR drift on {v}: js={js} engine={want}"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_field_c_floor_gate_two_modes():
    driver = _pure_logic_block() + """
    var ok = fieldClearsFloor([1,1])            // 2 modes -> drill
      && !fieldClearsFloor([1,0,0])             // 1 mode  -> atomic
      && !fieldClearsFloor([])                  // empty   -> atomic
      && !fieldClearsFloor([1]);                // single  -> atomic
    console.log(ok ? 'OK' : 'FAIL');
    """
    assert _run_node(driver) == "OK"


# --- WEB-FIELD-D : the typed settlement lanes, one endpoint, one setter each -

# The region lane + the five typed scalar conjugate lanes (paper2 §2). Each enters
# the engine through its ONE bridge setter (its ONE lane-vector datum), all inside
# /api/steer. This is the widened WEB-FIELD-D contract (Phase-1A typing table).
_SETTLEMENT_SETTERS = ("set_region", "set_continuity", "set_novelty",
                       "set_density", "set_gauge", "set_temperature")


def test_field_d_single_set_region_call_site():
    src = _APP.read_text()
    assert src.count(".set_region(") == 1, "set_region must have exactly ONE call site"
    steer = src.index('"/api/steer"')
    call = src.index(".set_region(")
    play = src.index('"/api/play"')
    assert steer < call < play, "set_region must live inside /api/steer only"


def test_field_d_typed_scalar_lanes_each_one_setter_inside_steer():
    """The widened settlement contract: region + the typed scalar lanes, each through
    its ONE setter, all inside /api/steer. Not 'region only' — the scalar force family
    is the conjugate-control lanes of paper2 §2 (T1/T2), routed like the desktop
    _push (one datum per lane). Exactly one call site per setter, and each lives
    between the /api/steer marker and the next handler (/api/play)."""
    src = _APP.read_text()
    steer = src.index('"/api/steer"')
    play = src.index('"/api/play"')
    for setter in _SETTLEMENT_SETTERS:
        call = "." + setter + "("
        assert src.count(call) == 1, f"{setter} must have exactly ONE call site"
        idx = src.index(call)
        assert steer < idx < play, f"{setter} must live inside /api/steer only"


def test_field_d_fe_adds_no_new_endpoint_one_steer():
    html = _INDEX.read_text()
    targets = re.findall(r'(?:fetch|EventSource)\(\s*["\'](/[^"\'?]*)', html)
    assert targets, "no API calls in the FE?"
    assert all(t.startswith("/api/") for t in targets), \
        [t for t in targets if not t.startswith("/api/")]
    assert targets.count("/api/steer") == 1, "steer must be the single engine-control call"
    ALLOWED = {"/api/health", "/api/status", "/api/world", "/api/explore",
               "/api/stream", "/api/telemetry", "/api/ingest", "/api/reset",
               "/api/steer", "/api/play", "/api/stop", "/api/share", "/api/open",
               "/api/train", "/api/auth"}
    extra = set(targets) - ALLOWED
    assert not extra, f"the field introduced new endpoint(s): {extra}"


# --- WEB-FIELD-E : no fabrication -------------------------------------------

def test_field_e_stores_start_empty_and_applier_shape():
    js = _inline_js()
    funcs = _js_functions(js)
    # every telemetry-fed store starts empty (empty payload -> empty field).
    assert re.search(r"var\s+fieldSettled\s*=\s*\[\s*\]", js), "fieldSettled must start []"
    for store in ("fieldNowPlaying", "fieldProfiles", "fieldUnitPools", "fieldTrackNames"):
        assert re.search(r"var\s+" + store + r"\s*=\s*\{\s*\}", js), \
            f"{store} must start empty {{}} (no fabricated roster)"
    # the live applier derives from the telemetry frame's roles; the static applier
    # derives from the world payload's sections. No other source of squares.
    assert "roles.map" in funcs.get("fieldApplySettled", ""), \
        "fieldApplySettled must derive fills from the telemetry roles frame"
    stat = funcs.get("fieldApplyStatic", "")
    assert "w.profiles" in stat and "w.unit_pools" in stat and "w.track_names" in stat, \
        "fieldApplyStatic must derive structure only from the /api/world payload"


def test_field_e_no_fabricated_grid_or_substructure():
    html = _INDEX.read_text()
    js = _inline_js()
    # the old cosmetic drill overlay (36 fabricated units) is gone entirely.
    assert "unit-grid" not in html and "units = 36" not in js, \
        "the fabricated cosmetic unit grid must be removed"
    # the placeholder empty-sub-feed hack is gone — real pools replace it.
    assert "FIELD_SUBSTRUCTURE" not in js, \
        "FIELD_SUBSTRUCTURE (fabricated empty sub-feed) must be gone — real pools now"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_field_e_empty_payload_empty_field():
    driver = _pure_logic_block() + """
    var empty = { roleact:[], nowplaying:{}, profiles:{}, unitPools:{}, names:{}, bias:{} };
    if(fieldCurrentSquares(empty, []).length !== 0){ console.log('FAIL empty'); process.exit(1); }
    if(fieldTrackSquares(empty).length !== 0){ console.log('FAIL tracks'); process.exit(1); }
    // roleact only (no profiles) -> the honest FLAT ROLE fallback, count == M.
    var rolesOnly = { roleact:[0.2,0.9,0.0], nowplaying:{}, profiles:{}, unitPools:{}, names:{}, bias:{} };
    var root = fieldCurrentSquares(rolesOnly, []);
    if(root.length !== 3){ console.log('FAIL flat ' + root.length); process.exit(1); }
    if(root[0].kind !== 'role'){ console.log('FAIL not role'); process.exit(1); }
    // profiles present -> root becomes TRACK squares.
    var withTracks = { roleact:[0.2,0.9], nowplaying:{0:0.5}, profiles:{0:[1,1]}, unitPools:{}, names:{}, bias:{} };
    var r2 = fieldCurrentSquares(withTracks, []);
    if(r2.length !== 1 || r2[0].kind !== 'track'){ console.log('FAIL track root'); process.exit(1); }
    console.log('OK');
    """
    assert _run_node(driver) == "OK"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_field_e_every_square_id_from_payload():
    driver = _pure_logic_block() + """
    var st = { roleact:[0.4,0.2,0.1],
               nowplaying:{0:0.9, 1:0.3},
               profiles:{0:[1,1,0], 1:[1,0,0]},
               unitPools:{0:[{unit_id:7,track_id:0,band:2,profile:[1,0,0]},
                             {unit_id:8,track_id:1,band:3,profile:[1,0,0]}]},
               names:{0:'kick.wav', 1:'demo track 1'}, bias:{} };
    var trackIds = {0:1,1:1};                 // from profiles + nowplaying payload
    // every track square id is a payload track id
    fieldTrackSquares(st).forEach(function(sq){
      if(!(sq.track in trackIds)){ console.log('FAIL track id ' + sq.track); process.exit(1); }
    });
    // drilling a track yields ROLE squares whose ids are < M (payload role axes)
    fieldRolesOfTrack(st, 0).forEach(function(sq){
      if(sq.key[0] !== 'role' || sq.key[1] < 0 || sq.key[1] >= 3){ console.log('FAIL role id'); process.exit(1); }
    });
    // drilling a role yields UNIT squares whose (uid,tid) come from the pool payload
    var pool = st.unitPools[0];
    fieldUnitSquares(st, 0).forEach(function(sq, i){
      if(sq.key[2] !== pool[i].unit_id || sq.key[3] !== pool[i].track_id){
        console.log('FAIL unit id'); process.exit(1); }
      if(sq.expandable){ console.log('FAIL unit not atomic'); process.exit(1); }
    });
    console.log('OK');
    """
    assert _run_node(driver) == "OK"


# --- full-ladder tree construction ------------------------------------------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ladder_track_expandability_by_pr():
    driver = _pure_logic_block() + """
    var st = { roleact:[0,0,0], nowplaying:{0:0.9},
               profiles:{0:[1,1,0],      // PR 2 -> expandable, 2 roles
                         1:[1,0,0],      // PR 1 -> atomic
                         2:[0.5,0.5,0.5]}, // PR 3 -> expandable, 3 roles
               unitPools:{}, names:{}, bias:{} };
    var out = {};
    fieldTrackSquares(st).forEach(function(sq){ out[sq.track] = [sq.expandable, sq.nChildren]; });
    console.log(JSON.stringify(out));
    """
    out = json.loads(_run_node(driver))
    assert out["0"] == [True, 2]
    assert out["1"] == [False, 0]
    assert out["2"] == [True, 3]


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ladder_roles_of_track_are_global_and_top_pr():
    driver = _pure_logic_block() + """
    // profile favours roles 2 and 0 (masses 0.9, 0.1, 1.0) -> PR ~ 2 -> top-2 roles {0,2}
    var st = { roleact:[0.1,0.5,0.7,0.0], nowplaying:{},
               profiles:{5:[0.1, 0.0, 1.0, 0.0]}, unitPools:{}, names:{}, bias:{} };
    var kids = fieldRolesOfTrack(st, 5).map(function(sq){ return sq.key[1]; });
    console.log(JSON.stringify(kids));
    """
    kids = json.loads(_run_node(driver))
    # PR([.1,0,1,0]) = (1.1^2)/(1.01) ~ 1.198 -> round 1 -> NOT expandable -> []
    assert kids == []


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ladder_role_unit_pool_exact_counts_and_atomicity():
    # for pool sizes 1..5: the expanded view shows EXACTLY the real child count,
    # units are atomic, and hit-testing every empty grid cell returns nothing.
    driver = _pure_logic_block() + """
    function unit(i){ return {unit_id:i, track_id:i%2, band:i, profile:[1,0]}; }
    var results = [];
    for(var size=1; size<=5; size++){
      var pool = []; for(var i=0;i<size;i++) pool.push(unit(i));
      var st = { roleact:[0.5,0.1], nowplaying:{0:0.4,1:0.2},
                 profiles:{}, unitPools:{0:pool}, names:{}, bias:{} };
      var units = fieldUnitSquares(st, 0);
      var atomic = units.every(function(u){ return u.expandable === false && u.kind === 'unit'; });
      var children = fieldChildren(st, ['role',0]).length;
      // hit-test: enumerate every grid cell centre; count real hits + empty cells.
      var g = fieldGrid(size), W = 400, H = 400;
      var cw = W/g.cols, ch = H/g.rows, hits = {}, empties = 0;
      for(var r=0;r<g.rows;r++) for(var c=0;c<g.cols;c++){
        var idx = fieldHitIndex(c*cw + cw/2, r*ch + ch/2, W, H, size);
        if(idx < 0) empties++; else hits[idx] = 1;
      }
      results.push([size, units.length, children, atomic, Object.keys(hits).length,
                    g.rows*g.cols - size, empties]);
    }
    console.log(JSON.stringify(results));
    """
    results = json.loads(_run_node(driver))
    for size, nunits, nchildren, atomic, nhits, empty_cells, empties in results:
        assert nunits == size, f"pool {size}: unitSquares={nunits}"
        assert nchildren == size, f"pool {size}: children={nchildren}"
        assert atomic is True, f"pool {size}: units not atomic"
        assert nhits == size, f"pool {size}: distinct hit cells={nhits}"
        # every padded (non-entity) grid cell returns nothing from hit-testing
        assert empties == empty_cells, f"pool {size}: empty cells {empties} != {empty_cells}"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ladder_marker_equals_expanded_count():
    # the ▸n affordance number equals the interactive square count the drill opens.
    driver = _pure_logic_block() + """
    function unit(i){ return {unit_id:i, track_id:0, band:i, profile:[1,0]}; }
    var pool = []; for(var i=0;i<3;i++) pool.push(unit(i));   // role 0 -> 3 units
    var st = { roleact:[0.5,0.1], nowplaying:{0:0.4},
               profiles:{0:[1,1]}, unitPools:{0:pool}, names:{}, bias:{} };
    var track = fieldTrackSquares(st)[0];
    var roleKids = fieldChildren(st, ['track', 0]);
    var role0 = fieldRoleSquare(st, 0);
    var unitKids = fieldChildren(st, ['role', 0]);
    console.log(JSON.stringify([track.nChildren, roleKids.length,
                                role0.nChildren, unitKids.length]));
    """
    tmark, tkids, rmark, rkids = json.loads(_run_node(driver))
    assert tmark == tkids, f"track ▸{tmark} != {tkids} role children"
    assert rmark == rkids == 3, f"role ▸{rmark} != {rkids} unit children"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ladder_bias_directions_per_grain():
    driver = _pure_logic_block() + """
    var st = { roleact:[0,0,0], nowplaying:{},
               profiles:{0:[0.5, 1.0, 0.0]},
               unitPools:{1:[{unit_id:2, track_id:0, band:0, profile:[0.0, 0.0, 2.0]}]},
               names:{}, bias:{} };
    var dRole  = fieldDirection(st, ['role', 1], 3);
    var dTrack = fieldDirection(st, ['track', 0], 3);
    var dUnit  = fieldDirection(st, ['unit', 1, 2, 0], 3);
    console.log(JSON.stringify([dRole, dTrack, dUnit]));
    """
    dRole, dTrack, dUnit = json.loads(_run_node(driver))
    assert dRole == [0.0, 1.0, 0.0], "role dir must be the unit axis e_r"
    assert dTrack == [0.5, 1.0, 0.0], "track dir must be its profile, peak-normalized"
    assert dUnit == [0.0, 0.0, 1.0], "unit dir must be its profile, peak-normalized"


# --- track legend (colour + honest name) ------------------------------------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_legend_entries_one_to_one_with_payload():
    driver = _pure_logic_block() + """
    var st = { roleact:[0.1], nowplaying:{5:0.4},
               profiles:{0:[1,1], 2:[1,0]},
               unitPools:{}, names:{0:'kick_drum_loop.wav', 2:'demo track 2'}, bias:{} };
    console.log(JSON.stringify(fieldLegendEntries(st)));
    """
    entries = json.loads(_run_node(driver))
    ids = [e["track"] for e in entries]
    # exactly the union of profiles + nowplaying ids, nothing invented
    assert ids == [0, 2, 5], ids
    by = {e["track"]: e["name"] for e in entries}
    assert by[0] == "kick_drum_loop.wav"       # real ingested name
    assert by[2] == "demo track 2"             # honest synthetic label
    assert by[5] == "track 5"                  # nowplaying-only, honest generic fallback


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_legend_trunc_middle_keeps_head_and_tail():
    driver = _pure_logic_block() + """
    console.log(fieldTruncMiddle('a_very_long_source_filename_take_2.wav', 20));
    console.log(fieldTruncMiddle('short.wav', 20));
    """
    long_out, short_out = _run_node(driver).splitlines()
    assert "…" in long_out and len(long_out) <= 20
    assert long_out.startswith("a_very") and long_out.endswith(".wav")
    assert short_out == "short.wav"            # under the limit -> untouched


# --- honest track-family colouring (role/unit squares vs the legend code) ----

def test_role_hue_inventor_is_gone():
    # the old fieldRoleColor invented hues (i*47 % 360) that collided with OTHER
    # tracks' legend colours — the operator misread a role square as another track.
    assert "fieldRoleColor" not in _inline_js(), \
        "fieldRoleColor (invented role hues) must be gone — family shades only"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_role_shades_stay_in_the_parent_tracks_family():
    driver = _pure_logic_block() + """
    // drilled into track 3 (stack carries it): every role shade keeps the PARENT
    // track's hue exactly — never a hue that belongs to another track.
    if(fieldParentTrack([['track',3],['role',1]]) !== 3){ console.log('FAIL parent'); process.exit(1); }
    if(fieldParentTrack([]) !== null){ console.log('FAIL root'); process.exit(1); }
    if(fieldParentTrack([['role',2]]) !== null){ console.log('FAIL roleonly'); process.exit(1); }
    var base = '#7CA8FF';                       // a track palette colour
    var hue = Math.round(fieldHexToHsl(base).h);
    var seen = {};
    for(var i=0;i<6;i++){
      var c = fieldFamilyShade(base, i);
      var m = c.match(/^hsl\\((\\d+),/);
      if(!m || parseInt(m[1],10) !== hue){ console.log('FAIL hue ' + c); process.exit(1); }
      seen[c] = 1;                              // shades must be distinguishable
    }
    if(Object.keys(seen).length < 4){ console.log('FAIL distinct'); process.exit(1); }
    console.log('OK');
    """
    assert _run_node(driver) == "OK"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_degraded_role_view_is_neutral_grey_not_track_like():
    driver = _pure_logic_block() + """
    // no track parent (the role-grain-only / degraded field): a NEUTRAL grey ramp,
    // zero saturation — colour never claims a track the payload didn't name.
    for(var i=0;i<8;i++){
      var c = fieldFamilyShade(null, i);
      if(c.indexOf('hsl(0,0%') !== 0){ console.log('FAIL grey ' + c); process.exit(1); }
    }
    console.log('OK');
    """
    assert _run_node(driver) == "OK"
