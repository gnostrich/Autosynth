"""MVP-D: no renderer/decoder in the cloud path; nothing here emits audio.

Static: importing the service pulls in NO writer/render/audio/panel module.
Behavioural: a /train result is a world+receipt npz — no audio array, no waveform.
"""
from __future__ import annotations

import io
import sys

import numpy as np

from cloud.service import run_job_inprocess
from cloud.common import encode_job
from cloud.tests.fixtures import make_synthetic_protos

# Modules that would mean a decoder/renderer or audio I/O leaked into the cloud.
_FORBIDDEN_MODULE_SUBSTRINGS = (
    "ets.writer", "ets.render", "sounddevice", "pyaudio", "soundfile",
    "librosa", "ets.engine.audio", "python_osc", "pythonosc", "PySide6",
    "ets.panel", "ets.meters",
)


def test_service_import_graph_has_no_decoder_or_audio():
    # Import the whole service surface fresh and inspect what it dragged in.
    import importlib
    for m in ("cloud.service", "cloud.service.app", "cloud.common",
              "cloud.common.protocol"):
        importlib.import_module(m)
    loaded = set(sys.modules)
    leaked = [m for m in loaded
              if any(bad in m for bad in _FORBIDDEN_MODULE_SUBSTRINGS)]
    assert not leaked, f"cloud service pulled in decoder/audio modules: {leaked}"


def test_service_result_contains_no_audio_arrays():
    protos = make_synthetic_protos(n_tracks=3, seed=5)
    result_bytes = run_job_inprocess(encode_job(protos, {"seed": 0, "sweeps": 4}))
    with np.load(io.BytesIO(result_bytes)) as z:
        keys = list(z.files)
        # keys are only world.* and receipt.*
        assert all(k.startswith("world.") or k.startswith("receipt.") for k in keys)
        assert not any(s in k.lower()
                       for k in keys
                       for s in ("audio", "wav", "pcm", "sample", "waveform")), keys
        # no array is a long 1-D audio-like buffer (sanity on the payload shapes)
        for k in keys:
            arr = np.asarray(z[k])
            if arr.ndim == 1 and arr.size > 4096 and arr.dtype.kind == "f":
                raise AssertionError(f"suspiciously audio-like array on wire: {k}")


def test_no_render_symbol_reachable_from_service():
    import cloud.service.app as app
    for banned in ("render", "decode_audio", "to_wav", "play", "schedule"):
        assert not hasattr(app, banned), f"service exposes {banned!r}"
