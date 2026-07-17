"""F3-A — OUTBOARD (the master safety net). Deleting / stubbing Feature 3 leaves
main-out audio BYTE-IDENTICAL on a fixed seed.

Two teeth, run together:
  (1) STRUCTURAL: no module in the render/engine/writer/functional path imports
      ets.instrument. If the audio path cannot even reach Feature 3, deleting it
      cannot change a sample. This is the real proof of "outboard".
  (2) BEHAVIOURAL: a fixed-seed offline render is byte-identical whether or not
      ets.instrument has been imported (and used) in-process. The feature being
      present perturbs nothing.

Kept to a ~1.5s synthetic clip (fixed seed, embedded bank) so the byte-compare is
fast and does not contend with the long render running under samples/.
"""
from __future__ import annotations

import ast
import hashlib
import pathlib

import numpy as np
import pytest

ETS = pathlib.Path(__file__).resolve().parents[2] / "ets"
RENDER_PATH_PKGS = ("render", "engine", "writer", "functional")


def _imports(src: str) -> set:
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(("." * n.level) + (n.module or ""))
    return mods


def test_render_path_never_imports_feature3():
    offenders = {}
    for pkg in RENDER_PATH_PKGS:
        for p in sorted((ETS / pkg).rglob("*.py")):
            mods = _imports(p.read_text())
            if any(m == "ets.instrument" or m.startswith("ets.instrument.")
                   for m in mods):
                offenders[str(p)] = "imports ets.instrument"
    assert not offenders, (
        f"the audio path imports Feature 3 — not outboard: {offenders}")


def _render_audio(tmp_path, seed=7):
    from ets.engine.worldfile import load_world
    from ets.engine.engine import Engine, resolve_sigma
    from tests.harness.worldtools import write_synthetic_worldfile
    tmp_path.mkdir(parents=True, exist_ok=True)
    wp = tmp_path / "w.etsworld"
    write_synthetic_worldfile(str(wp), seed=0)
    wf = load_world(str(wp))
    eng = Engine(wf, seed=seed, sigma=resolve_sigma(wf))
    knob = tmp_path / "knob.json"
    knob.write_text('{"events": [{"bar": 1, "lane": "region", '
                    '"value": [1.0, 0.0, -0.5, 0.0]}]}')
    res = eng.render_offline(1.5, knob_script=str(knob))
    return res.audio


def test_main_out_byte_identical_with_and_without_feature3(tmp_path):
    a = _render_audio(tmp_path / "a", seed=7)
    ha = hashlib.sha256(a.tobytes()).hexdigest()

    # now import + exercise Feature 3 in-process, then render again: identical.
    import ets.instrument as I
    mon = I.MonitorState()
    mon.pads.observe([I.SoundingCell(2, 0, 0, 10, 1.0)])
    tr = I.Transport(); tr.load(len(a), 44100); tr.play(); tr.tick(0.1); tr.seek(5)
    cue = I.CueMonitor(); cue.set_active(True); cue.audition(2)

    b = _render_audio(tmp_path / "b", seed=7)
    hb = hashlib.sha256(b.tobytes()).hexdigest()

    assert ha == hb, "Feature 3 present perturbed main-out (not byte-identical)"
    assert np.array_equal(a, b)
