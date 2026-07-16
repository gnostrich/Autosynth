"""The five Layer-0 arrangement statistics phi_i (ets-connector-v0, Layer 0).

    p(a) ∝ exp( −F(a)/T_s + Σ_i λ_i · φ_i(a) )

φ_i are the NORMATIVE arrangement statistics: gauge-invariant, computable from
the candidate arrangement alone (connector Layer 0, verbatim):

  φ_region   = anchor-occupancy vector of the bar's scheduled mass
  φ_density  = filled-slot count / scheduled mass  (the scheduled mass; see note)
  φ_cont     = count of source-successor continuation events
  φ_gauge    = frame-move indicator × magnitude on the section-gauge variable
  φ_novelty  = recency-weighted unit reuse vs the committed tape

This module is PURE STATISTICS: it reads a `BarArrangement` and returns numbers.
It imports no F-weights, no solver, no meters, no OSC. It is consumed by
  * the tilt map (ets.writer.tilt) — λ_i·φ_i enters the settlement measure;
  * the σ_φ calibration instrument (ets.writer.calibrate);
  * the C-2 gauge-invariance test (machine-precision, per connector).

GAUGE INVARIANCE (spec §3; the C-2 law). The per-track/section gauge group is
transposition × beat-phase shift × loudness scale × timbre-basis normalization.
Each φ below is invariant by construction:
  φ_region / φ_density : role-occupancy mass, divided by the section gauge
      loudness (loudness quotient); transposition never touches the role axis;
      a section phase shift permutes the bar's slot axis, and both are sums over
      slots (permutation-invariant).
  φ_cont : reads only source-successor IDENTITY relations between placed units —
      within-track content adjacency, untouched by any gauge component.
  φ_gauge : reads only frame DIFFERENCES on the quotient circles (Z12 pitch,
      Z_S phase, log-loudness), so a global re-referencing of the frame (the
      gauge action on the frame bundle) cancels exactly.
  φ_novelty : unit identities + masses normalized by their own total (both the
      loudness scale and any global mass rescale cancel).

φ_density DEFINITION NOTE (declared): the connector names it "filled-slot count /
scheduled mass". The scheduled MASS is used: it is the smooth statistic the
DENSITY lane's Doob tilt can act on through the O-block (a count is a step
function with zero gradient a.e.). The count is recoverable from the same
arrangement and is not a second statistic.

φ_novelty RECENCY KERNEL (declared): "recency-weighted" requires a kernel; the
scale-free choice r(Δ) = 1/Δ (Δ = bars since the unit last appeared on the
committed tape, Δ ≥ 1; 0 if never used) is taken because it introduces NO
timescale constant (any exponential kernel would). Declared here and in the
calibration PREREG; σ_φ then measures its natural fluctuation unit, so no scale
constant reaches λ.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Mapping, Tuple

import numpy as np

# canonical order of the five direction statistics (matches the five direction
# lanes of spec §8 / ets.panel.lanes.DIRECTION_IDS).
PHI_IDS: Tuple[str, ...] = ("region", "density", "cont", "gauge", "novelty")


@dataclass(frozen=True)
class GaugeFrame:
    """A section gauge frame (spec §3): the variables the writer's running frame
    carries. v0 writers hold this at the identity for every bar (the frame is
    frozen; see the WALL note on φ_gauge in ets/writer/tilt.py)."""
    transpose: float = 0.0      # pitch classes on Z_12
    phase: float = 0.0          # slots on Z_S
    loudness: float = 1.0       # > 0


@dataclass(frozen=True)
class BarArrangement:
    """One bar of a candidate arrangement — everything φ needs, nothing more.

    O_bar      : (M, S) settled role-occupancy of the bar, in the bar's frame.
    placements : ((slot, band, track_id, unit_id, mass), ...) fiber content.
    continues  : (bool, ...) per placement — True iff the placement is a genuine
                 SOURCE-successor continuation event of its band's run.
    frame      : this bar's section gauge frame.
    prev_frame : the previous bar's frame (φ_gauge reads the DIFFERENCE).
    recency    : (track_id, unit_id) -> Δbars since last use on the COMMITTED
                 tape (Δ >= 1), for units that have appeared; absent = never.
    s_phase    : slots per bar (the metrical circle size, for the phase circle).
    """
    O_bar: np.ndarray
    placements: Tuple[Tuple[int, int, int, int, float], ...]
    continues: Tuple[bool, ...]
    frame: GaugeFrame = GaugeFrame()
    prev_frame: GaugeFrame = GaugeFrame()
    recency: Mapping[Tuple[int, int], int] = field(default_factory=dict)
    s_phase: int = 8

    def __post_init__(self):
        if len(self.placements) != len(self.continues):
            raise ValueError("placements and continues must align")


def _circ_dist(x: float, modulus: float) -> float:
    """Distance on the circle R/(modulus·Z), in [0, modulus/2]."""
    d = float(x) % float(modulus)
    return min(d, float(modulus) - d)


def phi_region(a: BarArrangement) -> np.ndarray:
    """(M,) anchor-occupancy vector of the bar's scheduled mass (loudness-
    quotiented: divided by the section gauge loudness)."""
    return np.asarray(a.O_bar, float).sum(axis=1) / float(a.frame.loudness)


def phi_density(a: BarArrangement) -> float:
    """Scheduled mass of the bar (loudness-quotiented). See module note."""
    return float(np.asarray(a.O_bar, float).sum() / float(a.frame.loudness))


def phi_cont(a: BarArrangement) -> float:
    """Count of source-successor continuation events in the bar."""
    return float(sum(1 for c in a.continues if c))


def phi_gauge(a: BarArrangement) -> float:
    """Frame-move indicator × magnitude on the section-gauge variable.

    Magnitude = circular distance of the frame move on each gauge circle, in
    natural (full-circle = 1) units, plus |log| of the loudness move: reads only
    frame DIFFERENCES, so a global frame re-referencing cancels (C-2)."""
    d_t = _circ_dist(a.frame.transpose - a.prev_frame.transpose, 12.0) / 12.0
    d_p = _circ_dist(a.frame.phase - a.prev_frame.phase, float(a.s_phase)) \
        / float(a.s_phase)
    d_l = abs(float(np.log(a.frame.loudness / a.prev_frame.loudness)))
    mag = d_t + d_p + d_l
    return float(mag if mag > 0.0 else 0.0)   # indicator × magnitude == magnitude


def phi_novelty(a: BarArrangement) -> float:
    """Recency-weighted unit reuse vs the committed tape: mass-weighted mean of
    r(Δ)=1/Δ over the bar's placements (0 for never-used units). In [0,1]."""
    tot = 0.0
    reuse = 0.0
    for (slot, band, tid, uid, mass) in a.placements:
        m = float(mass)
        tot += m
        d = a.recency.get((int(tid), int(uid)))
        if d is not None and d >= 1:
            reuse += m * (1.0 / float(d))
    if tot <= 0.0:
        return 0.0
    return float(reuse / tot)


