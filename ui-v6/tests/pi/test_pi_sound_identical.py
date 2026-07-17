"""PI sound-untouched guard (PREREG-uiv5-playable-instrument PI-A).

The whole telemetry/instrument slice is read-only monitor output: adding it must
not perturb the audio path. The strongest local witness we can run offline is
DETERMINISM of the render at a fixed seed — the same (world, λ, knob, seed) tuple
must produce bit-identical audio. Two independent fixed-seed renders therefore
share one audio sha256; if a telemetry addition ever reached into settlement /
the writer / render / provenance-generation, this identity is the first thing to
break.

This is a bite, not a full A/B: it does not import the telemetry emitter (that is
tested where it lives). It pins the property the emitter must never violate.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pytest


def _render(worldfile_path):
    wf_mod = pytest.importorskip("ets.engine.worldfile")
    eng_mod = pytest.importorskip("ets.engine.engine")
    wf = wf_mod.load_world(worldfile_path)
    eng = eng_mod.Engine(wf, seed=0, sigma=eng_mod.resolve_sigma(wf))
    return eng.render_offline(1.0)


def test_two_fixed_seed_renders_have_identical_audio_sha256(worldfile_path):
    a = _render(worldfile_path)
    b = _render(worldfile_path)

    # audio is finite (no NaN/Inf leaked into the buffer).
    assert np.all(np.isfinite(a.audio)), "render produced non-finite audio"
    assert a.audio.shape == b.audio.shape and a.audio.size > 0

    sha_a = hashlib.sha256(a.audio.tobytes()).hexdigest()
    sha_b = hashlib.sha256(b.audio.tobytes()).hexdigest()

    # the engine's own receipt sha and our recomputation must all agree.
    assert sha_a == sha_b, "fixed-seed render is not deterministic (audio moved)"
    assert sha_a == a.receipt["audio_sha256"] == b.receipt["audio_sha256"]
    # bit-for-bit, not merely equal hashes.
    assert np.array_equal(a.audio, b.audio)
