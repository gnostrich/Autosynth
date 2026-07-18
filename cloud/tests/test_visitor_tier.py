"""OPEN_ENDS #16 — the KEYLESS VISITOR TIER + the full owner-gate mode matrix.

A keyless visitor in a keyed deploy is no longer walled out: / serves the app and the
read/play routes serve that visitor's OWN anonymous session (read + play + steer +
open shared sets; minted via the ``ets_session`` cookie on first API contact — two
anonymous visitors are ISOLATED, never one shared session). Only the OWNER surfaces
(ingest/train/reset/share) stay key-gated, and the gate answer depends on the deploy
mode:

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


def _req_c(url, method="GET", cookie=None, body=None):
    """Cookie-carrying request (a browser-like anonymous visitor). Returns
    (status, body, set_cookie_token_or_None)."""
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if cookie is not None:
        headers["Cookie"] = "ets_session=" + cookie
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status, out, hdrs = r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        status, out, hdrs = e.code, e.read(), dict(e.headers)
    sc = hdrs.get("Set-Cookie", "")
    token = None
    if "ets_session=" in sc:
        token = sc.split("ets_session=", 1)[1].split(";", 1)[0]
    return status, out, token


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
        assert code == 200 and b'id="tabs"' in body   # app-only marker (post-rebrand)
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


# --------------------------------------------------------------------------- #
# PER-VISITOR ANONYMOUS SESSIONS — keyless visitors never share one session    #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("keys", [["k1"], []])   # keyed+public AND legacy keyless+public
def test_anon_cookie_minted_once_and_session_sticky(tmp_path, monkeypatch, keys):
    httpd, url = _server(tmp_path, public=True, keys=keys, monkeypatch=monkeypatch)
    try:
        # first API contact mints the anonymous session cookie.
        code, body, tok = _req_c(url + "/api/status")
        assert code == 200 and tok, "first contact must Set-Cookie an anon session"
        sdir = json.loads(body)["session_dir"]
        # replaying the cookie resolves the SAME session and mints nothing new.
        code2, body2, tok2 = _req_c(url + "/api/status", cookie=tok)
        assert code2 == 200 and tok2 is None, "a known visitor must not be re-minted"
        assert json.loads(body2)["session_dir"] == sdir
    finally:
        httpd.shutdown(); httpd.server_close()


def test_two_anonymous_visitors_are_isolated(tmp_path, monkeypatch):
    """THE leak the operator hit: visitor A opens a shared set; visitor B's Play
    page must NOT show it. Engine-free: /api/open + /api/status only."""
    from cloud.companion.app import CatalogEntry
    httpd, url = _server(tmp_path, public=True, keys=["k1"], monkeypatch=monkeypatch)
    try:
        # a shared set exists in the catalog (metadata only; the file must exist).
        wpath = tmp_path / "shared.etsworld"
        wpath.write_bytes(b"world")
        httpd.hub.catalog["set-a"] = CatalogEntry(
            set_id="set-a", name="A's set", owner="a", world_path=str(wpath),
            region_armed=True, disarmed=[], owner_token="set-a")
        # visitor A: mint cookie, open the set, status shows it opened.
        _, _, tok_a = _req_c(url + "/api/status")
        code, _, _ = _req_c(url + "/api/open", method="POST", cookie=tok_a,
                            body={"set_id": "set-a"})
        assert code == 200
        st_a = json.loads(_req_c(url + "/api/status", cookie=tok_a)[1])
        assert st_a["opened_set_id"] == "set-a"
        # visitor B: a DIFFERENT session — nothing of A's appears.
        _, body_b, tok_b = _req_c(url + "/api/status")
        assert tok_b and tok_b != tok_a, "each keyless visitor gets their own session"
        st_b = json.loads(body_b)
        assert st_b["opened_set_id"] is None, \
            "visitor B must not inherit visitor A's opened set"
        assert st_b["session_dir"] != st_a["session_dir"]
        # and B's Play surface is honestly empty (engine-free in public mode).
        w_b = json.loads(_req_c(url + "/api/world", cookie=tok_b)[1])
        assert w_b["ready"] is False and w_b["loaded"] is False
    finally:
        httpd.shutdown(); httpd.server_close()


def test_engines_stay_pooled_not_per_visitor(tmp_path, monkeypatch):
    # per-visitor SESSIONS are pointers; engines resolve through the ONE shared
    # WorldRegistry LRU (the OOM bound). Many anon sessions -> zero loaded engines
    # until a world is actually played, and one hub-wide registry object.
    httpd, url = _server(tmp_path, public=True, keys=["k1"], monkeypatch=monkeypatch)
    try:
        toks = [_req_c(url + "/api/status")[2] for _ in range(5)]
        assert len(set(toks)) == 5
        assert httpd.hub.registry.loaded_worlds() == [], \
            "anon sessions alone must load NO engines"
        sessions = list(httpd.hub.anon_sessions.values())
        assert len(sessions) == 5
        assert all(s.registry is httpd.hub.registry for s in sessions), \
            "every session must share the single engine registry"
    finally:
        httpd.shutdown(); httpd.server_close()


def test_anon_lru_eviction_also_removes_the_empty_session_dir(tmp_path, monkeypatch):
    """Auditor note (2026-07-18): the in-memory anon LRU must not leave evicted
    sessions' (empty) directories accreting on disk. Non-empty dirs are spared
    (rmdir semantics) — cleanup may never destroy data."""
    monkeypatch.setenv("ETS_MAX_ANON_SESSIONS", "2")
    httpd, url = _server(tmp_path, public=True, keys=["k1"], monkeypatch=monkeypatch)
    try:
        hub = httpd.hub
        t1, s1 = hub.new_anon_session()
        d1 = s1.session_dir
        assert d1.is_dir()
        hub.new_anon_session()
        hub.new_anon_session()                       # cap 2 -> evicts s1
        assert t1 not in hub.anon_sessions, "LRU must have evicted the oldest"
        assert not d1.exists(), "evicted empty anon dir must be removed from disk"
        # a NON-empty dir must survive eviction (never destroy data)
        t2, s2 = hub.new_anon_session()              # evicts another; now mint one with content
        (s2.session_dir / "keep.bin").write_bytes(b"x")
        hub.new_anon_session(); hub.new_anon_session()   # push s2 out
        assert t2 not in hub.anon_sessions
        assert (s2.session_dir / "keep.bin").exists(), "eviction must never rm non-empty dirs"
    finally:
        httpd.shutdown(); httpd.server_close()
