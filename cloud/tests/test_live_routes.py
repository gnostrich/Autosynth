"""LIVE mode — the three HTTP routes (Train B2, playable milestone only):

  POST /api/live/start  {"track": <int>, "t": <seconds>}
       -> {"ok":true,"mode":"straight","track":<int>,"unit":<int>}
  POST /api/live/enter   -> {"ok":true,"mode":"idle"}   (hold, scoped to LIVE)
  POST /api/live/stop    -> {"ok":true,"mode":"off"}    (release to GRID/TRACKS)
  GET  /api/live/state   -> {"ok":true,"mode":"idle"|"straight",
                              "track":<int|null>,"unit":<int|null>,
                              "slice_index":<int|null>,"starved":<bool>}

Driven exactly like cloud/tests/test_field_unit_bias_route.py: a fake
"playable" object stands in for the engine (a recorder for start/stop, a
canned dict for state), so the ROUTING is pinned end-to-end over real HTTP
without needing a world or the Part-A carrier. No edits to any GRID/TRACKS
route in app.py; these three are new, additive branches only (LM-0).
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from cloud.companion.app import serve
from cloud.companion.live import LiveCarrierUnavailable


class _FakeLivePlayer:
    """Stands in for a StreamPlayer for the three LIVE routes only."""

    def __init__(self, start_result=None, start_exc=None, state=None):
        self.calls = []
        self._start_result = start_result
        self._start_exc = start_exc
        self._state = state or {"mode": "idle", "track": None, "unit": None,
                                "slice_index": None, "starved": False}

    def live_start(self, track, t):
        self.calls.append(("live_start", track, t))
        if self._start_exc is not None:
            raise self._start_exc
        return self._start_result

    def live_click(self, track, t):
        # THE route's real entry point since the 2026-08-14 bridge reframe:
        # StreamPlayer.live_click dispatches internally to live_start (idle)
        # or the bridge (already-playing) — that dispatch logic is exercised
        # against the REAL engine in test_live_engine_integration.py; this
        # fake only pins the ROUTE's own contract (status/body shape), so it
        # reuses the SAME canned result/exception live_start already had.
        self.calls.append(("live_click", track, t))
        if self._start_exc is not None:
            raise self._start_exc
        return self._start_result

    def live_stop(self):
        self.calls.append(("live_stop",))

    def live_state(self):
        self.calls.append(("live_state",))
        return dict(self._state)


def _server(tmp_path, monkeypatch):
    monkeypatch.delenv("ETS_ACCESS_KEYS", raising=False)
    httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
                  session_dir=str(tmp_path / "sess"), public=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def _post(url, path, body):
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(url + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def _get(url, path):
    try:
        with urllib.request.urlopen(url + path, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


# --- /api/live/start ------------------------------------------------------

def test_live_start_routes_track_and_t_and_returns_the_straight_contract(
        tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, monkeypatch)
    try:
        fake = _FakeLivePlayer(start_result={"track": 2, "unit": 137})
        httpd.hub.playable_for = lambda session: fake
        status, body = _post(url, "/api/live/start", {"track": 2, "t": 4.5})
        assert status == 200, body
        assert body == {"ok": True, "mode": "straight", "track": 2, "unit": 137}
        assert fake.calls == [("live_click", 2, 4.5)]
    finally:
        httpd.shutdown(); httpd.server_close()


def test_live_start_no_playable_world_refuses_with_409(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, monkeypatch)
    try:
        httpd.hub.playable_for = lambda session: None
        status, body = _post(url, "/api/live/start", {"track": 0, "t": 0.0})
        assert status == 409
        assert body["ok"] is False
    finally:
        httpd.shutdown(); httpd.server_close()


def test_live_start_missing_body_fields_refuses_with_400(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, monkeypatch)
    try:
        fake = _FakeLivePlayer()
        httpd.hub.playable_for = lambda session: fake
        status, body = _post(url, "/api/live/start", {"track": 0})   # no "t"
        assert status == 400
        assert body["ok"] is False
        assert fake.calls == [], "must not call live_start on a malformed body"
    finally:
        httpd.shutdown(); httpd.server_close()


def test_live_start_carrier_unavailable_refuses_honestly_never_falls_back(
        tmp_path, monkeypatch):
    """A-2/A2.3: an unavailable/unwired carrier must be a clear, honest
    refusal — never a 200 that silently played unfenced."""
    httpd, url = _server(tmp_path, monkeypatch)
    try:
        fake = _FakeLivePlayer(start_exc=LiveCarrierUnavailable(
            "ets.writer.clamp.clamp0 is not importable yet"))
        httpd.hub.playable_for = lambda session: fake
        status, body = _post(url, "/api/live/start", {"track": 0, "t": 0.0})
        assert status == 503, body
        assert body["ok"] is False
        assert "clamp0" in body["error"]
    finally:
        httpd.shutdown(); httpd.server_close()


def test_live_start_unknown_track_refuses_with_400(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, monkeypatch)
    try:
        fake = _FakeLivePlayer(start_exc=ValueError("unknown track 9"))
        httpd.hub.playable_for = lambda session: fake
        status, body = _post(url, "/api/live/start", {"track": 9, "t": 0.0})
        assert status == 400, body
        assert body["ok"] is False
    finally:
        httpd.shutdown(); httpd.server_close()


# --- /api/live/stop (V-1) --------------------------------------------------

def test_live_stop_calls_live_stop_and_reports_idle(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, monkeypatch)
    try:
        fake = _FakeLivePlayer()
        httpd.hub.playable_for = lambda session: fake
        status, body = _post(url, "/api/live/stop", None)
        assert status == 200
        assert body == {"ok": True, "mode": "off"}
        assert fake.calls == [("live_stop",)]
    finally:
        httpd.shutdown(); httpd.server_close()


def test_live_stop_with_no_playable_world_still_reports_idle(tmp_path, monkeypatch):
    """V-1: stop must ALWAYS be able to establish idle — even a session with
    no world loaded yet reports the honest idle contract, never an error."""
    httpd, url = _server(tmp_path, monkeypatch)
    try:
        httpd.hub.playable_for = lambda session: None
        status, body = _post(url, "/api/live/stop", None)
        assert status == 200
        assert body == {"ok": True, "mode": "off"}
    finally:
        httpd.shutdown(); httpd.server_close()


# --- /api/live/state (measured, not asserted) ------------------------------

def test_live_state_reports_the_players_own_measured_state(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, monkeypatch)
    try:
        fake = _FakeLivePlayer(state={"mode": "straight", "track": 1, "unit": 55,
                                      "slice_index": 12, "starved": False})
        httpd.hub.playable_for = lambda session: fake
        status, body = _get(url, "/api/live/state")
        assert status == 200
        assert body == {"ok": True, "mode": "straight", "track": 1, "unit": 55,
                        "slice_index": 12, "starved": False}
        assert fake.calls == [("live_state",)]
    finally:
        httpd.shutdown(); httpd.server_close()


def test_live_state_no_playable_world_is_honest_idle_not_an_error(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, monkeypatch)
    try:
        httpd.hub.playable_for = lambda session: None
        status, body = _get(url, "/api/live/state")
        assert status == 200
        assert body["ok"] is True
        assert body["mode"] == "idle"
        assert body["track"] is None and body["unit"] is None
        assert body["slice_index"] is None and body["starved"] is False
    finally:
        httpd.shutdown(); httpd.server_close()


def test_live_state_starved_defaults_false_never_fabricated(tmp_path, monkeypatch):
    """If the carrier records no starvation evidence, the route reports
    False honestly (never guessed True, never omitted)."""
    httpd, url = _server(tmp_path, monkeypatch)
    try:
        fake = _FakeLivePlayer(state={"mode": "idle", "track": None, "unit": None,
                                      "slice_index": None, "starved": False})
        httpd.hub.playable_for = lambda session: fake
        status, body = _get(url, "/api/live/state")
        assert status == 200 and body["starved"] is False
    finally:
        httpd.shutdown(); httpd.server_close()
