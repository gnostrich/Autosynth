"""V5-E — SLEW (B3.2). A target change emits a MONOTONE, per-step-bounded ramp,
not a one-frame step; and the slew path touches ONLY the outbound value (it reads
nothing from settlement / F / render).
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import numpy as np
import pytest

from ets.panel.envelope import RegionSlew, SLEW_MAX_STEP


def test_step_is_a_bounded_monotone_ramp_not_a_jump():
    s = RegionSlew(max_step=0.08, n=2)
    target = np.array([1.0, -0.5], dtype=np.float32)
    frames = []
    prev = s.current
    for _ in range(200):
        cur = s.step(target)
        # per-step delta is bounded on every component.
        assert np.all(np.abs(cur - prev) <= SLEW_MAX_STEP + 1e-6)
        frames.append(cur.copy())
        prev = cur
        if s.at_target(target):
            break
    # it took MORE than one frame (a real ramp, not a step).
    assert len(frames) > 1, "the slew jumped in one frame (not a ramp)"
    # monotone toward target on each component.
    col0 = np.array([f[0] for f in frames])
    col1 = np.array([f[1] for f in frames])
    assert np.all(np.diff(col0) >= -1e-7), "component 0 not monotone up"
    assert np.all(np.diff(col1) <= 1e-7), "component 1 not monotone down"
    # and it actually reaches the target.
    np.testing.assert_allclose(frames[-1], target, atol=1e-6)


def test_a_far_jump_takes_many_bounded_steps():
    s = RegionSlew(max_step=0.08, n=1)
    n = 0
    while not s.at_target([1.0]):
        s.step([1.0])
        n += 1
        assert n < 10_000
    assert n >= int(1.0 / 0.08), "a full-scale jump collapsed into too few steps"


def test_panel_emits_a_ramp_for_a_region_jump():
    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import Panel
    QApplication.instance() or QApplication([])

    class _RecEmitter:
        def __init__(self):
            self.calls = []
        def emit(self, u):
            self.calls.append(u.copy())

    em = _RecEmitter()
    panel = Panel(emitter=em, n_anchors=2)
    # a sudden full region jump (as a mid-stream lane change would be).
    panel.u.u_region[:] = [1.0, 0.0]
    panel._push()                      # first bounded step
    while not panel._region_slew.at_target(panel._region_target()):
        panel.tick_slew()
    seq = np.array([c.u_region[0] for c in em.calls])
    assert len(seq) > 1, "region jump emitted as a single step (no ramp)"
    assert np.all(np.diff(seq) >= -1e-7), "emitted region ramp not monotone"
    assert np.all(np.diff(seq) <= SLEW_MAX_STEP + 1e-6), "a per-step jump leaked"
    assert seq[-1] == pytest.approx(1.0, abs=1e-3)


def test_slew_reads_nothing_from_the_trained_object():
    """Structural: the envelope module imports nothing settlement/F/render-side —
    the slew shapes only the outbound control value."""
    src = (pathlib.Path(inspect.getfile(RegionSlew))).read_text()
    forbidden = ("ets.render", "ets.engine", "ets.writer", "ets.functional",
                 "ets.geometry", "ets.training", "ets.calibration",
                 "ets.connector")
    mods = set()
    for nd in ast.walk(ast.parse(src)):
        if isinstance(nd, ast.Import):
            mods |= {a.name for a in nd.names}
        elif isinstance(nd, ast.ImportFrom):
            mods.add(("." * nd.level) + (nd.module or ""))
    bad = {m for m in mods for f in forbidden if m == f or m.startswith(f + ".")}
    assert not bad, f"the slew module reaches the trained object: {bad}"
