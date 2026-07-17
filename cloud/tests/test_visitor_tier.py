"""OPEN_ENDS #16 — the KEYLESS VISITOR TIER + the full owner-gate mode matrix.

A keyless visitor in a keyed deploy is no longer walled out: / serves the app and the
read/play routes serve a shared VISITOR session (read + play + steer + open shared
sets). Only the OWNER surfaces (ingest/train/reset/share) stay key-gated, and the gate
answer depends on the deploy mode:

    deploy mode                     owner POST (ingest/train/reset/share)
    ------------------------------  --------------------------------------
    keyed  + public, no token       401 auth_required   (unlock with a key)
    keyed  + public, valid token    proceed (owner)
    keyless+ public (legacy)        503 public-block    (unchanged)
    keyed  + local, no token        401 auth_required
    keyed  + local, valid token     proceed (owner)
    keyless+ local                  proceed (owner)

The read/play routes are exercised in PUBLIC mode so /api/world is ENGINE-FREE (no
demo is surfaced on the hosted path, so no player is built). Unlock-in-place is
proven: a keyless visitor that POSTs a good key to /api/auth upgrades to an owner
session (can_train flips true) without any page/access-wall navigation.
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


_OWNER_POSTS = ("/api/ingest", "/api/train", "/api/reset", "/api/share")
_VISITOR_POSTS = ("/api/steer", "/api/play", "/api/stop", "/api/open")


# --------------------------------------------------------------------------- #
# the OWNER-GATE mode matrix — the crux of #16 (all six cells, engine-free)    #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("public,keyed,authed,expect", [
    (True,  True,  False, 401),   # keyed+public, keyless visitor -> unlock (401)
    (True,  True,  True,  None),  # keyed+public, owner           -> proceed (not 401/503)
    (True,  False, False, 503),   # keyless+public (legacy)       -> demo-block (503)
    (False, True,  False, 401),   # keyed+local, keyless visitor  -> unlock (401)
    (False, True,  True,  None),  # keyed+local, owner            -> proceed
    (False, False, False, None),  # keyless+local                 -> proceed (owner)
])
def test_owner_gate_matrix(tmp_path, monkeypatch, public, keyed, authed, expect):
    keys = ["k1"] if keyed else []
    httpd, url = _server(tmp_path, public=public, keys=keys, monkeypatch=monkeypatch)
    try:
        token = _auth(url, "k1") if authed else None
        for path in _OWNER_POSTS:
            code, _ = _req(url + path, method="POST", token=token, body={})
            if expect is None:
                assert code not in (401, 503), \
                    f"owner {path} must proceed (not gated), got {code}"
            else:
                assert code == expect, \
                    f"{path} public={public} keyed={keyed} authed={authed}: " \
                    f"expected {expect}, got {code}"
    finally:
        httpd.shutdown(); httpd.server_close()


# --------------------------------------------------------------------------- #
# the VISITOR READ/PLAY surface (public -> engine-free /api/world)             #
# --------------------------------------------------------------------------- #

def test_keyless_visitor_read_and_play_routes_open(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, public=True, keys=["k1"], monkeypatch=monkeypatch)
    try:
        # / serves the app (no access wall).
        code, body = _req(url + "/")
        assert code == 200 and b"Equilibrium Tape Synth" in body
        # read routes: status/world/explore all 200 without a token.
        for path in ("/api/status", "/api/world", "/api/explore"):
            assert _req(url + path)[0] == 200, path
        # /api/world is honestly empty + carries the keyed flag for the FE affordance.
        w = json.loads(_req(url + "/api/world")[1])
        assert w["ready"] is False and w["loaded"] is False
        assert w["can_train"] is False and w["keyed"] is True
        # visitor play/steer/open routes are NOT auth-blocked (no world -> 409/404).
        for path in _VISITOR_POSTS:
            code, _ = _req(url + path, method="POST", body={})
            assert code != 401, f"{path} must be open to a visitor, got {code}"
    finally:
        httpd.shutdown(); httpd.server_close()


# --------------------------------------------------------------------------- #
# UNLOCK IN PLACE — a good key upgrades the keyless visitor to an owner        #
# --------------------------------------------------------------------------- #

def test_unlock_upgrades_visitor_to_owner_in_place(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, public=True, keys=["k1"], monkeypatch=monkeypatch)
    try:
        # as a keyless visitor: can_train is false.
        st = json.loads(_req(url + "/api/status")[1])
        assert st["can_train"] is False
        # enter the key (the in-app affordance's POST) -> token minted.
        token = _auth(url, "k1")
        # the SAME page, now carrying the token, is an owner: can_train flips true and
        # the owner surfaces open (ingest 200) — no access-wall navigation involved.
        st2 = json.loads(_req(url + "/api/status", token=token)[1])
        assert st2["can_train"] is True and st2["keyed"] is True
        assert _req(url + "/api/ingest", method="POST", token=token, body={})[0] == 200
    finally:
        httpd.shutdown(); httpd.server_close()
