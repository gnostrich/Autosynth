"""Native PySide6 panel (spec §8, §12): six CV lanes exactly, XY vector pad, meter jacks, MIDI CC learn. No web tech (I-13). Separate process; OSC to engine.

Package layout:
  lanes.py       — the exhaustive six lanes + the LaneVector (u, T_s) typing.
  osc_schema.py  — the panel↔engine OSC wire contract (engine binds to it).
  meters.py      — read-only inbound meter display model (I-5 separation).
  midi.py        — MIDI CC-learn mapping (pure logic, headless).
  transport.py   — OSC emitter (u+T_s out) + meter receiver (meters in).
  widget.py      — the PySide6 widget (imports Qt; import lazily via `Panel`).

The pure modules import no Qt, so tooling and the I-13 scan need no display.
`Panel` is imported lazily so `import ets.panel` stays Qt-free.
"""
from __future__ import annotations

from ets.panel import lanes, meters, midi, osc_schema, tolerances, transport
from ets.panel.lanes import (
    LANES, LANE_IDS, LaneKind, LaneSpec, LaneVector, assert_lanes_exhaustive,
    default_lane_vector,
)
from ets.panel.meters import MeterState
from ets.panel.midi import CCMap, LaneTarget
from ets.panel.tolerances import (
    TOLERANCES, TOLERANCE_IDS, Tolerances, assert_tolerances_exhaustive,
)
from ets.panel.transport import MeterReceiver, OscEmitter

__all__ = [
    "lanes", "meters", "midi", "osc_schema", "tolerances", "transport",
    "LANES", "LANE_IDS", "LaneKind", "LaneSpec", "LaneVector",
    "assert_lanes_exhaustive", "default_lane_vector",
    "TOLERANCES", "TOLERANCE_IDS", "Tolerances", "assert_tolerances_exhaustive",
    "MeterState", "CCMap", "LaneTarget", "MeterReceiver", "OscEmitter",
    "Panel",
]


def __getattr__(name):
    # Lazy Qt import: `ets.panel.Panel` pulls PySide6 only when actually used.
    if name == "Panel":
        from ets.panel.widget import Panel
        return Panel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
