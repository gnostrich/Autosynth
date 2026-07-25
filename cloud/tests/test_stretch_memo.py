"""PREREG-render-throughput — the fitted-unit memo IS the original render.

`render.render` memoizes the loudness-independent half of `_apply_gauge` (pitch
shift + time-stretch + fix_length) per SourceUnitBank; the per-placement loudness
(gauge loudness x settled mass) is applied afterwards by the same expression as
before. The memo's MISS path is the original call verbatim, so a hit returns
exactly the array a miss would have built. This file is the CI teeth for that;
the end-to-end proof (real produce loop, >=4k-unit worlds, throughput) lives in
`cloud/tools/fast_realize_verify.py`.

Pinned here, out of process (the arch-v6 engine is kept out of the cloud
interpreter, like test_channel_bias / test_fast_realize):

  BYTE-IDENTITY   streamed PCM is byte-equal memo-on vs memo-off over many bars
                  under a lean, and a direct `render()` of a schedule that
                  REPEATS units at different masses and unequal slot lengths (so
                  the phase vocoder really runs) returns bit-identical audio AND
                  bit-identical provenance (the stretch ratio it records).
  KILL SWITCH     ETS_STRETCH_CACHE=0/false/off leaves the memo untouched
                  (no entries at all); the default fills and hits it.
  BOUNDED         under a tiny budget the resident bytes stay within it, entries
                  are evicted — and the audio is STILL byte-identical, because a
                  dropped entry is only recomputed (a memory bound, never a
                  semantic one).
  PER-BANK KEYS   two banks holding the SAME (track, unit) ids with DIFFERENT
                  audio render differently: the memo is per bank, so one world's
                  material can never be served for another's.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


_DUMP = r"""
import os, sys, json
sys.path.insert(0, r"%s")
sys.path.insert(0, r"%s/architecture-v6")
import importlib
import numpy as np
R = importlib.import_module("ets.render.render")
from ets.render.schedule import Schedule, Section, Gauge, PLACEMENT_DTYPE
from ets.render.sources import SourceUnit, SourceUnitBank
from ets.engine.worldfile import load_world
from ets.engine.engine import Engine, resolve_sigma, build_bank, bar_schedule
from ets.panel.lanes import default_lane_vector

WORLD = "demo.etsworld"

def _sched_and_banks(seed=3, n_units=6, in_len=96, out_len=64, reps=3):
    "A schedule that REPEATS each unit at DIFFERENT masses, with in_len != out_len."
    rng = np.random.default_rng(seed)
    bounds = np.arange(4, dtype=np.int64) * out_len          # 3 output slots
    banks = []
    for b in range(2):                                       # two DIFFERENT banks,
        bank = SourceUnitBank(sr=44100)                      # same (track, unit) ids
        for u in range(n_units):
            bank.add(SourceUnit(track_id=0, unit_id=u, band=0, src_start=0,
                                src_end=in_len,
                                audio=rng.standard_normal(in_len), sr=44100))
        banks.append(bank)
    rows = []
    for r in range(reps):
        for u in range(n_units):
            rows.append((u %% 3, 0, u, 0, 0.3 + 0.05 * (u + n_units * r)))
    placements = np.array(rows, dtype=PLACEMENT_DTYPE)
    sections = (Section(0, 0, 3, Gauge(loudness_scale=0.7)),)
    return Schedule(sr=44100, slot_boundaries=bounds, placements=placements,
                    sections=sections), banks

def _render(cache, budget_mb=None, seed=3):
    os.environ["ETS_STRETCH_CACHE"] = cache
    if budget_mb is None:
        os.environ.pop("ETS_STRETCH_CACHE_MB", None)
    else:
        os.environ["ETS_STRETCH_CACHE_MB"] = str(budget_mb)
    sched, banks = _sched_and_banks(seed=seed)
    audio, prov = R.render(sched, banks[0])
    return audio, prov, banks[0]

# ---- direct render: identity, provenance identity, kill switch, bound ------
a_off, p_off, bank_off = _render("0")
a_on, p_on, bank_on = _render("1")
direct_identical = a_on.tobytes() == a_off.tobytes()
prov_identical = (p_on.segments.tobytes() == p_off.segments.tobytes())
stats_off = R.stretch_memo_stats(bank_off)
stats_on = R.stretch_memo_stats(bank_on)

