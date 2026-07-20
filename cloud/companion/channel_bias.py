"""Per-channel SOFT bias (PREREG-channel-bias-squares, REV2 — bidirectional).

A "channel" is a source track. Biasing channel T applies a SOFT lean on track-T
material: an additive log-weight on track-T's candidate units inside the Layer-0
FIBER choice measure — the distribution over the pooled channels at each beat
(``ets.writer.tilt.fiber_choice_logits``). The Gibbs settlement PERCEIVES the lean
and accommodates it (it draws track-T units more/less often where they are
candidates, and the run-continuation / other bands settle around that); NOTHING is
pinned, no slot is forced, the writer stays fully generative. This is the operator
mechanism correction: a soft prior the settlement reads, not a hard I-7 clamp.

The lean rides the ONE ``TiltTerms`` the writer already consumes (I-1) via a
``channel_logbias`` field ({track_id -> additive log-weight}); there is no second
control channel, no new lane, no clamp. amplify ∈ [-1, 1] is the bias STRENGTH,
now BIDIRECTIONAL (REV2, operator-directed 2026-07-19): POSITIVE amplifies (a
positive addend up-weights that channel's candidates in the softmax), NEGATIVE
soft-damps / down-weights it (a negative addend). Zero / empty ⇒ no addend ⇒ the
fiber draw is byte-identical.

GAUGE INVARIANCE (honest note): the fiber choice is a softmax, so adding a
CONSTANT to every channel's log-weight leaves the draw unchanged — only the
RELATIVE β between channels matters. Amplifying one channel is thus the same move
as damping all the rest; bidirectional simply exposes both handles explicitly so
one gesture can lift one channel AND cut another. Damp is SOFT: a negative addend
down-weights but does not hard-mute — a channel with real candidates never goes to
exactly zero unless F and the other channels naturally exclude it.

STRENGTH SCALE (derived, not hand-set): the per-unit-amplify log-weight is F's own
metrical phase-charge weight ``LAMBDA['T1p']`` (read live), so amplify=1 leans a
channel by one natural "unit of preference" on the same log-odds scale the fiber
energies live on — strong but soft (F's phase / continuation terms still compete,
and a channel with no candidate at a beat gets no lean there). No magic constant.

DEGENERACY IS THE OPEN QUESTION (measured, Phase-1 gate). A soft lean can COLLAPSE
if the channels overlap in the pooled candidate set or F's energies dominate. The
verifier measures the provenance pull curve; if it is mushy, that is the honest H0
(keep the XY pad; disarm the squares) — we do NOT fall back to the hard clamp.

REV3 — MULTI-GRAIN FIELD BIAS (operator-directed 2026-07-19). The same soft
bidirectional lean now resolves at TWO drill grains, ADDITIVELY, on the ONE
TiltTerms (single carrier, I-1): addend(candidate) = β_track[candidate.track_id] +
β_unit[candidate.unit_id]. The UNIT grain is the operator's ultimate "channel" (a
beat-normalized sound unit); the TRACK grain is its ROLL-UP (biasing a track leans
all its units). A candidate biased at both grains gets the SUM. The carrier is a
single tagged datum {"track": {tid->β}, "unit": {uid->β}} (``field_logbias``); the
writer still receives ONE per-candidate addend array. The track grain is bit-for-
bit unchanged from REV2 (``channel_logbias``), so its ratified gate keeps holding.

ROLE IS NOT A FIBER GRAIN (REV3 wall, first-principles, MEASURED). A per-candidate
addend can only steer an attribute that VARIES within a fiber choice set. Within one
choice (realize.FiberThreader._choose(k, b)) every candidate shares the settled role
k (the choice set is exactly "role-k units in band b"), and k itself is chosen by the
O-block (place_slot: k = argmax(col·B[:,b])), which the fiber never revisits. So a
role addend is a softmax CONSTANT — it cancels in the Gumbel-argmax and leaves the
draw byte-identical even at nonzero bias (inert). Role provenance is an O-BLOCK
property; its natural steering channel is the REGION lane (φ_region is per-anchor =
per-role, an O-block tilt through λ_region), which already exists as a first-class
control. Forcing role into the fiber addend would be a silent no-op; it is surfaced,
not built (see PREREG-field-bias-REV3-unit-grain.md).
"""
from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np


def channel_tids(world) -> List[int]:
    """Channel ordering: channel i is the i-th track_id in ascending order —
    stable and world-independent, so a bias vector's component i always addresses
    the same channel."""
    return sorted(int(t.track_id) for t in world.tracks)


def default_strength() -> float:
    """The per-unit-amplify log-weight = F's own metrical phase-charge weight
    (read live, so it tracks calibration). Derived scale, no hand-set constant."""
    from ets.functional.f import LAMBDA
    return float(LAMBDA["T1p"])


