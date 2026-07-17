"""Internal scramble comparison class (spec §6; invariant I-6).

The training condition (spec §6) is: *each real track is an equilibrium of F;
its re-arrangements are not.* The estimator is contrastive/NCE-shaped, and the
comparison class (the negatives) is generated INTERNALLY by DISARRANGING a real
track's own units. There is no external "bad music" data anywhere — ever
(invariant I-6). The negatives are re-arrangements of REAL units; nothing is
synthesized.

Fixed family (spec §6, verbatim names): **grid-shuffle, role-permute,
phase-rotate, cross-track-swap**. Per spec §6 the scramble family is an estimator
degree of freedom and MUST be fixed in PREREG before any training run, with a
stated rationale per member. This module is the single source of truth for the
family; ``PREREGISTERED_FAMILY`` is the closed set and ``assert_family_fixed``
refuses any drift from it.

Content vs arrangement (the axis every scramble acts on)
--------------------------------------------------------
A Track row is a real audio unit placed into an arrangement:

* ARRANGEMENT (where/what-role the unit is placed): metrical position
  ``phase``/``bar``/``slot``/``level`` and the ``C_metrical`` cost; the role a
  unit plays.
* CONTENT (the real audio unit itself): the source span
  ``provenance(src_start, src_end, band)``, its ``mass``, and its timbre /
  pitch-class descriptors ``C_timbre``/``C_pitchclass``.

A scramble transforms ARRANGEMENT and must preserve the CONTENT inventory
exactly (a permutation/relocation of real units — never fabrication). The
canonical content key is the provenance triple + mass + content descriptors;
``content_keys`` computes it and ``assert_inventory_preserved`` enforces
inventory equality (I-6: re-arrangement, not fabrication; only real units).

Two levels: Track-level and role-level
--------------------------------------
Two family members act on the Track (unit) arrangement and are IMPLEMENTED as
``Track -> Track``: ``grid-shuffle`` and ``phase-rotate``. The other two act in
ROLE space — they were correctly REFUSED before build-order step c because "role"
(the unit→anchor assignment produced by F/anchors, spec §4/§5) did not exist.
Step c built anchors + the coupling, so they are now ACTIVATED here, defined
strictly through the gauge-invariant anchor channel (I-2):

* ``role-permute`` (``(Track, world) -> Arrangement``): couple the track's
  prototypes to the frozen anchors (world.couple, a pure-GW transport map), then
  PERMUTE the anchor columns of that coupling — i.e. reassign which learned ROLE
  each prototype plays. The permuted coupling no longer matches the barycentric
  geometry, so transport (T1) and the occupancy terms move. The filterbank band
  is NOT used as a role (spec §2 step 3); the role is the anchor assignment.
* ``cross-track-swap`` (``([Track,Track], world) -> Arrangement``): couple BOTH
  tracks to the SAME frozen anchors and swap a subset of ANCHOR ROWS of the two
  occupancies. The only thing that crosses the track boundary is anchor-space
  (role) mass — gauge-invariant, I-2-legal. No raw cross-track coordinate/cost is
  ever formed, and no foreign unit is injected into a single-``track_id`` Track
  (the output is an ``Arrangement`` in shared role space, not a Track), so the
  single-source schema (I-12) is not violated either.

Both role-level ops return an ``Arrangement`` (anchor×slot occupancy + transport
scalar + the real ``mass_sources``) — the object F's occupancy terms consume —
rather than a Track, because a role-space perturbation has no faithful single-Track
realization. ``assert_arrangement_real`` is the I-6 guard for these ops: the
occupancy is assembled ONLY from real tracks' couplings (no fabrication) and every
contributing ``track_id`` is a real input id.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Tuple

import numpy as np

from ets.ingestion.track import CostStructure, Track
from ets.geometry import roles
from ets.functional import ot
from ets.training.world import WorldFreeze, _occ


# --------------------------------------------------------------------------
# deterministic sub-seeding (seedable determinism, spec §6 requirement)
# --------------------------------------------------------------------------

def _subseed(seed: int, label: str, track_id: int) -> int:
    """A stable 64-bit sub-seed from (seed, label, track_id). Same inputs →
    identical stream, so every scramble is a pure, reproducible function."""
    h = hashlib.sha256(f"{int(seed)}|{label}|{int(track_id)}".encode()).digest()
    return int.from_bytes(h[:8], "little")


def _rebuild(src: Track, *, units, masses, timbre, pitch, metric, prov,
             seed: int) -> Track:
    """Assemble a scramble output Track from transformed arrays.

    Cost structures are RE-BUILT from the (transformed) descriptors within the
    SAME single track_id — so the negative is self-consistent with its own
    arrangement and stays I-2-clean (single-track, within-track normalized). The
    beat_grid (the master clock, immutable) is shared by reference; scrambles are
    pure and never mutate it.
    """
    tid = src.track_id
    ct = CostStructure.build(tid, "timbre", np.ascontiguousarray(timbre),
                             np.random.default_rng(_subseed(seed, "C_timbre", tid)))
    cp = CostStructure.build(tid, "pitchclass", np.ascontiguousarray(pitch),
                             np.random.default_rng(_subseed(seed, "C_pitch", tid)))
    cm = CostStructure.build(tid, "metrical", np.ascontiguousarray(metric),
                             np.random.default_rng(_subseed(seed, "C_metric", tid)))
    return Track(track_id=tid, units=units, masses=masses,
                 C_timbre=ct, C_pitchclass=cp, C_metrical=cm,
                 beat_grid=src.beat_grid, provenance_index=prov,
                 n_samples=src.n_samples, sr=src.sr)


# --------------------------------------------------------------------------
# inventory bookkeeping (I-6: only real units; re-arrangement, not fabrication)
# --------------------------------------------------------------------------

def content_keys(track: Track) -> Counter:
    """Multiset of CONTENT identities in ``track``.

    A content key ties a row to a REAL audio unit: its provenance triple
    ``(track_id, src_start, src_end, band)`` (the source-audio link, I-12) plus
    the derived content that must travel with that audio unchanged — its ``mass``
    and its timbre / pitch-class descriptors. Arrangement fields (phase, bar,
    slot, metrical desc) are deliberately EXCLUDED: a scramble is allowed to move
    them. Fabrication (a new source span, an invented descriptor, an altered
    mass) changes a key and is caught by ``assert_inventory_preserved``.
    """
    p = track.provenance_index
    m = track.masses
    tb = track.C_timbre.desc
    pc = track.C_pitchclass.desc
    keys: List[Tuple] = []
    for r in range(len(p)):
        keys.append((
            int(p["track_id"][r]), int(p["src_start"][r]),
            int(p["src_end"][r]), int(p["band"][r]),
            np.asarray(m[r]).tobytes(),
            np.ascontiguousarray(tb[r]).tobytes(),
            np.ascontiguousarray(pc[r]).tobytes(),
        ))
    return Counter(keys)


def assert_inventory_preserved(inputs: List[Track], output: Track) -> None:
    """I-6 executable core: ``output`` is a re-arrangement of the REAL units in
    ``inputs`` — nothing external, nothing fabricated, nothing lost.

    (a) no external data / no fabrication: every output unit is a real input unit
        (output content multiset ⊆ input content multiset).
    (c) inventory preserved: the multisets are EQUAL (a bijection — no unit is
        dropped or duplicated; the arrangement changed, the inventory did not).

    Raises AssertionError on any violation. Both branches are exercised
    (proved non-vacuous) by the I-6 manifest check.
    """
    inp: Counter = Counter()
    for t in inputs:
        inp.update(content_keys(t))
    out = content_keys(output)

    extra = out - inp  # keys where output exceeds input (external / fabricated)
    assert not extra, (
        f"scramble introduced {sum(extra.values())} unit(s) absent from the real "
        f"input inventory — external data / fabrication (I-6)")
    assert out == inp, (
        "scramble did not preserve the unit inventory (content multiset "
        "mismatch: a unit was dropped, duplicated, or altered) — I-6")


# --------------------------------------------------------------------------
# the fixed family registry (spec §6 — FIXED IN PREREG; enumerated, closed)
# --------------------------------------------------------------------------

# The pre-registered family: EXACTLY these four names (spec §6). This is the
# closed set the training loop may draw from; ``assert_family_fixed`` refuses any
# addition or removal. Fixing this set is a PREREG obligation (see PREREG.md,
# "Scramble family (training comparison class)").
PREREGISTERED_FAMILY = frozenset(
    {"grid-shuffle", "role-permute", "phase-rotate", "cross-track-swap"})

# Presentation order (for docs / prereg); the authority for membership is the set.
FAMILY_ORDER = ("grid-shuffle", "role-permute", "phase-rotate", "cross-track-swap")


@dataclass(frozen=True)
class ScrambleOp:
    name: str
    arity: str            # "track"  (Track -> Track)  |  "corpus" ([Track] -> Track)
    breaks: str           # rationale: which equilibrium property it disarranges
    status: str           # "implemented" | "blocked_on_c"
    fn: Callable          # the operation; blocked ops raise NotImplementedError


_REGISTRY: Dict[str, ScrambleOp] = {}


def register(name: str, arity: str, breaks: str, status: str):
    """Decorator: register a scramble op. Registration is the ONLY way an op
    enters the family, so a new scrambler cannot be smuggled past the closed-set
    check — it lands in ``_REGISTRY`` and ``assert_family_fixed`` then bites."""
    def deco(fn: Callable) -> Callable:
        if name in _REGISTRY:
            raise ValueError(f"scramble op already registered: {name}")
        _REGISTRY[name] = ScrambleOp(name, arity, breaks, status, fn)
        return fn
    return deco


def family() -> List[ScrambleOp]:
    """The registered family, in presentation order."""
    return [_REGISTRY[n] for n in FAMILY_ORDER if n in _REGISTRY]


def registry_names() -> frozenset:
    return frozenset(_REGISTRY)


def assert_family_fixed() -> None:
    """I-6 (family fixed in PREREG): the registered set is EXACTLY the
    pre-registered family — enumerated and closed. Any unregistered addition or
    any removal raises. This is what makes the comparison class a fixed estimator
    degree of freedom rather than an open-ended knob."""
    got = frozenset(_REGISTRY)
    assert got == PREREGISTERED_FAMILY, (
        "scramble family drifted from the fixed PREREG set (I-6). "
        f"registered={sorted(got)} prereg={sorted(PREREGISTERED_FAMILY)}")


# --------------------------------------------------------------------------
# TRACK-LEVEL family members
# --------------------------------------------------------------------------

@register(
    "grid-shuffle", arity="track", status="implemented",
    breaks="metrical placement — within each band, real units are re-dealt to "
           "different metrical slots, so the pairing of a unit to its beat/bar "
           "position (groove) is destroyed while the band/role inventory and the "
           "metrical grid itself are untouched.")
def grid_shuffle(track: Track, seed: int = 0) -> Track:
    """Re-arrange WHICH real unit sits at each metrical slot, permuting content
    WITHIN each band (role/channel left intact; metrical grid left intact).

    Concretely: the arrangement lattice (units' slot/band/phase/bar/level and the
    provenance band/track_id/unit_id) is held fixed, and the CONTENT bundle
    (source span, mass, timbre & pitch-class descriptors) is permuted within each
    band. Because the permutation stays within a band, ``provenance.band`` still
    equals ``units.band`` and ``unit_id`` stays positional — the output is a
    well-formed single-source Track (I-12 holds). Breaks metrical placement.
    """
    n = len(track.units)
    bands = track.units["band"]
    ub = np.unique(bands)
    rng = np.random.default_rng(_subseed(seed, "grid-shuffle", track.track_id))

    perm = np.arange(n)
    for b in ub:
        idx = np.where(bands == b)[0]
        perm[idx] = idx[rng.permutation(len(idx))]

    # arrangement lattice unchanged; provenance band/track/unit_id unchanged
    new_units = track.units.copy()
    new_prov = track.provenance_index.copy()
    # move only the CONTENT: source span follows the permuted unit
    new_prov["src_start"] = track.provenance_index["src_start"][perm]
    new_prov["src_end"] = track.provenance_index["src_end"][perm]

    new_masses = track.masses[perm]
    new_timbre = track.C_timbre.desc[perm]
    new_pitch = track.C_pitchclass.desc[perm]
    new_metric = track.C_metrical.desc.copy()   # metrical position = arrangement, fixed

    return _rebuild(track, units=new_units, masses=new_masses, timbre=new_timbre,
                    pitch=new_pitch, metric=new_metric, prov=new_prov, seed=seed)


@register(
    "phase-rotate", arity="track", status="implemented",
    breaks="gauge phase — an INCOHERENT per-band rotation of the metrical circle. "
           "A single GLOBAL beat-phase shift is pure gauge (spec §3) and leaves F "
           "invariant; making the rotation differ per band destroys the single "
           "consistent gauge-phase frame the track settles into (T5 gauge-fixing) "
           "and the cross-band phase lock, without touching any audio content.")
def phase_rotate(track: Track, seed: int = 0) -> Track:
    """Rotate the metrical phase by a DIFFERENT offset per band (incoherent),
    breaking the track's single gauge-phase frame.

    Content is untouched (same real units, same masses, same source spans,
    same timbre/pitch descriptors); only the arrangement coordinate ``phase``
    (and the ``C_metrical`` descriptor derived from it) is rotated. A global
    (single-offset) rotation would be pure gauge and F-invariant — hence useless
    as a negative — so the offsets are per-band and require ≥2 bands.
    """
    bands = track.units["band"]
    ub = np.unique(bands)
    if len(ub) < 2:
        # A single band admits only a GLOBAL phase shift, which is pure gauge
        # (F-invariant) and cannot break equilibrium. Report, do not fake.
        raise ValueError(
            "phase-rotate needs >=2 bands: with one band the only phase rotation "
            "is a global gauge shift (F-invariant), not an equilibrium-breaking "
            "negative (spec §3 gauge law)")
    rng = np.random.default_rng(_subseed(seed, "phase-rotate", track.track_id))
    # per-band offsets in (0,1), bounded away from 0/1 so each band truly moves
    offs = rng.uniform(0.05, 0.95, size=len(ub))
    off_by_band = {int(b): float(o) for b, o in zip(ub, offs)}
    delta = np.array([off_by_band[int(b)] for b in bands])

    new_units = track.units.copy()
    new_phase = (track.units["phase"] + delta) % 1.0
    new_units["phase"] = new_phase
    new_metric = new_phase.reshape(-1, 1).copy()

    return _rebuild(track, units=new_units, masses=track.masses.copy(),
                    timbre=track.C_timbre.desc.copy(),
                    pitch=track.C_pitchclass.desc.copy(),
                    metric=new_metric,
                    prov=track.provenance_index.copy(), seed=seed)


# --------------------------------------------------------------------------
# ROLE-LEVEL family members (ACTIVATED at step c: anchors + coupling exist)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Arrangement:
    """A scored arrangement in shared role space: what F's occupancy terms
    consume. ``O`` is the anchor×slot occupancy (gauge-invariant, I-2), ``t1`` the
    transport cost to the anchors, ``mass_sources`` the real input ``track_id``\\s
    whose couplings supplied the mass (I-6 provenance for role-space ops).

    (rev-r1) ``phase_charge`` and ``succ_reward`` are the FIBER scalars F now reads
    directly (spec §5 rev-r1): the gauge-aligned phase-displacement charge and the
    unit-successor run-continuation reward of the unit-resolved arrangement. They
    default to the real-track values (charge 0, reward 1) — a role-space op that
    does not disturb the metrical fiber (role-permute) carries them unchanged and
    is separated by T1's GW transport instead."""
    O: np.ndarray
    t1: float
    mass_sources: Tuple[int, ...]
    phase_charge: float = 0.0
    succ_reward: float = 1.0


