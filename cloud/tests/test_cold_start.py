"""COLD-START (OPEN_ENDS #21d) — no more 6-9 minutes of silent dead Play.

Two halves, both backed by REAL state (never decoration):

  PRE-WARM   when a train COMPLETES (the repoint in Companion._run_train) and
             when a set is SHARED (Hub.share on=True), the ONE world involved
             gets its produce loop started immediately (player.start() spawns
             the daemon loop thread) so the bank build + first bars happen
             BEFORE the first listener connects. Guarded by the registry LRU:
             a world already evicted is never warmed (the memory cap wins).
             Disclosed tradeoff (operator-accepted): CPU may be spent on a
             world nobody listens to.

  WARMING FLAG  the bridge's ``_warmed`` turns True exactly when the produce
             loop renders its FIRST bar; /api/world carries it (world_info),
             and the FE shows "engine warming up — first sound can take a few
             minutes" while a world is open but not warmed — an honest state
             readout gated on the real flag, cleared by telemetry bar>0 or the
             flag itself, replaced by the honest failure report if the loop
             recorded a last_error.
"""
from __future__ import annotations

import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "companion"))

import cloud.companion.app as app
from cloud.companion.app import Companion, Hub, WorldRegistry, _prewarm_engine
from engine_bridge import StreamPlayer  # noqa: E402

_INDEX = (Path(__file__).resolve().parents[1] / "companion" / "static"
          / "index.html")

# Local copies of the shared JS-extraction helpers (test_web_field.py, whose
# FIELD PURE LOGIC these were named for, was retired with the field itself —
# OPEN_ENDS item 2; this module's own use of them is field-independent, so the
# helpers move in-tree rather than import from a deleted module). Identical to
# the copies in test_web_scalar_lanes.py / test_eigenpanel.py / test_web_fab_guard.py.

def _inline_js() -> str:
    html = _INDEX.read_text()
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert blocks, "no inline <script> found in index.html"
    return max(blocks, key=len)


