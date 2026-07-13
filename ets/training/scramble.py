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

Implemented now vs blocked-on-c
-------------------------------
Two family members are cleanly definable on the *current* (pre-anchor) Track
schema and are IMPLEMENTED here: ``grid-shuffle`` and ``phase-rotate``. The other
two are BLOCKED on build-order step c (anchors + F role assignment) and are
registered as blocked stubs that REFUSE to run rather than fake a proxy:

* ``role-permute`` needs the learned ROLE assignment (spec §4/§5: unit→role→
  slot). "Role" does not exist until anchors/F assign it. The fixed filterbank
  ``band`` is explicitly NOT a role (spec §2 step 3 forbids letting the band
  decomposition pre-decide roles). Permuting bands would fabricate a role F never
  assigned — forbidden. Blocked until step c/d.
* ``cross-track-swap`` needs to move a unit across a track boundary. The only
  I-2-legal channel for cross-track traffic is the gauge-invariant anchor/role
  representation (spec §3/§4); a direct cross-track descriptor cost violates I-2,
  and honest foreign provenance in a single ``track_id`` Track violates the
  single-source schema (I-12 / ``assert_provenance_complete``). Blocked until the
  anchor channel exists (step c). See the WALL note in PREREG.md.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Tuple

import numpy as np

from ets.ingestion.track import CostStructure, Track


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


def _blocked(name: str, reason: str) -> Callable:
    """Build a stub that REFUSES to run (WALL PROTOCOL: report the dependency,
    do not fabricate a proxy)."""
    def stub(*_args, **_kwargs):
        raise NotImplementedError(f"scramble '{name}' is blocked-on-c: {reason}")
    return stub


# --------------------------------------------------------------------------
# IMPLEMENTED family members
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
# BLOCKED-on-c family members (registered, refuse to run — never faked)
# --------------------------------------------------------------------------

register(
    "role-permute", arity="track", status="blocked_on_c",
    breaks="role assignment — permute which learned ROLE each unit plays. "
           "Requires the anchor/F role map (unit→role→slot, spec §4/§5); the "
           "fixed filterbank band is NOT a role (spec §2 step 3), so this cannot "
           "be faked on bands. Blocked until step c/d.",
)(_blocked(
    "role-permute",
    "'role' is assigned by anchors/F (spec §4,§5), which do not exist until "
    "build-order step c/d; the filterbank band is explicitly not a role "
    "(spec §2 step 3), so permuting bands would fabricate a role F never "
    "assigned. Implement once the role map exists."))

register(
    "cross-track-swap", arity="corpus", status="blocked_on_c",
    breaks="anchor-mediated cross-track coherence — swap real units between "
           "tracks so the within-track coherence that anchors certify is broken. "
           "Legal cross-track transfer requires the gauge-invariant anchor/role "
           "channel (spec §3/§4); blocked until step c.",
)(_blocked(
    "cross-track-swap",
    "moving a unit across a track boundary legally requires the gauge-invariant "
    "anchor/role channel (spec §3,§4). A direct cross-track descriptor cost "
    "violates I-2, and honest foreign provenance in a single-track_id Track "
    "violates the single-source schema (I-12 / assert_provenance_complete). "
    "Implement once anchors exist (step c). See PREREG.md wall note."))
