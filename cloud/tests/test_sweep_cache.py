"""MODES-BY-TEMPERATURE sidecar cache (auditor Note B coverage).

The auto-sweep worker persists a STAMPED sidecar so future loads/redeploys read the
measured table instantly, and self-invalidates it if the world file or the sweep params
change — while still TRUSTING an unstamped externally-supplied table (the committed demo
sidecar, an admin upload). These tests pin that contract directly on the cache methods
(no real-world load needed — they touch only world_path / M / os.stat), the way the eigen
cache is covered.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "companion"))

from engine_bridge import StreamPlayer  # noqa: E402


def _skeleton(world_path, M=2):
    """A bare StreamPlayer with only what the cache methods read — no engine/world load."""
    p = object.__new__(StreamPlayer)
    p.world_path = str(world_path)
    p.M = M
    return p


def _write_world(tmp_path, content=b"world-bytes"):
    w = tmp_path / "corpus.etsworld"
    w.write_bytes(content)
    return w


def test_stamped_roundtrip_and_hit(tmp_path):
    w = _write_world(tmp_path)
    p = _skeleton(w)
    result = {"M": 2, "n_seed": 24, "n_bar": 32, "observable_names": ["a"],
              "sweep": [{"T_s": 1.0, "k": 1, "modes": [], "eigen_floor": 0.0}]}
    p._write_sweep_cache(result, 24, 32)
    loaded = p._load_sweep_cache()
    assert loaded is not None
    assert "stamp" in loaded                     # auto-cache is stamped
    assert loaded["sweep"] == result["sweep"]


def test_stale_world_invalidates(tmp_path):
    w = _write_world(tmp_path)
    p = _skeleton(w)
    p._write_sweep_cache({"M": 2, "n_seed": 24, "n_bar": 32, "observable_names": ["a"],
                          "sweep": [{"T_s": 1.0, "k": 1, "modes": [], "eigen_floor": 0.0}]}, 24, 32)
    assert p._load_sweep_cache() is not None
    # world file changes (size + mtime) → the stamp no longer matches → cache rejected.
    w.write_bytes(b"world-bytes-CHANGED-longer")
    assert p._load_sweep_cache() is None


def test_param_change_invalidates(tmp_path):
    w = _write_world(tmp_path)
    p = _skeleton(w)
    p._write_sweep_cache({"M": 2, "n_seed": 24, "n_bar": 32, "observable_names": ["a"],
                          "sweep": [{"T_s": 1.0, "k": 1, "modes": [], "eigen_floor": 0.0}]}, 24, 32)
    # same world, but a blob claiming different ensemble params must be rejected: rewrite the
    # sidecar with a mismatched n_seed recorded inside it (stamp is validated against it).
    blob = json.load(open(p._sweep_cache_path()))
    blob["n_seed"] = 12                          # claim 12 but stamp was written for 24
    json.dump(blob, open(p._sweep_cache_path(), "w"))
    assert p._load_sweep_cache() is None


def test_unstamped_external_table_is_trusted(tmp_path):
    # The committed demo sidecar / an admin upload carry NO stamp — trusted as-is (operator
    # vouched), never rejected for lacking a machine stamp.
    w = _write_world(tmp_path)
    p = _skeleton(w)
    external = {"M": 2, "n_seed": 24, "n_bar": 32, "observable_names": ["a"],
                "sweep": [{"T_s": 0.5, "k": 1, "modes": [], "eigen_floor": 0.0},
                          {"T_s": 2.0, "k": 2, "modes": [], "eigen_floor": 0.0}]}
    with open(p._sweep_cache_path(), "w") as f:
        json.dump(external, f)                    # no stamp
    loaded = p._load_sweep_cache()
    assert loaded is not None and len(loaded["sweep"]) == 2


def test_malformed_blob_is_none(tmp_path):
    w = _write_world(tmp_path)
    p = _skeleton(w)
    with open(p._sweep_cache_path(), "w") as f:
        f.write("{ not json")
    assert p._load_sweep_cache() is None
    with open(p._sweep_cache_path(), "w") as f:
        json.dump({"no_sweep_key": True}, f)
    assert p._load_sweep_cache() is None


def test_missing_sidecar_is_none(tmp_path):
    w = _write_world(tmp_path)
    p = _skeleton(w)
    assert p._load_sweep_cache() is None          # nothing written yet


def test_partial_autocache_reloads_and_write_is_incremental(tmp_path):
    # A PARTIAL stamped auto-cache (fewer than the full grid) round-trips and is recognised
    # as partial — the basis for resume-after-eviction. Also confirms each write persists.
    w = _write_world(tmp_path)
    p = _skeleton(w)
    from engine_bridge import _SWEEP_T_GRID
    # a partial covering the first two grid temperatures
    g0, g1 = _SWEEP_T_GRID[0], _SWEEP_T_GRID[1]
    partial = {"M": 2, "n_seed": 24, "n_bar": 32, "observable_names": ["a"],
               "sweep": [{"T_s": g0, "k": 1, "modes": [], "eigen_floor": 0.0},
                         {"T_s": g1, "k": 2, "modes": [], "eigen_floor": 0.0}]}
    p._write_sweep_cache(partial, 24, 32)
    reloaded = p._load_sweep_cache()
    assert reloaded is not None and reloaded.get("stamp") is not None   # stamped auto-cache
    have = {round(float(r["T_s"]), 4) for r in reloaded["sweep"]}
    missing = [T for T in _SWEEP_T_GRID if round(float(T), 4) not in have]
    assert missing == list(_SWEEP_T_GRID[2:])          # resume would compute exactly the rest
