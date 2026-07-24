"""Durable per-KEY owner identity + orphan adoption + async train reconcile.

The live failure this pins down (2026-07-24): every /api/auth minted a FRESH
session dir per token, so a re-login (new browser session / lost cookie)
stranded the operator's trained corpus in an orphaned visitor_* dir — "my
trained set is gone". The contract now:

  * ONE KEY = ONE SESSION, durably: authenticate() with the same key re-lands
    on the same session dir (corpus + trained world + pointers), resident or
    restored from owners.json, across logins AND redeploys.
  * ADOPTION: the first-ever login for a key adopts the most recent orphaned
    visitor_*/anon_* dir holding a trained world (or ingested audio) — a corpus
    trained under the old per-token scheme is recovered, not stranded.
  * /api/recover (key-gated) lists every on-volume dir holding a trained world
    or audio, and can repoint the owner session at one (pointers only).
  * ASYNC TRAIN (hosted): /api/train returns {training:true} immediately; the
    truth lives in /api/status (training/train_result/train_error); a re-click
    ATTACHES to the running train instead of double-training.
"""
import json
import threading
import time
from pathlib import Path

import pytest

from cloud.companion import app
from cloud.companion.app import Hub


class _FakePlayer:
    """Engine-build seam fake (same pattern as test_mem_bounds): these tests
    exercise session identity/recovery pointers, never real rendering — and the
    background WARM threads must not drag the real engine into sys.modules
    (test_role_grain_arming's interpreter-purity check would trip)."""
    def __init__(self, path, seed, is_trained=True):
        self.path, self.seed, self.is_trained = path, seed, is_trained
    def start(self):
        pass
    def world_info(self):
        return {"ready": True, "region_armed": False, "disarmed": []}


@pytest.fixture(autouse=True)
def _fake_engine(monkeypatch):
    monkeypatch.setattr(app, "_build_stream_player",
                        lambda path, seed, is_trained: _FakePlayer(path, seed, is_trained))


@pytest.fixture()
def demo(tmp_path):
    d = tmp_path / "demo.etsworld"
    d.write_bytes(b"demo")
    return d


def _hub(tmp_path, demo, keys=("k",)):
    return Hub(session_dir=str(tmp_path), access_keys=list(keys),
               play_world=str(demo))


# ---------------- per-key identity ------------------------------------------

def test_same_key_relogin_same_session(tmp_path, demo):
    hub = _hub(tmp_path, demo)
    a = hub.session_for_token(hub.authenticate("k"))
    b = hub.session_for_token(hub.authenticate("k"))
    assert a is b, "same key must resolve to the SAME session object"
    assert a.session_dir == b.session_dir


def test_same_key_survives_redeploy(tmp_path, demo):
    h1 = _hub(tmp_path, demo)
    s1 = h1.session_for_token(h1.authenticate("k"))
    (s1.session_dir / "track.wav").write_bytes(b"x")
    tw = s1.trained_world_path
    tw.write_bytes(b"world")
    s1.play_world = str(tw)
    s1._is_trained = True
    h1._persist_session(s1)
    # "redeploy": a fresh Hub over the same volume, a fresh login (NEW token)
    h2 = _hub(tmp_path, demo)
    s2 = h2.session_for_token(h2.authenticate("k"))
    assert s2.session_dir == s1.session_dir
    assert s2._is_trained is True
    assert s2.play_world == str(tw)
    assert s2.ingested_track_names() == ["track.wav"]


def test_distinct_keys_distinct_sessions(tmp_path, demo):
    hub = _hub(tmp_path, demo, keys=("k", "k2"))
    a = hub.session_for_token(hub.authenticate("k"))
    b = hub.session_for_token(hub.authenticate("k2"))
    assert a is not b
    assert a.session_dir != b.session_dir


# ---------------- orphan adoption -------------------------------------------

def test_first_login_adopts_orphaned_trained_dir(tmp_path, demo):
    # a corpus trained under the OLD per-token scheme sits orphaned on the volume
    orphan = tmp_path / "visitor_deadbeefdeadbeef"
    orphan.mkdir()
    (orphan / "one.wav").write_bytes(b"a")
    (orphan / "two.wav").write_bytes(b"b")
    (orphan / "trained.etsworld").write_bytes(b"world")
    hub = _hub(tmp_path, demo)
    s = hub.session_for_token(hub.authenticate("k"))
    assert s.session_dir == orphan, "first-ever login must ADOPT the orphan"
    assert s._is_trained is True
    assert s.play_world == str(orphan / "trained.etsworld")
    assert s.ingested_track_names() == ["one.wav", "two.wav"]


