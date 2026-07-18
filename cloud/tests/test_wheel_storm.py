"""WHEEL STORM (OPEN_ENDS #21a) — one deliberate gesture = one action.

Operator report (desktop): fieldOnWheel acted once PER EVENT, so a trackpad
flick fired dozens of zoom steps (skipping the role layer straight to units)
and slammed bias toward the stop in one flick. The fix is DELTA ACCUMULATION
with named constants, on BOTH wheel gestures and on the touch pinch:

  ZOOM (Ctrl+wheel / pinch)  one zoom layer requires FIELD_ZOOM_STEP_DELTA of
      accumulated same-direction travel AND FIELD_ZOOM_COOLDOWN_MS since the
      last layer; storm events inside the cooldown are ABSORBED (and absorbed
      travel never counts toward the next layer). Direction change resets.
  BIAS (plain wheel)  deltaY is normalized across deltaModes (line/page -> px)
      and quantized at FIELD_WHEEL_BIAS_PX per bias step through the EXISTING
      fieldAddBias lane (same clamp/saturation, remainder kept like
      fieldDragSteps). A discrete mouse notch (~100-120px) lands 2-3 steps.

All step arithmetic is in the test-extractable FIELD PURE LOGIC block and is
driven here in node; the wiring checks are static reads of the handlers.
"""
from __future__ import annotations

import json
import re
import shutil

import pytest

from cloud.tests.test_web_field import (
    _inline_js,
    _input_handler_violations,
    _js_functions,
    _pure_logic_block,
    _reach,
    _run_node,
)

_NODE = shutil.which("node")


# ---- named constants: present, pinned to the operator's values ---------------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_constants_pinned():
    driver = _pure_logic_block() + """
    console.log(JSON.stringify([FIELD_WHEEL_BIAS_PX, FIELD_ZOOM_STEP_DELTA,
                                FIELD_ZOOM_COOLDOWN_MS, FIELD_WHEEL_LINE_PX,
                                FIELD_WHEEL_PAGE_PX]));
    """
    bias_px, zoom_delta, cooldown, line_px, page_px = json.loads(_run_node(driver))
    assert bias_px == 40, "one bias step per ~40px of normalized wheel travel"
    assert zoom_delta == 120, "one zoom layer per ~120px-equivalent of travel"
    assert cooldown == 350, "~350ms storm-absorption cooldown after a zoom layer"
    assert line_px > 0 and page_px > line_px


# ---- deltaMode normalization -------------------------------------------------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_wheel_px_normalizes_delta_modes():
    driver = _pure_logic_block() + """
    console.log(JSON.stringify([
      fieldWheelPx(100, 0),                       // pixel mode: passthrough
      fieldWheelPx(-3, 1),                        // line mode (Firefox notch = 3 lines)
      fieldWheelPx(1, 2),                         // page mode
      fieldWheelPx(0, 0)]));
    """
    px, line, page, zero = json.loads(_run_node(driver))
    assert px == 100
    assert line == -120, "a 3-line Firefox notch must equal a ~120px pixel notch"
    assert page == 800
    assert zero == 0


# ---- bias quantization: notch = 2-3 steps, remainder kept, same clamp lane ---

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_wheel_bias_notch_lands_two_to_three_steps():
    driver = _pure_logic_block() + """
    var a = fieldWheelSteps(100);     // Chrome notch: 2 steps + 20px remainder
    var b = fieldWheelSteps(120);     // 120px notch: exactly 3 steps
    var c = fieldWheelSteps(-100);    // downward notch mirrors
    var d = fieldWheelSteps(39);      // sub-threshold: no step, remainder kept
    console.log(JSON.stringify([a, b, c, d]));
    """
    a, b, c, d = json.loads(_run_node(driver))
    assert (a["steps"], a["rem"]) == (2, 20)
    assert (b["steps"], b["rem"]) == (3, 0)
    assert (c["steps"], c["rem"]) == (-2, -20)
    assert (d["steps"], d["rem"]) == (0, 39)


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_wheel_bias_remainder_accumulates_through_the_same_addbias_lane():
    # 3 notches of 100px consumed 25px at a time = exactly floor(300/40)=7 steps,
    # every step through fieldAddBias (the ONE clamp lane the touch drag uses too).
    driver = _pure_logic_block() + """
    var bias = {}, k = JSON.stringify(['role', 0]), acc = 0, steps = 0;
    for(var i = 0; i < 12; i++){
      acc += 25;
      var s = fieldWheelSteps(acc); acc = s.rem;
      if(s.steps){ steps += s.steps; fieldAddBias(bias, k, s.steps * FIELD_BIAS_STEP); }
    }
    console.log(JSON.stringify([steps, bias[k]]));
    """
    steps, bias = json.loads(_run_node(driver))
    assert steps == 7, "300px of accumulated travel must land floor(300/40)=7 steps"
    assert abs(bias - 7 * 0.125) < 1e-9, "steps must flow through fieldAddBias"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_drag_steps_and_wheel_steps_share_one_quantizer():
    # no parallel arithmetic: both are the SAME fieldStepQuant at different px.
    src = _pure_logic_block()
    funcs = _js_functions(src)
    assert "fieldStepQuant" in funcs["fieldDragSteps"]
    assert "fieldStepQuant" in funcs["fieldWheelSteps"]
    driver = src + """
    var a = fieldDragSteps(65), b = fieldWheelSteps(85);
    console.log(JSON.stringify([a.steps, a.rem, b.steps, b.rem]));
    """
    a_steps, a_rem, b_steps, b_rem = json.loads(_run_node(driver))
    assert (a_steps, a_rem) == (2, 5)      # 30px/step (touch), unchanged
    assert (b_steps, b_rem) == (2, 5)      # 40px/step (wheel)


