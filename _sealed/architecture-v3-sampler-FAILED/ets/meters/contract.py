"""Authority typing contract for the slide[g]/loop[g] meter pair (directive-v1
Feature 2 STAGE 1, operator amendment ``stage1-delete-conflated-jack``).

WHY THIS MODULE EXISTS. Stage 0 split one conflated DRIFT jack into two
distinct read-only meters: slide[g] (continuous frame-slide-from-home,
``ets.meters.gauge_slide``) and loop[g] (discrete committed-region curvature,
``ets.meters.gauge_loop``). Both remain read-only instruments (spec §9;
I-5/I-14 stand exactly as before — nothing here feeds an objective, gradient,
or settlement decision). This module types how a *decision* consumer (code
that turns a jack reading into an action, as opposed to a display/report --
those are already covered by I-5 and the panel's display-only structural
tests, and by the gauge-trace sidecar) is allowed to use each jack:

    slide[g]  ->  CONTINUOUS / TILT-LANE-SETTING consumers only.
                  A slide consumer is a function whose output is a genuine
                  ``float``: a continuous lane lean (spec §8) that would ride
                  the ONE tilt jack into the writer (I-1). slide never drives
                  a boolean/gate/veto directly.

    loop[g]   ->  DISCRETE / COMPARATOR + VETO + GATE consumers only.
                  A loop consumer is a function whose output is a genuine
                  ``bool``: a comparator/veto/gate that would act through a
                  CLAMP EVENT (spec §7, I-7 -- the only OTHER sanctioned
                  door; see the scope-guard note in REGISTRY
                  stage1-delete-conflated-jack, "the two sanctioned doors:
                  tilt lane, clamp events"). A loop-gate consumer MAY also
                  read a slide reading as a SUPPLEMENTARY precondition inside
                  the SAME gate -- the one Stage-1-specified example,
                  ``safe_to_end`` below, needs both slide~0 and loop~0-or-
                  discharged -- but the consumer's OUTPUT remains a single
                  bool feeding that one gate; slide is never separately
                  exposed as a lane input from inside it.

    NO THIRD KIND. Nothing outside these two output shapes may consume either
    jack for a decision. ``register_slide_consumer`` / ``register_loop_
    consumer`` enforce the shape at REGISTRATION time (every canary call's
    return value is type-checked; a wrong shape raises TypeError immediately,
    not at an audit years later). The paired structural sweep (H-5a,
    tests/harness/test_h5_authority_typing.py) walks the decision-adjacent
    packages (writer, engine, render, functional, planner) for any import of
    ``ets.meters.gauge_slide`` / ``ets.meters.gauge_loop`` that does not go
    through this module -- today there are ZERO such imports anywhere (see
    the session report's consumer inventory), so the sweep is a pure guard
    against a FUTURE unregistered/third consumer, proven non-vacuous against
    a planted fixture.

TODAY: NO LIVE CONSUMER OF EITHER JACK EXISTS. The thin external planner
(spec §10, I-10) is PENDING (not built); Feature-1's search for LEASH/COMMA's
"existing budget mechanic" found none (REGISTRY
feature1-engine-panel-2026-07-15); there is no autopilot, no live ending/
steering code path anywhere in this tree. ``SLIDE_CONSUMERS`` is therefore
EMPTY -- honestly, not papered over. ``LOOP_CONSUMERS`` holds exactly the one
entry the operator amendment specifies: ``safe_to_end``, the ending-veto
predicate. It is registered here as the CONTRACT itself, not as a live writer/
planner integration -- there is no ending code path anywhere yet to wire it
INTO; when the planner (I-10) lands, its ending decision must call this exact
function (or fail the H-5a sweep).

STAGE 2 DEFERRED (not decided here, per the amendment): HOW a "reset event"
(clamped-gauge-move-at-EOC) is detected, and how it discharges loop, is left
undecided. ``safe_to_end`` takes ``reset_discharged`` as a plain boolean
input and makes no claim about its origin.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Tuple

# A representative spread of canary inputs used to type-check a registrant's
# OWN declared canary calls (see ``register_slide_consumer`` docstring): the
# registrant supplies the argument tuples appropriate to its own signature,
# and every one of them is exercised before the consumer is trusted.
CanaryCall = Tuple[tuple, dict]


@dataclass(frozen=True)
class SlideConsumer:
    """A registered CONTINUOUS/tilt-lane-setting consumer of slide[g]."""
    name: str
    fn: Callable[..., float]


@dataclass(frozen=True)
class LoopConsumer:
    """A registered DISCRETE comparator/veto/gate consumer of loop[g]."""
    name: str
    fn: Callable[..., bool]


SLIDE_CONSUMERS: Dict[str, SlideConsumer] = {}
LOOP_CONSUMERS: Dict[str, LoopConsumer] = {}


def register_slide_consumer(name: str, fn: Callable[..., float],
                            canary_calls: Iterable[CanaryCall]) -> SlideConsumer:
    """Register a CONTINUOUS/tilt-lane-setting consumer of slide[g].

    ``canary_calls`` is an iterable of ``(args, kwargs)`` tuples the caller
    supplies, exercising a representative spread of its own signature; every
    call's return value must be a genuine ``float`` (bool is explicitly
    excluded -- ``bool`` is an ``int`` subclass in Python, so a gate smuggled
    in as 0.0/1.0 would otherwise slip past an ``isinstance(x, float)``
    check alone) or registration raises ``TypeError`` immediately."""
    calls = list(canary_calls)
    if not calls:
        raise ValueError(f"slide consumer {name!r}: no canary calls supplied "
                         "(a consumer must be exercised before registration)")
    for args, kwargs in calls:
        out = fn(*args, **kwargs)
        if isinstance(out, bool) or not isinstance(out, float):
            raise TypeError(
                f"slide consumer {name!r} returned {out!r} ({type(out)}), "
                "not a continuous float -- slide[g] may only feed a tilt-lane "
                "lean (directive-v1 Feature 2 Stage 1 typing contract)")
    c = SlideConsumer(name, fn)
    SLIDE_CONSUMERS[name] = c
    return c


def register_loop_consumer(name: str, fn: Callable[..., bool],
                           canary_calls: Iterable[CanaryCall]) -> LoopConsumer:
    """Register a DISCRETE comparator/veto/gate consumer of loop[g].

    Same canary-call discipline as ``register_slide_consumer``: every result
    must be a genuine ``bool`` or registration raises ``TypeError``."""
    calls = list(canary_calls)
    if not calls:
        raise ValueError(f"loop consumer {name!r}: no canary calls supplied "
                         "(a consumer must be exercised before registration)")
    for args, kwargs in calls:
        out = fn(*args, **kwargs)
        if not isinstance(out, bool):
            raise TypeError(
                f"loop consumer {name!r} returned {out!r} ({type(out)}), not "
                "a bool gate -- loop[g] may only feed a comparator/veto/gate "
                "(directive-v1 Feature 2 Stage 1 typing contract)")
    c = LoopConsumer(name, fn)
    LOOP_CONSUMERS[name] = c
    return c


def safe_to_end(slide_reading: float, loop_reading: float,
                reset_discharged: bool, *, slide_tol: float = 1e-9,
                loop_tol: float = 1e-9) -> bool:
    """THE ending-veto rule (directive-v1 Feature 2 Stage 1, operator
    amendment, verbatim): end permitted iff slide~0 AND (loop~0 OR a reset
    event just discharged it).

    ``slide_reading`` / ``loop_reading`` are a single already-computed jack
    reading (e.g. a bar's ``slide_phase`` charge and ``loop_g`` value); this
    function makes no claim about HOW they were produced, only about the
    veto logic once they are in hand. ``reset_discharged`` is an OPAQUE
    caller-supplied boolean: Stage 2 (what counts as "a reset event just
    discharged it", i.e. how a clamped-gauge-move-at-EOC is detected and
    causes discharge) is explicitly DEFERRED -- not decided in this stage.

    This predicate is a GATE (spec-typed: it would authorize a clamp event,
    the ending clamp, per I-7's single intervention species) and is the one
    Stage-1-specified consumer that legitimately reads BOTH jacks; it is
    registered below as the sole ``LOOP_CONSUMERS`` entry.
    """
    slide_ok = abs(float(slide_reading)) <= slide_tol
    loop_ok = abs(float(loop_reading)) <= loop_tol or bool(reset_discharged)
    return bool(slide_ok and loop_ok)


# The one Stage-1 typed consumer: canary calls spanning the four boundary
# combinations (slide near/away from home) x (loop near/away from zero) x
# (reset discharged True/False), proving the registration itself both works
# (every result really is a bool) and is exercised across the predicate's
# real decision boundaries before being trusted.
register_loop_consumer(
    "safe_to_end", safe_to_end,
    canary_calls=[
        ((0.0, 0.0, False), {}),
        ((0.0, 1.0, False), {}),
        ((1.0, 0.0, False), {}),
        ((0.0, 1.0, True), {}),
        ((1.0, 1.0, True), {}),
    ],
)
