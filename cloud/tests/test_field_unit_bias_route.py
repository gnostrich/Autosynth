"""PREREG-field-bias-REV3 Phase B — the /api/steer UNIT-BIAS routing (CI teeth).

The field is the single Play steering surface: a biased TRACK square rides
``channel_bias`` (the ratified REV2 roll-up path -> ``set_channel_bias``) and a biased
UNIT square rides ``unit_bias`` (the REV3 unit grain -> ``set_unit_bias``). This smoke
test pins the app-level ROUTING of the new unit grain end-to-end through the real
``/api/steer`` handler (a recorder stands in for the playable, so no engine is
needed):

  ROUTE     ``unit_bias`` in the POST body reaches ``p.set_unit_bias`` with the map.
  CLEAR     an ABSENT ``unit_bias`` clears it (``set_unit_bias(None)``) — a neutral
            field (which sends an empty map) disarms the grain, no stale lean.
  REV2      ``channel_bias`` still routes to ``set_channel_bias`` (regression: the
            ratified track path is untouched).

Both grains empty ⇒ each setter clears ⇒ no fiber addend ⇒ byte-identical audio (the
byte-identity invariant is proven at the mechanism level in test_channel_bias.py; here
we only prove the wire routing).
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from cloud.companion.app import serve


class _Recorder:
    """Stands in for a playable; records every setter call the steer branch makes."""

    def __init__(self):
        self.calls = {}

    def __getattr__(self, name):
        def _f(*a, **k):
            self.calls.setdefault(name, []).append(a[0] if len(a) == 1 else a)
        return _f


def _server(tmp_path, monkeypatch):
    monkeypatch.delenv("ETS_ACCESS_KEYS", raising=False)
    httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
                  session_dir=str(tmp_path / "sess"), public=True)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def _post(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url + "/api/steer", data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_api_steer_routes_unit_bias_to_set_unit_bias(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, monkeypatch)
    try:
        rec = _Recorder()
        httpd.hub.playable_for = lambda session: rec   # inject the recorder

        # (1) unit_bias present -> set_unit_bias called with the map
        assert _post(url, {"region": [], "channel_bias": [],
                           "unit_bias": {"20": 0.6}}) == 200
        assert rec.calls.get("set_unit_bias"), "set_unit_bias was never called"
        assert rec.calls["set_unit_bias"][-1] == {"20": 0.6}, \
            "unit_bias body must reach set_unit_bias verbatim"

        # (2) unit_bias ABSENT -> cleared (set_unit_bias(None)) — neutral field disarms
        assert _post(url, {"region": []}) == 200
        assert rec.calls["set_unit_bias"][-1] is None, \
            "an absent unit_bias must clear the grain (set_unit_bias(None))"

        # (3) REV2 regression: channel_bias still routes to set_channel_bias
        assert _post(url, {"region": [], "channel_bias": [0.5, 0.0]}) == 200
        assert rec.calls.get("set_channel_bias"), "set_channel_bias was never called"
        assert rec.calls["set_channel_bias"][-1] == [0.5, 0.0], \
            "channel_bias must still route to set_channel_bias (ratified REV2 path)"
    finally:
        httpd.shutdown()
        httpd.server_close()
