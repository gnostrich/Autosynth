"""EXP-A..E — the opt-in share + Explore layer, per PREREG-explore-shared-sets.md.

Demo-fork reading (operator-signed 2026-07-17): the simplest opt-in share on the
hosted topology. Sharing is a server-side catalog toggle (metadata only); playing a
shared set reuses the SAME LRU render path a session's own trained world uses; the
visitor's only control over a shared set is the region-tilt lane. These tests prove:

  EXP-A  an unshared / unknown set is unreachable by direct id and unlisted.
  EXP-B  unshare revokes immediately: delisted, unopenable, and a held handle reverts.
  EXP-C  the visitor->shared-set control boundary is region-tilt ONLY.
  EXP-D  toggling share puts NOTHING new on the wire (no cloud call; metadata only).
  EXP-E  the share/explore path imports no renderer/decoder (no cloud decoder).

The heavy engine is injected (``app._build_stream_player``) so these run offline.
"""
from pathlib import Path

import pytest

import cloud.companion.app as app
from cloud.companion.app import Hub


class _FakePlayer:
    def __init__(self, path, seed, is_trained):
        self.path = path; self.regions = []
        self.started = False
    def start(self): self.started = True   # pre-warm target (OPEN_ENDS #21d)
    def stop(self): pass
    def set_region(self, r): self.regions.append(r)
    def world_info(self): return {"region_armed": True, "disarmed": []}
    def static_field(self):
        # the bridge's honest generics for a 2-track trained world (the /api/world
        # name override rewrites these from session / share-catalog metadata).
        return {"profiles": {}, "unit_pools": {},
                "track_names": {0: "track 0", 1: "track 1"}}


@pytest.fixture
def hub(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "_build_stream_player",
                        lambda path, seed, is_trained: _FakePlayer(path, seed, is_trained))
    demo = tmp_path / "demo.etsworld"; demo.write_bytes(b"demo")
    h = Hub(session_dir=str(tmp_path), access_keys=["k", "k2"], play_world=str(demo))
    h._demo_file = str(demo)
    return h


def _owner_with_trained_set(hub, tmp_path, name="Owner Set"):
    owner = hub.session_for_token(hub.authenticate("k"))
    tw = Path(owner.session_dir) / "trained.etsworld"; tw.write_bytes(b"world")
    owner._is_trained = True
    owner.play_world = str(tw)
    owner.set_name = name
    return owner


# ---------------- EXP-A -----------------------------------------------------

def test_unshared_set_is_unreachable_and_unlisted(hub, tmp_path):
    owner = _owner_with_trained_set(hub, tmp_path)
    visitor = hub.session_for_token(hub.authenticate("k2"))
    # not shared yet: not in the catalog, not openable by its real id
    assert hub.explore(visitor) == []
    assert hub.open_set(visitor, owner.set_id) is None
    # a bogus id is likewise unreachable
    assert hub.open_set(visitor, "set-does-not-exist") is None


# ---------------- EXP-B -----------------------------------------------------

def test_unshare_revokes_immediately(hub, tmp_path):
    owner = _owner_with_trained_set(hub, tmp_path)
    visitor = hub.session_for_token(hub.authenticate("k2"))

    hub.share(owner, True)
    assert [e["id"] for e in hub.explore(visitor)] == [owner.set_id]
    # visitor opens it and holds the handle (its player resolves to the shared world)
    assert hub.open_set(visitor, owner.set_id) is not None
    assert visitor.opened_set_id == owner.set_id
    p_shared = hub.playable_for(visitor)
    assert p_shared.path == owner.play_world

    # owner unshares -> delisted, unopenable, AND the held handle reverts to demo
    hub.share(owner, False)
    assert hub.explore(visitor) == []
    assert hub.open_set(visitor, owner.set_id) is None
    p_after = hub.playable_for(visitor)
    assert visitor.opened_set_id is None, "held handle must be revoked"
    assert visitor.play_world == visitor._demo_world
    assert p_after.path == hub._demo_file, "visitor reverts to the demo engine"


