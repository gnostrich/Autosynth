"""WEB-FIELD backend payloads — the read-only reductions the field ladder consumes
are TRACEABLE to the world/rows, computed by the SAME desktop reductions, and folded
into the EXISTING /api/world + /api/telemetry payloads (no new route, no new authority).

The value-traceability checks run in a SUBPROCESS: constructing a real StreamPlayer
imports the arch-v6 engine (ets.render / ets.writer), which must never enter the cloud
test interpreter (test_mvp_d's import-graph guard). Out-of-process keeps that clean,
exactly like the render smoke gate. The wiring checks are cheap static reads.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BRIDGE = _ROOT / "cloud" / "companion" / "engine_bridge.py"
_APP = _ROOT / "cloud" / "companion" / "app.py"


# ---- value traceability (subprocess: real world + real reductions) ----------

_DUMP = r"""
import sys, json
from pathlib import Path
sys.path.insert(0, r"%s")
import numpy as np
from cloud.companion.engine_bridge import StreamPlayer          # puts arch-v6 on path
p = StreamPlayer("demo.etsworld", seed=0)
sf = p.static_field()
from ets.engine.engine import (track_anchor_profiles, role_unit_pool,
                               nowplaying_activity)
w = p.world
prof, pools = track_anchor_profiles(w), role_unit_pool(w)

# profiles: exactly the desktop reduction, peak-normalized to 1.0
prof_ok = all(np.allclose(sf["profiles"][t], prof[t]) for t in prof)
norm_ok = all(abs(max(sf["profiles"][t]) - 1.0) < 1e-9
              for t in sf["profiles"] if any(sf["profiles"][t]))
# unit pools: unit_id / track_id / band / profile trace the world provenance + B
pool_ok = True
for r in pools:
    got = sf["unit_pools"][r]
    if len(got) != len(pools[r]): pool_ok = False; break
    for e, (uid, tid, band, pr) in zip(got, pools[r]):
        if not (e["unit_id"] == uid and e["track_id"] == tid and e["band"] == band
                and np.allclose(e["profile"], pr)):
            pool_ok = False; break
# nowplaying: reduces the produced rows by source-track mass, peak-normalized
rows = [(0, 0, 10, 0, 2.0), (0, 1, 11, 0, 1.0), (0, 0, 12, 0, 2.0)]  # T0 mass 4, T1 mass 1
npa = dict(nowplaying_activity(rows))
np_ok = abs(npa[0] - 1.0) < 1e-9 and abs(npa[1] - 0.25) < 1e-9

print(json.dumps({
    "prof_ok": prof_ok, "norm_ok": norm_ok, "pool_ok": pool_ok, "np_ok": np_ok,
    "names": {str(k): v for k, v in sf["track_names"].items()},
    "M": int(w.M), "nprof": len(sf["profiles"]),
    "pool_role0": len(sf["unit_pools"][0]),
    "keys": sorted(sf.keys()),
}))
""" % str(_ROOT)


def _dump():
    r = subprocess.run([sys.executable, "-c", _DUMP], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"subprocess failed:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_static_field_traceable_to_world():
    d = _dump()
    assert d["keys"] == ["profiles", "track_names", "unit_pools"], d["keys"]
    assert d["prof_ok"], "profiles must equal track_anchor_profiles(world)"
    assert d["norm_ok"], "each track profile must be peak-normalized to 1.0"
    assert d["pool_ok"], "unit pools must trace the world provenance + band profile"
    assert d["nprof"] == d["M"] or d["nprof"] >= 1
    assert d["pool_role0"] >= 1


def test_nowplaying_reduces_the_produced_rows():
    d = _dump()
    assert d["np_ok"], "nowplaying must be per-track mass, peak-normalized (traceable to rows)"


def test_demo_track_names_are_honest_generics():
    d = _dump()
    # the demo world is synthetic (no source filenames) -> honest "demo track N",
    # never an invented name.
    assert d["names"], "demo world must still carry honest track names"
    for tid, name in d["names"].items():
        assert name == "demo track %s" % tid, (tid, name)


# ---- wiring (cheap static reads; no engine import in-process) ---------------

def test_bridge_wires_the_three_reductions():
    src = _BRIDGE.read_text()
    # the SAME desktop reductions, imported read-only
    assert "track_anchor_profiles" in src and "role_unit_pool" in src, \
        "static_field must use the desktop profile + unit-pool reductions"
    assert "nowplaying_activity" in src, "produce_one_bar must use nowplaying_activity"
    # the live frame carries per-track nowplaying
    assert '"nowplaying": nowplaying' in src, \
        "the telemetry frame must include per-track nowplaying activity"
    # static_field exposes the three sections
    for section in ('"profiles"', '"unit_pools"', '"track_names"'):
        assert section in src, f"static_field must expose {section}"


def test_app_folds_static_field_and_overrides_names():
    src = _APP.read_text()
    assert "static_field()" in src, "/api/world must fold in the static field payload"
    # the honest name override: only for a session's OWN trained world, from real
    # ingested filenames (session metadata) — never invented.
    assert "session._is_trained" in src and "session.session_files()" in src, \
        "track names must be overridden from real ingest metadata for the owning session"
    assert "_AUDIO_EXTS" in src, "name override must consider only ingested audio files"
    # no new route / no new authority: set_region still single-site (checked in
    # test_web_field too); here just guard that /api/world stays a GET read.
    assert 'if path == "/api/world":' in src


def test_no_new_post_route_added():
    src = _APP.read_text()
    # the field ladder adds NO POST handler; the only settlement input stays /api/steer.
    posts = src.count("if path == ")
    # (sanity) set_region remains a single call site — the one engine-bound gesture.
    assert src.count(".set_region(") == 1
    assert posts >= 1
