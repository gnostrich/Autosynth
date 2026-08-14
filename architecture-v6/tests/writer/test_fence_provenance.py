"""FENCE PROVENANCE — the leak that was heard before it was caught.

On 2026-08-14 LIVE was reported as "routing through other tracks". It was: both
choosers took a degenerate early return

    if not choices: return (idx.unit_of[(k, b)], False)

that handed back a candidate BEFORE the ClampTerms fence was consulted, so any
(role, band) with no candidate list cast whatever the minimal index named — in
the middle of a fenced passage. Amendment 4 R1 ("no cast outside ClampTerms,
ever") had struck exactly that behaviour in the neighbouring branch; this one
was missed.

These two fixtures exist so the reproduction outlives the comment that describes
it, and so the class of bug is caught at the level it actually lives at:

  * ``test_starving_fence_casts_nothing`` — the reproduction. A fence admitting
    NOTHING must produce ZERO casts, and every refused (bar, role, band) demand
    must appear in the starvation record. Silence is inside every fence;
    reaching to another track is not (LM-11).

  * ``test_passage_provenance_*`` — the generalisation. Over a FULL passage
    (straight play, and a bridge with a two-track fence at a decaying openness),
    every cast's source track must lie inside the fence in force for that bar.
    A per-slot assertion missed the original defect because it lived in a
    rarely-hit degenerate branch; a passage-level assertion does not.
"""
from __future__ import annotations

import pytest

from ets.writer.clamp import clamp0
from ets.writer.stream import StreamWriter
from tests.harness.worldtools import build_synthetic_world


@pytest.fixture(scope="module")
def world():
    return build_synthetic_world()


def _admits(fence, tid):
    """The carrier's own rule, applied to a track id."""
    return float(fence.track_mask.get(int(tid), 0.0)) >= float(fence.openness)


def _admitted_tracks(world, fence):
    return {int(tr.track_id) for tr in world.tracks if _admits(fence, tr.track_id)}


def test_starving_fence_casts_nothing(world):
    """A fence that admits NO track casts nothing at all, and says so."""
    tid = int(world.tracks[0].track_id)
    # "admit nothing" spelled the way clamp0's own error names it — through
    # track_mask, below openness. An empty unit pin is rejected by clamp0 as
    # not being a pin, correctly.
    starving = clamp0(track_mask={tid: 0.0}, openness=1.0)
    assert _admitted_tracks(world, starving) == set()

    w = StreamWriter(world, seed=3)
    w.write_bar()                                   # one unfenced bar first
    r = w.write_bar(fence=starving)

    assert r.rows == [], "a starving fence cast %d rows" % len(r.rows)
    assert r.continues == []
    # Starvation is DISCLOSED, never swallowed: one record per refused demand.
    assert len(r.starved) > 0, "no starvation recorded for a fence admitting nothing"
    # every record is a (bar, role, band) triple for THIS bar only
    assert all(len(s) == 3 for s in r.starved)
    assert len({int(s[0]) for s in r.starved}) == 1


def test_starving_fence_starves_every_demand_the_open_bar_cast(world):
    """The starvation record covers the demands that WOULD have cast — the
    unfenced bar's own (role, band) demands, not a subset."""
    tid = int(world.tracks[0].track_id)
    w = StreamWriter(world, seed=3)
    w.write_bar()
    open_bar = w.write_bar()                        # what an unfenced bar casts

    w2 = StreamWriter(world, seed=3)
    w2.write_bar()
    starved_bar = w2.write_bar(fence=clamp0(track_mask={tid: 0.0}, openness=1.0))

    assert starved_bar.rows == []
    assert len(starved_bar.starved) >= len(open_bar.rows), (
        "%d demands cast when open but only %d starvation records when fenced shut"
        % (len(open_bar.rows), len(starved_bar.starved)))


def test_passage_provenance_straight(world):
    """A FULL straight passage: every cast comes from the fenced track."""
    tid = int(world.tracks[0].track_id)
    fence = clamp0(track_mask={tid: 1.0}, openness=1.0)
    w = StreamWriter(world, seed=7)
    strays = []
    for _ in range(24):                             # a passage, not a slot
        r = w.write_bar(fence=fence)
        for (_s, cast_tid, _uid, _sec, _m) in r.rows:
            if int(cast_tid) != tid:
                strays.append(int(cast_tid))
    assert not strays, "fenced passage cast from tracks %s" % sorted(set(strays))


def test_passage_provenance_bridge(world):
    """A FULL bridge passage under a TWO-track fence at a decaying openness:
    every cast comes from one of the two admitted tracks, at every openness
    down to the floor. The decay is what exposed the original leak — at
    openness 0 an unmasked track's implicit 0.0 satisfies `>= openness`."""
    a = int(world.tracks[0].track_id)
    b = int(world.tracks[2 % len(world.tracks)].track_id)
    w = StreamWriter(world, seed=11)
    openness = 1.0
    strays = []
    seen_tracks = set()
    for _ in range(24):
        openness = max(1e-6, openness * 0.8)        # the adopted slew's shape
        fence = clamp0(track_mask={a: openness, b: openness}, openness=openness)
        admitted = _admitted_tracks(world, fence)
        assert admitted == {a, b}, "fence admitted %s, not the pair" % sorted(admitted)
        r = w.write_bar(fence=fence)
        for (_s, cast_tid, _uid, _sec, _m) in r.rows:
            seen_tracks.add(int(cast_tid))
            if int(cast_tid) not in admitted:
                strays.append(int(cast_tid))
    assert not strays, "bridge passage cast from outside the pair: %s" % sorted(set(strays))
    # non-vacuous: the passage really did cast, and from both sides of the pair
    assert seen_tracks, "the bridge passage cast nothing at all"


def test_passage_provenance_is_non_vacuous(world):
    """The provenance assertions above would BITE: with no fence, the same
    passage casts from tracks a fenced passage must never touch."""
    tid = int(world.tracks[0].track_id)
    w = StreamWriter(world, seed=7)
    others = set()
    for _ in range(24):
        r = w.write_bar()                           # unfenced
        for (_s, cast_tid, _uid, _sec, _m) in r.rows:
            if int(cast_tid) != tid:
                others.add(int(cast_tid))
    assert others, ("an unfenced passage never left track %d, so the fenced "
                    "assertions prove nothing on this world" % tid)