def assert_arrangement_real(arr: "Arrangement", real_ids) -> None:
    """I-6 for role-space ops: the arrangement is assembled ONLY from real tracks'
    couplings — no fabricated mass, no external source. Every contributing
    ``track_id`` is a real input id, occupancy is finite/non-negative, and total
    mass is a convex combination of real per-track occupancies (each sums to ~1)."""
    real = set(int(i) for i in real_ids)
    assert set(int(i) for i in arr.mass_sources) <= real, (
        f"arrangement draws mass from a non-real source {arr.mass_sources} "
        f"(external data / fabrication) — I-6")
    O = np.asarray(arr.O)
    assert np.all(np.isfinite(O)) and np.all(O >= -1e-12), \
        "arrangement occupancy is non-finite/negative (fabrication) — I-6"
    assert 0.5 < float(O.sum()) < 1.5, \
        f"arrangement mass {float(O.sum())} is not a convex mix of real tracks — I-6"


def _derangement(M: int, rng: np.random.Generator) -> np.ndarray:
    """A permutation of range(M) with no fixed point when M>1 (a genuine
    reassignment, not a silent identity)."""
    perm = rng.permutation(M)
    while M > 1 and np.any(perm == np.arange(M)):
        perm = rng.permutation(M)
    return perm


@register(
    "role-permute", arity="role", status="implemented",
    breaks="role assignment — permutes which learned ROLE (anchor) each prototype "
           "plays by deranging the anchor columns of the pure-GW coupling. The "
           "permuted coupling no longer matches the barycentric geometry, so "
           "transport (T1) and the occupancy terms move; the filterbank band is "
           "NOT used as a role (spec §2 step 3). Needs the step-c anchor map.")