def _js_functions(src: str):
    out = {}
    for m in re.finditer(r"function\s+([A-Za-z_$][\w$]*)\s*\(", src):
        name = m.group(1)
        i = src.index("{", m.end() - 1)
        depth, j = 0, i
        while j < len(src):
            ch = src[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out[name] = src[i + 1:j]
    return out


class _FakePlayer:
    def __init__(self, path, seed=0, is_trained=False):
        self.path = path
        self.started = False
    def start(self): self.started = True
    def stop(self): pass
    def set_region(self, r): pass
    def world_info(self): return {"region_armed": True, "disarmed": []}


# ---- the warmed flag: false -> true on the FIRST produced bar ----------------

def _bare_player(sr: int = 8000) -> StreamPlayer:
    p = object.__new__(StreamPlayer)
    p.sr = sr
    p._playing = threading.Event()
    p._thread = None
    p._sub_lock = threading.Lock()
    p._subscribers = set()
    p.telemetry = {"roles": [], "t": 0.0, "bar": 0}
    p.last_error = None
    p._warmed = False
    return p


def test_warmed_flag_transitions_on_first_produced_bar():
    p = _bare_player()
    p.produce_one_bar = lambda: (b"\x01\x02" * 400, None)
    assert p._warmed is False, "a fresh engine must report cold"
    q = p.subscribe()                        # starts the produce loop
    got = None
    deadline = time.monotonic() + 3.0
    while got is None and time.monotonic() < deadline:
        try:
            got = q.get(timeout=0.25)
        except Exception:
            continue
    p.stop()
    p.unsubscribe(q)
    assert got is not None
    assert p._warmed is True, "the first produced bar must flip warmed"


def test_warmed_stays_false_when_the_first_bar_fails():
    p = _bare_player()
    def boom():
        raise RuntimeError("no bank")
    p.produce_one_bar = boom
    p._playing.set()
    t = threading.Thread(target=p._loop, daemon=True)
    t.start(); t.join(timeout=3.0)
    assert not t.is_alive()
    assert p._warmed is False, "a failed warmup must never claim warm"
    assert p.last_error is not None


# ---- pre-warm: train-complete path ------------------------------------------

def test_prewarm_called_on_train_complete(tmp_path, monkeypatch):
    # the test_mvp2 runtime pattern: stub the seam builder + the bridge class,
    # run the REAL _run_train branch, assert the repointed player was started.
    import cloud.companion.train_local as tl
    import cloud.companion.engine_bridge as eb
    built = []
    monkeypatch.setattr(tl, "build_trained_world",
                        lambda *a, **k: {"receipt": {"n_anchors": 3},
                                         "sigma_phi_disarmed": []})
    def _mk(path, seed=0, is_trained=False):
        p = _FakePlayer(path, seed, is_trained); built.append(p); return p
    monkeypatch.setattr(eb, "StreamPlayer", _mk)

    comp = Companion(cloud_url="inproc", session_dir=str(tmp_path / "s"))
    comp.ingest_bytes("clip.wav", b"RIFF0000WAVE")
    out = comp.run_train()
    assert out["ok"] and out["playback"] == "live"
    assert len(built) == 1
    assert built[0].started is True, \
        "train-complete must pre-warm the freshly repointed engine"


def test_prewarm_called_on_train_complete_with_registry(tmp_path, monkeypatch):
    import cloud.companion.train_local as tl
    import cloud.companion.engine_bridge as eb
    built = []
    monkeypatch.setattr(tl, "build_trained_world",
                        lambda *a, **k: {"receipt": {}, "sigma_phi_disarmed": []})
    def _mk(path, seed=0, is_trained=False):
        p = _FakePlayer(path, seed, is_trained); built.append(p); return p
    monkeypatch.setattr(eb, "StreamPlayer", _mk)

    reg = WorldRegistry(max_loaded=2)
    comp = Companion(cloud_url="inproc", session_dir=str(tmp_path / "s"),
                     registry=reg)
    comp.ingest_bytes("clip.wav", b"RIFF0000WAVE")
    out = comp.run_train()
    assert out["ok"]
    assert built[0].started is True
    # the warmed engine was ADOPTED into the LRU (counts against the cap).
    assert str(comp.trained_world_path) in reg.loaded_worlds()


# ---- pre-warm: share path ----------------------------------------------------

def test_prewarm_called_on_share(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "_build_stream_player",
                        lambda path, seed, is_trained: _FakePlayer(path, seed, is_trained))
    demo = tmp_path / "demo.etsworld"; demo.write_bytes(b"demo")
    hub = Hub(session_dir=str(tmp_path), access_keys=["k"], play_world=str(demo))
    owner = hub.session_for_token(hub.authenticate("k"))
    tw = Path(owner.session_dir) / "trained.etsworld"; tw.write_bytes(b"world")
    owner._is_trained = True
    owner.play_world = str(tw)
    out = hub.share(owner, True)
    assert out["ok"] and out["shared"]
    shared = hub.registry.trained_player(owner.play_world, owner.seed)
    assert shared.started is True, "sharing a set must pre-warm its engine"


def test_unshare_does_not_prewarm(tmp_path, monkeypatch):
    built = []
    def _mk(path, seed, is_trained):
        p = _FakePlayer(path, seed, is_trained); built.append(p); return p
    monkeypatch.setattr(app, "_build_stream_player", _mk)
    demo = tmp_path / "demo.etsworld"; demo.write_bytes(b"demo")
    hub = Hub(session_dir=str(tmp_path), access_keys=["k"], play_world=str(demo))
    owner = hub.session_for_token(hub.authenticate("k"))
    tw = Path(owner.session_dir) / "trained.etsworld"; tw.write_bytes(b"world")
    owner._is_trained = True
    owner.play_world = str(tw)
    hub.share(owner, True)
    hub.share(owner, False)                 # delist: no new warm anywhere
    assert all(p.started for p in built if p.path == str(tw)) and len(built) == 1


# ---- the LRU guard: never warm past the memory cap ---------------------------

def test_prewarm_guard_skips_an_evicted_world(monkeypatch):
    monkeypatch.setattr(app, "_build_stream_player",
                        lambda path, seed, is_trained: _FakePlayer(path, seed, is_trained))
    reg = WorldRegistry(max_loaded=1)
    p_a = reg.trained_player("/w/a", 0)
    reg.trained_player("/w/b", 0)           # evicts /w/a
    assert "/w/a" not in reg.loaded_worlds()
    _prewarm_engine(reg, "/w/a", p_a)
    assert p_a.started is False, \
        "pre-warm must never start an engine the LRU already evicted (cap wins)"
    p_b = reg.trained_player("/w/b", 0)
    _prewarm_engine(reg, "/w/b", p_b)
    assert p_b.started is True


def test_prewarm_without_registry_warms_directly():
    p = _FakePlayer("/w/solo")
    _prewarm_engine(None, "/w/solo", p)     # standalone/local: one world, warm it
    assert p.started is True


def test_prewarm_tradeoff_is_disclosed_in_code():
    src = (Path(app.__file__)).read_text()
    m = re.search(r"def _prewarm_engine.*?def _build_stream_player", src, re.S)
    assert m, "_prewarm_engine missing"
    body = m.group(0)
    assert "TRADEOFF" in body and "CPU" in body, \
        "the spend-CPU-on-an-unlistened-world tradeoff must be disclosed in code"
    assert "ETS_MAX_LOADED_WORLDS" in body, "the LRU guard must be documented"


# ---- FE: the warming copy is gated on the REAL flag --------------------------

def test_fe_warming_note_exists_and_ships_hidden():
    html = _INDEX.read_text()
    assert re.search(r'<div class="warm-note" id="warmNote" hidden', html), \
        "the warming note must exist and ship hidden"


def test_fe_warming_copy_gated_on_the_real_flag():
    funcs = _js_functions(_inline_js())
    body = funcs["updateWarming"]
    assert "engine warming up — first sound can take a few minutes" in body, \
        "the exact warming copy must live in updateWarming"
    assert "world.warmed" in body and "world.ready" in body, \
        "the warming copy must be gated on the REAL warmed flag (and a ready world)"
    # a recorded loop failure replaces the warming promise with the honest report.
    assert "world.lastError" in body and "engine failed: " in body, \
        "a recorded last_error must be reported instead of eternal 'warming'"


def test_fe_flag_flows_from_api_world_and_clears_on_telemetry():
    js = _inline_js()
    funcs = _js_functions(js)
    # /api/world -> world.warmed (explicit false = cold; absent = no cold claim).
    assert re.search(r"world\.warmed\s*=\s*\(\s*w\.warmed\s*!==\s*false\s*\)", js), \
        "world.warmed must be read from the /api/world payload"
    assert "w.last_error" in js, "world.lastError must be read from /api/world"
    # telemetry bar>0 clears the note (the engine HAS rendered).
    tele = funcs["applyTelemetry"]
    assert "d.bar" in tele and "world.warmed = true" in tele \
        and "updateWarming" in tele, \
        "the first telemetry bar>0 must clear the warming state"
    # the poll keeps refreshing the flag while cold — via the SLIM re-read that
    # never re-runs enableInstrument on a live instrument.
    poll = funcs["pollTick"]
    assert "refreshEngineState" in poll and "world.warmed" in poll
    refresh = funcs["refreshEngineState"]
    assert "enableInstrument" not in refresh, \
        "the slim warmed poll must never re-init the live instrument"
    assert "updateWarming" in refresh


def test_fe_warming_note_is_not_a_data_claim_caption():
    # WEB-FAB: the copy asserts an engine STATE ("warming"), not a data source —
    # it must not carry any data-claim token that would need allowlisting, and it
    # must not be styled as a caption span (it is a status line, role="status").
    from cloud.tests.test_web_fab_guard import _DATA_CLAIM_TOKENS
    copy = "engine warming up — first sound can take a few minutes"
    assert not any(tok in copy for tok in _DATA_CLAIM_TOKENS)
    html = _INDEX.read_text()
    assert 'role="status"' in html.split('id="warmNote"')[0].rsplit("<div", 1)[-1] \
        or re.search(r'id="warmNote"[^>]*role="status"', html)
