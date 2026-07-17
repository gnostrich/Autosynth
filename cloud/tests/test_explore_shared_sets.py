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
    def stop(self): pass
    def set_region(self, r): self.regions.append(r)
    def world_info(self): return {"region_armed": True, "disarmed": []}


@pytest.fixture
def hub(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "_build_stream_player",
                        lambda path, seed, is_trained: _FakePlayer(path, seed, is_trained))
    demo = tmp_path / "demo.etsworld"; demo.write_bytes(b"demo")
    h = Hub(session_dir=str(tmp_path), access_keys=["k"], play_world=str(demo))
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
    visitor = hub.session_for_token(hub.authenticate("k"))
    # not shared yet: not in the catalog, not openable by its real id
    assert hub.explore(visitor) == []
    assert hub.open_set(visitor, owner.set_id) is None
    # a bogus id is likewise unreachable
    assert hub.open_set(visitor, "set-does-not-exist") is None


# ---------------- EXP-B -----------------------------------------------------

def test_unshare_revokes_immediately(hub, tmp_path):
    owner = _owner_with_trained_set(hub, tmp_path)
    visitor = hub.session_for_token(hub.authenticate("k"))

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
    stranger = hub.session_for_token(hub.authenticate("k"))
    hub.share(stranger, False)            # stranger has no trained set of its own
    assert [e["id"] for e in hub.explore(owner)] == [owner.set_id]


# ---------------- EXP-C -----------------------------------------------------

def test_visitor_steer_is_region_tilt_only(hub, tmp_path):
    owner = _owner_with_trained_set(hub, tmp_path)
    hub.share(owner, True)
    visitor = hub.session_for_token(hub.authenticate("k"))
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
