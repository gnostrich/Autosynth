"""Directive-v1 Feature 2 Stage 1 acceptance fixtures (operator amendment
stage1-delete-conflated-jack). See PREREG.md "Directive-v1 FEATURE 2 STAGE 1"
and REGISTRY id stage1-authority-typing-2026-07-15.

  (1) H-8 CROSS-VERSION BIT-IDENTITY: offline render on a SYNTHETIC world
      (never the 20-track corpus — a concurrent builder is rendering the
      full corpus and the box OOMs if two source banks load at once) with a
      fixed seed and the shipped default Tolerances (leash=inf, comma=inf,
      untouched by this stage and still consumed by nothing) reproduces the
      EXACT golden audio_sha256/provenance_sha256/world_sha256 captured from
      the pre-Stage-1 tree, BEFORE any edit in this session. Same idiom as
      the H-2 golden-sha256 pin in tests/harness/test_h1_h2.py.

  (2) VETO-BLOCKS-ENDING is covered in tests/meters/test_contract.py (the
      ending-veto predicate's own behavioural tests); not duplicated here.

  (3) Fresh-clone-clean is covered by tests/harness/test_h5_authority_typing.py
      (H-5b re-run against `git ls-files`, not just the working tree).
"""
from __future__ import annotations
import json
import os

import numpy as np
import pytest

from ets.engine.engine import Engine, resolve_sigma
from ets.engine.worldfile import load_world
from ets.panel.tolerances import Tolerances
from tests.harness.worldtools import write_synthetic_worldfile

# Golden hashes of a SYNTHETIC world FROZEN at test time (build_world_from_tracks ->
# anchors.build_world). Originally captured on the pre-Stage-1 tree (commit 05f8848):
#   world=3c4b4a23..  audio=14eb05a0..  provenance=9f7b651d..
#
# RE-BLESSED for engine-v1.1-freeze (PREREG-informative-B.md; informative anchor
# band-profile B at freeze). That change makes the FROZEN B the coupling-weighted
# band profile of the settled couplings instead of the uniform band-blind fixed
# point. It is scoped to FREEZE only and provably leaves the settled D/a/theta/pi
# BIT-IDENTICAL (verified old-vs-new: D/a/theta/pi array_equal, only B moves,
# row-ptp 0.0 -> 0.0142); so this synthetic world's `world_sha256` changes (new B),
# and its render changes through the settled-energy band split `e = col @ B`
# (realize.py) -> new `audio_sha256`/`provenance_sha256`. This is the INTENDED
# newly-frozen-world consequence (existing committed .etsworld files are NOT
# re-frozen and render byte-identical -- see cloud/tests/test_freeze_only_byte_
# identity.py). The assertions below stay EXACT-equality golden pins; only the
# reference values are re-based to the v1.1-freeze freeze output.
PRE_STAGE1_AUDIO_SHA256 = (
    "5d7063f2ed29a8da087259e569afb2e6fee7d3243a1ba6a9499084f108cfd013")
PRE_STAGE1_PROVENANCE_SHA256 = (
    "b96d5e2aa93984cfb0a1615149b2809bcd9ebeeaa3ada354de47cffa4e76ff2c")
PRE_STAGE1_WORLD_SHA256 = (
    "d77fff6c124aea00b88312a43d96c98cd57646447b00dea29bc383e040ae8c66")

KNOBS = {"events": [
    {"bar": 1, "lane": "density", "value": 1.5},
    {"bar": 2, "lane": "region", "value": [2.0, -1.0]},
    {"bar": 3, "lane": "continuity", "value": -2.0},
    {"bar": 4, "lane": "temperature", "value": 0.25},
    {"bar": 5, "lane": "novelty", "value": 2.0},
]}


@pytest.fixture(scope="module")
def world_path(tmp_path_factory):
    p = tmp_path_factory.mktemp("stage1") / "stage1.etsworld"
    write_synthetic_worldfile(str(p), seed=0)
    return str(p)


@pytest.fixture(scope="module")
def knob_path(tmp_path_factory):
    p = tmp_path_factory.mktemp("stage1k") / "knobs.json"
    p.write_text(json.dumps(KNOBS))
    return str(p)


def test_shipped_default_tolerances_are_still_untouched():
    """comma=inf + default leash: unchanged by this stage (no consumer was
    added, per the scope guard)."""
    import math
    t = Tolerances()
    assert math.isinf(t.leash)
    assert math.isinf(t.comma)


def test_stage1_offline_render_is_bit_identical_to_pre_deletion_baseline(
        world_path, knob_path):
    """The conflated-jack deletion + typing contract touch ONLY the meter
    layer + panel/OSC surface (scope guard). This is the concrete proof: the
    SAME synthetic world + knob trajectory + seed reproduces the EXACT
    pre-edit golden hashes -- nothing on the render path moved."""
    wf = load_world(world_path)
    eng = Engine(wf, profile="desktop", seed=11, sigma=resolve_sigma(wf))
    r = eng.render_offline(8.0, knob_script=knob_path)

    assert r.receipt["world_sha256"] == PRE_STAGE1_WORLD_SHA256, (
        "the synthetic-world construction itself drifted -- fixture is not "
        "comparable to the golden baseline")
    assert r.receipt["audio_sha256"] == PRE_STAGE1_AUDIO_SHA256, (
        "Stage 1 changed rendered audio bytes -- scope guard violated "
        "(F/LAMBDA/world/settlement/render/tape/provenance must be zero-diff)")
    assert r.receipt["provenance_sha256"] == PRE_STAGE1_PROVENANCE_SHA256, (
        "Stage 1 changed provenance bytes -- scope guard violated")
