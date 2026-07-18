"""OPEN_ENDS #16(c) — NO founding demo surfaced on the hosted site.

The operator's decision (2026-07-18): the founding demo is NOT auto-loaded or
exposed on the site. For ANY hosted session (keyless or keyed) the initial Play
state is EMPTY until (a) the user opens a shared set from Explore, or (b) a keyed
user trains their own world. The demo stays in the repo for the LOCAL / fresh-clone
path (R5) — this is purely a HOSTED-surface decision, gated on ``public``.

These checks pin four facts:

  NO-BOOT   a public Hub loads NOTHING at boot — no demo world is auto-picked and
            the shared demo engine never spins up (a memory win + the honest empty
            surface). A LOCAL (non-public) Hub keeps the demo (R5 preserved).
  EMPTY     a fresh hosted session's /api/world is ready:false + loaded:false with
            an HONEST reason (keyless -> "open a shared set from Explore"; keyed
            owner -> also offered "train your own"). Engine-free: no world loads.
  OPEN      after a shared set is opened, the session resolves to a ready world.
  TRAIN     after training (its post-state: is_trained + play_world -> the trained
            world), a keyed session resolves to a ready world.

The empty-state checks are ENGINE-FREE (a session with no world never constructs a
player); OPEN/TRAIN inject a fake player (``app._build_stream_player``) so they run
offline, exactly like test_explore_shared_sets.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import cloud.companion.app as app
from cloud.companion.app import Hub, serve


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #

class _FakeReadyPlayer:
    """A player whose world_info reports a READY world (the shape the real
    StreamPlayer returns once a world is loaded)."""
    def __init__(self, path, seed, is_trained):
        self.path = path; self.regions = []
        self.started = False
    def start(self): self.started = True   # pre-warm target (OPEN_ENDS #21d)
    def stop(self): pass
    def set_region(self, r): self.regions.append(r)
    def world_info(self):
        return {"ready": True, "M": 4, "sr": 48000, "region_armed": True,
                "disarmed": [], "is_trained": True}
    def static_field(self):
        return {"profiles": {}, "unit_pools": {}, "track_names": {}}


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


# --------------------------------------------------------------------------- #
# NO-BOOT — a public Hub loads nothing; a local Hub keeps the demo (R5)        #
# --------------------------------------------------------------------------- #

def test_public_hub_surfaces_no_demo_and_loads_nothing_at_boot(tmp_path):
    hub = Hub(session_dir=str(tmp_path / "s"), public=True)
    sess = hub.default_session
    # no world auto-picked: the initial Play state is empty on the site.
    assert sess.play_world is None, "public deploy must not auto-load the demo"
    assert sess._demo_world is None, "reset must revert to EMPTY, not the demo"
    assert sess.player() is None, "no world -> no engine"
    # the shared demo engine never spun up at boot (memory win), and no trained/
    # shared world is resident either.
    assert hub.registry._demo is None
    assert hub.registry.loaded_worlds() == []


def test_local_hub_keeps_the_demo_for_the_fresh_clone_path(tmp_path):
    # LOCAL (non-public) run: R5 preserved — the committed demo is still the default
    # so a fresh clone plays out of the box. (The engine is NOT built at boot — the
    # player stays lazy — but the world is SELECTED.)
    hub = Hub(session_dir=str(tmp_path / "s"), public=False)
    sess = hub.default_session
    demo = app._REPO_ROOT / "demo.etsworld"
    if demo.exists():
        assert sess.play_world == str(demo), "local run keeps the founding demo (R5)"
        assert sess._demo_world == str(demo)
    # still no boot-time engine construction either way (lazy).
    assert hub.registry._demo is None
    assert hub.registry.loaded_worlds() == []


# --------------------------------------------------------------------------- #
# EMPTY — a fresh hosted session's /api/world is honestly empty (engine-free)  #
# --------------------------------------------------------------------------- #

def test_public_keyless_world_is_empty_with_honest_reason(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, public=True, keys=[], monkeypatch=monkeypatch)
    try:
        code, body = _req(url + "/api/world")
        assert code == 200, (code, body)
        w = json.loads(body)
        assert w["ready"] is False and w["loaded"] is False, w
        assert "Explore" in w["reason"], w
        # a keyless-public visitor is not an owner -> no "train your own" offer.
        assert "train" not in w["reason"].lower(), w
    finally:
        httpd.shutdown(); httpd.server_close()


def test_public_keyed_owner_world_is_empty_until_train(tmp_path, monkeypatch):
    httpd, url = _server(tmp_path, public=True, keys=["k1"], monkeypatch=monkeypatch)
    try:
        tok = _auth(url, "k1")
        code, body = _req(url + "/api/world", token=tok)
        assert code == 200, (code, body)
        w = json.loads(body)
        # keyed owner also lands EMPTY (no founding demo for keyed either, #16(c)) —
        # but the reason offers the owner's path: train your own.
        assert w["ready"] is False and w["loaded"] is False, w
        assert "train" in w["reason"].lower(), w
        assert w["can_train"] is True, w
    finally:
        httpd.shutdown(); httpd.server_close()


# --------------------------------------------------------------------------- #
# OPEN / TRAIN — the empty surface becomes ready via the two sanctioned paths  #
# --------------------------------------------------------------------------- #

def test_opening_a_shared_set_makes_the_world_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "_build_stream_player",
                        lambda path, seed, is_trained: _FakeReadyPlayer(path, seed, is_trained))
    hub = Hub(session_dir=str(tmp_path), access_keys=["k"], public=True)
    # owner trains (simulate its post-state) + shares
    owner = hub.session_for_token(hub.authenticate("k"))
    tw = Path(owner.session_dir) / "trained.etsworld"; tw.write_bytes(b"world")
    owner._is_trained = True
    owner.play_world = str(tw)
    hub.share(owner, True)

    visitor = hub.session_for_token(hub.authenticate("k"))
    # fresh visitor is EMPTY (public, no demo) until it opens something
    assert hub.playable_for(visitor) is None
    assert hub.open_set(visitor, owner.set_id) is not None
    p = hub.playable_for(visitor)
    assert p is not None and p.world_info()["ready"] is True


def test_keyed_train_post_state_makes_the_world_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "_build_stream_player",
                        lambda path, seed, is_trained: _FakeReadyPlayer(path, seed, is_trained))
    hub = Hub(session_dir=str(tmp_path), access_keys=["k"], public=True)
    owner = hub.session_for_token(hub.authenticate("k"))
    # fresh keyed session starts EMPTY (no founding demo)
    assert hub.playable_for(owner) is None
    # train's post-state: is_trained + play_world repointed at the trained world
    tw = Path(owner.session_dir) / "trained.etsworld"; tw.write_bytes(b"world")
    owner._is_trained = True
    owner.play_world = str(tw)
    p = hub.playable_for(owner)
    assert p is not None and p.world_info()["ready"] is True
