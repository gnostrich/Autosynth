"""Layer-0 tilt observables phi_i (ets-connector-v0.md, Layer 0) [MECHANISM].

The connector's settlement measure per bar is

    p(a)  proportional to  exp( -F(a)/T_s + sum_i lambda_i * phi_i(a) )

with lambda_i = u_i / sigma_phi_i. This module implements the phi_i — the
normative, gauge-invariant arrangement statistics, computable from the candidate
arrangement alone (plus the frozen world's role/successor structure and, for
phi_novelty ONLY, the committed tape — read traffic the connector explicitly
sanctions). It contains ZERO learned content and ZERO hand constants.

LANE -> OBSERVABLE MAP (connector Layer 0; spec s8 lanes; exhaustive):

  lane 1 REGION TILT      -> phi_region    (M-vector over anchors)
  lane 2 DENSITY          -> phi_density   (scalar)
  lane 3 CONTINUITY       -> phi_continuity (scalar)
  lane 4 GAUGE STIFFNESS  -> phi_gauge     (scalar)
  lane 5 NOVELTY PRESSURE -> phi_novelty   (scalar)
  lane 6 TEMPERATURE      -> (no phi: T_s scales settlement sharpness; typed
                              separately by the connector — five direction
                              lanes + one sharpness lane)

DEFINITIONS (per bar r; a bar = s_phase consecutive output slots — the tape's
own metrical clock, spec s1):

  phi_region[k]  = sum of the bar's SCHEDULED MASS attributed to anchor role k:
                   sum over placements p in bar of mass_p^2 * 1[role(p) = k].
                   A placement's stored ``mass`` is the amplitude sqrt(e) that
                   conserves its cell's settled mass e (ets.writer.realize), so
                   mass_p^2 recovers the scheduled mass of the cell the
                   placement realizes. role(p) is the PLACED unit's dominant
                   anchor (frozen world structure): the realized role content
                   of the arrangement, sensitive to both the occupancy and the
                   fiber (which real unit actually sits there).

  phi_density    = the bar's total scheduled mass = sum_k phi_region[k]
                   (exactly; the region vector's marginal). The connector names
                   this lane's statistic "filled-slot count / scheduled mass":
                   under the settled-field writer every cell carries strictly
                   positive settled mass (no threshold exists, by the
                   writer-settled-field ruling), so the filled-cell COUNT is
                   the constant s_phase * n_bands and carries no information;
                   the scheduled MASS is the density sufficient statistic. The
                   marginal relation phi_density = sum_k phi_region[k] is
                   structural: DENSITY is the isotropic direction of REGION
                   (one scalar lane vs one vector lane on the panel).

  phi_continuity = count of source-successor continuation events in the bar:
                   placements whose unit is the SOURCE successor (within its
                   own track and band — frozen world structure) of the unit
                   most recently placed in the same band. Pure within-track
                   content adjacency; no cross-track coordinate (I-2).

  phi_gauge      = frame-move indicator x magnitude on the section-gauge
                   variable: for every section boundary falling in the bar, the
                   intrinsic (group-invariant) magnitude of the frame move.
                   Each gauge component contributes its own group's natural
                   metric — derived, not chosen:
                     transposition: circular distance on the pitch-class circle
                                    (period 12), normalized by the period;
                     phase:         circular distance on the phase circle
                                    (period 1);
                     loudness:      |log(l2/l1)|, the invariant metric of the
                                    multiplicative group R_{>0}.
                   All three are invariant under a GLOBAL gauge roll (adding a
                   constant to every frame / scaling every loudness), which is
                   exactly the C-2 gauge law. A section with loudness_scale 0
                   is outside the gauge group (not invertible) and is rejected.

  phi_novelty    = recency-weighted unit reuse vs the committed tape:
                   sum over placements p in bar r whose unit was last placed in
                   an earlier bar r' < r of  1 / (r - r').
                   The kernel 1/Delta is the SCALE-FREE recency weight: it is
                   the unique choice introducing no length constant (any
                   exponential kernel would require a hand-set decay length,
                   which is forbidden), and its overall normalization is
                   absorbed by the sigma_phi calibration (lambda = u/sigma is
                   invariant to rescaling phi). Reads only the tape's own
                   committed bars (sanctioned read traffic; the tape node has
                   zero structural authority — nothing here feeds anchors).

METERS ARE NOT OBSERVABLES (I-5 / I-14). phi_novelty is the connector's tilt
statistic, NOT the NOVELTY SATURATION meter; phi_gauge is NOT the drift-CV
holonomy jack. This module imports nothing from ets.meters and computes no
holonomy; the C-2 test enforces the import law structurally.

GAUGE INVARIANCE (C-2, CI-enforced). Every phi_i is invariant, to machine
precision, under the section gauges: a global transposition roll, a global
phase roll, and a global loudness scale (lawful: phi reads settled mass, which
is settlement output, never the gauge loudness; spec schedule law "MASS IS NOT
GAUGE"). No phi reads an absolute frame, absolute pitch, or absolute loudness.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Mapping, Tuple
import numpy as np

# Lane number -> phi name (lane 6 TEMPERATURE has no phi by connector typing).
LANE_PHI = {1: "region", 2: "density", 3: "continuity", 4: "gauge", 5: "novelty",
            6: None}

# The calibrated observable list, in lane order.
PHI_NAMES = ("region", "density", "continuity", "gauge", "novelty")


@dataclass(frozen=True)
class RoleMaps:
    """Frozen-world role/successor structure the observables read.

    unit_role : (track_id, unit_id) -> dominant anchor role k in [0, M).
    unit_band : (track_id, unit_id) -> filterbank band.
    successor : (track_id, unit_id) -> the source-consecutive unit in the same
                band of the same track (within-track content adjacency, I-2).
    M         : anchor count (region vector dimension).

    This is a READ of the frozen world (the same structure the writer's
    realization index carries); it grants the tape no structural authority.
    """
    unit_role: Mapping[Tuple[int, int], int]
    unit_band: Mapping[Tuple[int, int], int]
    successor: Mapping[Tuple[int, int], Tuple[int, int]]
    M: int


def role_maps_from_world(world) -> RoleMaps:
    """RoleMaps from a frozen ``ets.writer.World`` (its realization index +
    tracks). Raises if the index lacks the run structure (a world built before
    rev-r1 has no successor map — that is a wall, not a default)."""
    idx = world.index
    if not idx.unit_role or not idx.successor:
        raise ValueError("world's realization index carries no unit_role/"
                         "successor structure; rebuild the world (rev-r1)")
    unit_band: Dict[Tuple[int, int], int] = {}
    for t in world.tracks:
        tid = int(t.track_id)
        uid = t.units["unit_id"].astype(int)
        band = t.units["band"].astype(int)
        for j in range(len(uid)):
            unit_band[(tid, int(uid[j]))] = int(band[j])
    return RoleMaps(unit_role=dict(idx.unit_role), unit_band=unit_band,
                    successor=dict(idx.successor), M=int(idx.M))


def _circ_dist(x: float, period: float) -> float:
    """Circular distance of a difference ``x`` on a circle of ``period``:
    min(x mod p, p - x mod p). Invariant under x -> x + k*p for integer k, and
    under a common shift of both endpoints (a global roll)."""
    r = float(x) % float(period)
    return float(min(r, float(period) - r))


def _gauge_move_magnitude(g1, g2) -> float:
    """Intrinsic magnitude of the frame move g1 -> g2 (see module docstring:
    each component contributes its own gauge group's natural metric)."""
    if not (g1.loudness_scale > 0.0 and g2.loudness_scale > 0.0):
        raise ValueError(
            "phi_gauge: loudness_scale 0 is outside the gauge group R_{>0} "
            "(not invertible); a silent section is not a gauge frame")
    dt = _circ_dist(g2.transpose_semitones - g1.transpose_semitones, 12.0) / 12.0
    dp = _circ_dist(g2.phase_shift - g1.phase_shift, 1.0)
    dl = abs(float(np.log(g2.loudness_scale / g1.loudness_scale)))
    return dt + dp + dl


def phi_bars(schedule, maps: RoleMaps, s_phase: int) -> Dict[str, np.ndarray]:
    """All five phi_i for every bar of ``schedule``.

    Returns {"region": (R, M), "density": (R,), "continuity": (R,),
    "gauge": (R,), "novelty": (R,)} with R = n_out_slots / s_phase.

    The schedule must hold WHOLE bars (n_out_slots divisible by s_phase);
    anything else raises — a partial bar is not silently truncated or padded.
    Placement scan order is (slot, band, track, unit): deterministic, and the
    per-band continuation threads are order-independent across bands.
    """
    n_slots = int(schedule.n_out_slots)
    s_phase = int(s_phase)
    if s_phase <= 0 or n_slots % s_phase != 0:
        raise ValueError(f"phi_bars needs whole bars: n_out_slots={n_slots} "
                         f"not divisible by s_phase={s_phase}")
    R = n_slots // s_phase
    M = int(maps.M)

    region = np.zeros((R, M))
    density = np.zeros(R)
    continuity = np.zeros(R)
    gauge = np.zeros(R)
    novelty = np.zeros(R)

    P = schedule.placements
    if len(P):
        bands = np.empty(len(P), dtype=np.int64)
        for i in range(len(P)):
            key = (int(P[i]["src_track"]), int(P[i]["src_unit"]))
            if key not in maps.unit_band:
                raise KeyError(f"placement unit {key} unknown to the frozen "
                               f"world's band map")
            bands[i] = maps.unit_band[key]
        order = np.lexsort((P["src_unit"], P["src_track"], bands, P["out_slot"]))

        last_bar: Dict[Tuple[int, int], int] = {}   # unit -> most recent bar used
        prev: Dict[int, Tuple[int, int]] = {}       # band -> last unit placed
        for i in order:
            p = P[i]
            key = (int(p["src_track"]), int(p["src_unit"]))
            if key not in maps.unit_role:
                raise KeyError(f"placement unit {key} unknown to the frozen "
                               f"world's role map")
            r = int(p["out_slot"]) // s_phase
            m2 = float(p["mass"]) ** 2                 # scheduled (settled) mass
            region[r, int(maps.unit_role[key])] += m2
            density[r] += m2

            b = int(bands[i])
            pv = prev.get(b)
            if pv is not None and maps.successor.get(pv) == key:
                continuity[r] += 1.0
            prev[b] = key

            lb = last_bar.get(key)
            if lb is not None and lb < r:
                novelty[r] += 1.0 / float(r - lb)
            last_bar[key] = r

    secs = sorted(schedule.sections, key=lambda s: s.out_slot_start)
    for s1, s2 in zip(secs[:-1], secs[1:]):
        r = int(s2.out_slot_start) // s_phase
        if r < R:
            gauge[r] += _gauge_move_magnitude(s1.gauge, s2.gauge)

    return {"region": region, "density": density, "continuity": continuity,
            "gauge": gauge, "novelty": novelty}
