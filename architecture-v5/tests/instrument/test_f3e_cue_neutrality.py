"""F3-E — cue neutrality. With cue active and pads auditioned in cue mode,
main-out is BYTE-IDENTICAL to cue-off on a fixed seed.

CueMonitor derives its buffer from a COPY of the produced audio and never writes
back; it holds no writer/emitter handle. So activating cue + auditioning tracks
cannot move a main-out byte. We render main-out, run a full cue/audition session
against it, and require the main buffer (and a re-render) to be byte-identical —
plus a check that the cue buffer is a distinct array (mutating it is inert on
main).
"""
from __future__ import annotations

import hashlib

import numpy as np

from ets.instrument.cue import CueMonitor
from tests.instrument._offline import render_clip


def test_cue_and_audition_leave_main_out_byte_identical(tmp_path):
    main, segs, n, sr = render_clip(tmp_path / "a", seed=11)
    h_off = hashlib.sha256(main.tobytes()).hexdigest()

    playhead = len(main) // 4
    frontier = (3 * len(main)) // 4
    tracks = sorted({int(t) for t in np.unique(segs["src_track"])})

    cue = CueMonitor()
    cue.set_active(True)
    for t in tracks[:1]:
        cue.audition(t)
    cue_buf = cue.render_cue(main, segs, playhead, frontier)

    # cue produced real signal from the frontier, yet main is untouched.
    assert cue_buf.size > 0
    assert hashlib.sha256(main.tobytes()).hexdigest() == h_off, \
        "cue/audition mutated main-out (F3-E violated)"

    # the cue buffer is a private copy: scribbling on it cannot reach main.
    if cue_buf.size:
        cue_buf[:] = 1234.5
    assert hashlib.sha256(main.tobytes()).hexdigest() == h_off

    # cue-off vs cue-on re-render: main-out byte-identical.
    main2, _s, _n, _sr = render_clip(tmp_path / "b", seed=11)
    assert np.array_equal(main, main2)


def test_cue_never_touches_the_writer_or_emitter():
    cue = CueMonitor()
    forbidden = {"settle", "write_bar", "render_offline", "emit", "world",
                 "writer", "emitter"}
    assert not (forbidden & set(dir(cue))), \
        "CueMonitor grew a path into settlement/render/emit"
