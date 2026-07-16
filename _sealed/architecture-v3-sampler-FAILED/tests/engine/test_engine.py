"""Engine unit surface: world file integrity, σ_φ resolution precedence,
knob-script validation, offline receipt contents."""
from __future__ import annotations
import json

import numpy as np
import pytest

from ets.engine.engine import (Engine, apply_knob_events, load_knob_script,
                               resolve_sigma)
from ets.engine.worldfile import load_world, save_world
from ets.panel.lanes import default_lane_vector
from tests.harness.worldtools import (build_synthetic_world, embedded_bank_for,
                                      measure_sigma_inline,
                                      write_synthetic_worldfile)


@pytest.fixture(scope="module")
def world_path(tmp_path_factory):
    p = tmp_path_factory.mktemp("eng") / "w.etsworld"
    write_synthetic_worldfile(str(p), seed=0)
    return str(p)


def test_worldfile_roundtrip_and_integrity(tmp_path, world_path):
    wf = load_world(world_path)
    assert wf.world.M >= 1
    assert wf.sources["kind"] == "embedded"
    assert wf.sigma_phi is not None
    # a corrupted payload is refused (hash check), not silently loaded.
    raw = open(world_path, "rb").read()
    bad = tmp_path / "corrupt.etsworld"
    bad.write_bytes(raw[:-64] + bytes(64))
    with pytest.raises(ValueError):
        load_world(str(bad))
    # a non-world pickle is refused.
    import pickle
    notworld = tmp_path / "not.etsworld"
    with open(notworld, "wb") as fh:
        pickle.dump({"magic": "nope"}, fh)
    with pytest.raises(ValueError):
        load_world(str(notworld))


def test_sigma_resolution_precedence(tmp_path, world_path):
    wf = load_world(world_path)
    # embedded sigma resolves...
    s_embedded = resolve_sigma(wf)
    assert s_embedded is not None
    # ...but an explicit --sigma-phi file wins.
    other = dict(wf.sigma_phi)
    other["density"] = float(other["density"]) * 2.0
    p = tmp_path / "sigma.json"
    p.write_text(json.dumps(other))
    s_cli = resolve_sigma(wf, str(p))
    assert s_cli.density == pytest.approx(2.0 * s_embedded.density)
    # a world without sigma and no registered artifact resolves to None
    # (uncalibrated: leans refuse; nothing is invented).
    wp2 = tmp_path / "nosigma.etsworld"
    write_synthetic_worldfile(str(wp2), seed=1, with_sigma=False)
    wf2 = load_world(str(wp2))
    assert wf2.sigma_phi is None
    # NOTE: resolve_sigma(wf2) may still find the REGISTERED corpus artifact
    # via ets.calibration once that (concurrent) feature lands; precedence is
    # CLI > embedded > registered, so this test pins only the first two.


def test_knob_script_events_bind_at_their_bar():
    u = default_lane_vector(2)
    events = [{"bar": 2, "lane": "density", "value": 1.0},
              {"bar": 2, "lane": "region", "value": [0.5, -0.5]},
              {"bar": 3, "lane": "temperature", "value": 0.5}]
    apply_knob_events(u, events, bar=0)
    assert u.u_density == 0.0
    apply_knob_events(u, events, bar=2)
    assert u.u_density == 1.0 and u.u_region[0] == pytest.approx(0.5)
    assert u.T_s == 1.0
    apply_knob_events(u, events, bar=3)
    assert u.T_s == 0.5
    with pytest.raises(ValueError):
        apply_knob_events(u, [{"bar": 0, "lane": "swing", "value": 1}], bar=0)


def test_offline_receipt_records_the_h8_tuple(world_path):
    wf = load_world(world_path)
    eng = Engine(wf, seed=2, sigma=resolve_sigma(wf))
    res = eng.render_offline(4.0)
    r = res.receipt
    assert r["world_sha256"] == wf.world_hash
    assert set(r["lambda"]) >= {"T2", "T3", "T4", "T5", "T1p"}
    assert r["seed"] == 2
    assert len(r["audio_sha256"]) == 64
    assert r["n_placements"] > 0
    assert res.audio.shape[0] == r["n_bars"] * 8 * wf.world.out_tatum_len
