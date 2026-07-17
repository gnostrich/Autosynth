"""WEB-FIELD harness — the companion's FIELD steer surface honors the same law the
desktop field does (ui-v6/tests/field/test_field_inv.py), at the honest web grain.

The FIELD replaces the role pads + XY vector pad in cloud/companion/static/index.html.
Governing invariant: you push -> the engine re-settles -> the display shows the
ENGINE'S ANSWER. Fill brightness = settled telemetry only, never the echoed input.

Teeth (all must BITE):
  WEB-FIELD-INV  no input handler writes the brightness store (static/structural on
                 the inline JS, TRANSITIVE through helpers); an echo fixture MUST fail.
  WEB-FIELD-B    bias soft-saturates at +-1; emitted region components <= the safe
                 envelope (pinned to SAFE_REGION_MAGNITUDE); full down-bias re-weights,
                 never mutes (runtime, via node on the extracted pure-logic block).
  WEB-FIELD-C    the JS participation-ratio equals anchors.effective_rank (value pin);
                 round(PR) >= 2 gates drill (atomic squares refuse).
  WEB-FIELD-D    the engine's settlement input stays a SINGLE call site (app.py
                 .set_region once); the FE adds no new /api/ endpoint, one /api/steer.
  WEB-FIELD-E    squares derive from telemetry roles (empty telemetry -> empty field);
                 no fabricated squares / cosmetic unit grid; no fabricated depth.
"""
from __future__ import annotations

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
    m = re.search(r"<script>(.*)</script>", html, re.S)
    assert m, "no inline <script> found in index.html"
    return m.group(1)


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


def _assigns_settled(body: str) -> bool:
    # a direct write to the fill store: `fieldSettled =` or `fieldSettled[..] =`
    # (but NOT `==` / `===`).
    return bool(re.search(r"fieldSettled\s*(?:\[[^\]]*\])?\s*=(?!=)", body))


# The brightness/fill writers in the field: the telemetry applier, plus any direct
# assignment to the fill store (caught structurally by _assigns_settled).
BRIGHTNESS_WRITERS = {"fieldApplySettled"}
INPUT_HANDLERS = {"fieldOnWheel", "fieldOnMove", "fieldZoom",
                  "fieldTouchStart", "fieldTouchMove"}


def _input_handler_violations(src: str):
    """Brightness writers reachable from any input handler in `src`, TRANSITIVELY
    through same-source helpers (mirrors ui-v6 test_field_inv._input_handler_
    violations). Returns a list of (handler, writer) offences — empty on the real
    module, non-empty on an echo fixture."""
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
            out.add("fieldSettled=")
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
    # the handlers must actually exist (guard against a rename silently passing).
    funcs = _js_functions(src)
    assert INPUT_HANDLERS <= set(funcs), \
        f"missing field input handlers: {INPUT_HANDLERS - set(funcs)}"
    assert "fieldApplySettled" in funcs, "the telemetry applier is missing"
    assert _input_handler_violations(src) == [], \
        "WEB-FIELD-INV violated: an input handler reaches the brightness store"


def test_field_inv_wheel_reaches_the_steer_post_not_the_fill():
    """The wheel handler MUST reach the steer POST (bias -> engine) and MUST NOT
    reach the fill store — the two halves of the same claim."""
    src = _inline_js()
    funcs = _js_functions(src)
    # transitively reachable calls from fieldOnWheel
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
    assert "fieldApplySettled" not in reach, "the wheel handler must not write the fill"


_ECHO_SRC = """
function echoWheel(ev){
  fieldApplySettled([ev.deltaY]);   // echo!
}
"""

_LAUNDERED_ECHO_SRC = """
function _echoApply(v){ fieldSettled = [v]; }   // echo, one call deep
function fieldOnWheel(ev){ _echoApply(ev.deltaY); }
"""


def test_field_inv_bites_on_direct_echo():
    # rename the echo handler to a known input handler so the checker inspects it.
    src = _ECHO_SRC.replace("echoWheel", "fieldOnWheel")
    assert _input_handler_violations(src), \
        "the WEB-FIELD-INV checker failed to flag a direct input->brightness echo"


def test_field_inv_bites_transitively_through_a_helper():
    assert _input_handler_violations(_LAUNDERED_ECHO_SRC), \
        "the WEB-FIELD-INV checker missed a handler->helper->fill-write chain"


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


# --- WEB-FIELD-B : soft saturation + envelope -------------------------------

def _envelope_cap() -> float:
    txt = _ENVELOPE.read_text()
    m = re.search(r"SAFE_REGION_MAGNITUDE\s*:\s*float\s*=\s*([0-9.]+)", txt)
    assert m, "could not read SAFE_REGION_MAGNITUDE from the engine envelope"
    return float(m.group(1))


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_field_b_soft_saturation_and_envelope():
    cap = _envelope_cap()
    driver = _pure_logic_block() + f"""
    var CAP = {cap};
    // FIELD_SAFE_MAG must be pinned to the engine's wire cap.
    if(FIELD_SAFE_MAG !== CAP){{ console.log('FAIL safe_mag ' + FIELD_SAFE_MAG); process.exit(1); }}
    var bias = [];
    // drive the wheel step far past the up-stop: must saturate at exactly +1.
    for(var k=0;k<40;k++) fieldAddBias(bias, 0, FIELD_BIAS_STEP);
    if(bias[0] !== FIELD_BIAS_LIMIT){{ console.log('FAIL up ' + bias[0]); process.exit(1); }}
    // and past the down-stop: exactly -1 (soft, finite — never -Infinity / a mute).
    for(var k=0;k<80;k++) fieldAddBias(bias, 0, -FIELD_BIAS_STEP);
    if(bias[0] !== -FIELD_BIAS_LIMIT){{ console.log('FAIL down ' + bias[0]); process.exit(1); }}
    if(!isFinite(bias[0])){{ console.log('FAIL nonfinite'); process.exit(1); }}
    // the emitted region components never exceed the safe envelope.
    var full = [1, -1, 1, -1, 1];
    var reg = fieldRegionVector(full, full.length);
    for(var i=0;i<reg.length;i++){{
      if(Math.abs(reg[i]) > CAP + 1e-9){{ console.log('FAIL envelope ' + reg[i]); process.exit(1); }}
    }}
    console.log('OK');
    """
    assert _run_node(driver) == "OK"


