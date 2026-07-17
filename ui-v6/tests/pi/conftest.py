"""Shared fixtures/helpers for the playable-instrument (PI) smoke+bite tests.

These tests exercise the CONNECTED, playable instrument slice (PREREG-uiv5-
playable-instrument): read-only telemetry (/ets/nowplaying, /ets/profiles,
/ets/roleactivity), the role/anchor tap surface driving the panel's EXISTING
region-tilt emitter, and the sound-byte-identical guard.

Design law honored here (do not fabricate a second channel): a role-pad tap
reaches the engine ONLY as a spike on the region-tilt lane, via the panel's
existing `tap_region_anchor` -> `_push` -> /ets/lanes path. Every capture point
below is on THAT path; no test invents an alternate sink.

Pieces still under concurrent construction (TelemetryReceiver, /ets/profiles,
/ets/roleactivity, RegionTapPads.set_role_activity) are probed and SKIPPED
gracefully so this package always collects.
"""
from __future__ import annotations

import importlib
import os

import pytest

# Qt must be told to run windowless BEFORE PySide6 is imported anywhere.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# --------------------------------------------------------------------------
# A fake OSC emitter that records exactly which outbound channel fired.
# The panel calls emitter.emit(u) on the region/lanes path and nothing else for
# a region gesture; recording every method lets a test PROVE single-channel.
# --------------------------------------------------------------------------
class RecordingEmitter:
    def __init__(self) -> None:
        self.lanes = []          # list[LaneVector] sent on /ets/lanes
        self.tolerances = []     # list of tolerance emits (must stay empty)
        self.hellos = []         # list of hello emits (must stay empty)

    def emit(self, u) -> None:
        # copy the region so later slew steps cannot mutate what we captured.
        import numpy as np
        self.lanes.append(np.asarray(u.u_region, dtype=float).copy())

    def emit_tolerances(self, t) -> None:
        self.tolerances.append(t)

    def emit_hello(self, meters_port) -> None:
        self.hellos.append(meters_port)


@pytest.fixture
def recording_emitter():
    return RecordingEmitter()


@pytest.fixture(scope="session")
def qapp():
    """One offscreen QApplication for the whole PI Qt suite (or skip)."""
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return app


@pytest.fixture(scope="session")
def worldfile_path(tmp_path_factory):
    """A complete synthetic .etsworld (embedded bank + measured σ_φ) — the same
    fast, audio-free corpus the engine unit tests use. Skips if the harness that
    builds it is unavailable in this checkout."""
    wt = pytest.importorskip("tests.harness.worldtools")
    p = tmp_path_factory.mktemp("pi_world") / "pi.etsworld"
    wt.write_synthetic_worldfile(str(p), seed=0)
    return str(p)


# --------------------------------------------------------------------------
# Locate the TelemetryReceiver (concurrent feature). Tries the plausible homes;
# returns the class or None so the caller can importorskip-style skip.
# --------------------------------------------------------------------------
_TELEMETRY_MODULES = (
    "ets.instrument.live",
    "ets.instrument.telemetry",
    "ets.instrument.feed",
    "ets.panel.telemetry",
    "ets.panel.transport",
)


def load_telemetry_receiver():
    for modname in _TELEMETRY_MODULES:
        try:
            mod = importlib.import_module(modname)
        except Exception:
            continue
        cls = getattr(mod, "TelemetryReceiver", None)
        if cls is not None:
            return cls
    return None
