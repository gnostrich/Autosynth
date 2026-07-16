"""MIDI CC-learn (spec §8: "MIDI CC-mappable (CC learn)").

Pure mapping logic — no hardware, no display, fully headless-testable. Binding
to a real controller (opening an ALSA/CoreMIDI input port) would use
python-rtmidi/mido and is deferred to the running desktop app; the substance —
learn a CC, map it to a lane, apply an incoming 7-bit value to that lane — lives
here and is exercised in CI.

A CC maps to a LaneTarget = one of the six lanes (§8), and for the REGION lane
(a vector over anchors) an anchor index selects which channel-strip the CC
drives. Nothing here can target a seventh lane: targets are validated against
`ets.panel.lanes.LANE_IDS`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from ets.panel.lanes import LaneVector, spec, LANE_IDS, LaneKind


@dataclass(frozen=True)
class LaneTarget:
    """A CC destination: a lane, plus an anchor index for the vector REGION lane."""
    lane_id: str
    anchor: Optional[int] = None   # only meaningful for the region (vector) lane

    def __post_init__(self) -> None:
        if self.lane_id not in LANE_IDS:
            raise ValueError(
                f"CC target {self.lane_id!r} is not one of the six lanes "
                f"{list(LANE_IDS)} — a seventh target is a spec violation")
        s = spec(self.lane_id)
        if s.is_vector and self.anchor is None:
            raise ValueError("region target requires an anchor index")
        if (not s.is_vector) and self.anchor is not None:
            raise ValueError(f"scalar lane {self.lane_id!r} takes no anchor index")


def cc_to_lane_value(lane_id: str, value7: int) -> float:
    """Map a 7-bit MIDI CC value (0..127) to a lane's natural-unit range."""
    if not 0 <= int(value7) <= 127:
        raise ValueError(f"CC value {value7} out of 7-bit range")
    s = spec(lane_id)
    frac = int(value7) / 127.0
    return float(s.lo + frac * (s.hi - s.lo))


def apply_to_lane_vector(u: LaneVector, target: LaneTarget, value7: int) -> None:
    """Write one incoming CC value into the lane vector at `target`."""
    val = cc_to_lane_value(target.lane_id, value7)
    lid = target.lane_id
    if lid == "region":
        i = int(target.anchor)
        if not 0 <= i < u.n_anchors:
            raise IndexError(
                f"region anchor {i} out of range (n_anchors={u.n_anchors})")
        u.u_region[i] = val
    elif lid == "density":
        u.u_density = val
    elif lid == "continuity":
        u.u_continuity = val
    elif lid == "gauge":
        u.u_gauge = val
    elif lid == "novelty":
        u.u_novelty = val
    elif lid == "temperature":
        u.T_s = val
    else:  # unreachable: LaneTarget validated lid ∈ the six
        raise AssertionError(f"unhandled lane {lid!r}")


class CCMap:
    """Learned map from a hardware (channel, cc) to a LaneTarget.

    Learn protocol (classic CC-learn): `arm(target)` then the next `observe`d CC
    binds it. `apply(channel, cc, value, u)` routes a live CC to its lane.
    """

    def __init__(self) -> None:
        self._map: Dict[Tuple[int, int], LaneTarget] = {}
        self._armed: Optional[LaneTarget] = None

    # --- learn ----------------------------------------------------------------
    def arm(self, target: LaneTarget) -> None:
        """Enter learn mode for `target`: the next observed CC binds to it."""
        self._armed = target

    def disarm(self) -> None:
        self._armed = None

    @property
    def armed(self) -> Optional[LaneTarget]:
        return self._armed

    def observe(self, channel: int, cc: int) -> Optional[LaneTarget]:
        """Feed an incoming CC during learn. If armed, binds (channel,cc)→target
        and returns it; otherwise returns any existing binding (or None)."""
        key = (int(channel), int(cc))
        if self._armed is not None:
            self._map[key] = self._armed
            bound = self._armed
            self._armed = None
            return bound
        return self._map.get(key)

    def bind(self, channel: int, cc: int, target: LaneTarget) -> None:
        """Directly bind (channel, cc) → target (no arm/observe round-trip)."""
        self._map[(int(channel), int(cc))] = target

    def target_for(self, channel: int, cc: int) -> Optional[LaneTarget]:
        return self._map.get((int(channel), int(cc)))

    def mappings(self) -> Dict[Tuple[int, int], LaneTarget]:
        return dict(self._map)

    # --- live routing ---------------------------------------------------------
    def apply(self, channel: int, cc: int, value7: int, u: LaneVector) -> bool:
        """Route a live CC to its mapped lane. Returns True if it hit a binding
        (and wrote a lane), False if (channel, cc) is unmapped."""
        target = self._map.get((int(channel), int(cc)))
        if target is None:
            return False
        apply_to_lane_vector(u, target, value7)
        return True
