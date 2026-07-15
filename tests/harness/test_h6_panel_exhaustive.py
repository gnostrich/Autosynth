"""H-6 — panel exhaustiveness + closed control surface (directive v1), and the
connector C-3 static law (control reaches the writer ONLY via the Layer-0 map).

Teeth (each proven non-vacuous where scanners are involved):
  (1) the built panel exposes EXACTLY six lanes + LEASH + COMMA + the jack set;
  (2) a seventh lane (or a third tolerance) makes construction FAIL;
  (3) the OSC message space is CLOSED at both ends: the panel can only send
      the three outbound addresses; the engine binds exactly those and emits
      only the inbound set;
  (4) tolerances are consumed by NOTHING (no writer/render/functional/engine-
      loop identifier); Stage-1 authority does not exist yet and cannot sneak;
  (5) C-3: ets.panel imports nothing writer/engine-side; ets.writer imports
      nothing panel/OSC/Qt-side; inside ets.engine no TiltTerms is constructed
      directly — the ONLY producer is ets.writer.tilt.layer0/untilted; and the
      writer's control parameter is exactly `tilt`.
"""
from __future__ import annotations
import ast
import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ETS = pathlib.Path(__file__).resolve().parents[2] / "ets"


def _sources(pkg: str):
    for p in sorted((ETS / pkg).rglob("*.py")):
        yield p, p.read_text()


def _imports(src: str) -> set:
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            base = ("." * n.level) + (n.module or "")
            mods.add(base)
            mods |= {base + "." + a.name for a in n.names}
    return mods


def _identifiers(src: str) -> set:
    out = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, ast.keyword) and n.arg:
            out.add(n.arg)
    return out


# --- (1)/(2) the built panel is exhaustive ------------------------------------

def _make_panel(n_anchors=2):
    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import Panel
    QApplication.instance() or QApplication([])
    return Panel(emitter=None, n_anchors=n_anchors)


def test_h6_panel_exposes_exactly_the_declared_controls():
    panel = _make_panel()
    assert set(panel.lane_control_ids) == {
        "region", "density", "continuity", "gauge", "novelty", "temperature"}
    assert len(panel.lane_control_ids) == 6
    assert set(panel.tolerance_control_ids) == {"leash", "comma"}
    # jack set: deprecated conflated drift + slide/loop pairs + eoc + novelty.
    assert set(panel._jacks) == {
        "drift_key", "drift_phase_feel", "drift_timbre",
        "slide_key", "slide_phase_feel", "slide_timbre",
        "loop_key", "loop_phase_feel", "loop_timbre",
        "eoc", "novelty_sat"}
    # comma reads 'inf' out of the box (shipped behavior unchanged).
    import math
    assert math.isinf(panel.tolerances.comma)
    from ets.panel.tolerances import display
    assert display(panel.tolerances.comma) == "inf"


def test_h6_a_seventh_lane_fails_construction(monkeypatch):
    import ets.panel.widget as Wdg
    from ets.panel.lanes import LaneSpec, LaneKind
    seventh = LaneSpec("swing", "SWING", LaneKind.DIRECTION, "phi_swing",
                       lo=-3.0, hi=3.0, default=0.0)
    monkeypatch.setattr(Wdg, "LANES", tuple(Wdg.LANES) + (seventh,))
    # construction refuses the seventh lane: the closed lane table (KeyError —
    # `spec()` refuses an id outside the six) or the exhaustiveness guard
    # (AssertionError) fires first, depending on where the intruder lands.
    with pytest.raises((AssertionError, KeyError)):
        _make_panel()


def test_h6_a_third_tolerance_fails_construction(monkeypatch):
    import ets.panel.widget as Wdg
    from ets.panel.tolerances import ToleranceSpec
    third = ToleranceSpec("slack", "SLACK", "extra tolerance", default=1.0)
    monkeypatch.setattr(Wdg, "TOLERANCES", tuple(Wdg.TOLERANCES) + (third,))
    with pytest.raises(AssertionError):
        _make_panel()


# --- (3) the OSC message space is closed at both ends -------------------------

def _send_addr_names(src: str) -> set:
    """The ADDR_* constant names used as first arg of any send_message call."""
    names = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "send_message" and n.args:
            a0 = n.args[0]
            if isinstance(a0, ast.Attribute):
                names.add(a0.attr)
            elif isinstance(a0, ast.Name):
                names.add(a0.id)
            else:
                names.add("<NON-CONSTANT-ADDRESS>")
    return names


def test_h6_panel_sends_only_the_outbound_space():
    from ets.panel import osc_schema as S
    out_names = set()
    for p, src in _sources("panel"):
        out_names |= _send_addr_names(src)
    assert "<NON-CONSTANT-ADDRESS>" not in out_names, \
        "panel sends to a non-schema (computed) OSC address"
    allowed = {"ADDR_LANES", "ADDR_TOLERANCES", "ADDR_HELLO"}
    assert out_names <= allowed, \
        f"panel sends outside the closed outbound space: {out_names - allowed}"
    # ...and the scanner bites on a rogue sender.
    rogue = "client.send_message('/ets/backdoor', [1])\n"
    assert _send_addr_names(rogue) == {"<NON-CONSTANT-ADDRESS>"}


