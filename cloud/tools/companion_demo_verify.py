"""Standalone demo-phase companion proof (own process; real HTTP over real sockets).

Exercises the rebuilt ets-web delta end to end against a LIVE inproc server:
  * ACCESS gate: keyless is ungated; keyed = 401 (auth_required) everywhere except
    health/auth, access page at /, good key mints a token that unlocks;
  * MEMORY bounds: ONE shared demo engine across sessions; the LRU evicts past the
    cap; a second concurrent train is refused (429/busy);
  * SHARE/EXPLORE: publish -> list -> visitor open -> steer (region-tilt only) ->
    unshare revokes (a held handle reverts to the demo);
  * PROGRESS: /api/status exposes REAL ordered train-stage transitions.

The ONE injected part is the heavy engine bridge (``app._build_stream_player`` -> a
lightweight fake), because this sandbox has no audio device and the real bank is
~GB/slow; the RENDER path itself is proven separately by instrument_verify.py /
seam_verify.py. Everything else here is the real handler, Hub, auth, catalog, LRU,
and revocation, over real TCP.
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = "/home/user/Geodesic-Mixing"
sys.path.insert(0, ROOT)
sys.path.insert(0, ROOT + "/architecture-v6")

import cloud.companion.app as app
from cloud.companion.app import serve, WorldRegistry, Companion, TrainBusy


def log(m): print(m, flush=True)


# --- inject a lightweight fake engine bridge (no audio device in the sandbox) ---
class FakePlayer:
    def __init__(self, path, seed, is_trained):
        self.path = path; self.is_trained = is_trained; self.regions = []; self.stopped = False
    def stop(self): self.stopped = True
    def start(self): pass
    def set_region(self, r): self.regions.append(list(r))
    def world_info(self):
        return {"ready": True, "M": 3, "sr": 48000, "world": os.path.basename(self.path),
                "is_trained": self.is_trained, "armed": ["region"], "disarmed": [],
                "region_armed": True, "bar_seconds": 1.0}
    telemetry = {"roles": [0.0, 0.0, 0.0], "t": 0.0, "bar": 0}

app._build_stream_player = lambda path, seed, is_trained: FakePlayer(path, seed, is_trained)


def req(url, method="GET", token=None, body=None, cookie=None):
    headers = {}; data = None
    if body is not None:
        data = json.dumps(body).encode(); headers["Content-Type"] = "application/json"
    if token: headers["Authorization"] = "Bearer " + token
    if cookie: headers["Cookie"] = "ets_session=" + cookie
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def run_server(**env):
    for k, v in env.items():
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
    # a real demo world path must exist for the player to resolve
    demo = ROOT + "/demo.etsworld"
    httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
                  session_dir=ROOT + "/cache/_verify_sess")
    httpd.hub._play_world = demo
    httpd.hub.default_session.play_world = demo
    httpd.hub.default_session._demo_world = demo
    t = threading.Thread(target=httpd.serve_forever, daemon=True); t.start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def section(n): log("\n" + "=" * 4 + " " + n + " " + "=" * 4)


# ============================ 1. ACCESS GATE ================================
section("1. ACCESS GATE (keyed)")
os.environ["ETS_ACCESS_KEYS"] = "alpha,beta"
httpd, url = run_server()
try:
    for route in ("/api/status", "/api/world", "/api/explore"):
        code, body, _ = req(url + route)
        j = json.loads(body)
        assert code == 401 and j["auth_required"] is True, (route, code, j)
    log("    gated GET routes -> 401 auth_required  OK")
    code, body, _ = req(url + "/api/auth", method="POST", body={"key": "nope"})
    assert code == 401 and json.loads(body)["ok"] is False
    log("    bad key -> 401  OK")
    code, body, _ = req(url + "/")
    assert code == 200 and b'id="accessGate"' in body
    log("    / (unauth) -> access page  OK")
    code, body, hdrs = req(url + "/api/auth", method="POST", body={"key": "beta"})
    token = json.loads(body)["token"]
    assert code == 200 and token and "ets_session=" in hdrs.get("Set-Cookie", "")
    code, sbody, _ = req(url + "/api/status", token=token)
    assert code == 200 and "files" in json.loads(sbody)
    code, w, _ = req(url + "/api/world", token=token)
    assert code == 200 and json.loads(w)["ready"] is True
    log("    good key mints token; token unlocks status + world  OK")
    code, _, _ = req(url + "/api/health")
    assert code == 200
    log("    health stays ungated  OK")
finally:
    httpd.shutdown(); httpd.server_close()

section("1b. KEYLESS (gate disarmed)")
httpd, url = run_server(ETS_ACCESS_KEYS=None)
try:
    code, _, _ = req(url + "/api/status"); assert code == 200
    code, w, _ = req(url + "/api/world"); assert code == 200 and json.loads(w)["ready"]
    code, b, _ = req(url + "/"); assert code == 200 and b'id="accessGate"' not in b
    log("    keyless: status/world/root all open (today's behavior)  OK")
finally:
    httpd.shutdown(); httpd.server_close()


# ============================ 2. MEMORY BOUNDS =============================
section("2. MEMORY BOUNDS")
reg = WorldRegistry(max_loaded=2)
d1 = reg.demo_player("demo.etsworld", 0); d2 = reg.demo_player("demo.etsworld", 0)
assert d1 is d2
log("    demo engine is a shared singleton  OK")
reg.trained_player("/w/a", 0); reg.trained_player("/w/b", 0); reg.trained_player("/w/c", 0)
assert "/w/a" not in reg.loaded_worlds() and len(reg.loaded_worlds()) == 2
log("    LRU evicts past the cap (cap=2)  OK")
assert reg.begin_train() and not reg.begin_train()
comp = Companion(cloud_url="inproc", session_dir=ROOT + "/cache/_verify_busy", registry=reg)
try:
    comp.run_train(); raise SystemExit("expected TrainBusy")
except TrainBusy:
    log("    second concurrent train refused (TrainBusy)  OK")


# ==================== 3. SHARE / EXPLORE / OPEN / REVOKE ===================
section("3. SHARE / EXPLORE / OPEN / REVOKE (over HTTP)")
os.environ["ETS_ACCESS_KEYS"] = "k"
httpd, url = run_server()
try:
    hub = httpd.hub
    # owner authenticates and simulates a completed train (its own trained world)
    _, ob, _ = req(url + "/api/auth", method="POST", body={"key": "k"})
    ot = json.loads(ob)["token"]; owner = hub.session_for_token(ot)
    tw = os.path.join(owner.session_dir, "trained.etsworld")
    open(tw, "wb").write(b"world"); owner._is_trained = True; owner.play_world = tw
    owner.set_name = "Owner Set"

    _, vb, _ = req(url + "/api/auth", method="POST", body={"key": "k"})
    vt = json.loads(vb)["token"]

    # not shared yet -> explore empty, open refused
    _, e0, _ = req(url + "/api/explore", token=vt)
    assert json.loads(e0)["sets"] == []
    code, _, _ = req(url + "/api/open", method="POST", token=vt, body={"set_id": owner.set_id})
    assert code == 404
    log("    unshared set: unlisted + unopenable (EXP-A)  OK")

    # owner shares
    code, sb, _ = req(url + "/api/share", method="POST", token=ot, body={"on": True})
    assert code == 200 and json.loads(sb)["shared"] is True
    _, e1, _ = req(url + "/api/explore", token=vt)
    sets = json.loads(e1)["sets"]; assert [s["id"] for s in sets] == [owner.set_id]
    log("    share -> listed in Explore  OK")

    # visitor opens + steers (region-tilt only)
    code, _, _ = req(url + "/api/open", method="POST", token=vt, body={"set_id": owner.set_id})
    assert code == 200
    code, _, _ = req(url + "/api/steer", method="POST", token=vt, body={"region": [0.3, 0, 0]})
    assert code == 200
    vp = hub.playable_for(hub.session_for_token(vt))
    assert vp.path == tw and vp.regions, "visitor steered the SHARED set via region lane"
    log("    visitor open + region-tilt steer (EXP-C)  OK")

    # owner unshares -> delisted, unopenable, held handle reverts to demo
    req(url + "/api/share", method="POST", token=ot, body={"on": False})
    _, e2, _ = req(url + "/api/explore", token=vt); assert json.loads(e2)["sets"] == []
    code, _, _ = req(url + "/api/open", method="POST", token=vt, body={"set_id": owner.set_id})
    assert code == 404
    vp2 = hub.playable_for(hub.session_for_token(vt))
    vs = hub.session_for_token(vt)
    assert vs.opened_set_id is None and vp2.path == vs._demo_world
    log("    unshare revokes: delisted + unopenable + handle reverts (EXP-B)  OK")
finally:
    httpd.shutdown(); httpd.server_close()


# ============================ 4. PROGRESS =================================
section("4. STAGED PROGRESS (real transitions in /api/status)")
httpd, url = run_server(ETS_ACCESS_KEYS=None)
try:
    from cloud.client.cli import save_prototypes
    from cloud.tests.fixtures import make_synthetic_protos
    p = ROOT + "/cache/_verify_sess/protos.npz"
    save_prototypes(p, make_synthetic_protos(4, 6, 0))
    payload = open(p, "rb").read()
    r = urllib.request.Request(url + "/api/ingest", data=payload,
                               headers={"X-Filename": "protos.npz"}, method="POST")
    urllib.request.urlopen(r, timeout=30).read()
    code, tb, _ = req(url + "/api/train", method="POST", body={})
    assert code == 200 and json.loads(tb)["ok"]
    _, sb, _ = req(url + "/api/status")
    stages = [s["stage"] for s in json.loads(sb)["train_stages"]]
    assert stages == ["cloud_fit", "save"], stages
    log("    /api/status train_stages = %s (ordered, real)  OK" % stages)
finally:
    httpd.shutdown(); httpd.server_close()

log("\nALL DEMO-PHASE COMPANION CHECKS PASSED")
