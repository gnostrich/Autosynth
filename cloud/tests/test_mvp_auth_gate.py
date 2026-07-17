"""MVP-1 single-user auth gate — proves the bearer-token check BITES.

The gate is transport auth, not a CS wall, but a public /train with no auth is an
open compute endpoint (open bill). These tests prove: with ETS_TRAIN_TOKEN set, a
missing/wrong token is rejected (401) and only the right token trains (200); with
the env UNSET the endpoint stays open (so local dev + parity tests are unaffected).
"""
import os
import threading
import urllib.error
import urllib.request

import pytest

from http.server import ThreadingHTTPServer

from cloud.common import encode_job
from cloud.service.app import _TrainHandler
from cloud.tests.fixtures import make_synthetic_protos


def _serve():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _TrainHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def _post(url, job, token=None):
    headers = {"Content-Type": "application/octet-stream"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url + "/train", data=job, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@pytest.fixture
def job():
    return encode_job(make_synthetic_protos(n_tracks=3, K=6, seed=0), {"seed": 0, "sweeps": 3})


def test_gate_bites_when_token_set(job, monkeypatch):
    monkeypatch.setenv("ETS_TRAIN_TOKEN", "s3cr3t-single-user")
    httpd, url = _serve()
    try:
        # no header -> 401
        code, _ = _post(url, job, token=None)
        assert code == 401, "missing token must be rejected"
        # wrong token -> 401
        code, _ = _post(url, job, token="wrong")
        assert code == 401, "wrong token must be rejected"
        # right token -> 200 + a real result
        code, body = _post(url, job, token="s3cr3t-single-user")
        assert code == 200 and len(body) > 0, "correct token must train"
    finally:
        httpd.shutdown()


def test_open_when_token_unset(job, monkeypatch):
    monkeypatch.delenv("ETS_TRAIN_TOKEN", raising=False)
    httpd, url = _serve()
    try:
        code, body = _post(url, job, token=None)
        assert code == 200 and len(body) > 0, "unset env must leave the endpoint open"
    finally:
        httpd.shutdown()


def test_health_never_gated(monkeypatch):
    monkeypatch.setenv("ETS_TRAIN_TOKEN", "s3cr3t")
    httpd, url = _serve()
    try:
        with urllib.request.urlopen(url + "/health", timeout=10) as r:
            assert r.status == 200, "health probe must stay open for the platform"
    finally:
        httpd.shutdown()
