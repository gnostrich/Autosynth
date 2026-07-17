"""FIELD-INV — nothing reaches a rendered brightness without settlement.

The governing invariant: you push -> the engine re-settles -> the display shows
the ENGINE'S ANSWER. Three teeth, all proven to BITE:

  1. RUNTIME capability guard: the model's settled stores are writable only
     through the telemetry writer; any other caller RAISES.
  2. STATIC (AST) check: no input handler in field.py (wheel/mouse/gesture)
     names a settled-writing method.
  3. THE FIXTURE THAT MUST FAIL: an "echo" widget that pipes wheel input to
     brightness fails BOTH checks — the harness detects the forbidden pattern.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from tests.field.conftest import FakeWheelEvent, fed_model

# every name that can write settled/brightness state in the field module.
BRIGHTNESS_WRITERS = {
    "_ingest", "apply_roleactivity", "apply_nowplaying", "apply_profiles",
    "apply_unitpool", "telemetry_writer", "decay",
}
INPUT_HANDLERS = {
    "wheelEvent", "mousePressEvent", "mouseMoveEvent", "mouseReleaseEvent",
    "event", "_zoom_gesture",
}


def _called_names(fn_node: ast.AST):
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute):
                yield f.attr
            elif isinstance(f, ast.Name):
                yield f.id


def _input_handler_violations(source: str):
    """Names of brightness writers reachable from input handlers in `source` —
    TRANSITIVELY: a handler that delegates to a private helper (any function
    defined in the same source) which reaches a writer is flagged too, so the
    check cannot be dodged by one level of indirection (auditor note 2,
    2026-07-17). The shared static check is used both on the REAL module (must
    be empty) and on the echo fixtures (must be non-empty — proves it bites)."""
    tree = ast.parse(source)
    # call graph over every function/method defined in the source, by name.
    calls_of = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls_of.setdefault(node.name, set()).update(_called_names(node))

    def reachable_writers(fn: str, seen=None):
        seen = set() if seen is None else seen
        if fn in seen:
            return set()
        seen.add(fn)
        out = set()
        for called in calls_of.get(fn, ()):
            if called in BRIGHTNESS_WRITERS:
                out.add(called)
            if called in calls_of:                  # same-source helper: follow
                out |= reachable_writers(called, seen)
        return out

    bad = []
    for handler in INPUT_HANDLERS:
        if handler in calls_of:
            for w in sorted(reachable_writers(handler)):
                bad.append((handler, w))
    return bad


# --- 1. runtime capability guard --------------------------------------------

def test_settled_stores_reject_unauthorized_writes():
    from ets.instrument.field import FieldModel
    m = FieldModel()
    with pytest.raises(PermissionError):
        m._ingest("roleactivity", [1.0, 1.0])           # no token
    with pytest.raises(PermissionError):
        m._ingest("nowplaying", {0: 1.0}, token=object())   # forged token
    # and the writer cannot be forged either:
    from ets.instrument.field import FieldTelemetryWriter
    with pytest.raises(PermissionError):
        FieldTelemetryWriter(m, object())


def test_legitimate_writer_is_the_only_path():
    from ets.instrument.field import FieldModel
    m = FieldModel()
    m.telemetry_writer().apply_roleactivity([0.4, 0.6])
    assert [s.settled for s in m.role_squares_flat()] == [0.4, 0.6]


# --- 2. static check on the real module -------------------------------------

def test_no_input_handler_writes_brightness():
    import ets.instrument.field as field_mod
    src = inspect.getsource(field_mod)
    assert _input_handler_violations(src) == [], \
        "FIELD-INV violated: an input handler reaches a brightness writer"


def test_gesture_leaves_settled_state_untouched(qapp):
    """A scroll gesture on a live view changes BIAS (input ring) but not one
    settled value (fill) — the runtime half of the same claim."""
    from ets.instrument.field import FieldView
    m = fed_model()
    v = FieldView(m)
    v.resize(400, 300)
    before = [s.settled for s in v.current_squares()]
    keys = [s.key for s in v.current_squares()]
    v.wheelEvent(FakeWheelEvent(30, 60, notches=+3))
    v.wheelEvent(FakeWheelEvent(300, 60, notches=-2))
    after = [s.settled for s in v.current_squares()]
    assert after == before, "scroll input echoed into brightness"
    assert any(abs(m.bias_of(k)) > 0 for k in keys), \
        "the gesture should have accumulated BIAS (the input channel)"


# --- 3. the echo fixture MUST fail (prove the checks bite) -------------------

_ECHO_WIDGET_SRC = '''
class EchoField:
    """FORBIDDEN pattern: brightness = f(cursor/scroll input)."""
    def wheelEvent(self, ev):
        lvl = ev.angleDelta().y() / 120.0
        self.model.telemetry_writer().apply_roleactivity([lvl])   # echo!
'''


_LAUNDERED_ECHO_SRC = '''
class LaunderedEchoField:
    """FORBIDDEN pattern, hidden one call deep: handler -> helper -> writer."""
    def _apply(self, lvl):
        self.model.telemetry_writer().apply_roleactivity([lvl])   # echo!
    def wheelEvent(self, ev):
        self._apply(ev.angleDelta().y() / 120.0)
'''


def test_static_check_bites_on_echo_fixture():
    assert _input_handler_violations(_ECHO_WIDGET_SRC), \
        "the FIELD-INV static check failed to flag a direct input->brightness " \
        "echo — the check does not bite"


def test_static_check_bites_transitively_through_helpers():
    """Auditor note 2 (2026-07-17): the check must follow a handler that
    launders the write through a same-module helper."""
    assert _input_handler_violations(_LAUNDERED_ECHO_SRC), \
        "the FIELD-INV static check missed a handler->helper->writer chain"


def test_runtime_guard_bites_on_echo_without_capability():
    """The same echo attempted WITHOUT the writer capability (the only path a
    handler could reach, since handlers are never handed the writer) raises."""
    from ets.instrument.field import FieldModel
    m = fed_model()

    class EchoNoCapability:
        def wheelEvent(self, ev):
            m._ingest("roleactivity", [ev.angleDelta().y() / 120.0])

    with pytest.raises(PermissionError):
        EchoNoCapability().wheelEvent(FakeWheelEvent(10, 30, notches=2))
    assert isinstance(m, FieldModel)
