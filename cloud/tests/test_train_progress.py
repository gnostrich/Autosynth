"""PROG — staged train progress is REAL, ordered, and never fabricated (design §4A).

Two proofs:
  * the audio seam emits its stages in exactly ``TRAIN_STAGES`` order, one per real
    boundary (unit-tested with the heavy engine steps injected out — the ORCHESTRATION
    and its progress emission are what's under test, and in production each step does
    real work);
  * a real train through the server records those transitions into session state, and
    /api/status exposes them in order — so the FE can render a staged indicator driven
    ONLY by real backend state (no timer-driven fake progress).
"""
import json
import threading
import urllib.request
from pathlib import Path

from cloud.client.cli import save_prototypes
from cloud.companion.app import serve
import cloud.companion.train_local as tl
from cloud.companion.train_local import TRAIN_STAGES, build_trained_world
from cloud.tests.fixtures import make_synthetic_protos


# ---------------- audio-seam stage ordering (unit) --------------------------

class _R:  # a stand-in decoded result (fstate + receipt)
    fstate = object()
    receipt = {"n_anchors": 3}


def test_seam_emits_stages_in_order(monkeypatch):
    # inject every heavy step; keep the REAL orchestration + progress emission.
    monkeypatch.setattr(tl, "_pin_archv6", lambda: None)
    monkeypatch.setattr(tl, "_stage_ingest", lambda paths, seed: ["track"])
    monkeypatch.setattr(tl, "_stage_stage3", lambda tracks, seed: ["proto"])
    monkeypatch.setattr(tl, "_stage_cloud_fit",
                        lambda protos, cloud_url, seed, sweeps, sigma: b"result-bytes")
    monkeypatch.setattr(tl, "_stage_verify", lambda protos, rb: _R())
    monkeypatch.setattr(tl, "_stage_build",
                        lambda fstate, protos, tracks, paths, receipt: ("world", "sources"))
    monkeypatch.setattr(tl, "_stage_sigma_phi",
                        lambda world, tracks: {"identifiable": {"region": True, "cont": True,
                                               "novelty": True, "density": False, "gauge": False}})
    saved = {}
    monkeypatch.setattr(tl, "_stage_save",
                        lambda out, world, sources, sigma_phi: saved.update(out=out))

    seen = []
    out = build_trained_world(["a.wav"], out_path="/tmp/x.etsworld",
                              progress=lambda s: seen.append(s))
    assert tuple(seen) == TRAIN_STAGES, f"stages out of order/missing: {seen}"
    assert out["is_trained"] is True
    assert sorted(out["sigma_phi_disarmed"]) == ["density", "gauge"]
    assert saved["out"] == "/tmp/x.etsworld"


def test_train_stages_constant_is_the_real_pipeline():
    # the stage list is the true seam order — the FE renders exactly this sequence.
    assert TRAIN_STAGES == ("ingest", "stage3", "cloud_fit", "verify", "build",
                            "sigma_phi", "save")


# ---------------- /api/status exposes real transitions during a train -------

def _server(tmp_path):
    httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
                  session_dir=str(tmp_path / "sess"))
    t = threading.Thread(target=httpd.serve_forever, daemon=True); t.start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.status, json.loads(r.read())

def _post(url, body):
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, json.loads(r.read())


def test_status_exposes_ordered_stage_transitions(tmp_path, monkeypatch):
    monkeypatch.delenv("ETS_ACCESS_KEYS", raising=False)   # keyless: no token needed
    httpd, url = _server(tmp_path)
    try:
        # ingest a synthetic stage-3 bundle (the offline geometry path) then train
        save_prototypes(str(tmp_path / "protos.npz"), make_synthetic_protos(4, 6, 0))
        payload = (tmp_path / "protos.npz").read_bytes()
        req = urllib.request.Request(url + "/api/ingest", data=payload,
                                     headers={"X-Filename": "protos.npz"}, method="POST")
        urllib.request.urlopen(req, timeout=30).read()

        code, out = _post(url + "/api/train", b"{}")
        assert code == 200 and out["ok"] is True

        code, status = _get(url + "/api/status")
        stages = status["train_stages"]
        names = [s["stage"] for s in stages]
        # the geometry path truthfully emits only the boundaries it runs — no
        # invented per-stage detail — and they are in order.
        assert names == ["cloud_fit", "save"], names
        ts = [s["t"] for s in stages]
        assert ts == sorted(ts), "stage timestamps must be non-decreasing (real order)"
    finally:
        httpd.shutdown(); httpd.server_close()
