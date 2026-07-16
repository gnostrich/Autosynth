"""C-1 (connector) — knob→render bypass: same settled schedule + different u
⇒ bit-identical audio. The render APPLIES the settled schedule; no lane value
can reach it around the settlement (I-11's control-side face).

Teeth:
  (1) STRUCTURAL — ets.render imports nothing panel/engine/writer-side; the
      render signature is (schedule, sources) and the Schedule type carries no
      lane/tilt/knob field anywhere in its dtype or dataclass fields.
  (2) BEHAVIORAL, end-to-end through the REAL engine: two knob settings that
      the Layer-0 map proves settlement-equivalent (they differ only on a
      σ_φ=0-degenerate lane — the exact identity tilt) produce the SAME
      settled schedule and BIT-IDENTICAL audio, while a genuinely different
      lean changes the audio (non-vacuity: the pipeline is not constant)."""
from __future__ import annotations
import ast
import inspect
import json
import pathlib

import numpy as np
import pytest

ETS = pathlib.Path(__file__).resolve().parents[2] / "ets"


def test_c1_structural_render_is_u_blind():
    import ets.render.render as R
    import ets.render.schedule as SCH
    forbidden = ("ets.panel", "ets.engine", "ets.writer", "pythonosc")
    for mod in (R, SCH):
        src = inspect.getsource(mod)
        mods = set()
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Import):
                mods |= {a.name for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                mods.add(n.module or "")
        bad = {m for m in mods for f in forbidden if m and m.startswith(f)}
        assert not bad, f"{mod.__name__} imports control-side tech: {bad}"

    from ets.render.render import render
    assert list(inspect.signature(render).parameters) == ["schedule", "sources"]

    from ets.render.schedule import PLACEMENT_DTYPE, Schedule
    lane_words = ("lane", "tilt", "knob", "lean", "u_", "temperature")
    for name in PLACEMENT_DTYPE.names + tuple(
            Schedule.__dataclass_fields__):
        assert not any(w in name.lower() for w in lane_words), \
            f"schedule field {name!r} smuggles a control value into the render"


@pytest.fixture(scope="module")
def world_path(tmp_path_factory):
    from tests.harness.worldtools import write_synthetic_worldfile
    p = tmp_path_factory.mktemp("c1") / "c1.etsworld"
    write_synthetic_worldfile(str(p), seed=0)
    return str(p)


def _render_with_gauge_lean(world_path, gauge_value, tmp_path, tag):
    from ets.engine.engine import Engine, resolve_sigma
    from ets.engine.worldfile import load_world
    knobs = tmp_path / f"k_{tag}.json"
    knobs.write_text(json.dumps({"events": [
        {"bar": 0, "lane": "gauge", "value": gauge_value}]}))
    wf = load_world(world_path)
    eng = Engine(wf, seed=5, sigma=resolve_sigma(wf))
    return eng.render_offline(5.0, knob_script=str(knobs))


def test_c1_same_settled_schedule_different_u_bit_identical(world_path, tmp_path):
    """GAUGE is σ_φ=0-degenerate on a v0 world (the frame is frozen), so its
    tilt is the exact identity: u_gauge=0 vs u_gauge=3 are DIFFERENT u with
    provably the SAME settlement — C-1 demands (and gets) bit-identical audio."""
    r0 = _render_with_gauge_lean(world_path, 0.0, tmp_path, "a")
    r3 = _render_with_gauge_lean(world_path, 3.0, tmp_path, "b")
    assert np.array_equal(r0.audio, r3.audio), \
        "different u with an identical settled schedule changed the AUDIO — " \
        "a knob is reaching the render around the settlement (C-1 violation)"
    assert r0.receipt["provenance_sha256"] == r3.receipt["provenance_sha256"]
    # non-vacuity: a NON-degenerate lean does change the audio.
    from ets.engine.engine import Engine, resolve_sigma
    from ets.engine.worldfile import load_world
    knobs = tmp_path / "k_c.json"
    knobs.write_text(json.dumps({"events": [
        {"bar": 0, "lane": "density", "value": 2.5}]}))
    wf = load_world(world_path)
    r_d = Engine(wf, seed=5, sigma=resolve_sigma(wf)).render_offline(
        5.0, knob_script=str(knobs))
    assert not np.array_equal(r0.audio, r_d.audio), \
        "C-1 check is vacuous: no lean changes the audio at all"
