"""ENGINE process (spec §12): Python core — frozen world + streaming writer +
render — driven over OSC by the separate PANEL process (or any OSC/MIDI
hardware), with real-time audio via a sounddevice callback and an offline
render mode.

    python -m ets.engine --world <world file> --latency-profile desktop
    python -m ets.engine --world <world file> --render out.flac --seconds 30 \
        --knob-script knobs.json --seed 0

Two processes, one wire: the engine binds the OSC addresses in
ets.panel.osc_schema (the closed message space) and NOTHING else. Control
reaches the writer ONLY as ets.writer.tilt.TiltTerms produced by the Layer-0
map (I-1 / connector C-3); meters flow one way, engine → panel (I-5).

No web technology anywhere (I-13): the runtime here is numpy + the ets writer
stack + python-osc + (live mode only, lazily imported) sounddevice.

Modules:
  worldfile.py — frozen-world artifact: save/load + content hash (H-8 key).
  latency.py   — declared latency profiles; L derived from buffer math.
  osc_io.py    — engine-side OSC endpoints (lanes/tolerances in, meters out).
  engine.py    — the Engine: offline render + live loop.
  __main__.py  — the CLI entry point.
"""
from __future__ import annotations

from ets.engine.worldfile import WorldFile, save_world, load_world
from ets.engine.latency import PROFILES, LatencyProfile, derive_L

__all__ = ["WorldFile", "save_world", "load_world",
           "PROFILES", "LatencyProfile", "derive_L", "Engine"]


def __getattr__(name):
    if name == "Engine":
        from ets.engine.engine import Engine
        return Engine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