def test_adoption_prefers_newest_trained_over_audio_only(tmp_path, demo):
    older = tmp_path / "visitor_aaaaaaaaaaaaaaaa"
    older.mkdir()
    (older / "trained.etsworld").write_bytes(b"w1")
    time.sleep(0.02)
    audio_only = tmp_path / "anon_bbbbbbbbbbbbbbbb"
    audio_only.mkdir()
    (audio_only / "x.wav").write_bytes(b"x")
    time.sleep(0.02)
    newer = tmp_path / "visitor_cccccccccccccccc"
    newer.mkdir()
    (newer / "trained.etsworld").write_bytes(b"w2")
    hub = _hub(tmp_path, demo)
    s = hub.session_for_token(hub.authenticate("k"))
    assert s.session_dir == newer, "newest TRAINED dir wins over audio-only"


def test_no_orphan_fresh_owner_dir(tmp_path, demo):
    hub = _hub(tmp_path, demo)
    s = hub.session_for_token(hub.authenticate("k"))
    assert s.session_dir.name.startswith("owner_")
    assert s._is_trained is False


# ---------------- recover inventory + rebind --------------------------------

def test_recover_candidates_and_rebind(tmp_path, demo):
    lost = tmp_path / "visitor_1111111111111111"
    lost.mkdir()
    (lost / "a.wav").write_bytes(b"a")
    (lost / "trained.etsworld").write_bytes(b"w")
    hub = _hub(tmp_path, demo)
    s = hub.session_for_token(hub.authenticate("k"))   # adopts `lost` (only orphan)
    # make a second dir and verify the inventory sees both
    other = tmp_path / "visitor_2222222222222222"
    other.mkdir()
    (other / "b.wav").write_bytes(b"b")
    cands = hub.recover_candidates()
    dirs = {c["dir"] for c in cands}
    assert str(lost) in dirs and str(other) in dirs
    got = {c["dir"]: c for c in cands}
    assert got[str(lost)]["trained"] is True
    assert got[str(other)]["trained"] is False
    assert got[str(other)]["tracks"] == ["b.wav"]
    # rebind: pointers only, nothing moved/deleted
    out = hub.rebind_session_dir(s, str(other))
    assert out["ok"] is True
    assert s.session_dir == other
    assert s._is_trained is False
    assert (lost / "trained.etsworld").exists(), "rebind must not delete anything"
    # refuse a dir outside the volume base
    bad = hub.rebind_session_dir(s, "/etc")
    assert bad["ok"] is False


# ---------------- async train reconcile -------------------------------------

def test_async_train_attaches_not_double_trains(tmp_path, demo, monkeypatch):
    hub = _hub(tmp_path, demo)
    s = hub.session_for_token(hub.authenticate("k"))
    gate = threading.Event()
    calls = []

    def slow_train(**kw):
        calls.append(kw)
        gate.wait(5)
        return {"ok": True, "built": True}

    monkeypatch.setattr(s, "run_train", slow_train)
    r1 = s.start_train_async()
    assert r1["training"] is True and r1.get("started") is True
    r2 = s.start_train_async()                      # the re-click
    assert r2.get("already_running") is True, "re-click must ATTACH, not restart"
    assert s.training is True
    gate.set()
    s.train_thread.join(5)
    assert len(calls) == 1, "exactly ONE train ran"
    assert s.train_result == {"ok": True, "built": True}
    assert s.train_error is None
    assert s.training is False


