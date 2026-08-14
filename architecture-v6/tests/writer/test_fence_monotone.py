"""THE FENCE NEVER WIDENS — §2.1's three comparisons can only restrict.

The operator's ratification question for `slot_pin` (2026-08-14): *"can the
slot_pin clause ever ADMIT something the other two clauses would exclude, or can
it only restrict further? Only restricts => the 'fence never widens' invariant
holds and the amendment is purely descriptive. Can widen => that needs its own
check and its own ruling."*

It can only restrict, and this pins it by exhaustion rather than by reading the
code: over a candidate grid, enabling any clause yields a SUBSET of leaving it
off, for every combination of the three. That is the invariant the amended §2.1
depends on — a fence that could widen would make "no cast outside ClampTerms"
(Amendment 4 R1) unprovable from the rule alone.

RE-KEYED 2026-08-14 (operator ruling: "strict per-slot pinning wins"):
`slot_pin` used to be keyed by slot ALONE (`{slot: (unit_ids,)}`), which is
global across tracks — on a bridge two members share the one map, and a
candidate on track A could be admitted by track B's own entry at the same
slot index if A's unit id happened to also be a member of B's set (measured on
worlds that number every track 0..N-1, which is every stock/demo world here:
straight-play spread inside a bar 55-63, the SAME bridge bar's spread 87-185
once the two windows diverged). `slot_pin` is now keyed by (track_id, slot),
so each pair member gets its own map entries and can never satisfy the other's
slot from its own material. `test_slot_pin_is_track_scoped` below pins the
new key shape directly, on the same overlapping-id grid this file already
uses (TRACKS 0-2 all share UNITS 10-13, exactly like every stock world's
0..N-1 numbering) — a regression back to a slot-only key is what this test
exists to catch.
"""
from __future__ import annotations

import itertools

from ets.writer.clamp import clamp0
from ets.writer.realize import _admits


TRACKS = (0, 1, 2)
UNITS = (10, 11, 12, 13)
SLOTS = (-1, 0, 1)                      # -1 = "no slot known" (the batch path)
CANDIDATES = tuple(itertools.product(TRACKS, UNITS))


def _fence(mask, openness, unit_pin=None, slot_pin=None):
    return clamp0(track_mask=mask, openness=openness,
                  unit_pin=unit_pin, slot_pin=slot_pin)


def _admitted(fence, slot):
    return {c for c in CANDIDATES if _admits(fence, c, slot)}


def test_unit_pin_only_restricts():
    """Adding (ii) to (i) can only shrink the admitted set."""
    mask = {0: 1.0, 1: 1.0}
    for slot in SLOTS:
        base = _admitted(_fence(mask, 1.0), slot)
        for pin_track in TRACKS:
            for r in range(1, len(UNITS) + 1):
                for pinned in itertools.combinations(UNITS, r):
                    got = _admitted(_fence(mask, 1.0, unit_pin=(pin_track, pinned)), slot)
                    assert got <= base, (
                        "unit_pin admitted %s that the bare fence excluded"
                        % sorted(got - base))


def test_slot_pin_only_restricts():
    """Adding (iii) to (i)+(ii) can only shrink the admitted set — the
    operator's ratification question, answered by exhaustion. Keys are
    (track_id, slot) — the 2026-08-14 re-keying — so every slot_pin map here
    is over the (track, slot) grid, not slot alone."""
    mask = {0: 1.0, 1: 1.0}
    pins = [None] + [(t, p) for t in TRACKS
                     for r in (1, 2) for p in itertools.combinations(UNITS, r)]
    slot_maps = [
        {(0, 0): (10,)},
        {(0, 0): (10, 11), (0, 1): (12,)},
        {(1, 1): (13,)},
        {(0, 0): (), (1, 0): (10,)},              # an empty slot entry admits nothing
        {(0, 5): (10,)},                          # a slot nobody asks about
        # entries for MULTIPLE tracks at the SAME slot index — the shape a
        # bridge produces (one entry per pair member per slot)
        {(0, 0): (10,), (1, 0): (11,)},
        {(0, 0): (10, 11), (1, 0): (12, 13)},
    ]
    for slot in SLOTS:
        for pin in pins:
            base = _admitted(_fence(mask, 1.0, unit_pin=pin), slot)
            for sp in slot_maps:
                got = _admitted(_fence(mask, 1.0, unit_pin=pin, slot_pin=sp), slot)
                assert got <= base, (
                    "slot_pin ADMITTED %s that (i)+(ii) excluded — the fence widened "
                    "(slot=%s pin=%s slot_pin=%s)" % (sorted(got - base), slot, pin, sp))


