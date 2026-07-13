"""Realization: the settled tape occupancy -> the render's ``Schedule`` (spec §11
contract), with NO decoder and NO static keymap (connector: THE TAPE PORT).

The settlement produced ``O_tape : (M, S_out)`` — role occupancy per output slot.
Realization reads that coupling OUT as unit->slot placements. Two pieces:

  1. The ROLE MATERIALIZATION INDEX (built once, settlement-independent): for each
     anchor role k and band b, a representative REAL source unit (track, unit).
     This is "what role k sounds like in band b" — the analogue of the render
     materializing a source unit from its identity. It is a READ of the frozen
     world (each track's coupling to the shared anchors); it grants the tape ZERO
     structural authority and spawns nothing (connector NO SELF-INGESTION).

  2. The PER-SLOT PLACEMENT: for each output slot, the SETTLED column O_tape[:,s]
     (with the frozen band gains B) decides WHICH roles sound in WHICH bands here,
     and thus which real unit is laid. This is decided by the settlement, per slot
     — never a fixed table (connector NO STATIC KEYMAP). Change the anchors or
     LAMBDA (step d) or, later, the tilt, and O_tape changes, so the placements
     change. The choice of unit is a WRITER decision (spec §8 temperature lives in
     the writer); the render only applies it (I-11).

Clamped cells (I-7) pass through verbatim: a ``unit_demands`` clamp forces its
exact unit at its slot; a ``role_columns`` clamp already shaped O_tape and thus
its realization. There is no exception path — a clamp is just a cell.

The emitted gauge is IDENTITY (u=0, lanes constant): one section, no transpose,
no phase shift, unit loudness. The tape's coupling IS the provenance record
(connector (i)) — the render then discharges I-12 sample-by-sample.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Dict, List, Tuple
import numpy as np

from ..functional import f as ff
from ..functional import solver as sv
from ..render.schedule import Schedule, Section, IDENTITY, PLACEMENT_DTYPE


# ---- role materialization index -------------------------------------------

def _track_membership(fstate, proto, n_settle: int = 4) -> np.ndarray:
    """Row-normalized coupling of ONE track's prototypes to the FROZEN anchors.

    Settles just this track's coupling in the frozen anchor field (the same
    ``solver.update_pi`` I-projection, anchors held fixed). Returns g:(K, M) with
    rows summing to 1 — prototype k's membership across anchors. Cross-track
    traffic factors through the shared anchors only (I-2)."""
    M = fstate.a.shape[0]
    K = proto.mass.shape[0]
    st = replace(fstate, pis=[np.outer(proto.mass, fstate.a)])
    for _ in range(n_settle):
        st = sv.update_pi(st, [proto])
    g = st.pis[0]
    g = g / (g.sum(1, keepdims=True) + 1e-12)
    return g


@dataclass
class RealizationIndex:
    """(anchor k, band b) -> representative real source unit (track_id, unit_id)."""
    unit_of: Dict[Tuple[int, int], Tuple[int, int]]
    role_track: Dict[int, int]     # anchor k -> the track that best carries it
    M: int
    n_bands: int


def build_index(fstate, protos, tracks) -> RealizationIndex:
    """Build the role materialization index from the frozen world.

    For each (anchor k, band b): the (track, prototype) that best carries role k
    AND has real band-b material — scored by ``membership_to_k * band_affinity_b``.
    Because different tracks are strong in different bands, this spreads the
    materialization across the corpus (a role's low end may come from one track,
    its top end from another) rather than collapsing to a single track. Then the
    concrete unit is the real band-b unit in that track whose timbre is closest to
    the prototype's centroid (salience-weighted tie-break). Choices here are WRITER
    role-materialization (allowed); the render only applies (I-11)."""
    M = int(fstate.a.shape[0])
    n_bands = int(fstate.B.shape[1])

    # membership of every prototype (across tracks) to every anchor, and each
    # prototype's per-band affinity (band_profile normalized by its own mass).
    memb = [_track_membership(fstate, P) for P in protos]     # list of (K_t, M)
    band_aff = []
    for P in protos:
        m = P.mass[:, None] + 1e-12
        band_aff.append(P.band_profile / m)                   # (K_t, n_bands), in [0,1]

    unit_of: Dict[Tuple[int, int], Tuple[int, int]] = {}
    role_track: Dict[int, int] = {}
    role_track_votes = {k: {} for k in range(M)}
    for k in range(M):
        for b in range(n_bands):
            best_ti, best_pi, best_val = 0, 0, -np.inf
            for ti, (g, ba) in enumerate(zip(memb, band_aff)):
                score = g[:, k] * (ba[:, b] + 1e-6)           # role AND band material
                pj = int(np.argmax(score))
                if score[pj] > best_val:
                    best_ti, best_pi, best_val = ti, pj, float(score[pj])
            P = protos[best_ti]
            tr = tracks[best_ti]
            role_track_votes[k][int(tr.track_id)] = \
                role_track_votes[k].get(int(tr.track_id), 0) + 1

            centroid = P.timbre[best_pi]                       # (4,) role timbre
            u = tr.units
            desc = tr.C_timbre.desc                            # (n,4) standardized
            masses = np.asarray(tr.masses, float)
            in_band = np.where(u["band"] == b)[0]
            if in_band.size == 0:
                pick = int(np.argmax(masses))                 # unreachable in practice
            else:
                d = np.linalg.norm(desc[in_band] - centroid[None, :], axis=1)
                d = d / (masses[in_band] + 1e-9)              # prefer salient units
                pick = int(in_band[int(np.argmin(d))])
            unit_of[(k, b)] = (int(tr.track_id), int(u["unit_id"][pick]))
    for k in range(M):
        role_track[k] = int(max(role_track_votes[k], key=role_track_votes[k].get))
    return RealizationIndex(unit_of=unit_of, role_track=role_track,
                            M=M, n_bands=n_bands)


# ---- settled occupancy -> Schedule ----------------------------------------

def realize(O: np.ndarray, tape, fstate, index: RealizationIndex,
            band_frac: float = 0.15) -> Tuple[Schedule, dict]:
    """Turn the settled tape occupancy into a Schedule (unit->slot + gauge).

    ``band_frac``: a band sounds at a slot when its settled energy clears this
    fraction of that slot's peak band energy. This is the tape's density coming
    from the settlement (spec §8 lane 2 sits on top of it later); at u=0 it is the
    untilted equilibrium density. It is a threshold on the SETTLED field, not a
    second decision channel.
    """
    B = fstate.B                                              # (M, n_bands) frozen
    n_slots = int(tape.grid.n_slots)
    n_bands = int(B.shape[1])
    clamps = tape.clamps

    rows: List[Tuple[int, int, int, int]] = []
    for s in range(n_slots):
        if s in clamps.unit_demands:                          # I-7 verbatim passthrough
            tid, uid, _b = clamps.unit_demands[s]
            rows.append((s, int(tid), int(uid), 0))
            continue
        col = O[:, s]                                         # (M,) settled roles
        e = col @ B                                           # (n_bands,) band energy
        emax = float(e.max())
        if emax <= 0:
            continue
        for b in range(n_bands):
            if e[b] <= band_frac * emax or e[b] <= 0:
                continue
            k = int(np.argmax(col * B[:, b]))                 # role carrying band b here
            tid, uid = index.unit_of[(k, b)]
            rows.append((s, int(tid), int(uid), 0))

    p = np.zeros(len(rows), dtype=PLACEMENT_DTYPE)
    for i, (s, tid, uid, sec) in enumerate(rows):
        p[i]["out_slot"] = s
        p[i]["src_track"] = tid
        p[i]["src_unit"] = uid
        p[i]["section"] = sec

    sections = (Section(0, 0, n_slots, IDENTITY),)            # identity gauge (u=0)
    sched = Schedule(sr=int(tape.grid.sr),
                     slot_boundaries=tape.grid.slot_boundaries,
                     placements=p, sections=sections)
    meta = {
        "n_placements": int(len(rows)),
        "n_slots": n_slots,
        "n_tracks_used": int(len({r[1] for r in rows})),
        "band_frac": float(band_frac),
        "clamped_unit_slots": sorted(clamps.unit_demands),
    }
    return sched, meta
