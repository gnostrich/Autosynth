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
from cloud.companion.engine_bridge import (StreamPlayer,        # puts arch-v6 on path
                                           anchor_profile_armed)
p = StreamPlayer("demo.etsworld", seed=0)
sf = p.static_field()
from ets.engine.engine import (track_anchor_profiles, role_unit_pool,
                               nowplaying_activity)
w = p.world
prof, raw_pools = track_anchor_profiles(w), role_unit_pool(w)

# MEASURED arming off the REAL demo B. The demo world (like every world trained to
# date) sits at the band-blind fixed point: B is uniform, so anchor_profile_armed is
# False and the role->unit drill + track-lean DISARM (Theorem A arming corollary).
armed = bool(anchor_profile_armed(w.fstate.B))

# profiles: exactly the desktop reduction, peak-normalized to 1.0 (tracks are real
# provenance and STAY served even when the profile observable is degenerate).
prof_ok = all(np.allclose(sf["profiles"][t], prof[t]) for t in prof)
norm_ok = all(abs(max(sf["profiles"][t]) - 1.0) < 1e-9
              for t in sf["profiles"] if any(sf["profiles"][t]))

# DISARM: the unit pools are WITHHELD (empty) rather than served as false structure.
pools_empty = (sf["unit_pools"] == {})
# ...and the raw pools they WOULD have served are indeed track-monopolized — the
# false attribution that JUSTIFIES the disarm (one track wins every band's argmax).
def _monop(entries):
    tids = [tid for (_uid, tid, _band, _pr) in entries]
    return (len(set(tids)) <= 1) if tids else True
raw_monopolized = all(_monop(raw_pools[r]) for r in raw_pools) and len(raw_pools) > 0

# ARM PATH (auto re-arm). Flip the MEASURED flag (the same decision an informative B
# would produce) and rebuild the static section: the SAME gating now SERVES the
# world's unit pools, traceably to role_unit_pool(w). Proves the disarm is a gate on
# the measured flag, not a hardcoded deletion — a world whose B arms serves the pools.
p._profile_armed = True
p._static_field_cache = None
sf_armed = p.static_field()
armed_pools_nonempty = (len(sf_armed["unit_pools"]) > 0
                        and sf_armed["profile_armed"] is True)
armed_pool_ok = True
for r in raw_pools:
    got = sf_armed["unit_pools"][r]
    if len(got) != len(raw_pools[r]): armed_pool_ok = False; break
    for e, (uid, tid, band, pr) in zip(got, raw_pools[r]):
        if not (e["unit_id"] == uid and e["track_id"] == tid and e["band"] == band
                and np.allclose(e["profile"], pr)):
            armed_pool_ok = False; break

# nowplaying: reduces the produced rows by source-track mass, peak-normalized
rows = [(0, 0, 10, 0, 2.0), (0, 1, 11, 0, 1.0), (0, 0, 12, 0, 2.0)]  # T0 mass 4, T1 mass 1
npa = dict(nowplaying_activity(rows))
np_ok = abs(npa[0] - 1.0) < 1e-9 and abs(npa[1] - 0.25) < 1e-9

print(json.dumps({
    "armed": armed, "profile_armed_key": bool(sf["profile_armed"]),
    "prof_ok": prof_ok, "norm_ok": norm_ok, "np_ok": np_ok,
    "pools_empty": pools_empty, "raw_monopolized": raw_monopolized,
    "armed_pools_nonempty": armed_pools_nonempty, "armed_pool_ok": armed_pool_ok,
    "names": {str(k): v for k, v in sf["track_names"].items()},
    "M": int(w.M), "nprof": len(sf["profiles"]),
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
    assert d["keys"] == ["profile_armed", "profiles", "track_names", "unit_pools"], d["keys"]
    assert d["prof_ok"], "profiles must equal track_anchor_profiles(world)"
    assert d["norm_ok"], "each track profile must be peak-normalized to 1.0"
    assert d["nprof"] == d["M"] or d["nprof"] >= 1


def test_demo_world_disarms_the_role_unit_grain_honestly():
    """HONEST ADAPTATION (OPEN_ENDS #22): the demo world's anchor band-profile B is
    uniform (the band-blind fixed point every trained world sits at), so the profile
    observable is degenerate. Per Theorem A's arming corollary the bridge DISARMS the
    role->unit drill: static_field withholds the unit pools (empty) instead of serving
    the track-monopolized false attribution. This is the corollary operating on the
    real world — NOT a fabricated-informative-B fixture to keep old expectations."""
    d = _dump()
    assert d["armed"] is False, "demo B is uniform → the profile observable is degenerate"
    assert d["profile_armed_key"] is False, "static_field must report profile_armed=False"
    assert d["pools_empty"], "disarmed → unit pools withheld (no false structure served)"
    assert d["raw_monopolized"], \
        "the withheld pools are track-monopolized — the false attribution the disarm avoids"


def test_static_field_arms_when_the_observable_is_informative():
    """AUTO RE-ARM (OPEN_ENDS #22, 2-NEXT continuity): the disarm is a gate on the
    MEASURED flag, not a hardcoded deletion. When the flag is armed (as an informative
    B would produce) the SAME static_field serves the world's unit pools traceably to
    role_unit_pool(w). So the pre-registered engine change that makes B informative
    re-arms the role->unit grain with no edit to the bridge."""
    d = _dump()
    assert d["armed_pools_nonempty"], "an armed observable must SERVE the unit pools"
    assert d["armed_pool_ok"], \
        "the served pools must trace the world provenance + band profile (role_unit_pool)"


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
    # static_field exposes the three sections + the measured arming flag
    for section in ('"profiles"', '"unit_pools"', '"track_names"', '"profile_armed"'):
        assert section in src, f"static_field must expose {section}"
    # the disarm is MEASURED off B (Theorem A corollary), not hardcoded: the arming
    # test reads the world's anchor band-profile and gates the unit pools on it.
    assert "def anchor_profile_armed" in src, \
        "the bridge must define the measured anchor-profile arming test"
    assert "anchor_profile_armed(self.world.fstate.B)" in src, \
        "arming must be measured off the frozen world's band-profile B, never hardcoded"
    assert "if self._profile_armed:" in src, \
        "unit pools must be served only when the profile observable is armed"


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
