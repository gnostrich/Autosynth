"""ets.meters.contract — the slide[g]/loop[g] authority typing contract
(directive-v1 Feature 2 Stage 1, operator amendment
stage1-delete-conflated-jack).

Covers:
  (1) registration SHAPE enforcement (behavioural, both directions, proven
      to bite): a slide consumer must return float, never bool; a loop
      consumer must return bool.
  (2) the honest today-state: no live slide consumer exists (I-10 planner
      PENDING); exactly one live loop consumer, ``safe_to_end``.
  (3) the ACCEPTANCE fixture (veto-blocks-ending): the ending-veto rule is
      exactly "end permitted iff slide~0 AND (loop~0 OR reset discharged)".
"""
from __future__ import annotations
import pytest

from ets.meters import contract as C


# --------------------------------------------------------------------------
# (1) registration shape enforcement
# --------------------------------------------------------------------------

def test_register_slide_consumer_accepts_a_continuous_float_consumer():
    fn = lambda s: float(s) * 0.5          # a plausible tilt-lane lean
    c = C.register_slide_consumer(
        "test_lane_nudge", fn, canary_calls=[((0.0,), {}), ((1.0,), {})])
    assert c.name == "test_lane_nudge"
    assert C.SLIDE_CONSUMERS["test_lane_nudge"] is c
    del C.SLIDE_CONSUMERS["test_lane_nudge"]      # keep the registry clean


def test_register_slide_consumer_rejects_a_bool_output():
    """Non-vacuity: a slide consumer that returns a gate (bool) is REJECTED —
    slide[g] may only feed a continuous tilt-lane lean."""
    fn = lambda s: s > 0.0                 # WRONG: a gate, not a lean
    with pytest.raises(TypeError):
        C.register_slide_consumer(
            "bad_gate_from_slide", fn, canary_calls=[((0.5,), {})])
    assert "bad_gate_from_slide" not in C.SLIDE_CONSUMERS


def test_register_slide_consumer_rejects_a_plain_int_output():
    # ints are not floats either -- the contract wants a genuine continuous
    # value, and Python's numeric tower does not implicitly widen here.
    fn = lambda s: 1
    with pytest.raises(TypeError):
        C.register_slide_consumer(
            "bad_int_from_slide", fn, canary_calls=[((0.5,), {})])
    assert "bad_int_from_slide" not in C.SLIDE_CONSUMERS


def test_register_loop_consumer_accepts_a_bool_consumer():
    fn = lambda l: abs(l) < 1e-9
    c = C.register_loop_consumer(
        "test_comparator", fn, canary_calls=[((0.0,), {}), ((1.0,), {})])
    assert c.name == "test_comparator"
    assert C.LOOP_CONSUMERS["test_comparator"] is c
    del C.LOOP_CONSUMERS["test_comparator"]


def test_register_loop_consumer_rejects_a_float_output():
    """Non-vacuity: a loop consumer that returns a continuous value is
    REJECTED — loop[g] may only feed a comparator/veto/gate."""
    fn = lambda l: float(l) * 2.0          # WRONG: a lane-shaped lean
    with pytest.raises(TypeError):
        C.register_loop_consumer(
            "bad_lean_from_loop", fn, canary_calls=[((0.5,), {})])
    assert "bad_lean_from_loop" not in C.LOOP_CONSUMERS


def test_registration_requires_at_least_one_canary_call():
    with pytest.raises(ValueError):
        C.register_slide_consumer("empty", lambda s: float(s), canary_calls=[])
    with pytest.raises(ValueError):
        C.register_loop_consumer("empty", lambda l: bool(l), canary_calls=[])


# --------------------------------------------------------------------------
# (2) honest today-state
# --------------------------------------------------------------------------

def test_no_live_slide_consumer_exists_yet():
    """I-10 (thin external planner) is PENDING; no autopilot/steering code
    path exists anywhere in this tree (session consumer inventory). The
    registry is honestly empty, not papered over."""
    assert C.SLIDE_CONSUMERS == {}


def test_exactly_one_live_loop_consumer_the_ending_veto():
    assert set(C.LOOP_CONSUMERS) == {"safe_to_end"}
    assert C.LOOP_CONSUMERS["safe_to_end"].fn is C.safe_to_end


# --------------------------------------------------------------------------
# (3) ACCEPTANCE fixture — veto-blocks-ending
# --------------------------------------------------------------------------

def test_veto_blocks_ending_while_loop_nonzero():
    # slide~0, loop far from zero, no reset -> ending is VETOED.
    assert C.safe_to_end(0.0, 0.37, reset_discharged=False) is False


def test_ending_permitted_when_both_are_home():
    assert C.safe_to_end(0.0, 0.0, reset_discharged=False) is True


def test_ending_permitted_when_reset_just_discharged_loop():
    # a reset event just discharged loop -> the veto lifts even though the
    # raw loop reading is still nonzero.
    assert C.safe_to_end(0.0, 0.9, reset_discharged=True) is True


def test_slide_alone_also_vetoes_ending():
    # slide away from home vetoes ending even if loop already reads zero --
    # the rule is a conjunction, not an either/or.
    assert C.safe_to_end(0.5, 0.0, reset_discharged=False) is False


def test_veto_tolerance_boundary_is_inclusive():
    assert C.safe_to_end(1e-9, 1e-9, reset_discharged=False,
                         slide_tol=1e-9, loop_tol=1e-9) is True
    assert C.safe_to_end(1.01e-9, 0.0, reset_discharged=False,
                         slide_tol=1e-9, loop_tol=1e-9) is False
