"""PHYSICS RUNNER — the isolated Railway compute surface (tools/physrunner).

These spin the handler on loopback and pin the load-bearing posture:
  * /health is OPEN (platform probe); /job REQUIRES X-Runner-Token == RUNNER_TOKEN
    (missing/wrong token -> 403; an unset server token fails closed).
  * a tiny settle_ensemble job on the COMMITTED demo world (n=2) returns
    well-formed, numbers-only observables (φ statistics; no audio/recipes).
  * a cycle job returns forward + reversed per-bar O/frame reads (holonomy P3
    raw material, computed client-side).
  * one job at a time per instance: a busy instance answers 409, never queues.

IMPORT-TREE ISOLATION. The runner needs architecture-v6 to own `import ets`. The
cloud test SUITE also imports root engine-v1's `ets` (e.g. test_mvp_c_parity),
which binds the `ets` namespace to engine-v1 for the whole interpreter. So the
health/auth/validation/busy tests run IN-PROCESS (they never import the engine —
the runner loads it lazily, only on a real settle), while the tests that actually
settle a world run against a SUBPROCESS server — a fresh interpreter where arch-v6
owns `ets`, which is exactly the deployed condition (its own container/process).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.physrunner import runner as physrunner  # noqa: E402

_TOKEN = "test-runner-token"


def _req(url, method="GET", token=None, body=None, timeout=60):
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["X-Runner-Token"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# --------------------------------------------------------------------------
# IN-PROCESS server — health/auth/validation/busy (no engine load)
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def server():
    httpd = physrunner.serve(token=_TOKEN, host="127.0.0.1", port=0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    url = "http://127.0.0.1:%d" % httpd.server_address[1]
    try:
        yield httpd, url
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_health_is_open(server):
    _httpd, url = server
    code, body = _req(url + "/health")
    assert code == 200
    assert body["ok"] is True
    assert body["service"] == "ets-physrunner"
    assert body["token_configured"] is True


def test_job_refused_without_token(server):
    _httpd, url = server
    code, body = _req(url + "/job", method="POST",
                      body={"kind": "settle_ensemble", "world": "demo.etsworld",
                            "n": 1})
    assert code == 403
    assert body["ok"] is False


def test_job_refused_with_wrong_token(server):
    _httpd, url = server
    code, body = _req(url + "/job", method="POST", token="nope",
                      body={"kind": "settle_ensemble", "world": "demo.etsworld",
                            "n": 1})
    assert code == 403
    assert body["ok"] is False


def test_server_with_unset_token_fails_closed():
    """A runner built with no token refuses every job (never open compute)."""
    httpd = physrunner.serve(token=None, host="127.0.0.1", port=0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        url = "http://127.0.0.1:%d" % httpd.server_address[1]
        code, body = _req(url + "/job", method="POST", token="anything",
                          body={"kind": "settle_ensemble", "world": "demo.etsworld"})
        assert code == 403
        assert body["ok"] is False
        _, h = _req(url + "/health")
        assert h["token_configured"] is False
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_settle_ensemble_rejects_bad_shape(server):
    """n<1 is rejected (400) BEFORE any engine load — pure request validation."""
    _httpd, url = server
    code, body = _req(url + "/job", method="POST", token=_TOKEN,
                      body={"kind": "settle_ensemble", "world": "demo.etsworld",
                            "n": 0})
    assert code == 400
    assert body["ok"] is False


def test_unknown_kind_is_400(server):
    _httpd, url = server
    code, body = _req(url + "/job", method="POST", token=_TOKEN,
                      body={"kind": "nope"})
    assert code == 400


def test_busy_returns_409(server):
    """Hold the instance's single job lock and prove a concurrent /job is refused
    (409) rather than queued — the memory bound the caller relies on."""
    httpd, url = server
    acquired = httpd.runner._busy.acquire(blocking=False)
    assert acquired
    try:
        code, body = _req(url + "/job", method="POST", token=_TOKEN, body={
            "kind": "settle_ensemble", "world": "demo.etsworld", "n": 1})
        assert code == 409
        assert body["ok"] is False
    finally:
        httpd.runner._busy.release()


# --------------------------------------------------------------------------
# SUBPROCESS server — the real settle path (fresh interpreter, arch-v6 owns ets)
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def subproc_server():
    port = _free_port()
    env = dict(os.environ, RUNNER_TOKEN=_TOKEN, PORT=str(port), HOST="127.0.0.1")
    proc = subprocess.Popen(
        [sys.executable, str(_REPO_ROOT / "tools" / "physrunner" / "runner.py")],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = "http://127.0.0.1:%d" % port
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
                raise RuntimeError(f"runner subprocess died on boot:\n{out}")
            try:
                code, body = _req(url + "/health", timeout=2)
                if code == 200 and body.get("ok"):
                    break
            except Exception:
                time.sleep(0.3)
        else:
            raise RuntimeError("runner subprocess never became healthy")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


def test_settle_ensemble_demo_n2_well_formed(subproc_server):
    url = subproc_server
    code, body = _req(url + "/job", method="POST", token=_TOKEN, body={
        "kind": "settle_ensemble", "world": "demo.etsworld", "seed0": 0, "n": 2,
        "u": {"continuity": 1.0}, "collect": ["Phi_region", "Phi_cont",
                                              "Phi_novelty"]})
    assert code == 200, body
    assert body["ok"] is True
    assert body["kind"] == "settle_ensemble"
    assert body["n"] == 2
    assert isinstance(body["world_hash"], str) and body["world_hash"]
    assert len(body["results"]) == 1                    # one u-point
    settles = body["results"][0]["settles"]
    assert len(settles) == 2                            # n=2 bars
    for i, s in enumerate(settles):
        assert s["bar"] == i
        assert isinstance(s["Phi_cont"], float)
        assert isinstance(s["Phi_novelty"], float)
        assert isinstance(s["Phi_region"], list) and len(s["Phi_region"]) == body["M"]
        assert all(isinstance(v, float) for v in s["Phi_region"])


def test_settle_ensemble_u_list_gives_per_point_results(subproc_server):
    """A list of u-points yields one result block per point (reciprocity sweeps)."""
    url = subproc_server
    code, body = _req(url + "/job", method="POST", token=_TOKEN, body={
        "kind": "settle_ensemble", "world": "demo.etsworld", "seed0": 3, "n": 1,
        "u": [{"continuity": 0.0}, {"continuity": 1.0}, {"novelty": 1.0}],
        "collect": ["Phi_cont", "Phi_novelty"]})
    assert code == 200, body
    assert len(body["results"]) == 3
    for block in body["results"]:
        assert len(block["settles"]) == 1
        assert "Phi_cont" in block["settles"][0]


def test_cycle_returns_forward_and_reversed(subproc_server):
    url = subproc_server
    cyc = [{"region": 0.0}, {"region": 1.0}, {"region": 0.0}, {"region": -1.0}]
    code, body = _req(url + "/job", method="POST", token=_TOKEN, body={
        "kind": "cycle", "world": "demo.etsworld", "seed0": 0, "u": cyc,
        "collect": ["O", "frame"]})
    assert code == 200, body
    assert body["kind"] == "cycle"
    assert len(body["forward"]) == len(cyc)
    assert len(body["reversed"]) == len(cyc)
    b0 = body["forward"][0]
    assert isinstance(b0["O"], list) and len(b0["O"]) == body["M"]   # (M x S)
    assert set(b0["frame"]) == {"transpose", "phase"}