def role_permute(track: Track, world: WorldFreeze, seed: int = 0) -> Arrangement:
    """Permute the unit→role assignment via the frozen anchor coupling (spec §4/§5)."""
    from . import fiber
    P = roles.extract_prototypes(track, seed=0)
    pi = world.couple(P)
    perm = _derangement(world.M, np.random.default_rng(
        _subseed(seed, "role-permute", track.track_id)))
    pi2 = pi[:, perm]
    O = _occ(pi2, P)
    t1 = ot.gw_distortion(P.cost, world.D, pi2)
    fib = fiber.role_permute_fiber(track, P, world)   # fiber unchanged: charge 0, reward 1
    return Arrangement(O=O, t1=float(t1), mass_sources=(int(track.track_id),),
                       phase_charge=fib["phase_charge"], succ_reward=fib["succ_reward"])


@register(
    "cross-track-swap", arity="role_pair", status="implemented",
    breaks="anchor-mediated cross-track coherence — couples BOTH tracks to the "
           "same frozen anchors and swaps a subset of anchor (role) ROWS of their "
           "occupancies. Only gauge-invariant anchor-space mass crosses the track "
           "boundary (I-2-legal); no raw cross-track cost, no foreign unit in a "
           "single-track Track. Needs the step-c anchor channel.")