# --- WEB-FIELD-C : PR pinned to effective_rank, and the floor gate ----------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_field_c_pr_pinned_to_effective_rank():
    from ets.functional.anchors import effective_rank
    vecs = [[1.0, 1.0], [1.0, 0.0, 0.0], [0.5, 0.3, 0.2, 0.05],
            [2.0, 2.0, 2.0], [1.0]]
    # JS side
    calls = "".join(
        f"console.log(fieldParticipationRatio({v}));\n" for v in vecs)
    js_out = _run_node(_pure_logic_block() + "\n" + calls)
    js_vals = [float(x) for x in js_out.splitlines()]
    for v, js in zip(vecs, js_vals):
        # effective_rank of diag(v): eigenvalues are v (non-negative), so PR(v).
        want = float(effective_rank(np.diag(np.asarray(v, dtype=float))))
        assert abs(js - want) < 1e-6, f"PR drift on {v}: js={js} engine={want}"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_field_c_floor_gate_two_modes():
    driver = _pure_logic_block() + """
    var ok = fieldClearsFloor([1,1])            // 2 modes -> drill
      && !fieldClearsFloor([1,0,0])             // 1 mode  -> atomic
      && !fieldClearsFloor([])                  // empty   -> atomic (web wall)
      && !fieldClearsFloor([1]);                // single  -> atomic
    console.log(ok ? 'OK' : 'FAIL');
    """
    assert _run_node(driver) == "OK"


# --- WEB-FIELD-D : single settlement lane, no new endpoint ------------------

def test_field_d_single_set_region_call_site():
    # unchanged from the pre-field boundary: the engine's settlement input is
    # mutated by exactly ONE .set_region( call, inside /api/steer.
    src = _APP.read_text()
    assert src.count(".set_region(") == 1, "set_region must have exactly ONE call site"
    steer = src.index('"/api/steer"')
    call = src.index(".set_region(")
    play = src.index('"/api/play"')
    assert steer < call < play, "set_region must live inside /api/steer only"


def test_field_d_fe_adds_no_new_endpoint_one_steer():
    html = _INDEX.read_text()
    # every FE call target is same-origin /api/*, steer appears exactly once, and the
    # target set is within the endpoints the app already served (no new control lane).
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

def test_field_e_squares_derive_from_telemetry():
    js = _inline_js()
    funcs = _js_functions(js)
    # the fill store starts empty and its count is exactly the telemetry length.
    assert re.search(r"var\s+fieldSettled\s*=\s*\[\s*\]", js), \
        "fieldSettled must start empty (empty telemetry -> empty field)"
    assert "fieldSettled.length" in funcs.get("fieldCount", ""), \
        "the square count must be the telemetry length, not a fabricated roster"
    # the applier maps roles -> settled (the real telemetry frame).
    assert "roles.map" in funcs.get("fieldApplySettled", ""), \
        "fieldApplySettled must derive squares from the telemetry roles frame"


def test_field_e_no_fabricated_depth_or_unit_grid():
    html = _INDEX.read_text()
    js = _inline_js()
    # the old cosmetic drill overlay (36 fabricated units) is gone entirely.
    assert "unit-grid" not in html and "units = 36" not in js, \
        "the fabricated cosmetic unit grid must be removed"
    # sub-structure is empty by construction (no fabricated deeper squares).
    assert re.search(r"var\s+FIELD_SUBSTRUCTURE\s*=\s*\{\s*\}", js), \
        "FIELD_SUBSTRUCTURE must be empty — no fabricated per-role sub-feed"


def test_field_e_empty_roles_gives_empty_field():
    # runtime: fieldApplySettled([]) leaves the field empty; a real frame fills it.
    if _NODE is None:
        pytest.skip("node not available")
    js = _inline_js()
    funcs = _js_functions(js)
    # reconstruct a tiny testable shim from the real applier + count (no DOM).
    shim = (
        "var fieldSettled = [];\n"
        "function fieldDraw(){}\n"
        "function fieldCount(){" + funcs["fieldCount"] + "}\n"
        "function fieldApplySettled(roles){" + funcs["fieldApplySettled"] + "}\n"
        "fieldApplySettled([]);\n"
        "if(fieldCount() !== 0){ console.log('FAIL empty'); process.exit(1); }\n"
        "fieldApplySettled([0.2, 0.9, 0.0]);\n"
        "if(fieldCount() !== 3){ console.log('FAIL fill'); process.exit(1); }\n"
        "console.log('OK');\n"
    )
    assert _run_node(shim) == "OK"
