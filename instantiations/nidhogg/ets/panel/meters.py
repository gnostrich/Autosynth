"""Meter display model (spec §9) — a READ-ONLY inbound sink.

The panel DISPLAYS meter values it receives from the engine (the slide/loop
gauge-drift jack pair, phrase EOC gate, novelty saturation). It must NOT
consume them into any control computation: meters→planner/feedback is the
sanctioned consumer, not the panel's lanes (spec §9, I-5).

(The prior conflated DRIFT jack was DELETED outright in directive-v1 Feature 2
Stage 1 — code, panel element, OSC address, registry field — per merged
evidence it carried zero bits the slide/loop pair does not already carry;
REGISTRY conflation-regression-stage1-2026-07-15.)

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

import math
from dataclasses import dataclass, field
from typing import Dict, Optional


def _nan_components() -> Dict[str, float]:
    # NaN = "no reading yet": the slide/loop pairs are fed by the Stage-0
    # meters; until that shadow feed exists the panel shows '—' (graceful,
    # never fabricated).
    return {"key": math.nan, "phase_feel": math.nan, "timbre": math.nan}


def fmt_reading(v: float) -> str:
    """Display formatting: '—' for NaN (absent shadow feed), signed value else."""
    return "—" if (v is None or math.isnan(v)) else f"{v:+.3f}"


@dataclass
class MeterState:
    """Latest received meter values, for display only.

    Deliberately carries NO lane/lean/emit handle — see module docstring. There
    is no getter here that a control computation could legitimately call; the
    field names make plain these are outputs of the engine, inputs to the eye.
    """
    slide: Dict[str, float] = field(default_factory=_nan_components)
    loop: Dict[str, float] = field(default_factory=_nan_components)
    eoc_gate: int = 0                 # phrase end-of-chain gate (0/1)
    novelty_saturation: float = 0.0   # ~[0,1]
    clock_bar: int = -1               # -1 = no clock received yet
    clock_seconds: float = math.nan
    # handshake reply (/ets/welcome) — connection/status display only.
    engine_K: Optional[int] = None
    engine_world_hash: str = ""
    engine_L: Optional[int] = None
    engine_bar_seconds: float = math.nan
    engine_sr: Optional[int] = None
    engine_disarmed: str = ""         # lanes with no identified tilt scale

    # --- inbound updates (the ONLY mutators; each writes display state only) --
    def set_slide(self, key: float, phase_feel: float, timbre: float) -> None:
        self.slide = {"key": float(key),
                      "phase_feel": float(phase_feel),
                      "timbre": float(timbre)}

    def set_loop(self, key: float, phase_feel: float, timbre: float) -> None:
        self.loop = {"key": float(key),
                     "phase_feel": float(phase_feel),
                     "timbre": float(timbre)}

    def set_eoc(self, gate: int) -> None:
        self.eoc_gate = int(bool(gate))

    def set_novelty_saturation(self, saturation: float) -> None:
        self.novelty_saturation = float(saturation)

    def set_clock(self, bar: int, seconds: float) -> None:
        self.clock_bar = int(bar)
        self.clock_seconds = float(seconds)

    def set_welcome(self, K: int, world_hash: str, L: int,
                    bar_seconds: float, sr: int, disarmed: str = "") -> None:
        self.engine_K = int(K)
        self.engine_world_hash = str(world_hash)
        self.engine_L = int(L)
        self.engine_bar_seconds = float(bar_seconds)
        self.engine_sr = int(sr)
        self.engine_disarmed = str(disarmed)
