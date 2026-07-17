"""Shared helpers for the FIELD harness (ui-v6).

The FieldView handlers touch only `ev.position()`, `ev.angleDelta()`,
`ev.modifiers()`, `ev.accept()`, so tiny stubs drive scroll/press
programmatically under the offscreen platform (no pixel assertions).

Engine-backed tests (FIELD-A/B) drive the REAL writer on the synthetic fixture
world (tests.harness.worldtools) whose embedded σ_φ was verified to ARM the
region lane (measured nonzero untilted fluctuation) — if it ever disarms, the
tests FAIL LOUDLY rather than silently passing (prereg wall #3).
"""
from __future__ import annotations

import os

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class FakeWheelEvent:
    """A wheel gesture: position + notches (+ optional Ctrl for zoom)."""

    def __init__(self, x: float, y: float, notches: float = 1.0,
                 ctrl: bool = False) -> None:
        self._p = QPointF(float(x), float(y))
        self._delta = QPoint(0, int(round(notches * 120)))
        self._mods = Qt.ControlModifier if ctrl else Qt.NoModifier
        self.accepted = None

    def position(self) -> QPointF:
        return self._p

    def angleDelta(self) -> QPoint:
        return self._delta

    def modifiers(self):
        return self._mods

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.accepted = False


class FakeMouseEvent:
    def __init__(self, x: float, y: float) -> None:
        self._p = QPointF(float(x), float(y))
        self.accepted = None

    def position(self) -> QPointF:
        return self._p

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.accepted = False


def fed_model():
    """A FieldModel fed one realistic telemetry frame through its CAPABILITY
    WRITER (the legitimate path): K=3 roles, two tracks, one drillable role."""
    from ets.instrument.field import FieldModel
    m = FieldModel()
    w = m.telemetry_writer()
    w.apply_roleactivity([0.9, 0.2, 0.5])
    w.apply_nowplaying({0: 0.8, 7: 0.3})
    w.apply_profiles({0: [0.7, 0.2, 0.1], 7: [0.1, 0.2, 0.7]})
    w.apply_unitpool(0, [
        {"unit_id": 0, "track_id": 0, "band": 2, "profile": [0.6, 0.3, 0.1]},
        {"unit_id": 5, "track_id": 7, "band": 4, "profile": [0.5, 0.2, 0.6]},
    ])
    return m


# ---- engine-side fixture (FIELD-A/B): the real writer on the synthetic world
def settled_run(u_region, n_bars=6, seed=7, tmp=None):
    """Drive the REAL writer for `n_bars` at a fixed region lean and return the
    per-bar UNNORMALIZED settled role-mass projections (B @ band_mass — the
    same projection /ets/roleactivity displays, before its per-bar peak
    normalization, which is display cosmetics and degenerate at small M).
    This is the engine's answer to the bias; nothing here is UI state."""
    import pathlib
    import tempfile

    import numpy as np

    from ets.engine.engine import Engine, resolve_sigma
    from ets.engine.worldfile import load_world
    from ets.panel.lanes import default_lane_vector
    from tests.harness.worldtools import (embedded_bank_for,
                                          write_synthetic_worldfile)

    tmp = pathlib.Path(tmp or tempfile.mkdtemp())
    wp = tmp / "w.etsworld"
    if not wp.exists():
        write_synthetic_worldfile(str(wp), seed=0)
    wf = load_world(str(wp))
    world = wf.world
    sigma = resolve_sigma(wf)
    assert sigma is not None, \
        "FIXTURE WALL: synthetic world lost its embedded σ_φ (fail loudly)"
    eng = Engine(wf, seed=seed, sigma=sigma)
    bank = embedded_bank_for(world)
    B = np.asarray(world.fstate.B, dtype=np.float64)
    M, n_bands = B.shape

    u = default_lane_vector(M)
    r = np.zeros(M, dtype=np.float32)
    v = np.asarray(u_region, dtype=np.float32).reshape(-1)
    r[:min(M, v.shape[0])] = v[:min(M, v.shape[0])]
    u.u_region[:] = r
    tilt = eng._tilt_for(u)
    assert "region" not in tilt.disarmed and not any(
        d.startswith("region") for d in tilt.disarmed), \
        "FIXTURE WALL: region lane DISARMED on the fixture world — the " \
        "FIELD-A/B engine tests cannot run (do not let them pass silently)"

    w = eng.writer.__class__(world, seed=seed)
    out = []
    for _ in range(int(n_bars)):
        res = w.write_bar(tilt=tilt)
        band_mass = np.zeros(n_bands)
        for (_slot, tid, uid, _sec, mass) in res.rows:
            try:
                band = int(bank.get(int(tid), int(uid)).band)
            except KeyError:
                continue
            if 0 <= band < n_bands:
                band_mass[band] += float(mass)
        out.append(B @ band_mass)
    return np.stack(out), M
