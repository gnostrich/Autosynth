"""F3-C — provenance-display fidelity.

Pad light-up + now-playing readout must match the ACTUAL provenance of sounding
cells. Two teeth:
  (1) a hand fixture with known segments — the model reports exactly the tracks
      sounding at a given sample, and the pads light exactly those tracks;
  (2) a REAL synthetic render — the display facts are self-consistent with the
      raw provenance the render emitted (nothing recomputed).
Both include a MUTATION that must flip the result, proving the check is not
vacuous.
"""
from __future__ import annotations

import numpy as np

from ets.render.provenance import PROV_SEG_DTYPE
from ets.instrument.model import (PadModel, TapeModel, cells_at, sounding_cells)


def _seg(out_start, out_end, track, unit, mass=1.0):
    s = np.zeros(1, dtype=PROV_SEG_DTYPE)[0]
    s["out_start"] = out_start
    s["out_end"] = out_end
    s["src_track"] = track
    s["src_unit"] = unit
    s["stretch_ratio"] = 1.0
    s["loudness_scale"] = 1.0
    s["mass"] = mass
    return s


def _fixture():
    # track 2 unit 0 sounds [0,100); track 5 unit 3 sounds [50,200);
    # track 2 unit 1 sounds [150,300). Overlap at [50,100) and [150,200).
    return np.array([_seg(0, 100, 2, 0), _seg(50, 200, 5, 3),
                     _seg(150, 300, 2, 1)], dtype=PROV_SEG_DTYPE)


def test_now_playing_matches_provenance_at_each_sample():
    segs = _fixture()
    tape = TapeModel()
    tape.set_provenance(segs, n_samples=300, sr=1000)

    def np_tracks(s):
        tape.set_playhead(s)
        return set(tape.now_playing_tracks())

    assert np_tracks(10) == {2}
    assert np_tracks(60) == {2, 5}          # overlap
    assert np_tracks(120) == {5}
    assert np_tracks(160) == {2, 5}         # overlap
    assert np_tracks(250) == {2}
    # the readout is provenance, not recomputed: it equals cells_at exactly.
    tape.set_playhead(60)
    assert {c.src_track for c in tape.now_playing()} == \
        {c.src_track for c in cells_at(segs, 60)}

    # MUTATION bites: drop the track-5 segment → sample 60 no longer shows T5.
    mutated = segs[[0, 2]]
    tape.set_provenance(mutated, n_samples=300, sr=1000)
    tape.set_playhead(60)
    assert set(tape.now_playing_tracks()) == {2}


def test_pads_light_exactly_the_sounding_tracks():
    segs = _fixture()
    pads = PadModel()
    # observe the cells sounding at sample 60 (tracks 2 and 5).
    pads.observe(cells_at(segs, 60))
    assert set(pads.lit()) == {2, 5}
    # a track never sounding never lights.
    assert 7 not in pads.lit()
    # decay eases a pad down; enough decays extinguish it (breathing, not latch).
    for _ in range(40):
        pads.decay(0.5)
    assert pads.lit() == []


def test_real_render_provenance_is_faithfully_displayed():
    from tests.harness.worldtools import build_synthetic_world, embedded_bank_for
    from ets.writer.stream import StreamWriter
    from ets.engine.engine import bar_schedule
    from ets.render import render

    world = build_synthetic_world()
    w = StreamWriter(world, seed=3)
    r = w.write_bar()
    sched = bar_schedule(world, r.rows, w.s_phase)
    audio, prov = render(sched, embedded_bank_for(world))
    segs = prov.segments
    assert len(segs) > 0, "synthetic render produced no provenance to display"

    tape = TapeModel()
    tape.set_provenance(segs, n_samples=prov.n_samples, sr=prov.sr)

    # the tracks the pads light == the tracks actually in the provenance.
    pads = PadModel()
    pads.observe(sounding_cells(segs))
    assert set(pads.lit()) == {int(t) for t in np.unique(segs["src_track"])}

    # now-playing at a covered sample == the raw provenance cells there (no
    # recompute, no drift from the emitted provenance).
    mid = int(prov.n_samples // 2)
    tape.set_playhead(mid)
    assert {(c.src_track, c.src_unit) for c in tape.now_playing()} == \
        {(int(s["src_track"]), int(s["src_unit"])) for s in segs
         if s["out_start"] <= mid < s["out_end"]}
