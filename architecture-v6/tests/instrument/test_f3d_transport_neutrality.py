"""F3-D — transport neutrality. Pause / seek do NOT change what the writer settles
for a fixed (world, LAMBDA, knob trajectory, seed).

Transport is a pure playhead over ALREADY-PRODUCED output; it holds no writer
handle. So the settled audio is fixed before the transport touches it, and every
pause/seek/tick leaves it byte-identical. We render once, drive the transport
through a gauntlet of controls, render again with the identical seed, and require
byte-equality — plus a structural check that Transport exposes no re-settle path.
"""
from __future__ import annotations

import hashlib

import numpy as np

from ets.instrument.transport import Transport
from tests.instrument._offline import render_clip


def test_pause_seek_do_not_change_the_settled_output(tmp_path):
    audio_a, segs, n, sr = render_clip(tmp_path / "a", seed=11)
    ha = hashlib.sha256(audio_a.tobytes()).hexdigest()

    # a real transport gauntlet over the produced buffer.
    tr = Transport()
    tr.load(len(audio_a), sr)
    tr.play()
    tr.tick(0.2)
    tr.pause()
    tr.seek(len(audio_a) // 3)
    tr.tick(0.5)          # ignored while paused
    tr.play()
    tr.tick(0.3)
    tr.seek_seconds(0.1)
    tr.stop()
    # the buffer the transport read is untouched (it holds no writable handle).
    assert hashlib.sha256(audio_a.tobytes()).hexdigest() == ha

    # re-render the identical (world, LAMBDA, knobs, seed): byte-identical.
    audio_b, _s, _n, _sr = render_clip(tmp_path / "b", seed=11)
    assert np.array_equal(audio_a, audio_b), \
        "transport activity changed what the writer settled (F3-D violated)"


def test_transport_has_no_resettle_surface():
    """Structural: Transport carries only playhead scalars — no world, writer,
    schedule, or settle method that could re-decide a bar."""
    tr = Transport()
    assert set(vars(tr)) == {"n_samples", "sr", "position", "playing"}
    forbidden = {"settle", "write_bar", "render", "world", "writer", "schedule"}
    assert not (forbidden & set(dir(tr))), \
        "Transport grew a path into settlement/render"
