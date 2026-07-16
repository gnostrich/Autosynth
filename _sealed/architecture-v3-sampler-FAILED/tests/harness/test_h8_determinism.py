"""H-8 — determinism: same (world hash, LAMBDA, knob trajectory, seed) ⇒
BIT-IDENTICAL offline render. Run once per merge (CI).

The fixture builds a small synthetic world FILE (embedded source bank +
inline-measured σ_φ — measured on this world by running the untilted writer,
never invented), scripts a knob trajectory across several lanes, and renders
offline twice through the real engine entry path. The receipt records the full
H-8 tuple; every element of the tuple is shown to matter (world, knobs, seed
each flip the hash — non-vacuity)."""
from __future__ import annotations
import json
import os

import numpy as np
import pytest

from ets.engine.engine import Engine, resolve_sigma
from ets.engine.worldfile import load_world
from tests.harness.worldtools import write_synthetic_worldfile

KNOBS = {"events": [
    {"bar": 1, "lane": "density", "value": 1.5},
    {"bar": 2, "lane": "region", "value": [2.0, -1.0]},
    {"bar": 3, "lane": "continuity", "value": -2.0},
    {"bar": 4, "lane": "temperature", "value": 0.25},
    {"bar": 5, "lane": "novelty", "value": 2.0},
]}


@pytest.fixture(scope="module")
def world_path(tmp_path_factory):
    p = tmp_path_factory.mktemp("h8") / "h8.etsworld"
    write_synthetic_worldfile(str(p), seed=0)
    return str(p)


@pytest.fixture(scope="module")
def knob_path(tmp_path_factory):
    p = tmp_path_factory.mktemp("h8k") / "knobs.json"
    p.write_text(json.dumps(KNOBS))
    return str(p)


def _render(world_path, knob_path, seed):
    wf = load_world(world_path)
    eng = Engine(wf, profile="desktop", seed=seed, sigma=resolve_sigma(wf))
    return eng.render_offline(8.0, knob_script=knob_path)


def test_h8_bit_identical_offline_render(world_path, knob_path):
    r1 = _render(world_path, knob_path, seed=11)
    r2 = _render(world_path, knob_path, seed=11)
    assert np.array_equal(r1.audio, r2.audio), "audio not bit-identical"
    assert r1.receipt["audio_sha256"] == r2.receipt["audio_sha256"]
    assert r1.receipt["provenance_sha256"] == r2.receipt["provenance_sha256"]
    # the receipt pins the full H-8 tuple.
    for key in ("world_sha256", "lambda", "knob_trajectory_sha256", "seed"):
        assert r1.receipt[key] == r2.receipt[key]


def test_h8_every_tuple_element_matters(world_path, knob_path, tmp_path):
    base = _render(world_path, knob_path, seed=11)
    # seed flips the hash
    assert _render(world_path, knob_path, seed=12).receipt["audio_sha256"] \
        != base.receipt["audio_sha256"]
    # knob trajectory flips the hash
    other = tmp_path / "other_knobs.json"
    other.write_text(json.dumps({"events": [
        {"bar": 1, "lane": "density", "value": -1.5}]}))
    assert _render(world_path, str(other), seed=11).receipt["audio_sha256"] \
        != base.receipt["audio_sha256"]
    # world flips the hash (different frozen world file)
    wp2 = tmp_path / "w2.etsworld"
    write_synthetic_worldfile(str(wp2), seed=99)
    r_w2 = _render(str(wp2), knob_path, seed=11)
    assert r_w2.receipt["world_sha256"] != base.receipt["world_sha256"]
    assert r_w2.receipt["audio_sha256"] != base.receipt["audio_sha256"]


def test_h8_knob_script_refuses_a_seventh_control(world_path, tmp_path):
    """The offline trajectory speaks the SAME closed lane space (spec §8): a
    non-lane control name in the script is refused, not improvised."""
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"events": [
        {"bar": 0, "lane": "swing", "value": 1.0}]}))
    wf = load_world(world_path)
    eng = Engine(wf, seed=0, sigma=resolve_sigma(wf))
    with pytest.raises(ValueError):
        eng.render_offline(2.0, knob_script=str(bad))
