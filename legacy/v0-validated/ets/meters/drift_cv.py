"""DRIFT CV OUT meter (spec §9) — one jack per gauge component.

  key-drift        : accumulated holonomy of the transposition section (Z_12).
  phase/feel-drift : accumulated holonomy of the beat-phase section (Z_S).
  timbre-drift     : accumulated holonomy of the timbre-basis section — SEE WALL.

Each jack is the circular holonomy (net signed winding) of the running gauge
frame's section value over an arrangement trajectory, gauge-invariant by
construction (holonomy.circular_holonomy reads only frame DIFFERENCES, so a
global re-referencing of the frame leaves it exactly unchanged; §9, I-2).

The meter takes NO F-weights and feeds NOTHING back into any solve (I-5, I-14):
it is a pure function (frame trajectory) -> CV, whose sanctioned consumers are
the planner and CV-lane feedback patching (spec §9, §10).

The frame trajectory is exactly the sequence of gauge SECTIONS the machine
already settles (f.FState.transpose, f.FState.phase_off — the per-section
variables T5 gauge-fixing ranges over), read out per committed bar/section of a
trajectory. This module never imports the functional package; the caller passes
the already-produced section values as plain arrays.

TIMBRE-DRIFT WALL (reported, not patched — spec §9 names three jacks):
  v0's gauge FRAME (F term T5 / connector φ_gauge) settles exactly two live
  per-section components: transposition and beat-phase. The third gauge-group
  component of spec §3 — timbre-basis normalization — is fixed ONCE at ingestion
  (descriptor standardization), NOT re-chosen per section, so v0 produces no
  running timbre-basis frame and its holonomy is identically absent (not zero-by-
  measurement — absent-by-construction). The ``timbre_drift`` machinery below is
  complete and correct (it accumulates the holonomy of a timbre-basis-angle
  trajectory on the continuous circle whenever one is supplied), but no v0 world
  drives it. Proposed spec revision (for the human): either (a) add a per-section
  timbre-basis gauge to T5 so the frame carries a settled timbre angle, or
  (b) reclassify timbre-drift as a corpus-time-fixed component (constant frame,
  zero holonomy in v0). A timbre-drift synthesized from occupancy MOVEMENT would
  NOT be a gauge-frame holonomy and is deliberately NOT fabricated here.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence
import numpy as np

from .holonomy import circular_holonomy

# Gauge-component moduli. Derived from the gauge group cardinality (spec §3),
# not hand-set: pitch classes = Z_12; the metrical circle has S phase slots
# (roles.S_SLOTS = 8 in v0, passed explicitly so the meter never hardcodes the
# world's slot count).
KEY_MODULUS = 12.0            # transposition on the pitch-class circle
TIMBRE_MODULUS = 2.0 * np.pi  # timbre-basis rotation angle (continuous circle)


@dataclass(frozen=True)
class DriftReadout:
    """One drift jack's output: the running CV and the closed-loop total."""
    component: str
    running: np.ndarray        # (T,) CV signal; running[0] = 0
    total: float               # net holonomy over the trajectory (running[-1])
    modulus: float


@dataclass(frozen=True)
class DriftCV:
    """The DRIFT CV OUT jack bank (spec §9). ``timbre`` is None on any v0 world
    (see TIMBRE-DRIFT WALL)."""
    key: DriftReadout
    phase: DriftReadout
    timbre: Optional[DriftReadout]

    def as_dict(self):
        out = {"key_drift_total": self.key.total,
               "phase_drift_total": self.phase.total}
        out["timbre_drift_total"] = None if self.timbre is None else self.timbre.total
        return out


def key_drift(transpose: Sequence[float]) -> DriftReadout:
    """Key-drift jack: net winding of the transposition section on Z_12."""
    running, total = circular_holonomy(transpose, KEY_MODULUS)
    return DriftReadout("key", running, total, KEY_MODULUS)


def phase_drift(phase_off: Sequence[float], phase_modulus: float) -> DriftReadout:
    """Phase/feel-drift jack: net winding of the beat-phase section on Z_S.
    ``phase_modulus`` = the world's metrical-slot count S (passed explicitly)."""
    running, total = circular_holonomy(phase_off, phase_modulus)
    return DriftReadout("phase", running, total, float(phase_modulus))


def timbre_drift(timbre_angle: Optional[Sequence[float]]) -> Optional[DriftReadout]:
    """Timbre-drift jack: net winding of the timbre-basis section angle on the
    continuous circle. Returns None when the trajectory carries no timbre-basis
    frame — which is EVERY v0 world (see TIMBRE-DRIFT WALL). Never fabricates a
    frame from non-gauge quantities."""
    if timbre_angle is None or len(timbre_angle) == 0:
        return None
    running, total = circular_holonomy(timbre_angle, TIMBRE_MODULUS)
    return DriftReadout("timbre", running, total, TIMBRE_MODULUS)


def drift_cv(transpose: Sequence[float], phase_off: Sequence[float],
             phase_modulus: float, timbre_angle: Optional[Sequence[float]] = None
             ) -> DriftCV:
    """Compute all three DRIFT CV jacks from a gauge-frame trajectory.

    ``transpose`` and ``phase_off`` are the per-bar settled gauge sections (the
    values f.FState.transpose / f.FState.phase_off take along a trajectory).
    ``timbre_angle`` defaults to None (no v0 timbre-basis frame exists)."""
    return DriftCV(key=key_drift(transpose),
                   phase=phase_drift(phase_off, phase_modulus),
                   timbre=timbre_drift(timbre_angle))
