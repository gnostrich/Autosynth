"""F3-B — the DOOR. A static (parse/import-graph) proof that no pad / transport /
cue / monitor code path reaches settlement, F, render, or provenance-generation,
EXCEPT pad tap/hold through the existing region-tilt lane.

The proof is by construction: if no module under ets/instrument imports any
trained-object package, then no monitor path can call into settlement/F/render/
provenance-generation — those symbols are not even reachable. The one sanctioned
exception is the region tap, which reaches the engine only through the panel's
existing region entry point (`tap_region_anchor` → the same /ets/lanes emitter),
never through a writer/render import. Each tooth is shown non-vacuous.
"""
from __future__ import annotations

import ast
import pathlib

INSTR = pathlib.Path(__file__).resolve().parents[2] / "ets" / "instrument"

# The trained object + its side channels. A monitor/display/tap path that imported
# ANY of these could reach settlement/F/render/provenance-generation.
FORBIDDEN = ("ets.render", "ets.engine", "ets.writer", "ets.functional",
             "ets.geometry", "ets.training", "ets.calibration", "ets.connector",
             "ets.meters", "ets.ingestion")


def _sources():
    for p in sorted(INSTR.rglob("*.py")):
        yield p, p.read_text()


def _imports(src: str) -> set:
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            base = ("." * n.level) + (n.module or "")
            mods.add(base)
    return mods


def _bad_imports(mods: set) -> set:
    return {m for m in mods for f in FORBIDDEN if m == f or m.startswith(f + ".")}


def test_no_instrument_module_imports_the_trained_object():
    offenders = {}
    for p, src in _sources():
        bad = _bad_imports(_imports(src))
        if bad:
            offenders[p.name] = bad
    assert not offenders, (
        "instrument code imports the trained object — a monitor path could "
        f"reach settlement/F/render/provenance-generation: {offenders}")


def test_the_scanner_bites_on_a_rogue_import():
    # a would-be monitor that imports the render path is caught.
    rogue = "from ets.render.render import render\nimport ets.writer as w\n"
    assert _bad_imports(_imports(rogue)) == {"ets.render.render", "ets.writer"}
    # and a clean monitor (only numpy / ets.panel / PySide6) is NOT flagged.
    clean = "import numpy as np\nfrom ets.panel.lanes import spec\n"
    assert _bad_imports(_imports(clean)) == set()


def test_the_only_engine_bound_gesture_is_the_region_tap():
    """The single panel entry the instrument calls to drive the engine is
    `tap_region_anchor` (the existing region-tilt lane). It must NOT name any
    other control-mutating panel entry (settle/emit/_push/_on_*)."""
    # NOTE: plain `emit` is deliberately absent — Qt Signal.emit() is the pad
    # widgets' own gesture bus, unrelated to the OSC emitter. We flag the panel's
    # control-mutating internals + the OSC emitter's tolerance send instead.
    forbidden_calls = {"_push", "_on_region", "_on_scalar", "_on_region_vector",
                       "_on_tolerance", "emit_tolerances", "emit_hello",
                       "settle", "write_bar", "put_lanes"}
    called = set()
    tap_seen = False
    for p, src in _sources():
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Attribute):
                if n.attr == "tap_region_anchor":
                    tap_seen = True
                if n.attr in forbidden_calls:
                    called.add((p.name, n.attr))
    assert tap_seen, "the region tap entry (tap_region_anchor) is never used"
    assert not called, (
        f"instrument calls a non-sanctioned control entry: {called} — the only "
        "gesture→engine path is the region tap (PREREG-feature3 hard lines)")


def test_region_tap_reaches_the_engine_only_via_the_existing_emitter():
    """`Panel.tap_region_anchor` must route through the SAME `_push`/emitter as
    the existing region path — no new OSC address, no second channel. (Proven on
    the panel source: the method body calls _push and touches no new emitter.)"""
    panel_src = (INSTR.parents[0] / "panel" / "widget.py").read_text()
    tree = ast.parse(panel_src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "tap_region_anchor")
    calls = {c.func.attr for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
    assert "_push" in calls, "tap_region_anchor must push via the existing path"
    # it must not open its own send_message / emitter address.
    assert "send_message" not in calls, \
        "tap_region_anchor opened a direct OSC send (second channel)"
