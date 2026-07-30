"""/api/wavemap — the FROZEN read-only contract the TRACKS view codes against
(PREREG-waveform-scrub technical annex).

  GET /api/wavemap  (same session/access resolution as /api/world; serves the SAME
  world ``playable_for(session)`` resolves)
    200 {ok, M, sr, q_source, tracks: {"<tid>": {name, duration_s,
         peaks:[~800 floats 0..1], slices:[[t0_s, t1_s, uid, m, [q_0..q_{M-1}]]]}}}
    409 {ok:false, error} — no playable world, OR a world that cannot yield an
        HONEST map (embedded sources = no user audio file; a source file that is
        missing or no longer matches the ingested track; a world that stores no
        per-unit role assignment). Never a partial or filled-in map.

Gated here: the 200 shape end-to-end over HTTP on a REAL trained world; the honest
409s (no world; the demo world's embedded sources; a vanished source file); and the
single-source-of-truth naming claim — the lane names must EQUAL /api/world's
``track_names`` for the same session, so a track can never be labelled two ways.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from cloud.companion.app import serve
from cloud.tests.test_wavemap_fixture import probe

# --- in-process: the no-playable-world refusal (no engine needed) ------------


def _server(tmp_path, monkeypatch):
    monkeypatch.delenv("ETS_ACCESS_KEYS", raising=False)
    httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
                  session_dir=str(tmp_path / "sess"), public=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def _get(url):
    try:
        with urllib.request.urlopen(url + "/api/wavemap", timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_no_playable_world_refuses_with_409_and_an_honest_reason(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, monkeypatch)
    try:
        httpd.hub.playable_for = lambda session: None
        status, body = _get(url)
        assert status == 409, f"expected 409 with no playable world, got {status}"
        assert body["ok"] is False and "no set loaded" in body["error"], body
    finally:
        httpd.shutdown()
        httpd.server_close()


# --- out-of-process: the real world / real engine arms -----------------------

_PROBE = r'''
import json, os, shutil, threading, urllib.error, urllib.request
from cloud.companion.app import serve
from cloud.companion.engine_bridge import StreamPlayer

httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
              session_dir=os.path.join(WDIR, "sess-ep"), public=True)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % httpd.server_address[1]

def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=300) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)

# (1) a REAL trained world (the fixture): the 200 contract + naming agreement.
#     A small eigen ensemble keeps /api/world's background measurement cheap here;
#     it has no bearing on the wavemap (which never touches the eigen path).
trained = StreamPlayer(WORLD, seed=0, is_trained=True, eigen_n_seed=2, eigen_n_bar=2)
httpd.hub.playable_for = lambda session, _p=trained: _p
wm_status, wm = get("/api/wavemap")
world_status, world = get("/api/world")

# (2) the DEMO world: EMBEDDED source units, no user audio file -> honest refusal.
demo = StreamPlayer("demo.etsworld", seed=0)
httpd.hub.playable_for = lambda session, _p=demo: _p
demo_status, demo_body = get("/api/wavemap")

# (3) a VANISHED source file -> honest refusal (never a half map). The file is moved
#     aside and restored; a fresh player is used so no memoized map can mask it.
httpd.hub.playable_for = lambda session, _p=trained: _p
src = os.path.join(WDIR, "t1.wav")
shutil.move(src, src + ".hidden")
try:
    gone = StreamPlayer(WORLD, seed=0, is_trained=True)
    httpd.hub.playable_for = lambda session, _p=gone: _p
    gone_status, gone_body = get("/api/wavemap")
finally:
    shutil.move(src + ".hidden", src)

emit({"wm_status": wm_status, "wm": wm,
      "world_status": world_status, "world_names": world.get("track_names"),
      "demo_status": demo_status, "demo_body": demo_body,
      "gone_status": gone_status, "gone_body": gone_body})
'''


def _d():
    if not hasattr(_d, "_v"):
        _d._v = probe(_PROBE)
    return _d._v


def test_trained_world_serves_the_frozen_contract():
    d = _d()
    assert d["wm_status"] == 200, d
    wm = d["wm"]
    assert set(wm) == {"ok", "M", "sr", "q_source", "tracks"}, sorted(wm)
    assert wm["ok"] is True
    assert isinstance(wm["M"], int) and wm["M"] >= 1
    assert isinstance(wm["sr"], int) and wm["sr"] > 0
    assert isinstance(wm["q_source"], str) and "unit_role" in wm["q_source"], \
        "the payload must disclose WHICH stored object q comes from"
    assert wm["tracks"], "no tracks served"
    for tid, tr in wm["tracks"].items():
        assert int(tid) >= 0, f"track key must be a track id: {tid!r}"
        assert set(tr) == {"name", "duration_s", "peaks", "slices"}, sorted(tr)
        assert isinstance(tr["name"], str) and tr["name"]
        assert tr["duration_s"] > 0
        assert len(tr["peaks"]) == 800
        assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in tr["peaks"])
        for s in tr["slices"]:
            assert len(s) == 5, f"slice must be [t0, t1, uid, m, q]: {s}"
            t0, t1, uid, m, q = s
            assert isinstance(uid, int) and uid >= 0
            assert isinstance(m, float) and m >= 0.0
            assert len(q) == wm["M"], f"q must be an M-vector: {q}"
            assert abs(sum(q) - 1.0) < 1e-12, f"q must be normalized: {q}"
            assert 0.0 <= t0 < t1 <= tr["duration_s"] + 1e-9


def test_lane_names_equal_api_world_track_names():
    """ONE naming rule: whatever /api/world calls a track, the lane calls it too."""
    d = _d()
    assert d["world_status"] == 200
    wm_names = {str(tid): tr["name"] for tid, tr in d["wm"]["tracks"].items()}
    world_names = {str(k): v for k, v in (d["world_names"] or {}).items()}
    assert wm_names == world_names, (
        f"lane names disagree with /api/world's track_names: {wm_names} vs {world_names}")


def test_embedded_source_world_refuses_honestly():
    """The demo/founding world carries EMBEDDED units, not the user's audio file —
    there is no given material to draw, and none is invented."""
    d = _d()
    assert d["demo_status"] == 409, d["demo_body"]
    assert d["demo_body"]["ok"] is False
    assert "embedded" in d["demo_body"]["error"], d["demo_body"]
    assert "tracks" not in d["demo_body"], "a refusal must not carry a partial map"


def test_the_one_naming_rule_is_honest_on_both_branches():
    """The shared rule itself (``_Handler._honest_track_names``, called by BOTH
    /api/world and /api/wavemap): a session's OWN trained world gets its real
    ingested filenames; an OPENED shared set gets the names its owner published;
    anything else keeps the world's honest generic label — never an invented name."""
    from types import SimpleNamespace
    from cloud.companion.app import _Handler

    base = {"0": "track 0", "1": "track 1"}
    rule = _Handler._honest_track_names

    own = SimpleNamespace(_is_trained=True, opened_set_id=None,
                          ingested_track_names=lambda: ["bass.wav", "kick.mp3"])
    me = SimpleNamespace(hub=SimpleNamespace(catalog={}))
    assert rule(me, own, base) == {"0": "bass.wav", "1": "kick.mp3"}

    entry = SimpleNamespace(track_names={0: "their_bass.wav"})
    opener = SimpleNamespace(_is_trained=False, opened_set_id="set-1",
                             ingested_track_names=lambda: [])
    shared_me = SimpleNamespace(hub=SimpleNamespace(catalog={"set-1": entry}))
    assert rule(shared_me, opener, base) == {"0": "their_bass.wav", "1": "track 1"}

    plain = SimpleNamespace(_is_trained=False, opened_set_id=None,
                            ingested_track_names=lambda: [])
    assert rule(me, plain, base) == base


def test_vanished_source_file_refuses_honestly():
    d = _d()
    assert d["gone_status"] == 409, d["gone_body"]
    assert d["gone_body"]["ok"] is False
    assert "source audio" in d["gone_body"]["error"], d["gone_body"]
    assert "tracks" not in d["gone_body"], "a refusal must not carry a partial map"
