"""PREREG-render-throughput — the vectorized fiber choice IS the original one.

`realize.FiberThreader._choose` dispatches, at call time, to one of two
implementations of the SAME Layer-0 fiber measure: `_choose_original` (the
reference, candidate-by-candidate) or `_choose_fast` (the same expressions on
precomputed arrays). This file is the CI teeth for that equivalence; the
end-to-end proof (real produce loop, >=4k-unit world, throughput) lives in
`cloud/tools/fast_realize_verify.py`.

Pinned here, out of process (the arch-v6 engine is kept out of the cloud
interpreter, like test_channel_bias / test_freeze_only_byte_identity):

  IDENTITY     streamed rows, continuation flags and settled O are bit-identical
               fast-vs-original over many bars, under a tilt WITH all three
               field-bias grains (so the reuse and channel-bias vectors are
               non-trivial) — and in the BATCH reduction too (tilt=None,
               rng=None, `realize()`), which the stream never exercises.
  KILL SWITCH  ETS_FAST_REALIZE=0/false/off routes every choice through
               `_choose_original` (and the default routes it through the fast
               one) — checked by counting calls, not by trusting the flag.
  BOUNDED      the fast path's memos are functions of the frozen index and the
               grid: after warmup they stop growing while bars keep being
               written (I-8 — no state that grows with elapsed time).
  ELEMENTWISE  the memos assume numpy's cos is a pure elementwise function of
               its input (same value whatever the array's size/offset). That
               assumption is what makes a memoized charge bit-identical to one
               computed inside a longer choice-set array, so it is asserted.
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
import numpy as np
from ets.engine.worldfile import load_world
from ets.engine.engine import Engine, resolve_sigma
from ets.panel.lanes import default_lane_vector
from ets.writer.realize import FiberThreader, realize as realize_batch
from ets.writer.settle import settle_tape
from ets.writer.tape import OutputGrid, TapeNode
from cloud.companion.channel_bias import (channel_logbias, grain_logbias,
                                          field_logbias, track_role_logbias,
                                          channel_tids)

WORLD = "demo.etsworld"

def _engine(seed=0):
    wf = load_world(WORLD)
    return wf.world, Engine(wf, seed=seed, sigma=resolve_sigma(wf, None))

def _field(w):
    "A tilt carrying ALL THREE field grains, so every fast-path array is live."
    tids = channel_tids(w)
    tw = channel_logbias([1.0] + [-0.5] * (len(tids) - 1), tids)
    uw = grain_logbias({u: (0.6 if u %% 2 else -0.3) for u in range(0, 40)})
    cw = track_role_logbias({(int(tids[0]), k): 0.5 for k in range(w.M)})
    return field_logbias(track=tw, unit=uw, track_role=cw)

def _stream(fast, n_bars=10):
    os.environ["ETS_FAST_REALIZE"] = "1" if fast else "0"
    w, e = _engine()
    u = default_lane_vector(w.M)
    u.u_region = np.array([0.35 * (-1.0) ** k for k in range(w.M)], dtype=np.float32)
    u.u_continuity, u.u_novelty, u.T_s = 0.4, 0.6, 1.25
    fld = _field(w)
    rows, conts, osum = [], [], []
    for _ in range(n_bars):
        r = e.writer.write_bar(tilt=e._tilt_for(u, channel_logbias=fld))
        rows.append([list(map(float, x)) for x in r.rows])
        conts.append([bool(c) for c in r.continues])
        osum.append(float(np.asarray(r.O, float).sum()))
    return rows, conts, osum

def _batch(fast, n_slots=64):
    "The batch T->0 reduction: tilt=None, rng=None, through realize()."
    os.environ["ETS_FAST_REALIZE"] = "1" if fast else "0"
    wf = load_world(WORLD)
    w = wf.world
    s_phase = int(getattr(w, "s_phase", 8))
    grid = OutputGrid(sr=int(w.sr), tatum_len=int(w.out_tatum_len),
                      n_slots=n_slots, s_phase=s_phase)
    tape = TapeNode(grid=grid, M=int(w.M))
    res = settle_tape(w.fstate, tape)
    sched, meta = realize_batch(res.O, tape, w.fstate, w.index)
    p = sched.placements
    return [[int(x["out_slot"]), int(x["src_track"]), int(x["src_unit"]),
             int(x["section"]), float(x["mass"])] for x in p]

rows_f, cont_f, o_f = _stream(True)
rows_o, cont_o, o_o = _stream(False)
batch_f, batch_o = _batch(True), _batch(False)

# ---- kill switch: count which implementation actually ran -----------------
counts = {"fast": 0, "orig": 0}
_f, _o = FiberThreader._choose_fast, FiberThreader._choose_original
def _cf(self, k, b, psi, bar):
    counts["fast"] += 1; return _f(self, k, b, psi, bar)
def _co(self, k, b, psi, bar):
    counts["orig"] += 1; return _o(self, k, b, psi, bar)
FiberThreader._choose_fast, FiberThreader._choose_original = _cf, _co
switch = {}
for tag, val in (("default", None), ("0", "0"), ("false", "false"),
                 ("off", "off"), ("1", "1")):
    counts["fast"] = counts["orig"] = 0
    os.environ.pop("ETS_FAST_REALIZE", None)
    if val is not None:
        os.environ["ETS_FAST_REALIZE"] = val
    w, e = _engine()
    u = default_lane_vector(w.M)
    e.writer.write_bar(tilt=e._tilt_for(u))
    switch[tag] = dict(counts)
FiberThreader._choose_fast, FiberThreader._choose_original = _f, _o

# ---- I-8: the memos are bounded by material x grid, not by elapsed time ---
os.environ["ETS_FAST_REALIZE"] = "1"
w, e = _engine()
u = default_lane_vector(w.M)
th = e.writer.threader
for _ in range(6):
    e.writer.write_bar(tilt=e._tilt_for(u, channel_logbias=_field(w)))
warm = (len(th._pools), len(th._energy), len(th._unit_row))
for _ in range(24):
    e.writer.write_bar(tilt=e._tilt_for(u, channel_logbias=_field(w)))
late = (len(th._pools), len(th._energy), len(th._unit_row))
n_pools = len(th.index.candidates)
bounds = {"warm": warm, "late": late, "n_pools": n_pools,
          "s_phase": int(e.writer.s_phase),
          "n_units": int(sum(len(t.units) for t in w.tracks))}

# ---- the elementwise assumption the charge memo rests on ------------------
rng = np.random.default_rng(0)
elementwise = True
for n in (1, 3, 7, 8, 15, 16, 97, 96, 257, 4096):
    x = rng.uniform(-4.0, 4.0, size=n)
    full = 1.0 - np.cos(2.0 * np.pi * x)
    head = 1.0 - np.cos(2.0 * np.pi * np.asarray(x[0], float))   # scalar path
    tail = 1.0 - np.cos(2.0 * np.pi * x[1:])                     # shorter + offset
    if head.tobytes() != np.float64(full[0]).tobytes():
        elementwise = False
    if n > 1 and tail.tobytes() != full[1:].tobytes():
        elementwise = False

print(json.dumps({
    "rows_identical": rows_f == rows_o,
    "cont_identical": cont_f == cont_o,
    "O_identical": o_f == o_o,
    "n_rows": sum(len(b) for b in rows_f),
    "batch_identical": batch_f == batch_o,
    "n_batch_rows": len(batch_f),
    "switch": switch,
    "bounds": bounds,
    "elementwise": elementwise,
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


def test_streamed_rows_are_bit_identical():
    d = _d()
    assert d["n_rows"] > 200, d["n_rows"]           # the comparison has teeth
    assert d["rows_identical"], "vectorized fiber choice changed the placements"
    assert d["cont_identical"], "continuation (phi_cont) events differ"
    assert d["O_identical"], "settled O differs (the rng stream was disturbed)"


def test_batch_reduction_is_bit_identical():
    d = _d()
    assert d["n_batch_rows"] > 100, d["n_batch_rows"]
    assert d["batch_identical"], \
        "the deterministic T->0 batch realization differs fast-vs-original"


def test_kill_switch_selects_the_implementation_at_call_time():
    s = _d()["switch"]
    for off in ("0", "false", "off"):
        assert s[off]["orig"] > 0 and s[off]["fast"] == 0, (off, s[off])
    for on in ("default", "1"):
        assert s[on]["fast"] > 0 and s[on]["orig"] == 0, (on, s[on])


def test_fast_memos_are_bounded():
    b = _d()["bounds"]
    assert b["warm"] == b["late"], \
        f"fast-path memos grew with elapsed time: {b['warm']} -> {b['late']}"
    n_pools, s_phase, n_units = b["n_pools"], b["s_phase"], b["n_units"]
    assert b["late"][0] <= n_pools                       # one entry per pool
    assert b["late"][1] <= n_pools * s_phase             # pools x slot phases
    assert b["late"][2] <= n_units                       # one row per real unit


def test_cos_is_elementwise_here():
    # If this ever fails, the memoized phase charge is NOT bit-identical to the
    # charge computed inside a longer choice-set array and the fast path must be
    # switched off (ETS_FAST_REALIZE=0) until it is re-derived.
    assert _d()["elementwise"], \
        "numpy cos is not a pure elementwise function on this build"
