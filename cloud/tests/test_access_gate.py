"""AUTH — the access-key gate BITES on OWNER routes, and the VISITOR TIER opens the
read/play surface without a key (OPEN_ENDS #16).

``ETS_ACCESS_KEYS`` (comma-separated) arms a per-visitor session token. POST /api/auth
trades a good key for a token. Under #16 the access WALL is gone: / always serves the
app, and the read/play routes (status/world/explore/steer/play/stop/open) serve a
keyless VISITOR. Only the OWNER surfaces (ingest/train/reset/share) require a key —
401 ``auth_required:true`` for a keyless visitor, so the in-app unlock affordance can
enter a key. KEYLESS (env unset) = today's behavior exactly: no gate anywhere.

These run fully offline (inproc); the owner-route + auth checks touch no player, so
the read-route assertions here avoid /api/world (which builds the demo engine on a
local/keyed deploy) — /api/world's visitor semantics are covered engine-free in
test_no_demo_surface + test_visitor_tier.
"""
import json
import threading
import urllib.error
import urllib.request

import pytest

from cloud.companion.app import serve


def _server(tmp_path):
    httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
                  session_dir=str(tmp_path / "sess"))
    t = threading.Thread(target=httpd.serve_forever, daemon=True); t.start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def _req(url, method="GET", token=None, body=None, cookie=None):
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode(); headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if cookie is not None:
        headers["Cookie"] = "ets_session=" + cookie
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


# ---------------- KEYED mode (gate armed) -----------------------------------

def test_owner_routes_401_visitor_read_routes_open(tmp_path, monkeypatch):
    monkeypatch.setenv("ETS_ACCESS_KEYS", "alpha,beta")
    httpd, url = _server(tmp_path)
    try:
        # VISITOR TIER (#16): read routes work WITHOUT a token (engine-free ones).
        for route in ("/api/status", "/api/explore"):
            code, _, _ = _req(url + route)
            assert code == 200, route
        # OWNER surfaces require a key -> 401 auth_required (the unlock affordance).
        # These are decided by the owner predicate BEFORE any player is built, so this
        # stays engine-free. (The visitor play/steer/open routes being NOT auth-blocked
        # is proven engine-free in test_visitor_tier, in public mode where no demo
        # engine is surfaced.)
        for route in ("/api/ingest", "/api/train", "/api/reset", "/api/share"):
            code, body, _ = _req(url + route, method="POST", body={})
            assert code == 401, route
            assert json.loads(body) == {
                "ok": False, "error": "unauthorized — enter your access key",
                "auth_required": True}, (route, json.loads(body))
    finally:
        httpd.shutdown(); httpd.server_close()


def test_bad_key_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("ETS_ACCESS_KEYS", "alpha,beta")
    httpd, url = _server(tmp_path)
    try:
        code, body, _ = _req(url + "/api/auth", method="POST", body={"key": "wrong"})
        assert code == 401
        j = json.loads(body)
        assert j["ok"] is False and j["auth_required"] is True
    finally:
        httpd.shutdown(); httpd.server_close()


def test_good_key_passes_and_token_unlocks(tmp_path, monkeypatch):
    monkeypatch.setenv("ETS_ACCESS_KEYS", "alpha,beta")
    httpd, url = _server(tmp_path)
    try:
        code, body, hdrs = _req(url + "/api/auth", method="POST", body={"key": "beta"})
        assert code == 200
        j = json.loads(body)
        token = j["token"]
        assert j["ok"] is True and token and j["keyed"] is True
        # cookie is set for the browser
        assert "ets_session=" in hdrs.get("Set-Cookie", "")
        # the token unlocks a gated route (both Bearer and cookie transports)
        code, sbody, _ = _req(url + "/api/status", token=token)
        assert code == 200 and "files" in json.loads(sbody)
        code, _, _ = _req(url + "/api/status", cookie=token)
        assert code == 200
    finally:
        httpd.shutdown(); httpd.server_close()


def test_health_and_auth_stay_ungated(tmp_path, monkeypatch):
    monkeypatch.setenv("ETS_ACCESS_KEYS", "alpha")
    httpd, url = _server(tmp_path)
    try:
        code, body, _ = _req(url + "/api/health")
        assert code == 200 and json.loads(body)["ok"] is True
    finally:
        httpd.shutdown(); httpd.server_close()


def test_root_serves_app_no_access_wall(tmp_path, monkeypatch):
    # OPEN_ENDS #16: / ALWAYS serves the app — no access page, authenticated or not.
    monkeypatch.setenv("ETS_ACCESS_KEYS", "alpha")
    httpd, url = _server(tmp_path)
    try:
        code, body, _ = _req(url + "/")
        assert code == 200
        html = body.decode()
        assert 'id="accessGate"' not in html, "the access wall must be gone"
        assert 'id="instrument"' in html, "keyless visitor gets the app instrument"
        # with a valid token cookie -> still the app (identical surface).
        _, ab, _ = _req(url + "/api/auth", method="POST", body={"key": "alpha"})
        token = json.loads(ab)["token"]
        code, body2, _ = _req(url + "/", cookie=token)
        assert code == 200 and b'id="instrument"' in body2
        assert b'id="accessGate"' not in body2
    finally:
        httpd.shutdown(); httpd.server_close()


# ---------------- KEYLESS mode (gate disarmed = today's behavior) -----------

def test_keyless_is_completely_ungated(tmp_path, monkeypatch):
    monkeypatch.delenv("ETS_ACCESS_KEYS", raising=False)
    httpd, url = _server(tmp_path)
    try:
        # every gated-in-keyed route answers WITHOUT any token
        code, _, _ = _req(url + "/api/status")
        assert code == 200
        code, _, _ = _req(url + "/api/explore")
        assert code == 200
        # / serves the instrument, not an access page
        code, body, _ = _req(url + "/")
        assert code == 200 and b'id="accessGate"' not in body
        # /api/auth is a benign no-op success (keyed:false)
        code, body, _ = _req(url + "/api/auth", method="POST", body={"key": "anything"})
        assert code == 200 and json.loads(body)["keyed"] is False
    finally:
        httpd.shutdown(); httpd.server_close()
