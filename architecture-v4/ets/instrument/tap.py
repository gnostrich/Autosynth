"""Pad tap/hold (F3.2) — the ONE sanctioned gesture→engine path.

A pad gesture becomes a transient/held spike on the EXISTING region-tilt lane and
NOTHING else. TAP = a transient spike that eases back over the lane's normal
constraint-lag (a LIVING loop — the machine still settles, this only biases the
current moment); HOLD = a sustained bias until release, then the same ease.

No second write path: this module computes a lane VALUE over time and hands it to
a `region_sink(anchor, value)` callback. The app wires that callback to the
panel's EXISTING region path (ets.panel emitter → /ets/lanes). This module never
imports the writer/engine/render and never opens an OSC address of its own; it
reads only the region lane's declared range from ets.panel.lanes (the control
typing, not the trained object).

The tap surface is per ANCHOR (1:1 with the region lane): tapping pad/anchor i
spikes u_region[i]. See ets.instrument.model for why the material DISPLAY pads
key on source track while this TAP surface keys on anchor — the two are the
honest, separately-sourced views (no fabricated track→anchor join).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from ets.panel.lanes import spec as lane_spec


@dataclass
class RegionTapEnvelope:
    """One anchor's region-lean input as a function of time.

    States:
      idle       — value 0, nothing happening.
      transient  — a TAP: jumped to `peak`, now easing exponentially to 0.
      held       — a HOLD: pinned at `peak` until release().
    `advance(dt)` moves time forward and returns the current lane value; the
    exponential ease has time-constant `lag_s` (the lane's constraint-lag).
    """
    peak: float = 0.0
    lag_s: float = 0.35
    value: float = 0.0
    state: str = "idle"

    def tap(self) -> None:
        self.value = self.peak
        self.state = "transient"

    def hold(self) -> None:
        self.value = self.peak
        self.state = "held"

    def release(self) -> None:
        # a held bias, released, eases exactly like a tap.
        if self.state == "held":
            self.state = "transient"

    def advance(self, dt: float) -> float:
        if self.state == "held":
            self.value = self.peak
        elif self.state == "transient":
            # exponential decay toward 0 with time-constant lag_s.
            self.value *= math.exp(-max(0.0, dt) / max(1e-6, self.lag_s))
            if self.value <= 1e-4 * max(1e-9, abs(self.peak)):
                self.value = 0.0
                self.state = "idle"
        else:
            self.value = 0.0
        return self.value


class RegionTapController:
    """Owns one `RegionTapEnvelope` per anchor and drives a region_sink with the
    summed lane value on every `advance`. The sink is the panel's existing region
    path; this controller adds no channel.

    `peak` defaults to the region lane's declared maximum lean (ets.panel.lanes),
    so a tap is a full-scale transient toward that anchor's material.
    """

    def __init__(self, n_anchors: int,
                 region_sink: Optional[Callable[[int, float], None]] = None,
                 peak: Optional[float] = None, lag_s: float = 0.35) -> None:
        s = lane_spec("region")
        self.peak = float(s.hi if peak is None else peak)
        self.lag_s = float(lag_s)
        self.region_sink = region_sink
        self._env: Dict[int, RegionTapEnvelope] = {}
        self.set_anchor_count(int(n_anchors))

    def set_anchor_count(self, n: int) -> None:
        n = int(n)
        for i in range(n):
            self._env.setdefault(
                i, RegionTapEnvelope(peak=self.peak, lag_s=self.lag_s))
        for i in list(self._env):
            if i >= n:
                del self._env[i]

    def tap(self, anchor: int) -> None:
        if anchor in self._env:
            self._env[anchor].tap()
            self._emit(anchor)

    def hold(self, anchor: int) -> None:
        if anchor in self._env:
            self._env[anchor].hold()
            self._emit(anchor)

    def release(self, anchor: int) -> None:
        if anchor in self._env:
            self._env[anchor].release()

    def value(self, anchor: int) -> float:
        return self._env[anchor].value if anchor in self._env else 0.0

    def advance(self, dt: float) -> None:
        """Tick every envelope forward and push each changed anchor to the sink
        (the panel's region path). The writer applies its own constraint-lag on
        top; this is only the lane INPUT easing."""
        for anchor, env in self._env.items():
            prev = env.value
            cur = env.advance(dt)
            if cur != prev:
                self._emit(anchor)

    def _emit(self, anchor: int) -> None:
        if self.region_sink is not None:
            self.region_sink(int(anchor), float(self._env[anchor].value))
