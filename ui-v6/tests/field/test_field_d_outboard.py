"""FIELD-D — the field is OUTBOARD: it changes WHAT IS BIASED, never how F
scores or how the writer settles. Deleting the field surface leaves the
settlement math identical; only the control/display is gone. The field steers
via the EXISTING region-tilt lane — it is not a new authority.

Teeth:
  (1) STRUCTURAL door: ets/instrument/field.py imports NOTHING from the
      trained object (render/engine/writer/functional/geometry), and the audio
      path never imports the instrument package (carried F3-A check).
  (2) SINGLE-LANE WIRE: a field gesture reaches the emitter ONLY as a lane
      vector on the panel's one region path (`emit`) — no other emitter method,
      no new address, and the emitted region obeys the safe clamp + slew step.
  (3) BEHAVIOURAL delete-test: a fixed-seed offline render is byte-identical
      whether or not the field was constructed and gestured in-process.
"""
from __future__ import annotations

import ast
import hashlib
import pathlib

import numpy as np

from tests.field.conftest import FakeWheelEvent, fed_model

ETS = pathlib.Path(__file__).resolve().parents[2] / "ets"
TRAINED_OBJECT_PKGS = ("render", "engine", "writer", "functional", "geometry")


def _imports(src: str) -> set:
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(("." * n.level) + (n.module or ""))
    return mods


def test_field_imports_nothing_from_the_trained_object():
    mods = _imports((ETS / "instrument" / "field.py").read_text())
    for pkg in TRAINED_OBJECT_PKGS:
        bad = {m for m in mods
               if m == f"ets.{pkg}" or m.startswith(f"ets.{pkg}.")}
        assert not bad, f"field.py reaches the trained object: {bad}"
    # the noise-floor criterion must be RESTATED, not imported (F3-B door):
    assert not any("functional" in m for m in mods)


def test_audio_path_never_imports_the_instrument():
    offenders = {}
    for pkg in TRAINED_OBJECT_PKGS:
        d = ETS / pkg
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.py")):
            mods = _imports(p.read_text())
            if any(m == "ets.instrument" or m.startswith("ets.instrument.")
                   for m in mods):
                offenders[str(p)] = "imports ets.instrument"
    assert not offenders, f"audio path reaches the field: {offenders}"


class _SpyEmitter:
    """Records EVERY method the panel invokes, so a second channel (a call
    other than the lane-vector emit) cannot hide."""

    def __init__(self) -> None:
        self.lane_vectors = []
        self.other_calls = []
        self.last_args = None

    def emit(self, u) -> None:
        self.lane_vectors.append(u.copy())
        self.last_args = True

    def __getattr__(self, name):
        def _rec(*a, **k):
            self.other_calls.append(name)
        return _rec


def test_field_gesture_reaches_only_the_region_lane(qapp):
    from ets.instrument.field import FieldView
    from ets.panel.envelope import SAFE_REGION_MAGNITUDE, SLEW_MAX_STEP
    from ets.panel.widget import Panel

    spy = _SpyEmitter()
    panel = Panel(emitter=spy, n_anchors=3)
    m = fed_model()
    view = FieldView(m)
    view.resize(400, 300)
    view.bias_changed.connect(
        lambda: panel.set_region_vector(m.region_vector(panel.u.n_anchors)))

    # a burst of scroll gestures over the first square:
    for k in range(6):
        view.wheelEvent(FakeWheelEvent(30, 60, notches=+2))
    assert spy.lane_vectors, "bias never reached the wire"
    assert spy.other_calls == [], \
        f"field gesture used a second emitter channel: {spy.other_calls}"
    # emitted region: clamped to the safe envelope, slew-bounded per emit.
    prev = np.zeros(3, dtype=np.float32)
    for u in spy.lane_vectors:
        r = np.asarray(u.u_region, dtype=np.float32)
        assert float(np.max(np.abs(r))) <= SAFE_REGION_MAGNITUDE + 1e-6
        assert float(np.max(np.abs(r - prev))) <= SLEW_MAX_STEP + 1e-6, \
            "emitted region jumped more than one slew step (raw jump leaked)"
        prev = r
    # non-region lanes untouched by the field gesture:
    last = spy.lane_vectors[-1]
    assert (last.u_density, last.u_continuity, last.u_gauge,
            last.u_novelty) == (0.0, 0.0, 0.0, 0.0)


def _render_audio(tmp_path, seed=7):
    from ets.engine.engine import Engine, resolve_sigma
    from ets.engine.worldfile import load_world
    from tests.harness.worldtools import write_synthetic_worldfile
    tmp_path.mkdir(parents=True, exist_ok=True)
    wp = tmp_path / "w.etsworld"
    write_synthetic_worldfile(str(wp), seed=0)
    wf = load_world(str(wp))
    eng = Engine(wf, seed=seed, sigma=resolve_sigma(wf))
    knob = tmp_path / "knob.json"
    knob.write_text('{"events": [{"bar": 1, "lane": "region", '
                    '"value": [1.0, -0.5]}]}')
    res = eng.render_offline(1.5, knob_script=str(knob))
    return res.audio


def test_render_byte_identical_with_and_without_the_field(tmp_path, qapp):
    a = _render_audio(tmp_path / "a", seed=7)
    ha = hashlib.sha256(a.tobytes()).hexdigest()

    # construct + exercise the ENTIRE field surface in-process...
    from ets.instrument.field import FieldView
    m = fed_model()
    v = FieldView(m)
    v.resize(300, 240)
    v.wheelEvent(FakeWheelEvent(20, 40, notches=+4))
    v.zoom_into(("track", 0))
    v.repaint()

    # ...and render again: byte-identical (the field touched nothing).
    b = _render_audio(tmp_path / "b", seed=7)
    hb = hashlib.sha256(b.tobytes()).hexdigest()
    assert ha == hb and np.array_equal(a, b), \
        "the field's presence perturbed main-out — NOT outboard"
