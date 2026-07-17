"""Unit-resolved fiber extraction (spec §5 rev-r1; fork C: richer fiber +
gauge-aligned groove target).

``ets.functional.f`` holds the fiber TERM MATH — the gauge-aligned phase-
displacement charge and the unit-successor run-continuation reward. This module
extracts the fiber those terms consume from a Track / arrangement: the unit-level
INTRINSIC metrical coordinate and the source-successor structure that the
K-prototype role marginal discards. Going finer than the marginal is the whole
fork: the metrical signal the aggregate O threw away (grid-shuffle sep 0.35) lives
BELOW role granularity, in which real unit sits at which metrical slot.

All quantities are gauge-invariant / gauge-quotiented (I-2):
  * the phase charge is a WITHIN-TRACK displacement (intrinsic vs slot phase),
    invariant to a global per-section phase shift (solved out in f.py);
  * the successor reward uses only WITHIN-TRACK content-adjacency (a unit's source
    successor is defined inside its own track), so cross-track grafts simply break
    the run rather than importing any foreign coordinate.
"""
from __future__ import annotations
import numpy as np

from ..ingestion import beatclock as bc
from ..functional import f as ff


def intrinsic_phase(track) -> np.ndarray:
    """Per-unit INTRINSIC metrical coordinate: the bar-phase of the unit's SOURCE
    content, read from provenance ``src_start`` through the beat grid (§3:
    microtiming is intrinsic content, not gauge). This travels WITH the audio: a
    grid-shuffle permutes ``src_start`` and the intrinsic phase follows the content
    to its new slot, while the arrangement ``phase`` (the slot it now occupies)
    does not — the displacement between them is exactly what the charge reads. For
    a real track intrinsic_phase == units['phase'] (each unit sits at its own
    slot), so the charge is 0."""
    g = track.beat_grid
    phi, _, _ = bc.metrical_coords(g.tatum_boundaries, g)
    tb = np.asarray(g.tatum_boundaries, np.int64)
    ss = np.asarray(track.provenance_index["src_start"], np.int64)
    ti = np.clip(np.searchsorted(tb, ss, side="right") - 1, 0, len(phi) - 1)
    return phi[ti]


def track_phase_charge(track) -> float:
    """The gauge-aligned circular phase-displacement charge of a Track's
    arrangement (T1's fiber term)."""
    m = np.asarray(track.masses, float)
    return ff.phase_displacement_charge(intrinsic_phase(track),
                                        np.asarray(track.units["phase"], float), m)


def _content_id(track) -> np.ndarray:
    """Content identity that a scramble moves with the audio: the source-span
    start. Two units are source-consecutive (a real run) iff their content ids are
    adjacent in the sorted per-band source order."""
    return np.asarray(track.provenance_index["src_start"], np.int64)


def track_continuation_reward(track) -> float:
    """Real-successor run-continuation reward of a Track's arrangement (T4's fiber
    term). Within each band, the OUTPUT/time order is (bar, slot); the reward is
    the mass-weighted fraction of output-adjacent pairs whose content is a genuine
    SOURCE successor (the run continues the real audio). Real track = 1.0 (output
    order == source order); grid-shuffle re-deals content within band → ~0."""
    u = track.units
    m = np.asarray(track.masses, float)
    band = np.asarray(u["band"], np.int64)
    cid = _content_id(track)
    is_succ, wgt = [], []
    for b in np.unique(band):
        idx = np.where(band == b)[0]
        order = idx[np.lexsort((u["slot"][idx], u["bar"][idx]))]      # time order
        srt = np.sort(cid[idx])
        nxt = {int(srt[i]): int(srt[i + 1]) for i in range(len(srt) - 1)}
        for i in range(len(order) - 1):
            a, c = order[i], order[i + 1]
            wgt.append(float(m[a] * m[c]))
            is_succ.append(1.0 if nxt.get(int(cid[a]), -1) == int(cid[c]) else 0.0)
    return ff.continuation_reward(is_succ, wgt)