def cross_track_swap(tracks: List[Track], world: WorldFreeze,
                     seed: int = 0) -> Arrangement:
    """Swap real units between two tracks ONLY through the gauge-invariant anchor
    channel (spec §3/§4): mix anchor rows of two co-coupled occupancies.

    (rev-r1) The swap decision (which anchor rows) also drives a UNIT-RESOLVED
    graft whose run-continuation the fiber reads: at swapped roles, A's units are
    replaced by real B units of the SAME anchor role. A grafted B-unit is no source
    successor of any A-unit → the run breaks → succ_reward < 1. Only role identity
    crosses the boundary (I-2); the successor test is within-track content
    adjacency, so no foreign coordinate is compared."""
    from . import fiber
    ta, tb = tracks[0], tracks[1]
    Pa = roles.extract_prototypes(ta, seed=0)
    Pb = roles.extract_prototypes(tb, seed=0)
    pia, pib = world.couple(Pa), world.couple(Pb)
    Oa, Ob = _occ(pia, Pa), _occ(pib, Pb)
    sub = _subseed(seed, "cross-track-swap", ta.track_id)
    rng = np.random.default_rng(sub)
    Q = rng.random(world.M) < 0.5
    O = np.where(Q[:, None], Ob, Oa)             # only anchor-space mass crosses
    wj = float(Q.mean())
    # T1 = mass-weighted sum of each track's OWN transport (no cross-track cost)
    t1 = (1.0 - wj) * ot.gw_distortion(Pa.cost, world.D, pia) \
        + wj * ot.gw_distortion(Pb.cost, world.D, pib)
    fib = fiber.cross_track_swap_fiber([ta, tb], [Pa, Pb], world, Q, seed=sub)
    return Arrangement(O=O, t1=float(t1),
                       mass_sources=(int(ta.track_id), int(tb.track_id)),
                       phase_charge=fib["phase_charge"], succ_reward=fib["succ_reward"])
