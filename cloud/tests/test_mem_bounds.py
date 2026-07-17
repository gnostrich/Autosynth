"""MEM — the OOM fix bites (the live service measured 7.997GB vs an 8GB cap from
per-visitor engines). Three bounds, each proven:

  1. the demo-world engine is a SHARED SINGLETON across sessions (not rebuilt per
     visitor — the primary memory win);
  2. trained/shared engines live in an LRU that EVICTS past ``ETS_MAX_LOADED_WORLDS``
     (evicted = engine released; world file untouched, reloads on demand);
  3. at most ONE in-proc training at a time — a second concurrent train is refused
     honestly (TrainBusy -> 429), never silently queued.

The heavy StreamPlayer is injected via ``app._build_stream_player`` so these run
offline with no engine load — the sharing/eviction POLICY is what's under test.
"""
import pytest

import cloud.companion.app as app
from cloud.companion.app import (Companion, Hub, TrainBusy, WorldRegistry)


class _FakePlayer:
    """A stand-in for the real engine bridge: records builds/stops, exposes the
    read-only surfaces the hub touches. No engine, no audio."""
    def __init__(self, path, seed, is_trained):
        self.path = path; self.seed = seed; self.is_trained = is_trained
        self.stopped = False
        self.regions = []
    def stop(self): self.stopped = True
    def set_region(self, r): self.regions.append(r)
    def world_info(self): return {"region_armed": True, "disarmed": []}


@pytest.fixture
def fake_build(monkeypatch):
    built = []
    def _build(path, seed, is_trained):
        p = _FakePlayer(path, seed, is_trained); built.append(p); return p
    monkeypatch.setattr(app, "_build_stream_player", _build)
    return built


# ---------------- 1. shared demo singleton ----------------------------------

def test_demo_engine_is_a_shared_singleton(fake_build):
    reg = WorldRegistry(max_loaded=2)
    d1 = reg.demo_player("demo.etsworld", 0)
    d2 = reg.demo_player("demo.etsworld", 0)
    d3 = reg.demo_player("demo.etsworld", 0)
    assert d1 is d2 is d3, "demo engine must be built once and shared"
    assert len(fake_build) == 1, "the demo bank must not be rebuilt per request"


def test_demo_shared_across_hub_sessions(fake_build, tmp_path):
    demo = tmp_path / "demo.etsworld"; demo.write_bytes(b"demo")   # must exist to resolve
    hub = Hub(session_dir=str(tmp_path), access_keys=["k"], play_world=str(demo))
    a = hub.session_for_token(hub.authenticate("k"))
    b = hub.session_for_token(hub.authenticate("k"))
    assert a is not b, "distinct visitors get distinct sessions"
    pa = hub.playable_for(a)
    pb = hub.playable_for(b)
    assert pa is pb, "both sessions must share the ONE demo engine"
    assert len(fake_build) == 1


# ---------------- 2. LRU eviction past the cap ------------------------------

def test_lru_evicts_past_the_cap(fake_build):
    reg = WorldRegistry(max_loaded=2)
    p1 = reg.trained_player("/w/one.etsworld", 0)
    p2 = reg.trained_player("/w/two.etsworld", 0)
    assert set(reg.loaded_worlds()) == {"/w/one.etsworld", "/w/two.etsworld"}
    # third load evicts the least-recently-used (one)
    p3 = reg.trained_player("/w/three.etsworld", 0)
    loaded = reg.loaded_worlds()
    assert "/w/one.etsworld" not in loaded, "LRU must evict the oldest past the cap"
    assert set(loaded) == {"/w/two.etsworld", "/w/three.etsworld"}
    assert len(loaded) <= reg.max_loaded
    assert p1.stopped is True, "evicted engine must be released (stop called)"
    assert p2.stopped is False and p3.stopped is False


def test_lru_recency_protects_recently_used(fake_build):
    reg = WorldRegistry(max_loaded=2)
    reg.trained_player("/w/a", 0)
    reg.trained_player("/w/b", 0)
    reg.trained_player("/w/a", 0)          # touch a -> b is now the LRU
    reg.trained_player("/w/c", 0)          # evicts b, keeps a
    loaded = set(reg.loaded_worlds())
    assert loaded == {"/w/a", "/w/c"}


def test_evicted_world_reloads_on_demand(fake_build):
    reg = WorldRegistry(max_loaded=1)
    reg.trained_player("/w/a", 0)
    reg.trained_player("/w/b", 0)          # evicts a
    assert "/w/a" not in reg.loaded_worlds()
    # a later request for a rebuilds it (file stayed on disk in real life)
    reg.trained_player("/w/a", 0)
    assert "/w/a" in reg.loaded_worlds()
    # two distinct builds of /w/a happened (evict then reload) — expected
    a_builds = [p for p in fake_build if p.path == "/w/a"]
    assert len(a_builds) == 2


# ---------------- 3. single in-proc train -----------------------------------

def test_second_concurrent_train_is_refused_honestly(fake_build, tmp_path):
    reg = WorldRegistry(max_loaded=2)
    assert reg.begin_train() is True
    assert reg.begin_train() is False, "a second concurrent train must be refused"
    reg.end_train()
    assert reg.begin_train() is True      # freed after the first finishes

    # and at the Companion level a busy registry makes run_train raise TrainBusy
    reg2 = WorldRegistry(max_loaded=2)
    reg2.begin_train()                    # someone else is training
    comp = Companion(cloud_url="inproc", session_dir=str(tmp_path / "s"),
                     registry=reg2)
    with pytest.raises(TrainBusy):
        comp.run_train()
