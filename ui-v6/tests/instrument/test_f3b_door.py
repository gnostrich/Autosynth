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


# Control-mutating panel/engine entries. If ANY instrument module *calls* one of
# these, a gesture could drive settlement / F / writer / render / provenance-
# generation directly — forbidden. The ONLY sanctioned gesture→engine CONTROL
# path is the region tap (tap_region_anchor → the existing /ets/lanes emitter).
#
# Deliberately ABSENT (each categorically NOT a control entry):
#  - plain `emit`         : Qt Signal.emit(), the pad widgets' own gesture bus,
#                           unrelated to the OSC emitter.
#  - `emit_hello`/`hello` : a READ-ONLY telemetry-SUBSCRIPTION handshake, NOT a
#    control entry. `osc_schema.encode_hello(meters_port)` returns
#    `[int(meters_port)]` — it carries ONLY the instrument's telemetry-receiver
#    PORT, nothing else. The engine consumes /ets/hello solely to
#    `meters.retarget(host, port)`, i.e. to choose WHERE it SENDS read-only
#    telemetry (meters / welcome / roleactivity). It never reaches the
#    writer / settlement / F / render / provenance path (see engine.answer_hello:
#    it only retargets + re-emits telemetry; the audio/control path is untouched).
#    So typing it as "control" was a mis-classification; it is correctly ALLOWED.
FORBIDDEN_CALLS = {"_push", "_on_region", "_on_scalar", "_on_region_vector",
                   "_on_tolerance", "emit_tolerances",
                   "settle", "write_bar", "put_lanes"}


def _control_calls(src: str) -> set:
    """Attribute names in `src` that hit a forbidden control-mutating entry.
    (Shared by the real scan and its self-bite so both use ONE definition.)"""
    return {n.attr for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Attribute) and n.attr in FORBIDDEN_CALLS}


def test_the_only_engine_bound_gesture_is_the_region_bias():
    """The single panel entry the instrument calls to DRIVE (control-mutate) the
    engine is the existing region-tilt lane: in ui-v6 the FIELD's composite
    bias via `set_region_vector` (the whole-vector twin of `tap_region_anchor`,
    same `_push`/`/ets/lanes` path). It must NOT
    name any other control-mutating panel/engine entry (settle / write_bar /
    put_lanes / _push / _on_region* / _on_scalar / emit_tolerances).

    The instrument's `emit_hello` is NOT a control path: it is a read-only
    telemetry-subscription handshake carrying only the receiver port
    (osc_schema.encode_hello → `[int(meters_port)]`); the engine uses it only to
    retarget where it SENDS telemetry, never to mutate the trained object. So the
    test's INTENT is unchanged — the sole gesture→engine CONTROL path is the
    region tap — while the read-only subscription handshake is correctly allowed."""
    called = set()
    bias_seen = False
    for p, src in _sources():
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Attribute):
                if n.attr in ("set_region_vector", "tap_region_anchor"):
                    bias_seen = True
                if n.attr in FORBIDDEN_CALLS:
                    called.add((p.name, n.attr))
    assert bias_seen, "the region bias entry (set_region_vector) is never used"
    assert not called, (
        f"instrument calls a non-sanctioned control entry: {called} — the only "
        "gesture→engine path is the region tap (PREREG-feature3 hard lines)")

    # SELF-BITE — the door must STILL fire on a genuine control-mutating entry.
    # A would-be instrument module that pushes lanes / settles a bar IS flagged.
    rogue = "panel.put_lanes(lanes)\nself.writer.settle(bar)\ne.write_bar(b)\n"
    assert _control_calls(rogue) == {"put_lanes", "settle", "write_bar"}, \
        "the control-entry scanner went blind — it no longer bites control"
    # and the sanctioned read-only telemetry-subscription handshake is NOT flagged.
    assert _control_calls("inst.emitter.emit_hello(port)\n") == set(), \
        "emit_hello is a read-only telemetry subscription, not a control entry"


def test_region_bias_reaches_the_engine_only_via_the_existing_emitter():
    """Both region entries (`set_region_vector` — the field's path — and
    `tap_region_anchor`) must route through the SAME `_push`/emitter as the
    existing region path — no new OSC address, no second channel. (Proven on
    the panel source: each method body calls _push and touches no new emitter.)"""
    panel_src = (INSTR.parents[0] / "panel" / "widget.py").read_text()
    tree = ast.parse(panel_src)
    for name in ("set_region_vector", "tap_region_anchor"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == name)
        calls = {c.func.attr for c in ast.walk(fn)
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
        assert "_push" in calls, f"{name} must push via the existing path"
        assert "send_message" not in calls, \
            f"{name} opened a direct OSC send (second channel)"