def test_slot_pin_is_track_scoped():
    """THE per-track-keying property itself (2026-08-14 amendment), on the
    same overlapping-unit-id grid every stock/demo world in this repo uses
    (TRACKS 0-2 all number units 10-13): a (track, slot) entry for track 0
    must NEVER admit track 1's candidate at the same slot, even when track 1
    owns an identically-numbered unit that IS in track 0's entry — and vice
    versa. This is exactly the cross-track leak the amendment closes; a
    regression back to a slot-only key (mutating `_admits` to look up
    `sp.get(slot)` instead of `sp.get((tid, slot))`) makes this test FAIL —
    see the PREREG's bite-by-mutation record for the captured output."""
    mask = {0: 1.0, 1: 1.0}
    # track 0's slot 0 admits unit 10 only; track 1's slot 0 admits unit 11
    # only. Both tracks are fully admitted by (i); nothing else restricts.
    sp = {(0, 0): (10,), (1, 0): (11,)}
    fence = _fence(mask, 1.0, slot_pin=sp)
    assert _admits(fence, (0, 10), 0) is True,  "track 0 must play its OWN slot-0 unit"
    assert _admits(fence, (0, 11), 0) is False, (
        "track 0 admitted unit 11 at slot 0 — that unit belongs to track 1's "
        "own slot-0 entry, not track 0's; the fence leaked across tracks")
    assert _admits(fence, (1, 11), 0) is True,  "track 1 must play its OWN slot-0 unit"
    assert _admits(fence, (1, 10), 0) is False, (
        "track 1 admitted unit 10 at slot 0 — that unit belongs to track 0's "
        "own slot-0 entry, not track 1's; the fence leaked across tracks")
    # a track with NO entry at this slot is untouched by clause (iii) — only
    # (i)/(ii) can restrict it, exactly like the slot-only scheme's absent-key
    # behaviour, just scoped per track now.
    assert _admits(fence, (0, 12), 0) is False, (
        "track 0's slot-0 entry is (10,); unit 12 is not a member and must "
        "be excluded")
    open_fence = _fence({0: 1.0, 1: 1.0, 2: 1.0}, 1.0, slot_pin=sp)
    assert _admits(open_fence, (2, 12), 0) is True, (
        "track 2 has NO slot-0 entry at all; clause (iii) must not touch it "
        "(clauses (i)/(ii) admit it here, so only (iii) is under test)")


def test_every_clause_combination_is_monotone():
    """The full lattice: for each of the three clauses, turning it ON is a
    subset of leaving it OFF, whatever the others are doing."""
    mask_on = {0: 1.0, 1: 1.0}
    mask_off = {t: 1.0 for t in TRACKS}          # (i) admitting more tracks
    pin = (0, (10, 11))
    sp = {(0, 0): (10,), (1, 1): (11, 12)}
    for slot in SLOTS:
        for m_on, p_on, s_on in itertools.product((False, True), repeat=3):
            fence = _fence(mask_on if m_on else mask_off, 1.0,
                           unit_pin=pin if p_on else None,
                           slot_pin=sp if s_on else None)
            got = _admitted(fence, slot)
            for which, off in (("track", (mask_off, pin if p_on else None, sp if s_on else None)),
                               ("unit_pin", (mask_on if m_on else mask_off, None, sp if s_on else None)),
                               ("slot_pin", (mask_on if m_on else mask_off, pin if p_on else None, None))):
                looser = _admitted(_fence(off[0], 1.0, unit_pin=off[1], slot_pin=off[2]), slot)
                assert got <= looser, (
                    "turning %s ON admitted %s the looser fence excluded"
                    % (which, sorted(got - looser)))


def test_monotonicity_check_is_non_vacuous():
    """Each clause actually removes candidates on this grid, so the subset
    assertions above are not trivially satisfied by nothing ever changing."""
    mask = {0: 1.0, 1: 1.0}
    bare = _admitted(_fence(mask, 1.0), 0)
    assert bare, "the bare fence admitted nothing; the grid proves nothing"
    assert len(bare) < len(CANDIDATES), "(i) excluded no candidate"
    with_pin = _admitted(_fence(mask, 1.0, unit_pin=(0, (10,))), 0)
    assert len(with_pin) < len(bare), "(ii) excluded no candidate"
    with_slot = _admitted(_fence(mask, 1.0, unit_pin=(0, (10,)),
                                 slot_pin={(0, 0): (11,)}), 0)
    assert len(with_slot) < len(with_pin), "(iii) excluded no candidate"
    # non-vacuity of the PER-TRACK shape specifically: a two-track slot_pin
    # (the bridge shape) must exclude something beyond what a single-track
    # slot_pin excludes, i.e. clause (iii)'s track-0 entry does not also
    # (incorrectly) restrict track 1 — restated positively: track 1 stays
    # admitted at slot 0 under a slot_pin that only names track 0 there.
    with_other_track_slot = _admitted(
        _fence(mask, 1.0, unit_pin=(0, (10,)), slot_pin={(0, 0): (10,)}), 0)
    assert (1, 10) in with_other_track_slot, (
        "a slot_pin entry naming ONLY track 0 at slot 0 excluded track 1's "
        "candidate too — clause (iii) is not track-scoped")
