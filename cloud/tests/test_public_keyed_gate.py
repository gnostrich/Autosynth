"""PUBLIC × KEYED gate — a keyed session keeps OWNER powers (Train/ingest/reset/share)
even under ETS_PUBLIC; only a KEYLESS-public visitor is the demo-only consumer.

The deployed service runs ETS_PUBLIC=1 AND keyed together. The old gate branched on
session.public alone, so every keyed session (which inherits public=True) lost Train.
The fix: one owner predicate, can_train = keyed || !public, drives BOTH the 503 POST
gate and the FE tab/publish visibility.

All five (public × keyed) combos, engine-free (asserted via /api/status + the POST
gate — never /api/world, so no engine import enters this interpreter):

  P+K anon    -> gated routes 401 (auth wall), NOT 503; / serves the access page.
  P+K keyed   -> can_train true; ingest/reset/train/share are NOT 503.
  P alone     -> 503 stays on ingest/train/reset/share; can_train false (R6 pin).
  K alone     -> can_train true; unchanged.
  neither     -> can_train true; unchanged.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from cloud.companion.app import serve


def _server(tmp_path, public, keys, monkeypatch):
    if keys:
        monkeypatch.setenv("ETS_ACCESS_KEYS", ",".join(keys))
    else:
        monkeypatch.delenv("ETS_ACCESS_KEYS", raising=False)
    httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
                  session_dir=str(tmp_path / "sess"), public=public)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def _req(url, method="GET", token=None, body=None):
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _auth(url, key):
    code, body = _req(url + "/api/auth", method="POST", body={"key": key})
    assert code == 200, (code, body)
    return json.loads(body)["token"]


_GATED_POSTS = ("/api/ingest", "/api/train", "/api/reset", "/api/share")


# --- P+K : public AND keyed -------------------------------------------------

def test_public_keyed_anon_hits_auth_wall_not_503(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, public=True, keys=["k1"], monkeypatch=monkeypatch)
    try:
        # anonymous: gated GET -> 401, gated POSTs -> 401 (auth wall), never 503.
        code, _ = _req(url + "/api/status")
        assert code == 401
        for path in _GATED_POSTS:
            code, _ = _req(url + path, method="POST", body={})
            assert code == 401, f"{path} anon should be 401 (auth), got {code}"
        # / serves the access page (unauthenticated keyed).
        code, body = _req(url + "/")
        assert code == 200 and b"access" in body.lower()
    finally:
        httpd.shutdown(); httpd.server_close()


def test_public_keyed_owner_keeps_train(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, public=True, keys=["k1"], monkeypatch=monkeypatch)
    try:
        tok = _auth(url, "k1")
        # can_train is TRUE for the keyed owner even under ETS_PUBLIC.
        code, body = _req(url + "/api/status", token=tok)
        assert code == 200
        st = json.loads(body)
        assert st["keyed"] is True and st["can_train"] is True, st
        # the owner surfaces are NOT 503: ingest + reset succeed; train/share proceed
        # to their real (non-503) outcome.
        code, _ = _req(url + "/api/ingest", method="POST", token=tok, body={})
        assert code == 200, f"keyed ingest should not be 503, got {code}"
        code, _ = _req(url + "/api/reset", method="POST", token=tok, body={})
        assert code == 200, f"keyed reset should not be 503, got {code}"
        for path in ("/api/train", "/api/share"):
            code, _ = _req(url + path, method="POST", token=tok, body={})
            assert code != 503, f"keyed {path} must not be gated 503, got {code}"
    finally:
        httpd.shutdown(); httpd.server_close()


# --- P alone : public, keyless (the R6 demo-only regression pin) ------------

def test_public_keyless_stays_gated_503(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, public=True, keys=[], monkeypatch=monkeypatch)
    try:
        # keyless-public: the single default session is public; can_train FALSE and
        # the owner surfaces stay 503 (R6 demo-only), unchanged.
        code, body = _req(url + "/api/status")
        assert code == 200
        st = json.loads(body)
        assert st["keyed"] is False and st["can_train"] is False, st
        for path in _GATED_POSTS:
            code, _ = _req(url + path, method="POST", body={})
            assert code == 503, f"{path} keyless-public must stay 503, got {code}"
    finally:
        httpd.shutdown(); httpd.server_close()


# --- K alone / neither : owners, unchanged ----------------------------------

def test_keyed_local_can_train(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, public=False, keys=["k1"], monkeypatch=monkeypatch)
    try:
        tok = _auth(url, "k1")
        st = json.loads(_req(url + "/api/status", token=tok)[1])
        assert st["keyed"] is True and st["can_train"] is True, st
        code, _ = _req(url + "/api/ingest", method="POST", token=tok, body={})
        assert code == 200
    finally:
        httpd.shutdown(); httpd.server_close()


def test_keyless_local_can_train(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, public=False, keys=[], monkeypatch=monkeypatch)
    try:
        st = json.loads(_req(url + "/api/status")[1])
        assert st["keyed"] is False and st["can_train"] is True, st
        code, _ = _req(url + "/api/ingest", method="POST", body={})
        assert code == 200
    finally:
        httpd.shutdown(); httpd.server_close()


# --- source pin: /api/world also carries can_train (FE reads either) ---------

def test_world_payload_exposes_can_train():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "companion" / "app.py").read_text()
    # both read-only payloads carry the owner predicate; the POST gate honors keyed.
    assert 'info["can_train"] = self._can_train(session)' in src
    assert '"can_train": self._can_train(session)' in src
    assert "not self.hub.keyed and path in (" in src
