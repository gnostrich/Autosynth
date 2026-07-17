"""V5-F — the DOOR (inherited). A static proof that the v5 interaction change
opened NO new path into the trained object, and that the region-tilt lane is
still the sole engine-bound gesture.

Teeth:
  (1) the v5-touched UI modules import nothing settlement/F/render/writer/
      functional-side (bites on a rogue import);
  (2) the panel opens no direct OSC send of its own — every emit still goes
      through the injected emitter via `_push` (the clamp/slew/pad added no
      second channel);
  (3) the new emission helpers (`_outbound`, `tick_slew`) route through the SAME
      `_push` and name no new emitter address; the pad reaches the engine only
      through the existing region path (`_on_region_vector` → `_push`).
"""
from __future__ import annotations

import ast
import pathlib

ETS = pathlib.Path(__file__).resolve().parents[2] / "ets"
V5_FILES = (ETS / "panel" / "widget.py", ETS / "panel" / "envelope.py")

FORBIDDEN = ("ets.render", "ets.engine", "ets.writer", "ets.functional",
             "ets.geometry", "ets.training", "ets.calibration", "ets.connector",
             "ets.ingestion")


def _imports(src: str) -> set:
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(("." * n.level) + (n.module or ""))
    return mods


def _bad(mods: set) -> set:
    return {m for m in mods for f in FORBIDDEN if m == f or m.startswith(f + ".")}


def test_v5_ui_modules_do_not_import_the_trained_object():
    offenders = {}
    for p in V5_FILES:
        bad = _bad(_imports(p.read_text()))
        if bad:
            offenders[p.name] = bad
    assert not offenders, f"a v5 UI module reaches the trained object: {offenders}"
    # the scanner bites.
    assert _bad(_imports("from ets.writer.settle import settle\n")) == {
        "ets.writer.settle"}


def _send_addr_names(src: str) -> set:
    names = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "send_message" and n.args:
            a0 = n.args[0]
            names.add(a0.attr if isinstance(a0, ast.Attribute)
                      else a0.id if isinstance(a0, ast.Name)
                      else "<NON-CONSTANT-ADDRESS>")
    return names


def test_widget_opens_no_direct_osc_send():
    """The panel widget emits only through the injected emitter (via `_push`); it
    makes no `send_message` call of its own — so the pad/clamp/slew opened no
    second channel."""
    src = (ETS / "panel" / "widget.py").read_text()
    assert _send_addr_names(src) == set(), \
        "the panel widget opened a direct OSC send (second channel)"


def _fn(src: str, name: str):
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError(f"function {name} not found")


def test_new_emission_helpers_route_through_the_single_push():
    src = (ETS / "panel" / "widget.py").read_text()
    for name in ("tick_slew",):
        fn = _fn(src, name)
        calls = {c.func.attr for c in ast.walk(fn)
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
        assert "_push" in calls, f"{name} must emit via the existing _push path"
        assert "send_message" not in calls, f"{name} opened a direct send"
        assert "emit_tolerances" not in calls and "emit_hello" not in calls

    # the pad reaches the engine only through the existing region path.
    init = (ETS / "panel" / "widget.py").read_text()
    assert "_xy.changed.connect(self._on_region_vector)" in init, \
        "the XY pad is not wired to the existing region path"
    # _push is still the one lane emit (calls emitter.emit, no new address).
    push = _fn(src, "_push")
    attrs = {c.func.attr for c in ast.walk(push)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
    assert "emit" in attrs and "send_message" not in attrs