def test_only_owner_can_unshare(hub, tmp_path):
    owner = _owner_with_trained_set(hub, tmp_path)
    hub.share(owner, True)
    # a different session cannot delist someone else's set via share() (it targets
    # the CALLER's own set_id) — the catalog entry survives.
    stranger = hub.session_for_token(hub.authenticate("k2"))
    hub.share(stranger, False)            # stranger has no trained set of its own
    assert [e["id"] for e in hub.explore(owner)] == [owner.set_id]


# ---------------- EXP-C -----------------------------------------------------

def test_visitor_steer_is_region_tilt_only(hub, tmp_path):
    owner = _owner_with_trained_set(hub, tmp_path)
    hub.share(owner, True)
    visitor = hub.session_for_token(hub.authenticate("k2"))
    hub.open_set(visitor, owner.set_id)
    p = hub.playable_for(visitor)

    # the visitor's ONLY engine-control surface is set_region (the region-tilt lane).
    p.set_region([0.2, 0.0])
    assert p.regions == [[0.2, 0.0]]

    # opening/steering a shared set grants NO ingest/train authority over it: the
    # visitor's ingest lands in the VISITOR's own dir, leaving the shared world byte-
    # identical (there is no path to mutate someone else's set).
    before = Path(owner.play_world).read_bytes()
    visitor.ingest_bytes("mine.wav", b"raw")
    assert "mine.wav" in visitor.session_files()
    assert Path(owner.play_world).read_bytes() == before
    assert Path(owner.play_world).parent != Path(visitor.session_dir)


def test_set_region_is_the_single_call_site():
    # static boundary (mirrors the mvp2 check, re-asserted for the sharing surface):
    # /api/steer is the ONLY route that reaches settlement, one call site total.
    src = (Path(app.__file__)).read_text()
    assert src.count(".set_region(") == 1
    steer = src.index('"/api/steer"'); call = src.index(".set_region(")
    play = src.index('"/api/play"')
    assert steer < call < play


# ---------------- EXP-D -----------------------------------------------------

def test_sharing_puts_nothing_new_on_the_wire(hub, tmp_path, monkeypatch):
    # a tripwire on the guarded wire exit — share/unshare must never call it.
    import cloud.client.cli as cli
    tripped = {"hit": False}
    def _trip(*a, **k):
        tripped["hit"] = True
        raise AssertionError("sharing must not contact the cloud")
    monkeypatch.setattr(cli, "post_job", _trip)

    owner = _owner_with_trained_set(hub, tmp_path)
    hub.share(owner, True)
    view = hub.explore(owner)[0]
    hub.share(owner, False)
    assert tripped["hit"] is False
    # the catalog view is metadata only — no audio/recipe/realization keys.
    assert set(view) == {"id", "name", "owner", "availability", "region_armed",
                         "disarmed", "mine"}


# ---------------- EXP-E -----------------------------------------------------