def phi_all(a: BarArrangement) -> Dict[str, object]:
    """All five statistics, keyed by PHI_IDS. φ_region is an (M,) vector."""
    return {
        "region": phi_region(a),
        "density": phi_density(a),
        "cont": phi_cont(a),
        "gauge": phi_gauge(a),
        "novelty": phi_novelty(a),
    }


def gauge_act(a: BarArrangement, d_transpose: float = 0.0, d_phase: int = 0,
              loud_scale: float = 1.0) -> BarArrangement:
    """The per-section gauge ACTION on a bar arrangement (spec §3) — the C-2
    fixture. Re-expresses the SAME physical content under a moved frame:
      * slot axis rolled by d_phase and the frame's phase advanced by d_phase
        (the content stays put on the physical circle);
      * frame transposition advanced by d_transpose (role occupancy and unit
        identities do not live on the pitch circle, so only the frame moves);
      * loudness re-referenced by loud_scale: masses scale by loud_scale while
        the frame's loudness records the same scale (physical loudness fixed).
    BOTH frames (prev and current) are re-referenced identically — this is a
    change of gauge, not a musical move. Every φ must be invariant under this
    map to machine precision (connector C-2)."""
    S = int(a.s_phase)
    dp = int(d_phase) % S
    O = np.roll(np.asarray(a.O_bar, float) * float(loud_scale), dp, axis=1)
    placements = tuple(
        ((int(slot) + dp) % S, int(band), int(tid), int(uid),
         float(mass) * float(loud_scale))
        for (slot, band, tid, uid, mass) in a.placements)
    f = a.frame
    pf = a.prev_frame
    frame = GaugeFrame(f.transpose + d_transpose, f.phase + dp,
                       f.loudness * float(loud_scale))
    prev = GaugeFrame(pf.transpose + d_transpose, pf.phase + dp,
                      pf.loudness * float(loud_scale))
    return BarArrangement(O_bar=O, placements=placements, continues=a.continues,
                          frame=frame, prev_frame=prev, recency=a.recency,
                          s_phase=S)
