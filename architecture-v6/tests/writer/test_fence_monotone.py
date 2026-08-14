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
    operator's ratification question, answered by exhaustion."""
    mask = {0: 1.0, 1: 1.0}
    pins = [None] + [(t, p) for t in TRACKS
                     for r in (1, 2) for p in itertools.combinations(UNITS, r)]
    slot_maps = [
        {0: (10,)},
        {0: (10, 11), 1: (12,)},
        {1: (13,)},
        {0: (), 1: (10,)},                       # an empty slot entry admits nothing
        {5: (10,)},                              # a slot nobody asks about
    ]
    for slot in SLOTS:
        for pin in pins:
            base = _admitted(_fence(mask, 1.0, unit_pin=pin), slot)
            for sp in slot_maps:
                got = _admitted(_fence(mask, 1.0, unit_pin=pin, slot_pin=sp), slot)
                assert got <= base, (
                    "slot_pin ADMITTED %s that (i)+(ii) excluded — the fence widened "
                    "(slot=%s pin=%s slot_pin=%s)" % (sorted(got - base), slot, pin, sp))


def test_every_clause_combination_is_monotone():
    """The full lattice: for each of the three clauses, turning it ON is a
    subset of leaving it OFF, whatever the others are doing."""
    mask_on = {0: 1.0, 1: 1.0}
    mask_off = {t: 1.0 for t in TRACKS}          # (i) admitting more tracks
    pin = (0, (10, 11))
    sp = {0: (10,), 1: (11, 12)}
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
                                 slot_pin={0: (11,)}), 0)
    assert len(with_slot) < len(with_pin), "(iii) excluded no candidate"