def test_h6_engine_binds_exactly_the_outbound_space_and_emits_inbound_only():
    src = (ETS / "engine" / "osc_io.py").read_text()
    # dispatcher .map first-arg constants
    mapped = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "map" and n.args:
            a0 = n.args[0]
            if isinstance(a0, ast.Attribute):
                mapped.add(a0.attr)
    assert mapped == {"ADDR_LANES", "ADDR_TOLERANCES", "ADDR_HELLO"}, \
        f"engine binds a non-closed inbound set: {mapped}"
    sent = _send_addr_names(src)
    allowed = {"ADDR_WELCOME", "ADDR_CLOCK", "ADDR_METER_DRIFT",
               "ADDR_METER_EOC", "ADDR_METER_NOVELTY_SAT"}
    assert sent <= allowed, f"engine emits outside the inbound space: {sent}"
    # slide/loop emitters are DELIBERATELY absent (Stage-0 meters own them;
    # this engine must not fabricate their values).
    assert "ADDR_METER_SLIDE" not in sent and "ADDR_METER_LOOP" not in sent


# --- (4) tolerances have NO consumer ------------------------------------------

_TOL_TOKENS = ("leash", "comma", "toleran")


def _tol_hits(src: str) -> set:
    idents = {i.lower() for i in _identifiers(src)}
    return {t for t in _TOL_TOKENS for i in idents if t in i}


def test_h6_nothing_consumes_the_tolerances():
    for pkg in ("writer", "render", "functional", "geometry", "ingestion",
                "meters", "training"):
        for p, src in _sources(pkg):
            hits = _tol_hits(src)
            assert not hits, (
                f"{p}: tolerance identifier {hits} reached a downstream "
                "package — LEASH/COMMA are declared-only until Stage-1")
    # in the engine, only the OSC store/log layer may name them; the engine
    # LOOP (engine.py) and the writer call path must not.
    src = (ETS / "engine" / "engine.py").read_text()
    assert not _tol_hits(src), \
        "engine loop references tolerances — a consumer exists (forbidden)"
    # bite: a settle that reads comma is flagged.
    assert _tol_hits("def settle(O, comma):\n    return O * comma\n")


# --- (5) C-3: single entry via the Layer-0 map --------------------------------

def test_c3_panel_imports_no_writer_or_engine():
    forbidden = ("ets.writer", "ets.engine", "ets.functional", "ets.render")
    for p, src in _sources("panel"):
        mods = _imports(src)
        bad = {m for m in mods for f in forbidden if m.startswith(f)}
        assert not bad, f"{p}: panel imports writer/engine side: {bad}"


def test_c3_writer_imports_no_panel_osc_or_qt():
    forbidden = ("ets.panel", "pythonosc", "PySide6", "sounddevice")
    for p, src in _sources("writer"):
        mods = _imports(src)
        bad = {m for m in mods for f in forbidden if m.startswith(f)}
        assert not bad, f"{p}: writer imports control-surface tech: {bad}"


def test_c3_engine_constructs_tilt_only_via_layer0():
    """Inside ets.engine no TiltTerms is constructed directly: the only
    producers are ets.writer.tilt.layer0/untilted. Bites on a mutant."""
    def _direct_tilt_calls(src: str) -> int:
        n_calls = 0
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Call):
                f = n.func
                name = f.attr if isinstance(f, ast.Attribute) else \
                    (f.id if isinstance(f, ast.Name) else "")
                if name == "TiltTerms":
                    n_calls += 1
        return n_calls

    layer0_called = False
    for p, src in _sources("engine"):
        assert _direct_tilt_calls(src) == 0, (
            f"{p}: constructs TiltTerms directly — control must go through "
            "the Layer-0 map (λ=u/σ), the single derivation point (C-3)")
        if "layer0(" in src:
            layer0_called = True
    assert layer0_called, "the engine never calls the Layer-0 map"
    assert _direct_tilt_calls(
        "t = TiltTerms(lam_region=r, lam_density=0, lam_cont=0, "
        "lam_gauge=0, lam_novelty=0, T_s=1)\n") == 1, "C-3 scan is vacuous"


def test_c3_writer_control_parameter_is_exactly_tilt():
    import inspect
    from ets.writer import settle_tape, generate_batch
    from ets.writer.stream import StreamWriter
    lane_shaped = {"u", "u_region", "u_density", "u_continuity", "u_gauge",
                   "u_novelty", "lanes", "lane_vector", "knobs", "cc",
                   "leash", "comma"}
    for fn in (settle_tape, generate_batch, StreamWriter.write_bar):
        params = set(inspect.signature(fn).parameters)
        assert "tilt" in params, f"{fn.__qualname__} lost the tilt jack"
        assert not (params & lane_shaped), (
            f"{fn.__qualname__} grew a lane-shaped control parameter "
            f"{params & lane_shaped} — second control channel (I-1)")
