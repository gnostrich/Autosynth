"""The six CV lanes (spec §8; connector Layer-0) — the EXHAUSTIVE control set.

This module is the single source of truth for what a panel control *is*. Per
spec §8 and the connector's Layer-0 map, the complete control interface is:

  five DIRECTION lanes  →  the lane vector  u = (u_region, u_density,
                            u_continuity, u_gauge, u_novelty)
  one  SHARPNESS lane   →  the temperature  T_s

  p(a) ∝ exp( −F(a)/T_s + Σ_i λ_i·φ_i(a) )     [connector Layer-0]

The five direction lanes each carry a lean u_i that scales one gauge-invariant
arrangement statistic φ_i; T_s scales settlement sharpness and carries no φ.
Together they are SIX and only six. "adding a seventh control requires spec
revision" (§8) — that law is executable here: `assert_lanes_exhaustive`.

Nothing in this module touches Qt, OSC, or meters. It is the typing the panel
widget renders, the OSC schema serialises, and the MIDI map targets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple

import numpy as np


class LaneKind(Enum):
    """A lane is either a settlement DIRECTION (carries a φ statistic and a lean
    u_i) or the settlement SHARPNESS (temperature T_s; no φ)."""
    DIRECTION = "direction"
    SHARPNESS = "sharpness"


@dataclass(frozen=True)
class LaneSpec:
    """One CV lane. `phi` names the gauge-invariant arrangement statistic the
    lean scales (None for the sharpness lane, which has no φ — connector L0)."""
    id: str            # canonical lane id (stable; the MIDI/OSC/UI key)
    title: str         # panel label, verbatim from spec §8
    kind: LaneKind
    phi: str | None    # the φ_i this lean scales, or None for T_s
    lo: float          # control range (natural units: standard fluctuations of lean)
    hi: float
    default: float
    is_vector: bool = False   # True only for REGION (a vector over anchors)


# --- THE SIX. Order is normative and stable (it is the OSC field order). ------
# Five direction-lanes + one sharpness-lane (connector Layer-0). This tuple is
# frozen and closed: it IS the exhaustive control interface.
LANES: Tuple[LaneSpec, ...] = (
    LaneSpec("region", "REGION TILT", LaneKind.DIRECTION, "phi_region",
             lo=-3.0, hi=3.0, default=0.0, is_vector=True),
    LaneSpec("density", "DENSITY", LaneKind.DIRECTION, "phi_density",
             lo=-3.0, hi=3.0, default=0.0),
    LaneSpec("continuity", "CONTINUITY<->RECOMBINATION", LaneKind.DIRECTION,
             "phi_cont", lo=-3.0, hi=3.0, default=0.0),
    LaneSpec("gauge", "GAUGE STIFFNESS", LaneKind.DIRECTION, "phi_gauge",
             lo=-3.0, hi=3.0, default=0.0),
    LaneSpec("novelty", "NOVELTY PRESSURE", LaneKind.DIRECTION, "phi_novelty",
             lo=-3.0, hi=3.0, default=0.0),
    LaneSpec("temperature", "TEMPERATURE", LaneKind.SHARPNESS, None,
             lo=1e-3, hi=4.0, default=1.0),
)

# Canonical, closed identity of the control set. Any deviation is a spec
# violation, caught by `assert_lanes_exhaustive`.
LANE_IDS: Tuple[str, ...] = tuple(s.id for s in LANES)
DIRECTION_IDS: Tuple[str, ...] = tuple(
    s.id for s in LANES if s.kind is LaneKind.DIRECTION)
SHARPNESS_ID: str = next(s.id for s in LANES if s.kind is LaneKind.SHARPNESS)

# The exhaustive law, as a frozenset literal so the number 6 is not incidental.
_CANONICAL: frozenset = frozenset(
    {"region", "density", "continuity", "gauge", "novelty", "temperature"})


def spec(lane_id: str) -> LaneSpec:
    for s in LANES:
        if s.id == lane_id:
            return s
    raise KeyError(f"no such lane: {lane_id!r} (lanes are {list(LANE_IDS)})")


def assert_lanes_exhaustive(control_ids) -> None:
    """The §8 exhaustiveness law, executable.

    `control_ids` is whatever set of lanes a caller (the panel, a test) claims
    to expose. It must equal EXACTLY the six canonical lanes — no seventh, none
    missing, none renamed. Raises AssertionError otherwise. This is the check a
    panel runs at construction and a test drives with a 7th to prove it bites.
    """
    ids = tuple(control_ids)
    assert len(ids) == len(set(ids)), f"duplicate lane ids: {ids}"
    got = frozenset(ids)
    assert got == _CANONICAL, (
        "PANEL CONTROL SET IS NOT THE EXHAUSTIVE SIX (spec §8). "
        f"extra={sorted(got - _CANONICAL)} missing={sorted(_CANONICAL - got)}. "
        "Adding a seventh control (or dropping one) requires a spec revision.")
    assert len(ids) == 6, f"the control set must be exactly six, got {len(ids)}"


@dataclass
class LaneVector:
    """Panel state = the lane vector u plus temperature T_s (connector L0).

    `u_region` is a vector over the *discovered anchors* (DeepSets/growable
    support — its length is the anchor count K, self-sized, never fixed-K). The
    other four leans and T_s are scalars. This object is the ONLY thing the
    panel emits; it is the boundary-measure typing the engine's Layer-0 map
    binds to.
    """
    u_region: np.ndarray = field(
        default_factory=lambda: np.zeros(0, dtype=np.float32))
    u_density: float = 0.0
    u_continuity: float = 0.0
    u_gauge: float = 0.0
    u_novelty: float = 0.0
    T_s: float = 1.0

    def __post_init__(self) -> None:
        self.u_region = np.asarray(self.u_region, dtype=np.float32).reshape(-1)

    @property
    def n_anchors(self) -> int:
        return int(self.u_region.shape[0])

    def resize_region(self, n_anchors: int) -> None:
        """Grow/shrink the region lean to match the current anchor count.
        Growth appends zeros (a newly discovered anchor starts untilted)."""
        n = int(n_anchors)
        cur = self.u_region
        if n == cur.shape[0]:
            return
        new = np.zeros(n, dtype=np.float32)
        keep = min(n, cur.shape[0])
        new[:keep] = cur[:keep]
        self.u_region = new

    def as_dict(self) -> dict:
        return {
            "region": self.u_region.copy(),
            "density": self.u_density,
            "continuity": self.u_continuity,
            "gauge": self.u_gauge,
            "novelty": self.u_novelty,
            "temperature": self.T_s,
        }

    def copy(self) -> "LaneVector":
        return LaneVector(self.u_region.copy(), self.u_density,
                          self.u_continuity, self.u_gauge, self.u_novelty,
                          self.T_s)


def default_lane_vector(n_anchors: int = 0) -> LaneVector:
    lv = LaneVector(
        u_region=np.zeros(int(n_anchors), dtype=np.float32),
        u_density=spec("density").default,
        u_continuity=spec("continuity").default,
        u_gauge=spec("gauge").default,
        u_novelty=spec("novelty").default,
        T_s=spec("temperature").default,
    )
    return lv
