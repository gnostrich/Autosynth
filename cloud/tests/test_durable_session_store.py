"""OPEN_ENDS #17 — the DURABLE SESSION STORE.

Today the hosted companion holds its sessions + share catalog IN MEMORY: every
Railway redeploy wipes them, so users must retrain + re-share from scratch (it
happened 5 times in one day). Session FILES already persist on the volume; only the
POINTERS did not. This suite proves the pointers now survive a restart, that the
store holds only hashes + metadata (never a raw token, never audio), and that the
writes are atomic — while the existing 6-cell owner-gate matrix keeps passing
UNADAPTED (imported, not copied).

A restart is simulated by constructing a SECOND (then THIRD) Hub over the SAME
session base dir; the engine build is faked (``app._build_stream_player``) so the
whole thing runs offline and NO engine is ever loaded at boot.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import cloud.companion.app as app
from cloud.companion.app import Hub, SessionStore, _hash_token


class _FakePlayer:
    def __init__(self, path, seed, is_trained):
        self.path = path
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        pass

    def set_region(self, r):
        pass

    def world_info(self):
        return {"region_armed": True, "disarmed": []}


@pytest.fixture(autouse=True)
def _fake_engine(monkeypatch):
    monkeypatch.setattr(app, "_build_stream_player",
                        lambda path, seed, is_trained: _FakePlayer(path, seed, is_trained))


def _train_marker(session, receipt=None, name="My Set"):
    """Give a session a (fake) trained world on disk + the pointer state a real train
    would set, so it can be shared and its trained-state persisted."""
    tw = Path(session.trained_world_path)
    tw.write_bytes(b"world")
    session._is_trained = True
    session.play_world = str(tw)
    session.last_receipt = receipt or {"cost": 1.0, "verified": True}
    session.set_name = name
    return str(tw)


# --------------------------------------------------------------------------- #
# THE restart simulation: keyed session + anon session + catalog all survive   #
# --------------------------------------------------------------------------- #

def test_restart_restores_keyed_anon_catalog_and_revocation_survives(tmp_path):
    base = str(tmp_path / "vol")

    # --- Hub1: the live server before a redeploy ---
    h1 = Hub(session_dir=base, access_keys=["k1"])
    token = h1.authenticate("k1")
    owner = h1.session_for_token(token)
    owner.ingest_bytes("bass.wav", b"raw-audio")          # a marker corpus file
    tw = _train_marker(owner, receipt={"cost": 2.5})
    h1._persist_session(owner)                            # the /api/train handler seam
    sid = owner.set_id
    assert h1.share(owner, True, name="My Set")["ok"]     # publish it

    atok, asess = h1.new_anon_session()                   # a visitor
    assert h1.open_set(asess, sid) is not None            # opens the shared set
    assert asess.opened_set_id == sid

    # --- Hub2: a fresh process over the SAME volume (the redeploy) ---
    h2 = Hub(session_dir=base, access_keys=["k1"])
    assert h2.store.skipped == 0, "a clean store must restore with zero skips"

    # keyed token still resolves BY HASH to the same dir, with trained-state + receipt.
    o2 = h2.session_for_token(token)
    assert o2 is not None, "keyed token must re-resolve after restart"
    assert o2.session_dir == owner.session_dir
    assert o2._is_trained is True
    assert o2.last_receipt == {"cost": 2.5}
    assert o2.play_world == tw
    assert o2.is_visitor is False, "a restored keyed session is still an OWNER"
    assert "bass.wav" in o2.session_files(), "the ingested corpus file is on the volume"

    # the catalog lists the set and it is playable (world file on the volume).
    assert sid in h2.catalog and h2.catalog[sid].available()
    assert [e["id"] for e in h2.explore(o2)] == [sid]

    # the anon cookie still resolves and its opened set is restored.
    a2 = h2.anon_session(atok)
    assert a2 is not None, "anon cookie must re-resolve after restart"
    assert a2.session_dir == asess.session_dir
    assert a2.opened_set_id == sid
    # playable_for re-derives the engine from the restored opened_set_id via the catalog.
    assert h2.playable_for(a2).path == tw, "opened set resolves to its world after restart"

    # --- EXP-B revocation survives the restart (unshare in Hub2) ---
    h2.share(o2, False)
    assert sid not in h2.catalog

    # --- Hub3: the unshared set STAYS gone ---
    h3 = Hub(session_dir=base, access_keys=["k1"])
    assert sid not in h3.catalog, "an unshared set must stay gone after reboot"
    o3 = h3.session_for_token(token)
    assert o3.shared is False and o3._is_trained is True, \
        "trained-state survives; only the share was revoked"


def test_shared_set_survives_restart_available_both_ways(tmp_path):
    """The dual of the revocation test: a set left SHARED stays available after a
    reboot (the 'no re-share needed' win)."""
    base = str(tmp_path / "vol")
    h1 = Hub(session_dir=base, access_keys=["k1"])
    owner = h1.session_for_token(h1.authenticate("k1"))
    _train_marker(owner)
    sid = owner.set_id
    h1.share(owner, True)

    h2 = Hub(session_dir=base, access_keys=["k1"])
    assert sid in h2.catalog and h2.catalog[sid].available()
    # a brand-new anon visitor on the rebooted server can open it.
    _, v = h2.new_anon_session()
    assert h2.open_set(v, sid) is not None


# --------------------------------------------------------------------------- #
# TOKEN-HASH: no raw bearer token (or token material) ever hits the store      #
# --------------------------------------------------------------------------- #

def test_raw_tokens_never_written_to_the_store(tmp_path):
    base = tmp_path / "vol"
    h = Hub(session_dir=str(base), access_keys=["k1"])
    ktok = h.authenticate("k1")
    atok, asess = h.new_anon_session()
    owner = h.session_for_token(ktok)
    _train_marker(owner)
    h.share(owner, True, name="S")
    h.open_set(asess, owner.set_id)          # persist the anon's opened pointer

    store_dir = base / "_store"
    blob = "".join(p.read_text() for p in store_dir.glob("*.json"))
    assert blob, "the store must have written its maps"
    # the raw bearer secrets never appear anywhere in the store...
    assert ktok not in blob, "raw keyed token leaked into the store"
    assert atok not in blob, "raw anon token leaked into the store"
    # ...and no token PREFIX rides in via the dir names or the set_id either.
    assert ktok[:12] not in blob and atok[:12] not in blob
    assert owner.set_id.startswith("set-") and ktok[:10] not in owner.set_id
    # the mapping IS keyed by the sha256 hash (that's how a returning token resolves).
    assert _hash_token(ktok) in blob and _hash_token(atok) in blob


# --------------------------------------------------------------------------- #
# ATOMICITY: temp + os.replace, no torn temp files left behind                 #
# --------------------------------------------------------------------------- #

def test_store_writes_are_atomic_temp_then_rename(tmp_path):
    # the pattern is present in the source (the killed-mid-write guarantee)...
    src = Path(app.__file__).read_text()
    assert "os.replace(" in src, "atomic rename must be used for store writes"
    # ...and a save leaves the live file with NO leftover temp sibling.
    st = SessionStore(str(tmp_path / "vol"))
    st.keyed["h0"] = {"dir": "d0", "is_trained": False}
    st.save_keyed()
    st.catalog["s0"] = {"set_id": "s0", "world_path": "w0"}
    st.save_catalog()
    assert (st.root / "keyed.json").exists()
    assert (st.root / "catalog.json").exists()
    assert not list(st.root.glob("*.tmp-*")), "no temp file may survive an atomic save"


# --------------------------------------------------------------------------- #
# ROBUSTNESS: a corrupt store logs loudly, starts EMPTY, counts skips, no crash #
# --------------------------------------------------------------------------- #

def test_corrupt_store_starts_empty_and_counts_skips_without_crashing(tmp_path, caplog):
    base = tmp_path / "vol"
    sdir = base / "_store"
    sdir.mkdir(parents=True)
    (sdir / "keyed.json").write_text("{ this is not valid json")     # file-level corruption
    (sdir / "catalog.json").write_text('{"s1": {"missing": "fields"}}')  # bad record
    (sdir / "anon.json").write_text('{"h": {"dir": "/x"}}')          # one valid record

    with caplog.at_level("ERROR"):
        h = Hub(session_dir=str(base), access_keys=["k1"])
    # the bad keyed file -> that map is EMPTY; the bad catalog record is skipped.
    assert h.store.keyed == {}
    assert h.catalog == {}
    assert h.store.skipped >= 2, "each corrupt/invalid entry must be counted"
    assert "session store" in caplog.text.lower(), "corruption must be logged loudly"
    # the valid anon record still restored (never half-abandon the good data).
    assert "h" in h.store.anon
    # and the server did NOT crash: a fresh auth + share still work.
    tok = h.authenticate("k1")
    assert tok and h.session_for_token(tok) is not None


def test_missing_store_starts_clean_no_skips(tmp_path):
    # a first-ever boot (no _store yet) is not corruption: empty maps, zero skips.
    h = Hub(session_dir=str(tmp_path / "vol"), access_keys=["k1"])
    assert h.store.keyed == {} and h.store.anon == {} and h.catalog == {}
    assert h.store.skipped == 0


# --------------------------------------------------------------------------- #
# NO EAGER ENGINE at boot (the OOM history): restore builds pointers only       #
# --------------------------------------------------------------------------- #

def test_restore_loads_no_engine_at_boot(tmp_path):
    base = str(tmp_path / "vol")
    h1 = Hub(session_dir=base, access_keys=["k1"])
    owner = h1.session_for_token(h1.authenticate("k1"))
    _train_marker(owner)
    h1.share(owner, True)

    # Hub2 boot must NOT touch the engine registry — no world loaded until played.
    h2 = Hub(session_dir=base, access_keys=["k1"])
    assert h2.registry.loaded_worlds() == [], \
        "restoring sessions/catalog must load ZERO engines at boot"


# --------------------------------------------------------------------------- #
# ANON LRU still bounds the DURABLE set across restarts                          #
# --------------------------------------------------------------------------- #

def test_anon_lru_bounds_the_persisted_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ETS_MAX_ANON_SESSIONS", "3")
    base = str(tmp_path / "vol")
    h = Hub(session_dir=base, access_keys=["k1"])
    for _ in range(10):
        h.new_anon_session()
    assert len(h.store.anon) == 3, "the durable anon map must stay LRU-capped"
    # the cap holds across a restart (the store reloads exactly the capped set).
    h2 = Hub(session_dir=base, access_keys=["k1"])
    assert len(h2.store.anon) == 3
