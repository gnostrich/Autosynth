"""Meter display model (spec §9) — a READ-ONLY inbound sink.

The panel DISPLAYS meter values it receives from the engine (drift CV outs,
phrase EOC gate, novelty saturation). It must NOT consume them into any control
computation: meters→planner/feedback is the sanctioned consumer, not the
panel's lanes (spec §9, I-5).

The guarantee is STRUCTURAL, not just conventional: `MeterState` is a distinct
object from `LaneVector`. It has no reference to any lane, emitter, or the
outbound channel, and exposes no method that could return a lean. Its only job
is to hold the latest received values so a widget can light an LED. Because the
emitter reads solely from `LaneVector` and this object cannot reach it, no
emitted byte can ever be a function of a received meter value. The
`tests/panel/test_meters_display_only.py` check drives this both structurally
and behaviourally.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class MeterState:
    """Latest received meter values, for display only.

    Deliberately carries NO lane/lean/emit handle — see module docstring. There
    is no getter here that a control computation could legitimately call; the
    field names make plain these are outputs of the engine, inputs to the eye.
    """
    drift: Dict[str, float] = field(default_factory=lambda: {
        "key": 0.0, "phase_feel": 0.0, "timbre": 0.0})
    eoc_gate: int = 0                 # phrase end-of-chain gate (0/1)
    novelty_saturation: float = 0.0   # ~[0,1]

    # --- inbound updates (the ONLY mutators; each writes display state only) --
    def set_drift(self, key: float, phase_feel: float, timbre: float) -> None:
        self.drift = {"key": float(key),
                      "phase_feel": float(phase_feel),
                      "timbre": float(timbre)}

    def set_eoc(self, gate: int) -> None:
        self.eoc_gate = int(bool(gate))

    def set_novelty_saturation(self, saturation: float) -> None:
        self.novelty_saturation = float(saturation)