def track_fiber(track) -> dict:
    """Both Track-level fiber scalars: {'phase_charge', 'succ_reward'}."""
    return {"phase_charge": track_phase_charge(track),
            "succ_reward": track_continuation_reward(track)}


# --------------------------------------------------------------------------
# role-space arrangements: unit-resolved fiber for the two anchor-channel ops
# --------------------------------------------------------------------------

def _unit_anchor(track, proto, world) -> np.ndarray:
    """Per-unit DOMINANT anchor (role) label via nearest prototype (timbre) then
    the pure-GW prototype→anchor coupling. Anchor space is gauge-invariant (I-2)."""
    g = world.couple(proto)                                # (K, M) transport
    role_of_proto = g.argmax(1)                            # prototype -> anchor
    desc = track.C_timbre.desc                             # (n, 4) private
    d = np.linalg.norm(desc[:, None, :] - proto.timbre[None, :, :], axis=2)
    return role_of_proto[d.argmin(1)]                      # (n,) unit -> anchor


def role_permute_fiber(track, proto, world) -> dict:
    """role-permute does NOT move any unit metrically (it relabels which ROLE a
    prototype plays); the metrical fiber is the real track's, so its charge is 0
    and its run-continuation is 1. role-permute is separated by T1's GW transport,
    not by the fiber — computing the fiber honestly shows exactly that."""
    return track_fiber(track)


def cross_track_swap_fiber(tracks, protos, world, swap_mask, seed: int) -> dict:
    """Unit-resolved fiber for a cross-track-swap: build the grafted output
    sequence (track A's units, with the swapped-role positions replaced by real
    units of the SAME anchor role drawn from track B) and read its run-continuation
    reward. A grafted B-unit is no successor of any A-unit (and vice versa), so
    every graft boundary breaks the run → the reward drops below the real 1.0.

    Only anchor-space (role) identity crosses the boundary to DECIDE the graft
    (gauge-invariant, I-2); the successor test is within-track content adjacency,
    so no foreign coordinate is compared. The phase charge is reported at the
    A-native level (0): grafting foreign content is a CONTINUITY violation, not a
    within-A groove violation, so it is charged by T4, not by T1's phase term
    (avoiding any cross-track absolute-phase comparison)."""
    A, B = tracks[0], tracks[1]
    PA, PB = protos[0], protos[1]
    roleA = _unit_anchor(A, PA, world)
    roleB = _unit_anchor(B, PB, world)
    Q = set(int(k) for k in np.where(swap_mask)[0].tolist())
    rng = np.random.default_rng(seed)

    uA = A.units; mA = np.asarray(A.masses, float); cidA = _content_id(A)
    mB = np.asarray(B.masses, float); cidB = _content_id(B)
    bandA = np.asarray(uA["band"], np.int64)

    # B pool of real units per anchor role (the swap source)
    Bpool = {k: np.where(roleB == k)[0] for k in Q}

    is_succ, wgt = [], []
    for b in np.unique(bandA):
        idx = np.where(bandA == b)[0]
        order = idx[np.lexsort((uA["slot"][idx], uA["bar"][idx]))]
        srt = np.sort(cidA[idx])
        nxt = {int(srt[i]): int(srt[i + 1]) for i in range(len(srt) - 1)}
        # per-position content: ('A', cid, mass) native, or ('B', cid, mass) graft
        seq = []
        for i in order:
            k = int(roleA[i])
            if k in Q and len(Bpool[k]) > 0:
                j = int(Bpool[k][rng.integers(len(Bpool[k]))])
                seq.append(("B", int(cidB[j]), float(mB[j])))
            else:
                seq.append(("A", int(cidA[i]), float(mA[i])))
        for i in range(len(seq) - 1):
            (t0, c0, m0), (t1, c1, m1) = seq[i], seq[i + 1]
            wgt.append(m0 * m1)
            real = (t0 == "A" and t1 == "A" and nxt.get(c0, -1) == c1)
            is_succ.append(1.0 if real else 0.0)
    return {"phase_charge": track_phase_charge(A),   # A-native groove (0); see note
            "succ_reward": ff.continuation_reward(is_succ, wgt)}
