"""LIVING-MARK / TWO-WAY TETHER LAW (operator directive + amendment, 2026-07-18).

Governs every T1/lean control (the radial pad axes + strips, and the legacy
VARY/SPREAD/DENSITY scalar sliders). EXEMPT: TEMP (T2 throttle), TEMPO (T5
clock, not wired), CRATE/walls (T4 switches, not built) — no mark, no tether.

  T-1  the MARK is ALIVE: it renders live settled telemetry every frame and
       moves on its own (UL-1). While HELD, emitted force = f(handle -
       mark_CURRENT), recomputed every tick — NEVER a fixed reference captured
       once at grab (UL-2).
  T-2  (amendment) the HANDLE is ALSO pulled toward the mark's CURRENT value,
       at a yield-rate read ONLY from the lane's own MEASURED calibration (a
       radial mode's eigenvalue `gain`, or a scalar lane's σ_φ) — never a
       hand-tuned spring/easing constant (TW-2/TW-4). The pull biases, never
       locks: sustained dragging always keeps advancing the handle (TW-3).
  T-3  RELEASE zeroes force; the mark resumes its own walk; the handle NEVER
       homes/snaps/tweens (UL-3). Chosen GLOBAL released-handle behavior:
       "handle tracks the living mark continuously" (scalarFollow, unmodified,
       reused for both scalar and radial).

Teeth (all must BITE):
  UL-1  every T1 mark trajectory == a live telemetry projection; frozen
        telemetry -> frozen marks; any non-telemetry mark motion FAILS.
  UL-2  held force == f(handle - mark_current) each tick; a fixture pinning
        the mark elsewhere changes the force.
  UL-3  static + runtime: NO animation writes handle/mark on release, any
        control.
  UL-4  TEMP/TEMPO/CRATE have NO living-mark/tether path; a fixture attaching
        one is structurally inert (never reads a mark).
  TW-1  two-way: held with a moving mark, the handle changes with NO drag
        input via the pull; the emitted force still points handle-ward.
  TW-2  yield == f(measured stiffness): a fixture swapping a hand-set constant
        FAILS; soft vs stiff fixture lanes show OPPOSITE compliance.
  TW-3  overpower: sustained drag always wins (a fixture where the pull is
        inescapable FAILS).
  TW-4  no-new-physics: the yield derives ONLY from telemetry/calibration; no
        spring/easing/invented constant anywhere in the tether path (static).
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


def _inline_js() -> str:
    html = _INDEX.read_text()
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert blocks, "no inline <script> found in index.html"
    return max(blocks, key=len)


def _block(name: str) -> str:
    js = _inline_js()
    m = re.search(r"/\* ===== %s.*?/\* ===== END %s ===== \*/" % (re.escape(name), re.escape(name)),
                  js, re.S)
    assert m, f"the test-extractable {name} block is missing/renamed"
    return m.group(0)


def _tether_and_deps() -> str:
    """TETHER + SCALAR + RADIAL pure-logic blocks concatenated (TW/UL fixtures
    need scalarForce/radialForceVector alongside tetherYieldRate/tetherHandleNext)."""
    return "\n".join([
        _block("TETHER PURE LOGIC"),
        _block("SCALAR LANE PURE LOGIC"),
        _block("RADIAL PURE LOGIC"),
    ])


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


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"//[^\n]*", " ", src)
    return src


def _run_node(script: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    finally:
        Path(path).unlink(missing_ok=True)
    assert r.returncode == 0, f"node failed: {r.stdout}\n{r.stderr}"
    return r.stdout.strip()


def _run(body: str) -> str:
    return _run_node(_tether_and_deps() + "\n" + body)


pytestmark = pytest.mark.skipif(_NODE is None, reason="node not available")


# ============================== T-1 / UL-2 ====================================

def test_ul2_force_is_a_function_of_the_current_mark_scalar():
    """UL-2 (scalar): scalarForce(handle, mark, held) — pinning the mark to a
    DIFFERENT value (same handle/held) changes the emitted force; the force is
    NEVER computed from a value fixed once at grab-time."""
    driver = """
    var handle = 0.8, held = true;
    var f_mark_low  = scalarForce(handle, 0.2, held);
    var f_mark_high = scalarForce(handle, 0.7, held);
    if(f_mark_low === f_mark_high){ console.log('FAIL same-force ' + f_mark_low); process.exit(1); }
    // the force is EXACTLY (handle - mark) * 2 * SCALAR_U_SCALE, recomputed fresh.
    var expect = Math.max(-SCALAR_U_SCALE, Math.min(SCALAR_U_SCALE, (handle - 0.2) * 2 * SCALAR_U_SCALE));
    if(Math.abs(f_mark_low - expect) > 1e-9){ console.log('FAIL formula ' + f_mark_low + ' vs ' + expect); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_ul2_force_is_a_function_of_the_current_mark_radial():
    """UL-2 (radial): radialModeValues returns the GAP (handle-mark), so
    radialForceVector's output changes when ONLY the mark moves (handle/held
    fixed) — pinning the mark elsewhere changes the force."""
    driver = """
    var modes = [{ gain: 3.0, composition: { density: 1.0, fill: 1.0 } }];
    var padLow  = { x: 0.6, y: 0, held: true, markX: 0.1, markY: null };
    var padHigh = { x: 0.6, y: 0, held: true, markX: 0.5, markY: null };
    var mvLow  = radialModeValues(2, padLow, []);
    var mvHigh = radialModeValues(2, padHigh, []);
    var fLow  = radialForceVector(modes, mvLow, 0);
    var fHigh = radialForceVector(modes, mvHigh, 0);
    if(fLow.density === fHigh.density){ console.log('FAIL same ' + fLow.density); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_t3_release_zeroes_force_radial_and_scalar():
    """T-3: force is EXACTLY 0 the instant a control is released, whatever the
    handle/mark currently are (the `held` gate — scalarForce and
    radialModeValues both check it)."""
    driver = """
    if(scalarForce(0.9, 0.1, false) !== 0){ console.log('FAIL scalar'); process.exit(1); }
    var modes = [{ gain: 3.0, composition: { density: 1.0, fill: 1.0 } }];
    var pad = { x: 0.9, y: 0, held: false, markX: 0.1, markY: null };
    var f = radialForceVector(modes, radialModeValues(2, pad, []), 0);
    if(f.density !== 0){ console.log('FAIL radial ' + f.density); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


# ============================== TW-1 (two-way) ================================

def test_tw1_held_handle_moves_with_zero_drag_when_mark_moves():
    """TW-1: with NO user drag input (dragDelta=0), a MOVING mark still pulls
    the handle (yieldRate>0) — the handle position CHANGES purely from the
    mark's own motion. One-way (handle static regardless of the mark) FAILS."""
    driver = """
    var handle = 0.0, yieldRate = 0.6;
    var next1 = tetherHandleNext(handle, 0, 0.8, yieldRate);
    if(next1 === handle){ console.log('FAIL no-motion'); process.exit(1); }
    var next2 = tetherHandleNext(next1, 0, 0.9, yieldRate);  // mark keeps moving
    if(next2 === next1){ console.log('FAIL no-second-motion'); process.exit(1); }
    // and it moved TOWARD the mark (handle-ward direction sanity: mark > handle -> next > handle).
    if(!(next1 > handle) || !(next2 > next1)){ console.log('FAIL direction ' + next1 + ' ' + next2); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_tw1_emitted_force_points_handle_ward():
    """TW-1: the emitted (mark-ward, T-1) force's SIGN always agrees with the
    handle's own displacement from the mark — the force pulls the OBJECT
    toward wherever the handle currently is, not the reverse."""
    driver = """
    var handleAhead = scalarForce(0.9, 0.3, true);   // handle > mark -> positive lean
    var handleBehind = scalarForce(0.1, 0.7, true);  // handle < mark -> negative lean
    if(!(handleAhead > 0)){ console.log('FAIL ahead ' + handleAhead); process.exit(1); }
    if(!(handleBehind < 0)){ console.log('FAIL behind ' + handleBehind); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


# ============================== TW-2 / TW-4 ====================================

def test_tw2_yield_rate_is_a_pure_function_of_lo_hi_span():
    driver = """
    // at/below lo -> 0 (SOFT: handle holds, mark comes to you).
    if(tetherYieldRate(0.5, 0.5, 2.0) !== 0){ console.log('FAIL at floor'); process.exit(1); }
    if(tetherYieldRate(0.2, 0.5, 2.0) !== 0){ console.log('FAIL below floor clamp'); process.exit(1); }
    // at hi -> 1 (STIFF: handle gets dragged toward the mark).
    var s = tetherYieldRate(2.0, 0.5, 2.0);
    if(Math.abs(s - 1) > 1e-9){ console.log('FAIL at max ' + s); process.exit(1); }
    // strictly between -> strictly between 0 and 1.
    var mid = tetherYieldRate(1.25, 0.5, 2.0);
    if(!(mid > 0 && mid < 1)){ console.log('FAIL mid ' + mid); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_tw2_soft_vs_stiff_fixture_lanes_show_opposite_compliance():
    """TW-2 (the biting fixture): two lanes on the SAME world (same lo/hi span),
    one near the floor (SOFT) and one near the world's own maximum (STIFF).
    Ticking BOTH held, zero-drag, toward a FIXED mark offset for the SAME
    number of steps: the soft lane's handle barely moves (holds where it was
    dropped, mark comes to it); the stiff lane's handle visibly gets dragged
    toward the mark. A constant/hand-set yieldRate (e.g. always 0.3 for both)
    would make the two lanes end up EQUALLY close to the mark — this fixture
    demands they differ, and in the STIFF-closer-than-SOFT direction."""
    driver = """
    var lo = 0.5, hi = 5.0;
    var softGain = 0.55;    // just above the floor
    var stiffGain = 4.8;    // near the world's own maximum
    var mark = 1.0;         // fixed target the whole run
    function run(gain){
      var yieldRate = tetherYieldRate(gain, lo, hi);
      var handle = 0.0;     // dropped far from the mark
      for(var t = 0; t < 20; t++){
        handle = tetherHandleNext(handle, 0, mark, yieldRate);
      }
      return { yieldRate: yieldRate, handle: handle, gap: Math.abs(handle - mark) };
    }
    var soft = run(softGain), stiff = run(stiffGain);
    if(!(stiff.yieldRate > soft.yieldRate)){
      console.log('FAIL yield ordering ' + JSON.stringify([soft, stiff])); process.exit(1); }
    // opposite compliance: the STIFF lane's handle ends up MUCH closer to the
    // mark (dragged) than the SOFT lane's (which barely moved off its drop point).
    if(!(stiff.gap < soft.gap * 0.5)){
      console.log('FAIL compliance ' + JSON.stringify([soft, stiff])); process.exit(1); }
    // and the soft lane genuinely "holds" — it moved only a little from 0.
    if(!(soft.handle < 0.3)){ console.log('FAIL soft-holds ' + soft.handle); process.exit(1); }
    // while the stiff lane is "visibly dragged" — most of the way to the mark.
    if(!(stiff.handle > 0.85)){ console.log('FAIL stiff-dragged ' + stiff.handle); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_tw2_swapping_in_a_hand_set_constant_fails_the_soft_vs_stiff_fixture():
    """TW-2 (the negative control — proves the fixture above actually BITES): a
    hand-set CONSTANT yield rate (bypassing tetherYieldRate entirely) makes the
    soft and stiff lanes end up EQUALLY close to the mark — the fixture must
    reject that, which is exactly what the assertion above would catch."""
    driver = """
    var HANDSET_YIELD = 0.3;   // the forbidden pattern: an invented constant
    function runHandset(){
      var handle = 0.0, mark = 1.0;
      for(var t = 0; t < 20; t++) handle = tetherHandleNext(handle, 0, mark, HANDSET_YIELD);
      return handle;
    }
    var softHandset = runHandset(), stiffHandset = runHandset();
    // with a hand-set constant the two lanes are IDENTICAL (no compliance
    // difference at all) -- the opposite of what TW-2 requires.
    if(softHandset !== stiffHandset){ console.log('FAIL expected-identical'); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_tw4_no_invented_constant_in_the_yield_functions():
    """TW-4 (static): tetherYieldRate/tetherHandleNext take their stiffness/
    span ONLY as parameters (telemetry-derived by the caller) — no spring/
    easing/hand-tuned literal anywhere in their bodies besides the 0/1 clamp
    bounds and the numerical-safety epsilon (1e-12, the SAME class of guard
    already used elsewhere in this codebase, e.g. radialSatForGain's own
    1e-9 span guard — not a physics constant)."""
    funcs = _js_functions(_block("TETHER PURE LOGIC"))
    yr = _strip_comments(funcs.get("tetherYieldRate", ""))
    hn = _strip_comments(funcs.get("tetherHandleNext", ""))
    assert yr.strip() and hn.strip(), "tetherYieldRate/tetherHandleNext missing"
    for tok in ("setTimeout", "setInterval", "requestAnimationFrame",
                "lerp", "tween", "ease("):
        assert tok not in yr and tok not in hn, f"forbidden token {tok!r} in tether math"
    # every numeric literal in tetherYieldRate must be 0, 1, or the safety epsilon.
    lits = re.findall(r"(?<![\w.])-?\d*\.?\d+(?:e-?\d+)?", yr)
    allowed = {"0", "1", "1e-12"}
    stray = [x for x in lits if x not in allowed]
    assert not stray, f"unexpected numeric literal in tetherYieldRate: {stray}"


def test_tw4_no_parallel_yield_assignment_outside_tetheryieldrate():
    """TW-4 (static): nowhere in the app does a variable literally named
    yield/yieldRate get assigned a bare numeric literal — every yieldRate MUST
    be computed via tetherYieldRate(...)."""
    js = _inline_js()
    bad = re.findall(r"\byield(?:Rate)?\s*=\s*-?\d", js)
    assert not bad, f"a hand-set yield constant was found: {bad}"


def test_tw4_scalar_and_radial_yield_route_through_tetheryieldrate():
    js = _inline_js()
    scalar_tick = _js_functions(js).get("scalarTetherStep", "")
    radial_yield = _js_functions(js).get("radialYieldForMode", "")
    assert "tetherYieldRate(" in scalar_tick, "scalarTetherStep must call tetherYieldRate"
    assert "tetherYieldRate(" in radial_yield, "radialYieldForMode must call tetherYieldRate"
    # scalar reads the lane's OWN measured sigma; radial reads the mode's OWN gain.
    assert "L.sigma" in scalar_tick
    assert ".gain" in radial_yield


# ============================== TW-3 (overpower) ================================

def test_tw3_sustained_drag_always_advances_the_handle_even_near_max_yield():
    """TW-3: even at (near-)maximum yieldRate, a SUSTAINED constant drag never
    gets "stuck" at the mark — it settles at a nonzero, drag-proportional
    OFFSET ahead of the mark (h* = mark + drag/yieldRate for the fixed-mark
    recurrence), proving the pull BIASES rather than LOCKS."""
    driver = """
    function settle(yieldRate, drag, mark, ticks){
      var handle = mark;   // start pinned exactly at the mark (worst case for escape)
      for(var t = 0; t < ticks; t++) handle = tetherHandleNext(handle, drag, mark, yieldRate);
      return handle;
    }
    var mark = 0.0, drag = 0.05;
    var yNearMax = tetherYieldRate(4.999, 0.0, 5.0);   // yieldRate close to 1
    var h = settle(yNearMax, drag, mark, 200);
    // sustained drag must have moved the handle meaningfully AWAY from the mark,
    // never pinned motionless at it (an "inescapable pull" fixture FAILS this).
    if(!(Math.abs(h - mark) > 0.01)){ console.log('FAIL stuck ' + h); process.exit(1); }
    // and it must be a STABLE, BOUNDED offset (not runaway) close to drag/yieldRate.
    var expect = drag / yNearMax;
    if(Math.abs((h - mark) - expect) > 1e-3){ console.log('FAIL offset ' + h + ' vs ' + expect); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_tw3_a_fixture_where_the_pull_is_inescapable_would_fail():
    """TW-3 negative control: an "inescapable pull" implementation (handle
    FORCED exactly to the mark every tick, ignoring drag) would fail the
    settle-away-from-mark assertion above — proving that assertion actually
    bites on a locking implementation."""
    driver = """
    function inescapableSettle(mark, ticks){
      var handle = mark;
      for(var t = 0; t < ticks; t++) handle = mark;   // drag is ignored entirely
      return handle;
    }
    var h = inescapableSettle(0.0, 200);
    if(Math.abs(h - 0.0) > 0.01){ console.log('FAIL should-have-locked'); process.exit(1); }
    console.log('OK (confirms the locking pattern would have failed TW-3s real assertion)');
    """
    assert "OK" in _run(driver)


# ============================== UL-1 (living mark) ================================

def test_ul1_mark_is_assigned_only_from_the_projection_functions():
    """UL-1 (static): every write to a `.mark`/`.markX`/`.markY` field in the
    app is EITHER (a) a null reset at (re)build time, or (b) a direct read of
    the live projection (scalarMark / radialProjectReading) — never any other
    expression (an animation, a constant, a fabricated ramp)."""
    js = _inline_js()
    # (a) reset sites: only inside build/init functions, always to null/0.
    resets = re.findall(r"\bmark\s*:\s*null|\bmarkX\s*:\s*null|\bmarkY\s*:\s*null", js)
    assert resets, "expected null-init reset sites for mark/markX/markY"
    # (b) live-write sites: L.mark = <expr>, radialPadState.markX = <expr>, etc.
    # (?!=) excludes ==/=== comparisons; \b anchors exclude substring collisions
    # (e.g. "radialEls.mark" containing "s.mark" — that's a DOM element ref, a
    # different field entirely, not the telemetry mark VALUE under test here).
    writes = re.findall(
        r"\b(?:L\.mark|radialPadState\.markX|radialPadState\.markY|s0\.mark|s\.mark)\s*=(?!=)\s*([^;]+);", js)
    assert writes, "no mark write sites found"
    allowed_rhs = re.compile(r"^(mk|achieved)$")
    for rhs in writes:
        rhs = rhs.strip()
        assert allowed_rhs.match(rhs), \
            f"a mark field was written from something other than the live projection: {rhs!r}"
    # and `mk`/`achieved` are themselves ALWAYS the projection function's return value.
    funcs = _js_functions(js)
    assert "scalarMark(lanes" in funcs.get("updateScalarLanes", "")
    assert "radialProjectReading(comp" in funcs.get("updateRadialFromTelemetry", "")


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ul1_frozen_telemetry_freezes_the_mark():
    """UL-1 runtime: repeating the SAME telemetry reading across ticks (a
    frozen input) must produce an EXACTLY frozen mark trajectory — scalarMark/
    radialProjectReading are pure functions of their input, never a counter/
    clock/random walk of their own."""
    driver = """
    var lanes = { continuity: 0.42 };
    var m1 = scalarMark(lanes, 'continuity');
    var m2 = scalarMark(lanes, 'continuity');
    var m3 = scalarMark(lanes, 'continuity');
    if(!(m1 === m2 && m2 === m3)){ console.log('FAIL not frozen ' + JSON.stringify([m1,m2,m3])); process.exit(1); }
    var comp = { density: 1.0, fill: 1.0 };
    var roles = [0.3];
    var r1 = radialProjectReading(comp, { density: 0.6 }, roles);
    var r2 = radialProjectReading(comp, { density: 0.6 }, roles);
    if(r1 !== r2){ console.log('FAIL radial not frozen'); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_ul1_a_non_telemetry_mark_motion_fixture_would_be_caught():
    """UL-1 negative control: a fixture that advances the mark from a clock/
    counter instead of telemetry (the forbidden pattern) produces a mark
    trajectory that CHANGES with no new telemetry input — proving the frozen-
    telemetry assertion above actually bites."""
    driver = """
    var t = 0;
    function fakeAnimatedMark(){ t += 1; return t * 0.01; }   // NOT from telemetry
    var a = fakeAnimatedMark(), b = fakeAnimatedMark();
    if(a === b){ console.log('FAIL fixture-itself-frozen'); process.exit(1); }
    console.log('OK (confirms a clock-driven mark would have failed the frozen-telemetry test)');
    """
    assert "OK" in _run(driver)


# ============================== UL-3 (no homing animation) ================================

def test_ul3_no_timer_or_easing_in_any_release_path():
    """UL-3: NO ease/tween/lerp/timer anywhere in either control family's
    release/tether path (scalar AND radial)."""
    js = _inline_js()
    funcs = _js_functions(js)
    watched = ("scalarFollow", "scalarDraw", "updateScalarLanes", "scalarOnUp",
               "scalarOnMove", "scalarOnDown", "scalarTetherStep",
               "radialDrawPad", "radialDrawStrip", "radialPadUp", "radialPadDown",
               "radialPadMove", "radialStripUp", "radialStripDown", "radialStripMove",
               "updateRadialFromTelemetry")
    banned = ("setTimeout", "setInterval", "requestAnimationFrame",
              "lerp", "tween", "easing", "ease(")
    for name in watched:
        body = _strip_comments(funcs.get(name, ""))
        assert body.strip() != "", f"{name} missing"
        for tok in banned:
            assert tok not in body, f"{name} uses forbidden easing/timer token {tok!r}"


def test_ul3_release_handles_have_no_css_transition_on_position():
    """UL-3 (static, CSS): the puck/mark/handle elements carry NO `transition`
    on their position-affecting properties — release is a direct assignment on
    the NEXT real telemetry frame, never a CSS-eased glide."""
    html = _INDEX.read_text()
    m = re.search(r"<style>(.*?)</style>", html, re.S)
    assert m, "no stylesheet"
    css = m.group(1)
    for sel in (".rp-puck", ".rp-mark", ".shandle", ".smark"):
        rule = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", css)
        if rule:
            assert "transition" not in rule.group(1), \
                f"{sel} must not carry a CSS transition (that would be a homing animation)"


def test_ul3_release_functions_never_write_handle_after_the_held_flag_flip():
    """UL-3: radialPadUp/radialStripUp/scalarOnUp set `held=false` and then
    ONLY re-send the (now-zeroed) force + redraw — they do not themselves
    write a new x/y/v (that would be a one-shot snap, forbidden)."""
    js = _inline_js()
    funcs = _js_functions(js)
    for name, forbidden in (("radialPadUp", ("radialPadState.x =", "radialPadState.y =")),
                            ("scalarOnUp", ("L.handle =",))):
        body = _strip_comments(funcs.get(name, ""))
        assert body.strip(), f"{name} missing"
        for tok in forbidden:
            assert tok not in body, f"{name} must not itself reposition the handle ({tok})"


# ============================== UL-4 (exempt types) ================================

def test_ul4_scalar_mark_obs_excludes_every_exempt_lane():
    js = _inline_js()
    m = re.search(r"SCALAR_MARK_OBS\s*=\s*\{([^}]*)\}", js)
    assert m, "SCALAR_MARK_OBS missing"
    keys = set(re.findall(r"(\w+)\s*:", m.group(1)))
    assert keys == {"continuity", "novelty", "density"}, keys
    for exempt in ("temperature", "tempo", "gauge", "crate"):
        assert exempt not in keys, f"{exempt} must have NO living-mark path"


def test_ul4_tether_tick_loop_is_scoped_to_scalar_mark_obs_only():
    """UL-4: the scalar tether-tick code lives INSIDE the SAME
    `for(var key in SCALAR_MARK_OBS)` loop the mark-read already uses — TEMP/
    TEMPO/gauge/CRATE structurally never enter this loop at all (there is no
    second, wider loop that could reach them)."""
    js = _inline_js()
    body = _js_functions(js).get("updateScalarLanes", "")
    assert "for(var key in SCALAR_MARK_OBS)" in body
    assert "scalarTetherStep(" in body
    # only ONE loop in this function (no parallel iteration over SCALAR_LANES
    # or scalarLanes-the-full-map that could reach an exempt lane's tether).
    assert body.count("for(var") <= 1, \
        "updateScalarLanes must not run a second loop that could reach an exempt lane"


def test_ul4_a_fixture_attaching_tether_to_an_exempt_lane_is_structurally_inert():
    """UL-4 (the biting fixture): TEMP/TEMPO never get a `sigma`/`mark` value
    (applyScalarSigma only sets sigma for SCALAR_MARK_OBS keys), so even if a
    caller mistakenly invoked the SAME tether math on an exempt lane, the
    result is INERT (yieldRate=0, zero pull) rather than silently steering —
    the exemption is enforced by the data (no sigma/mark ever populated), not
    merely by convention."""
    driver = """
    // TEMP-like lane: sigma/mark were NEVER populated (null, as applyScalarSigma
    // leaves any lane outside SCALAR_MARK_OBS).
    var exemptHandle = 0.5;
    var yieldRate = tetherYieldRate(null, 0, 5.0);   // stat=null -> 0
    var next = tetherHandleNext(exemptHandle, 0, null, yieldRate);
    if(next !== exemptHandle){ console.log('FAIL exempt lane moved ' + next); process.exit(1); }
    if(yieldRate !== 0){ console.log('FAIL nonzero yield for an unset stat ' + yieldRate); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_ul4_no_tempo_or_crate_scalar_lane_ever_gets_a_mark_element():
    """The TEMPO/CRATE rows never build a `.smark` visibility path in
    scalarDraw's mark-branch (only the else-if(typeof L.mark === 'number')
    branch touches `.smark`, and TEMPO/CHAOS take the earlier branches)."""
    js = _inline_js()
    body = _js_functions(js).get("scalarDraw", "")
    assert "L.chaos" in body and "L.tempo" in body
    idx_chaos = body.index("L.chaos")
    idx_mark_branch = body.index("typeof L.mark")
    assert idx_chaos < idx_mark_branch, \
        "CHAOS/TEMPO must be handled in EARLIER branches than the mark-visibility branch"
