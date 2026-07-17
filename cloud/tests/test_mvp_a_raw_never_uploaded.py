"""MVP-A (LOAD-BEARING): raw / stage-2 recipe / private descriptors NEVER cross.

Static: the wire type + grammar reference ONLY the stage-3 whitelist.
Runtime: the exact bytes the client would send carry ONLY the four whitelisted
prototype fields.
Bite: every attempt to attach raw audio / a recipe field / an off-whitelist param
FAILS to serialize.
"""
from __future__ import annotations

import io
from dataclasses import fields

import numpy as np
import pytest

from cloud.common import (
    STAGE3_PROTO_FIELDS, STAGE3_PARAM_FIELDS, Stage3Proto, WhitelistViolation,
    encode_job, assert_wire_whitelisted,
)
from cloud.tests.fixtures import make_synthetic_protos

_FORBIDDEN = ("audio", "raw", "pcm", "wav", "sample", "src_start", "src_end",
              "provenance", "prov", "recipe", "unit", "timbre", "chroma",
              "beat_grid", "waveform")


def test_stage3_type_is_structurally_closed():
    # The wire prototype type has EXACTLY the four whitelisted fields — no field
    # exists into which audio/recipe could be placed.
    assert tuple(f.name for f in fields(Stage3Proto)) == STAGE3_PROTO_FIELDS
    assert set(STAGE3_PROTO_FIELDS) == {"cost", "mass", "slot_hist", "band_profile"}
    assert set(STAGE3_PARAM_FIELDS) == {"seed", "sweeps", "sigma"}


def test_runtime_capture_wire_bytes_are_stage3_only():
    protos = make_synthetic_protos(n_tracks=3, seed=1)
    # sanity: the source prototypes DO carry private timbre/chroma...
    assert hasattr(protos[0], "timbre") and hasattr(protos[0], "chroma")

    job_bytes = encode_job(protos, {"seed": 0, "sweeps": 4})
    with np.load(io.BytesIO(job_bytes)) as z:
        keys = set(z.files)
        arrays = {k: z[k] for k in z.files}

    # ...but NONE of the private / raw / recipe fields reach the wire.
    for k in keys:
        low = k.lower()
        assert not any(bad in low for bad in _FORBIDDEN), f"forbidden key on wire: {k}"

    # every key is in the closed grammar (this also runs the structural gate)
    assert_wire_whitelisted(arrays)

    # the only per-proto arrays present are exactly the four whitelisted fields
    import re
    proto_fields = {m.group(2) for k in keys
                    for m in [re.match(r"^p(\d+)\.(.+)$", k)] if m}
    assert proto_fields == set(STAGE3_PROTO_FIELDS)


def test_attach_raw_audio_to_stage3_proto_fails():
    # Structurally impossible: the frozen type has no slot for audio.
    K = 4
    with pytest.raises(TypeError):
        Stage3Proto(cost=np.zeros((K, K)), mass=np.ones(K) / K,
                    slot_hist=np.ones((K, 8)) / (K * 8),
                    band_profile=np.ones((K, 8)) / (K * 8),
                    audio=np.random.randn(44100))  # noqa: unexpected kwarg


def test_encode_rejects_a_raw_audio_object():
    # A raw-audio ndarray has no .cost -> from_prototype refuses it.
    raw = np.random.randn(2, 44100)
    with pytest.raises((AttributeError, WhitelistViolation, TypeError)):
        encode_job([raw], {"seed": 0})


def test_encode_rejects_a_track_like_recipe_object():
    # A stage-2 recipe object (provenance, source spans) lacks .cost -> refused.
    class FakeTrack:
        provenance_index = np.zeros(3)
        units = np.zeros(3)
        masses = np.ones(3)
    with pytest.raises((AttributeError, WhitelistViolation, TypeError)):
        encode_job([FakeTrack()], {"seed": 0})


def test_wire_grammar_rejects_injected_audio_key():
    protos = make_synthetic_protos(n_tracks=2, seed=2)
    good = encode_job(protos, {"seed": 0})
    with np.load(io.BytesIO(good)) as z:
        payload = {k: z[k] for k in z.files}
    # smuggle a raw-audio array in under a new key: the gate bites.
    payload["p0.audio"] = np.random.randn(44100)
    with pytest.raises(WhitelistViolation):
        assert_wire_whitelisted(payload)
    payload.pop("p0.audio")
    payload["src_start"] = np.arange(10)
    with pytest.raises(WhitelistViolation):
        assert_wire_whitelisted(payload)


def test_off_whitelist_param_is_refused():
    protos = make_synthetic_protos(n_tracks=2, seed=3)
    with pytest.raises(WhitelistViolation):
        encode_job(protos, {"seed": 0, "audio_path": "/corpus/song.wav"})


def test_extra_private_attr_is_stripped_not_forwarded():
    # A prototype-like object carrying an extra 'audio' attribute: the encoder
    # reads ONLY the whitelist, so 'audio' never reaches the wire (safe strip,
    # not a silent leak).
    protos = make_synthetic_protos(n_tracks=2, seed=4)
    protos[0].audio = np.random.randn(1000)   # smuggle attempt
    job_bytes = encode_job(protos, {"seed": 0})
    with np.load(io.BytesIO(job_bytes)) as z:
        assert not any("audio" in k.lower() for k in z.files)
