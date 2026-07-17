"""V5-A — OUTBOARD (the inherited master safety net). Deleting / stubbing the v5
interaction changes leaves main-out audio BYTE-IDENTICAL on a fixed seed.

The v5 change set is a control/interaction-layer edit: the XY pad redesign, the
safe-envelope clamp, and the region slew all live in `ets.panel.widget` +
`ets.panel.envelope` (+ the panel `__main__` timer wiring). None of them are on
the audio path.

Two teeth:
  (1) STRUCTURAL — no module in the render/engine/writer/functional path imports
      the v5-touched UI modules. If the audio path cannot even reach them,
      deleting/altering them cannot move a sample.
  (2) BEHAVIOURAL — a fixed-seed offline render is byte-identical whether or not
      the v5 pad/clamp/slew have been constructed and exercised in-process.
"""
from __future__ import annotations

import ast
import hashlib
import pathlib

import numpy as np

ETS = pathlib.Path(__file__).resolve().parents[2] / "ets"
RENDER_PATH_PKGS = ("render", "engine", "writer", "functional")

# the v5-touched UI modules — the audio path must never import these.
V5_UI_MODULES = ("ets.panel.widget", "ets.panel.envelope")


def _imports(src: str) -> set:
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(("." * n.level) + (n.module or ""))
    return mods


def test_render_path_never_imports_the_v5_ui_modules():
    offenders = {}
    for pkg in RENDER_PATH_PKGS:
        for p in sorted((ETS / pkg).rglob("*.py")):
            mods = _imports(p.read_text())
            bad = {m for m in mods
                   for v in V5_UI_MODULES if m == v or m.startswith(v + ".")}
            if bad:
                offenders[str(p)] = bad
    assert not offenders, (
        f"the audio path imports a v5 UI module — not outboard: {offenders}")


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


def test_main_out_byte_identical_with_and_without_v5_interaction(tmp_path):
    a = _render_audio(tmp_path / "a", seed=7)
    ha = hashlib.sha256(a.tobytes()).hexdigest()

    # construct + exercise the v5 interaction surface in-process, then re-render.
    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import Panel
    from ets.panel.envelope import RegionSlew, clamp_region, SAFE_REGION_MAGNITUDE
    QApplication.instance() or QApplication([])
    panel = Panel(emitter=None, n_anchors=4)

    class _Ev:
        def __init__(self, x, y):
            from PySide6.QtCore import QPointF
            self._p = QPointF(x, y)
        def position(self):
            return self._p
        def accept(self):
            pass
        def ignore(self):
            pass

    # ui-v6: the region surface is the FIELD; exercise the same region path
    # (whole-vector + single-anchor entries) plus a field gesture in-process.
    import numpy as _np
    panel.set_region_vector(_np.array([0.8, -0.4, 0.0, 0.2], dtype=_np.float32))
    panel.tap_region_anchor(1, 0.5)
    for _ in range(30):
        panel.tick_slew()
    from ets.instrument.field import FieldModel, FieldView
    fm = FieldModel()
    fm.telemetry_writer().apply_roleactivity([0.5, 0.1, 0.9, 0.2])
    fv = FieldView(fm)
    fv.resize(240, 200)
    fm.add_bias(("role", 2), -0.5)
    fv.repaint()
    _ = clamp_region(np.array([9.0, -9.0, 0.0, 0.0], dtype=np.float32))
    _ = RegionSlew().step([1.0, 0.0])
    _ = SAFE_REGION_MAGNITUDE

    b = _render_audio(tmp_path / "b", seed=7)
    hb = hashlib.sha256(b.tobytes()).hexdigest()

    assert ha == hb, "the v5 interaction perturbed main-out (not byte-identical)"
    assert np.array_equal(a, b)