# tiny budget -> eviction, still byte-identical
a_tiny, p_tiny, bank_tiny = _render("1", budget_mb=0.001)
tiny_stats = R.stretch_memo_stats(bank_tiny)
tiny_identical = a_tiny.tobytes() == a_off.tobytes()

# per-bank keys: same ids, different audio -> different output (no leakage)
os.environ["ETS_STRETCH_CACHE"] = "1"
os.environ.pop("ETS_STRETCH_CACHE_MB", None)
sched, banks = _sched_and_banks()
r0, _ = R.render(sched, banks[0])
r1, _ = R.render(sched, banks[1])
per_bank_ok = r0.tobytes() != r1.tobytes()
# ...and each bank's own render is reproducible with its memo already warm
r0b, _ = R.render(sched, banks[0])
warm_repeat_identical = r0.tobytes() == r0b.tobytes()

# ---- streamed PCM through the engine, memo on vs off ----------------------
def _stream(cache, n_bars=8):
    os.environ["ETS_STRETCH_CACHE"] = cache
    wf = load_world(WORLD)
    e = Engine(wf, seed=0, sigma=resolve_sigma(wf, None))
    bank = build_bank(wf)
    w = wf.world
    u = default_lane_vector(w.M)
    u.u_region = np.array([0.35 * (-1.0) ** k for k in range(w.M)], dtype=np.float32)
    u.u_continuity, u.u_novelty, u.T_s = 0.4, 0.6, 1.25
    out = []
    for _ in range(n_bars):
        r = e.writer.write_bar(tilt=e._tilt_for(u))
        sched = bar_schedule(w, r.rows, e.writer.s_phase)
        audio, _prov = R.render(sched, bank)
        out.append(np.asarray(audio, float).tobytes())
    return b"".join(out), R.stretch_memo_stats(bank)

s_on, m_on = _stream("1")
s_off, m_off = _stream("0")

print(json.dumps({
    "direct_identical": bool(direct_identical),
    "prov_identical": bool(prov_identical),
    "n_placements": int(len(sched.placements)),
    "stats_off_is_none": stats_off is None,
    "stats_on": stats_on,
    "tiny_identical": bool(tiny_identical),
    "tiny_stats": tiny_stats,
    "per_bank_ok": bool(per_bank_ok),
    "warm_repeat_identical": bool(warm_repeat_identical),
    "stream_identical": s_on == s_off,
    "stream_bytes": len(s_on),
    "stream_stats_on": m_on,
    "stream_stats_off_is_none": m_off is None,
}))
""" % (_ROOT, _ROOT)


def _dump():
    p = subprocess.run([sys.executable, "-c", _DUMP], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=900)
    assert p.returncode == 0, p.stderr[-4000:]
    return json.loads(p.stdout.strip().splitlines()[-1])


_D = None


def _d():
    global _D
    if _D is None:
        _D = _dump()
    return _D


def test_direct_render_is_byte_identical_with_the_memo():
    d = _d()
    assert d["n_placements"] >= 18, d["n_placements"]     # repeats, so hits happen
    assert d["direct_identical"], "the memo changed the rendered audio"
    assert d["prov_identical"], "the memo changed the recorded provenance"
    assert d["stats_on"]["hits"] > 0, "the memo never hit — the test is vacuous"


def test_streamed_audio_is_byte_identical_with_the_memo():
    d = _d()
    assert d["stream_bytes"] > 100_000, d["stream_bytes"]
    assert d["stream_identical"], "streamed audio differs memo-on vs memo-off"
    assert d["stream_stats_on"]["hits"] > 0


def test_kill_switch_leaves_the_memo_untouched():
    d = _d()
    assert d["stats_off_is_none"], \
        "ETS_STRETCH_CACHE=0 still built a memo — the switch does not bypass it"
    assert d["stream_stats_off_is_none"]


def test_budget_is_a_memory_bound_not_a_semantic_one():
    d = _d()
    t = d["tiny_stats"]
    assert t["evictions"] > 0, "the tiny budget evicted nothing — no teeth"
    assert t["bytes"] <= max(t["budget_bytes"], 1) or t["entries"] == 1, t
    assert d["tiny_identical"], \
        "eviction changed the audio — the budget is not purely a memory bound"


def test_memo_is_per_bank():
    d = _d()
    assert d["per_bank_ok"], \
        "two banks with the same (track, unit) ids rendered identically — the " \
        "memo leaked one world's material into another's render"
    assert d["warm_repeat_identical"]