def channel_logbias(bias, tids: List[int], strength: Optional[float] = None
                    ) -> Optional[Dict[int, float]]:
    """Assemble the {track_id -> additive log-weight} soft-lean map for a
    per-channel amplify vector ∈ [-1, 1] (positive = amplify / up-weight,
    negative = soft damp / down-weight; REV2 bidirectional). Returns ``None``
    when nothing is biased (all-zero / empty ⇒ the writer's default fiber draw ⇒
    byte-identical).

    This is the TRACK grain of the field bias (REV3): biasing a track leans ALL
    of its candidate units — the ROLL-UP. It is UNCHANGED from REV2 (bit-for-bit)
    so the ratified track-grain gate keeps holding; REV3 only ADDS the finer
    UNIT grain (see ``grain_logbias`` / ``field_logbias``)."""
    b = np.asarray(bias, dtype=np.float64).reshape(-1)
    if b.size == 0 or not np.any(b != 0.0):
        return None
    if strength is None:
        strength = default_strength()
    out: Dict[int, float] = {}
    for ch in range(min(b.size, len(tids))):
        a = float(b[ch])
        if a != 0.0:
            # sign carries the direction: a>0 up-weights (amplify),
            # a<0 down-weights (soft damp) that channel's fiber candidates.
            out[int(tids[ch])] = float(strength) * a
    return out or None


def grain_logbias(amp, strength: Optional[float] = None
                  ) -> Optional[Dict[int, float]]:
    """Build a {key -> additive log-weight} soft-lean map from a keyed amplify
    map {key -> amplify∈[-1,1]}, β = strength·amplify (same derived F-scale as the
    track grain — ``default_strength`` = LAMBDA['T1p'], read live). This is the
    generic per-grain builder (REV3): the UNIT grain keys on ``unit_id``, the same
    soft bidirectional mechanism the track grain uses on ``track_id``. Returns
    ``None`` when nothing is biased (all-zero / empty ⇒ byte-identical).

    ``key`` is whatever addresses the grain's candidates (a ``unit_id`` for the
    UNIT grain = the operator's ultimate "channel"). The sign carries the
    direction (amplify vs soft damp), exactly as ``channel_logbias`` does."""
    if not amp:
        return None
    if strength is None:
        strength = default_strength()
    out: Dict[int, float] = {}
    for key, a in dict(amp).items():
        a = float(a)
        if a != 0.0:
            out[int(key)] = float(strength) * a
    return out or None


def field_logbias(track=None, unit=None, track_role=None
                  ) -> Optional[Dict[str, Dict]]:
    """Assemble the ONE multi-grain field-bias datum the writer consumes on its
    single ``TiltTerms.channel_logbias`` (REV3 + track_role prototype, single carrier
    / I-1):

        {"track": {track_id -> β}, "unit": {unit_id -> β},
         "track_role": {(track_id, role_k) -> β}}

    from the already-built per-grain WEIGHT maps (``track`` from ``channel_logbias``,
    ``unit`` from ``grain_logbias``, ``track_role`` from ``track_role_logbias``). At the
    fiber choice the writer resolves each candidate's addend ADDITIVELY over the grains
    present — ``β_track[c.track_id] + β_unit[c.unit_id] + β_track_role[(c.track_id, k)]``
    where ``k`` is the slot's settled role — so a candidate biased at several grains
    gets the SUM. Empty at EVERY grain ⇒ ``None`` ⇒ no addend ⇒ byte-identical.

    Grains carried are exactly those whose per-candidate value VARIES within a fiber
    choice set: the source track (roll-up), the unit (the ultimate "channel"), and the
    (track, slot-role) SUB-TRACK cell (leans track T only where it plays the settled
    role k). A per-candidate addend can only steer an attribute that distinguishes
    candidates; a PURE role of a choice set is fixed (it IS the set's identity), so a
    pure role is not a fiber grain — but (track, role) varies (via track) and does
    steer (PREREG-track-role-bias)."""
    grains: Dict[str, Dict] = {}
    if track:
        m = {int(k): float(v) for k, v in dict(track).items() if float(v) != 0.0}
        if m:
            grains["track"] = m
    if unit:
        m = {int(k): float(v) for k, v in dict(unit).items() if float(v) != 0.0}
        if m:
            grains["unit"] = m
    if track_role:
        m = {(int(k[0]), int(k[1])): float(v)
             for k, v in dict(track_role).items() if float(v) != 0.0}
        if m:
            grains["track_role"] = m
    return grains or None


def track_role_logbias(amp, strength: Optional[float] = None
                       ) -> Optional[Dict]:
    """Build a {(track_id, role_k) -> β} soft-lean map from a keyed amplify map
    {(track_id, role_k) -> amplify∈[-1,1]}, β = strength·amplify (same derived
    F-scale as every grain). This is the SUB-TRACK grain (PREREG-track-role-bias): it
    leans track T's candidates ONLY inside slots whose settled role is k — the first
    bias keyed on an EMERGENT structure (roles are training-emergent, unlike input-
    level track/unit). Returns ``None`` when nothing is biased (all-zero / empty ⇒
    byte-identical). The key is the pair (track_id, role_k), matched at the fiber
    choice against (candidate.track_id, slot_role)."""
    if not amp:
        return None
    if strength is None:
        strength = default_strength()
    out: Dict = {}
    for key, a in dict(amp).items():
        a = float(a)
        if a != 0.0:
            tid, role = key
            out[(int(tid), int(role))] = float(strength) * a
    return out or None