# ---- the zoom gate: one gesture = one layer ---------------------------------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_zoom_gate_trackpad_flick_is_exactly_one_layer():
    # a flick storm: 40 events of 30px within 320ms. Un-gated this was ~10 layers
    # (root -> past units); gated it must be EXACTLY ONE.
    driver = _pure_logic_block() + """
    var st = { acc: 0, lastStepMs: -1e9 }, layers = 0;
    for(var i = 0; i < 40; i++){
      var g = fieldZoomGate(st, 30, i * 8);
      st = { acc: g.acc, lastStepMs: g.lastStepMs };
      layers += g.step;
    }
    console.log(layers);
    """
    assert _run_node(driver) == "1"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_zoom_gate_second_deliberate_gesture_after_cooldown():
    driver = _pure_logic_block() + """
    var st = { acc: 0, lastStepMs: -1e9 }, out = [];
    function feed(px, t){ var g = fieldZoomGate(st, px, t);
      st = { acc: g.acc, lastStepMs: g.lastStepMs }; return g.step; }
    out.push(feed(120, 0));          // gesture 1 -> one layer
    out.push(feed(120, 100));        // storm inside the cooldown -> absorbed
    out.push(feed(120, 500));        // deliberate gesture after cooldown -> one layer
    console.log(JSON.stringify(out));
    """
    assert json.loads(_run_node(driver)) == [1, 0, 1]


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_zoom_gate_direction_change_resets_the_accumulator():
    driver = _pure_logic_block() + """
    var st = { acc: 0, lastStepMs: -1e9 }, out = [];
    function feed(px, t){ var g = fieldZoomGate(st, px, t);
      st = { acc: g.acc, lastStepMs: g.lastStepMs }; return g.step; }
    out.push(feed(100, 0));          // toward IN, sub-threshold
    out.push(feed(-100, 10));        // direction change: reset, then -100 (sub)
    out.push(feed(-30, 20));         // -130 total -> one OUT layer
    console.log(JSON.stringify(out));
    """
    assert json.loads(_run_node(driver)) == [0, 0, -1]


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_zoom_gate_absorbed_storm_travel_never_counts_after_expiry():
    # travel absorbed DURING the cooldown must not be banked toward the next
    # layer: after expiry the accumulator restarts from zero.
    driver = _pure_logic_block() + """
    var st = { acc: 0, lastStepMs: -1e9 }, out = [];
    function feed(px, t){ var g = fieldZoomGate(st, px, t);
      st = { acc: g.acc, lastStepMs: g.lastStepMs }; return g.step; }
    out.push(feed(120, 0));          // layer 1 at t=0
    out.push(feed(60, 100));         // absorbed (cooldown)
    out.push(feed(60, 200));         // absorbed (cooldown)
    out.push(feed(60, 400));         // post-expiry: acc = 60 only -> NO layer
    out.push(feed(60, 410));         // acc = 120 -> layer 2
    console.log(JSON.stringify(out));
    """
    assert json.loads(_run_node(driver)) == [1, 0, 0, 0, 1]


# ---- wiring: both handlers run through the gate; per-event action is gone ----

def test_wheel_handler_uses_the_gate_and_normalizer_not_per_event_math():
    funcs = _js_functions(_inline_js())
    body = funcs["fieldOnWheel"]
    assert "fieldZoomGate" in body, "Ctrl+wheel zoom must run through fieldZoomGate"
    assert "fieldWheelSteps" in body, "plain-wheel bias must be quantized (fieldWheelSteps)"
    assert "fieldWheelPx" in body, "deltaY must be normalized across deltaModes"
    assert not re.search(r"deltaY\s*/\s*100", body), \
        "the per-event notches=-deltaY/100 math must be gone"


def test_pinch_zoom_uses_the_same_gate():
    funcs = _js_functions(_inline_js())
    assert "fieldZoomGate" in funcs["fieldTouchMove"], \
        "the two-finger pinch must run through the SAME fieldZoomGate discipline"
    assert "fieldPinchState" in funcs["fieldTouchStart"], \
        "a new pinch gesture must start with a clean accumulator"


def test_gate_helpers_keep_the_field_invariant():
    # the new helpers are reachable from input handlers — they must introduce no
    # path to a telemetry store/writer (the standing WEB-FIELD-INV checker).
    src = _inline_js()
    assert _input_handler_violations(src) == []
    # and the wheel still reaches the ONE steer lane through fieldAddBias.
    reach = _reach(src, "fieldOnWheel")
    assert "fieldAddBias" in reach and "sendSteer" in reach
