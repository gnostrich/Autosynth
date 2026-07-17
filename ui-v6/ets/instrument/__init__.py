"""ETS instrument half (ui-v6): THE FIELD + tape/now-playing view + transport +
cue/PFL.

Nature: a READ / PUSH / MONITOR layer OUTSIDE the trained object. It lets the
player SEE what the machine already chose (from the read-only telemetry /
provenance the engine already produces), BIAS it via the ONE existing
region-tilt lane, and PREVIEW privately on a cue bus. It PINS nothing and opens
NO new write path into settlement.

Boundary law (why this is a SEPARATE package, not part of ets.panel):
  * ets.panel is forbidden by C-3 (tests/harness/test_h6_panel_exhaustive.py::
    test_c3_panel_imports_no_writer_or_engine) from importing render/engine/
    writer/functional. The DISPLAY here reads provenance-shaped data, so it may
    NOT live inside ets.panel.
  * This package therefore imports ets.panel (to drive the region lane through
    the panel's EXISTING emitter path) but the trained object never imports it.
  * The pure display models (`model`, `field.FieldModel`) read telemetry /
    provenance as plain data — they import nothing from the trained object
    (render/engine/writer/functional/geometry). That contract is what keeps the
    F3-B "door" static-check green: no monitor path reaches settlement, F,
    render, or provenance-generation.

The ONLY sanctioned gesture→engine path is the field's composite bias on the
existing region-tilt lane (ets.instrument.field → ets.panel region path →
/ets/lanes). Transport, cue, audition, and every readout are monitor-only.
Governing invariant (FIELD-INV): you push → the engine re-settles → the display
shows the ENGINE'S ANSWER; a square's fill brightness is its settled weight
from telemetry, never the input echoed back.
"""
from __future__ import annotations

# Only the PURE, Qt-free, trained-object-free pieces are re-exported at package
# import time. Widgets (field/tape/app) import PySide6 and are imported directly
# by the caller that has a Qt app, keeping headless/data tests light.
from ets.instrument.model import (
    SoundingCell, sounding_cells, cells_at, track_palette,
    PadModel, TapeModel, MonitorState,
)
from ets.instrument.transport import Transport
from ets.instrument.cue import CueMonitor

__all__ = [
    "SoundingCell", "sounding_cells", "cells_at", "track_palette",
    "PadModel", "TapeModel", "MonitorState",
    "Transport", "CueMonitor",
]