def test_async_train_error_is_surfaced(tmp_path, demo, monkeypatch):
    hub = _hub(tmp_path, demo)
    s = hub.session_for_token(hub.authenticate("k"))
    monkeypatch.setattr(s, "run_train",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    s.start_train_async()
    s.train_thread.join(5)
    assert s.train_result is None
    assert "boom" in s.train_error["error"]


# ---------------- legacy token migration -------------------------------------

def test_legacy_token_migrates_to_owner_on_single_key_deploy(tmp_path, demo):
    """A token minted BEFORE the per-key fix (record without an owner tag) must
    snap to the key's owner identity on a single-key deploy — the already-open
    browser recovers without a re-login."""
    hub = _hub(tmp_path, demo)
    # the orphaned trained corpus on the volume
    orphan = tmp_path / "visitor_feedfacefeedface"
    orphan.mkdir()
    (orphan / "t.wav").write_bytes(b"t")
    (orphan / "trained.etsworld").write_bytes(b"w")
    # a LEGACY keyed record: dir + no "owner" tag (the old schema), stale dir
    legacy_dir = tmp_path / "visitor_0123456789abcdef"
    legacy_dir.mkdir()
    token = "legacy-token"
    h = app._hash_token(token)
    hub.store.keyed[h] = {"dir": str(legacy_dir), "kind": "keyed",
                          "is_trained": False, "trained_world_path":
                          str(legacy_dir / "trained.etsworld"),
                          "play_world": None, "last_receipt": None,
                          "opened_set_id": None, "set_id": "set-old",
                          "set_name": None, "owner_label": "you",
                          "shared": False}
    hub.store.save_keyed()
    sess = hub.session_for_token(token)
    assert sess is not None
    assert sess.session_dir == orphan, "legacy token must land on the ADOPTED owner session"
    assert sess._is_trained is True
    # and a fresh login with the key shares the SAME session
    sess2 = hub.session_for_token(hub.authenticate("k"))
    assert sess2 is sess


# ---------------- auditor findings B1/B2/B3 (pinned) --------------------------

def test_multikey_no_adoption_no_aliasing(tmp_path, demo):
    """B1: on a MULTI-key deploy an orphan's owner is unknowable — no adoption;
    both keys get fresh, DISTINCT owner dirs and the orphan stays untouched."""
    orphan = tmp_path / "visitor_deadbeefdeadbeef"
    orphan.mkdir()
    (orphan / "trained.etsworld").write_bytes(b"w")
    hub = _hub(tmp_path, demo, keys=("keyA", "keyB"))
    a = hub.session_for_token(hub.authenticate("keyA"))
    b = hub.session_for_token(hub.authenticate("keyB"))
    assert a.session_dir != orphan and b.session_dir != orphan
    assert a.session_dir != b.session_dir
    assert a._is_trained is False and b._is_trained is False


def test_adoption_skips_dirs_claimed_by_an_owner(tmp_path, demo):
    """B1 (defense in depth): a dir already claimed by an owner record is never
    adoptable, even when it still carries an old visitor_* name."""
    claimed = tmp_path / "visitor_aaaaaaaaaaaaaaaa"
    claimed.mkdir()
    (claimed / "trained.etsworld").write_bytes(b"w")
    hub = _hub(tmp_path, demo, keys=("k",))
    hub.store.owners[app._hash_token("someone-else")] = {
        "dir": str(claimed), "kind": "keyed"}
    s = hub.session_for_token(hub.authenticate("k"))
    assert s.session_dir != claimed, "claimed dir must never be adopted"


def test_rebind_refuses_store_dir(tmp_path, demo):
    """B3: rebinding onto _store must refuse — else a later reset() would unlink
    the durable store itself."""
    hub = _hub(tmp_path, demo)
    s = hub.session_for_token(hub.authenticate("k"))
    out = hub.rebind_session_dir(s, str(tmp_path / "_store"))
    assert out["ok"] is False
    assert (tmp_path / "_store" / "owners.json").exists(), "store untouched"


def test_rebind_refuses_other_owners_dir(tmp_path, demo):
    """B2 (hub layer): a dir claimed by a DIFFERENT owner is not rebindable."""
    hub = _hub(tmp_path, demo, keys=("keyA", "keyB"))
    a = hub.session_for_token(hub.authenticate("keyA"))
    b = hub.session_for_token(hub.authenticate("keyB"))
    out = hub.rebind_session_dir(b, str(a.session_dir))
    assert out["ok"] is False
    assert "another owner" in out["error"]


def test_recover_route_refuses_multikey(tmp_path, demo, monkeypatch):
    """B2 (route layer): /api/recover 403s on a multi-key deploy."""
    import http.client
    monkeypatch.setenv("ETS_ACCESS_KEYS", "keyA,keyB")
    monkeypatch.setenv("ETS_PUBLIC", "1")
    httpd = app.serve(host="127.0.0.1", port=0, public=True,
                      session_dir=str(tmp_path))
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("POST", "/api/recover", json.dumps({"key": "keyA"}),
                  {"Content-Type": "application/json"})
        r = c.getresponse()
        body = json.loads(r.read().decode())
        assert r.status == 403
        assert body["ok"] is False
    finally:
        httpd.shutdown()
        httpd.server_close()
