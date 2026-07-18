"""The 1-NOW role-grain disarm AUTO-RE-ARMS on a newly-frozen informative world
(PREREG-informative-B.md §5.3; OPEN_ENDS #22 Remediation 1-NOW/2-NEXT).

The freeze-B change (2-NEXT) makes ``anchors.build_world`` produce an INFORMATIVE B
on a structured corpus. The already-shipped 1-NOW disarm gates the role->unit drill
and track-square lean on ``anchor_profile_armed(world.fstate.B)`` — a MEASURED test,
never a flag. So an informative freeze must re-arm with NO edit to the bridge. This
pins that composition:

  * in-process (no engine import): build_world(structured) -> the bridge's OWN
    ``anchor_profile_armed`` returns True; build_world(degenerate) -> False;
  * end-to-end (subprocess, real StreamPlayer over a real world file): a world whose
    frozen B is informative (built via the SAME freeze form) reports
    ``profile_armed: True`` in world_info AND static_field SERVES real unit pools;
    the uniform-B demo world honestly DISARMS (empty pools).

The in-process half imports ONLY the numpy-only predicate + root ``ets.functional``
(no arch-v6 engine), keeping the cloud import-graph guard clean; the StreamPlayer
half runs out-of-process exactly like test_web_field_payload.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from cloud.companion.engine_bridge import anchor_profile_armed
from ets.functional import anchors as an
from ets.geometry.roles import Prototypes

_ROOT = Path(__file__).resolve().parents[2]


def _proto(track_id, group, K=6, S=8, n_bands=8, seed=0, structured=True):
    rng = np.random.default_rng(seed)
    centre = np.zeros(3); centre[group % 3] = 2.5
    pts = centre[None, :] + 0.4 * rng.standard_normal((K, 3))
    cost = np.sqrt(((pts[:, None] - pts[None]) ** 2).sum(-1))
    off = cost[~np.eye(K, dtype=bool)]
    cost = cost / (np.sqrt(np.mean(off ** 2)) + 1e-12)
    cost = 0.5 * (cost + cost.T); np.fill_diagonal(cost, 0.0)
    mass = rng.random(K) + 0.1; mass /= mass.sum()
    slot = rng.random((K, S)); slot /= slot.sum()
    if structured:
        band = np.full((K, n_bands), 0.02); band[:, group % n_bands] += 1.0
        band = band / band.sum(1, keepdims=True) * mass[:, None]
    else:
        band = np.ones((K, n_bands)) / n_bands * mass[:, None]
    chroma = rng.random((K, 12)); chroma /= chroma.sum(1, keepdims=True)
    timbre = rng.standard_normal((K, 4))
    return Prototypes(track_id=track_id, cost=cost, mass=mass, slot_hist=slot,
                      band_profile=band, timbre=timbre, chroma=chroma)


def test_structured_freeze_arms_the_predicate():
    protos = [_proto(t, group=t, seed=t, structured=True) for t in range(6)]
    state, _ = an.build_world(protos, seed=0, sweeps=8)
    assert anchor_profile_armed(state.B) is True, \
        "an informative freeze must ARM the role/unit grain (bridge predicate)"


def test_degenerate_freeze_disarms_the_predicate():
    protos = [_proto(t, group=t, seed=t, structured=False) for t in range(6)]
    state, _ = an.build_world(protos, seed=0, sweeps=8)
    assert anchor_profile_armed(state.B) is False, \
        "a no-band-information freeze must stay honestly DISARMED (no fabricated spread)"


# ---- end-to-end: a real StreamPlayer over an informative world serves pools ----

_DUMP = r"""
import sys, json, tempfile, os
from dataclasses import replace
# arch-v6 must OWN `import ets` (the live-capped ui-v5 engine the bridge enforces):
# insert ROOT (for cloud.*) then arch-v6 LAST so it sits first on sys.path, and do
# NOT import any ets.* before the bridge. Mirrors train_local._pin_archv6.
sys.path.insert(0, r"%s")
sys.path.insert(0, r"%s/architecture-v6")
import numpy as np
from cloud.companion.engine_bridge import StreamPlayer      # bridge pins arch-v6
from ets.engine.worldfile import load_world, save_world     # -> arch-v6 ets
from ets.functional.anchors import coupling_weighted_B

# 1) the uniform-B demo world honestly DISARMS (empty pools).
demo = StreamPlayer("demo.etsworld", seed=0)
demo_info = demo.world_info(); demo_sf = demo.static_field()
demo_armed = bool(demo_info.get("profile_armed"))
demo_pools = sum(len(v) for v in demo_sf["unit_pools"].values())

# 2) freeze an INFORMATIVE B for the SAME world via the real freeze form, save, reload.
wf = load_world("demo.etsworld")
w = wf.world
Binf = coupling_weighted_B(w.fstate.pis, w.protos)      # the 2-NEXT freeze readout
w2 = replace(w, fstate=replace(w.fstate, B=Binf))
tmp = tempfile.NamedTemporaryFile(suffix=".etsworld", delete=False); tmp.close()
save_world(tmp.name, w2, wf.sources, sigma_phi=wf.sigma_phi)
inf = StreamPlayer(tmp.name, seed=0)
inf_info = inf.world_info(); inf_sf = inf.static_field()
inf_armed = bool(inf_info.get("profile_armed"))
inf_pools = sum(len(v) for v in inf_sf["unit_pools"].values())
row_ptp = float((np.asarray(Binf).max(1) - np.asarray(Binf).min(1)).max())
os.unlink(tmp.name)

print(json.dumps({
    "demo_armed": demo_armed, "demo_pools": demo_pools,
    "inf_armed": inf_armed, "inf_pools": inf_pools, "row_ptp": row_ptp,
}))
""" % (str(_ROOT), str(_ROOT))


def _dump():
    r = subprocess.run([sys.executable, "-c", _DUMP], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"subprocess failed:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_informative_world_arms_and_serves_pools_end_to_end():
    d = _dump()
    # uniform-B demo: disarmed, no pools served.
    assert d["demo_armed"] is False, "the uniform-B demo world must DISARM"
    assert d["demo_pools"] == 0, "a disarmed world must serve NO unit pools"
    # informative freeze: armed, real pools served.
    assert d["row_ptp"] > 1e-6, "the freeze form must produce an informative B here"
    assert d["inf_armed"] is True, "an informative frozen world must ARM (auto-re-arm)"
    assert d["inf_pools"] > 0, "an armed world must SERVE real unit pools"