def test_share_explore_path_imports_no_decoder():
    # static: the catalog/share/explore surface (app.py) imports no renderer/audio
    # module on its top-level graph (mirror MVP2-B). Every sample a visitor hears is
    # rendered by a device-local engine bridge, never on the sharing server.
    import ast
    tree = ast.parse(Path(app.__file__).read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                mods.add(n.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
            for n in node.names:
                mods.add(node.module + "." + n.name)
    banned = {"ets.render", "ets.writer", "soundfile", "sounddevice", "pyaudio"}
    banned_leaf = {"build_index"}
    hit = {m for m in mods
           if m in banned or any(m == b or m.startswith(b + ".") for b in banned)
           or m.rsplit(".", 1)[-1] in banned_leaf}
    assert not hit, f"share/explore path imports a decoder: {hit}"


# ---------------- honest shared track names (owner opt-in attribution) -------

def test_share_snapshots_the_real_ingested_track_names(hub, tmp_path):
    owner = _owner_with_trained_set(hub, tmp_path)
    # the owner's real corpus: index i = track id i (the train-seam sort order).
    Path(owner.session_dir, "bass_take2.wav").write_bytes(b"a")
    Path(owner.session_dir, "kick_loop.mp3").write_bytes(b"b")
    hub.share(owner, True)
    entry = hub.catalog[owner.set_id]
    assert entry.track_names == {0: "bass_take2.wav", 1: "kick_loop.mp3"}
    # the PUBLIC catalog card stays metadata-only (names travel via /api/world to
    # sessions that OPENED the set, not via the Explore listing).
    assert "track_names" not in hub.explore(owner)[0]


def test_share_with_no_ingested_audio_keeps_generic_labels(hub, tmp_path):
    owner = _owner_with_trained_set(hub, tmp_path)     # no audio files in the dir
    hub.share(owner, True)
    assert hub.catalog[owner.set_id].track_names == {}, \
        "no real names -> no names (never invented)"


def test_opened_shared_set_serves_owner_published_names_end_to_end(tmp_path, monkeypatch):
    """End-to-end over HTTP: the owner shares a set (with real ingested names); an
    ANONYMOUS visitor (cookie-minted session) opens it and /api/world returns those
    names — the legend shows honest attribution, not 'track N'."""
    import json
    import threading
    import urllib.request
    from cloud.companion.app import serve

    monkeypatch.setattr(app, "_build_stream_player",
                        lambda path, seed, is_trained: _FakePlayer(path, seed, is_trained))
    monkeypatch.setenv("ETS_ACCESS_KEYS", "k1")
    httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
                  session_dir=str(tmp_path / "sess"), public=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d" % httpd.server_address[1]

    def req(path, method="GET", cookie=None, token=None, body=None):
        headers = {}
        data = json.dumps(body).encode() if body is not None else None
        if cookie:
            headers["Cookie"] = "ets_session=" + cookie
        if token:
            headers["Authorization"] = "Bearer " + token
        r = urllib.request.Request(url + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(r, timeout=30) as resp:
            sc = dict(resp.headers).get("Set-Cookie", "")
            minted = sc.split("ets_session=", 1)[1].split(";", 1)[0] \
                if "ets_session=" in sc else None
            return resp.status, json.loads(resp.read() or b"{}"), minted

    try:
        # OWNER: authenticate, fake a trained 2-track corpus, share it over the wire.
        _, auth, _ = req("/api/auth", method="POST", body={"key": "k1"})
        tok = auth["token"]
        owner = httpd.hub.sessions[tok]
        tw = Path(owner.session_dir) / "trained.etsworld"
        tw.write_bytes(b"world")
        Path(owner.session_dir, "bass_take2.wav").write_bytes(b"a")
        Path(owner.session_dir, "kick_loop.mp3").write_bytes(b"b")
        owner._is_trained = True
        owner.play_world = str(tw)
        code, sh, _ = req("/api/share", method="POST", token=tok,
                          body={"on": True, "name": "My Set"})
        assert code == 200 and sh["ok"] is True

        # ANONYMOUS visitor: cookie minted on first contact; open the shared set.
        _, _, vtok = req("/api/status")
        assert vtok
        code, opened, _ = req("/api/open", method="POST", cookie=vtok,
                              body={"set_id": sh["set_id"]})
        assert code == 200 and opened["ok"] is True
        # /api/world for the opener carries the owner's REAL published names.
        _, w, _ = req("/api/world", cookie=vtok)
        assert w["track_names"] == {"0": "bass_take2.wav", "1": "kick_loop.mp3"}, w

        # a fresh anonymous visitor who did NOT open it sees nothing of the set.
        _, w2, _ = req("/api/world")
        assert w2.get("track_names") is None and w2["loaded"] is False
    finally:
        httpd.shutdown(); httpd.server_close()
