"""Standalone proof that the VECTORIZED fiber choice is the ORIGINAL one.

`ets.writer.realize.FiberThreader._choose` has two implementations of the same
Layer-0 measure (PREREG-render-throughput.md, ratified 2026-07-24): the
reference `_choose_original` (candidate-by-candidate Python) and `_choose_fast`
(the same expressions on precomputed arrays). `ETS_FAST_REALIZE=0` selects the
reference at call time. This tool runs the REAL produce path both ways on fixed
seeds and asserts the optimization is INVISIBLE:

  [G1] placement-row identity — every produced row (slot, track, unit, section,
       mass) and every φ_cont flag is EXACTLY equal fast-vs-original, on the
       committed demo world AND on a synthesized multi-track world of >=4k real
       units built through the actual train path (ingest -> stage-3 -> anchor
       fit -> build_index). Rows are compared bar by bar under a deterministic
       lane + FIELD-BIAS program, so the tilted, biased and untilted measures
       are all exercised (a u=0 run alone would never touch the reuse or
       channel-bias arrays).
  [G2] PCM byte identity — (a) the direct `produce_one_bar` sequence and (b) the
       REAL produce loop through `subscribe()` (the pacing/threading path the
       browser gets) both emit byte-equal audio.
  [G3] throughput — steady-state `produce_one_bar` bars/s both ways on both
       worlds; the ratified gate is >=2.0x on the >=4k-unit world (the demo
       world's smaller speedup is reported honestly, not gated).

Run (from the repo root):
    python3 cloud/tools/fast_realize_verify.py                 # all gates
    python3 cloud/tools/fast_realize_verify.py --build-world   # (re)build only
    python3 cloud/tools/fast_realize_verify.py --skip-big      # demo world only

The big world is synthesized (rhythmic non-stationary WAVs, the CAPACITY_STUDY
recipe) and CACHED under --work; building it takes tens of minutes in this
sandbox, replaying from the cache takes seconds. Read-only w.r.t. the engine.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)                          # for cloud.*
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))   # arch-v6 engine WINS

import numpy as np                                                       # noqa: E402


def log(m):
    print(m, flush=True)


# ---------------------------------------------------------------------------
# the >=4k-unit world: synthesized rhythmic audio -> the REAL train path
# ---------------------------------------------------------------------------

def _synth_wav(path, sr=44100, seconds=30.0, bpm=120.0, seed=0):
    """A rhythmic, NON-STATIONARY clip (the CAPACITY_STUDY / seam_verify recipe):
    percussion on the beat + a melodic sequence stepping through a per-track
    scale, so bars carry different role content and the units are real audio."""
    import soundfile as sf
    rng = np.random.default_rng(seed)
    n = int(sr * seconds)
    y = np.zeros(n)
    step = int(sr * 60.0 / bpm)
    base = 110.0 * (2.0 ** (seed / 3.0))
    scale = base * np.array([1.0, 9 / 8, 5 / 4, 4 / 3, 3 / 2, 5 / 3, 15 / 8, 2.0])
    n_harm = 2 + seed
    click_env = np.exp(-np.linspace(0, 40, step))
    beat = 0
    for start in range(0, n - step, step):
        f = scale[(beat * (seed + 1)) % len(scale)]
        seg = np.zeros(step)
        tt = np.arange(step) / sr
        tone_env = np.exp(-np.linspace(0, 6, step))
        for h in range(1, n_harm + 1):
            seg += (0.16 / h) * np.sin(2 * np.pi * f * h * tt) * tone_env
        seg += click_env * rng.standard_normal(step) * 0.30
        y[start:start + step] += seg
        beat += 1
    y += 0.01 * rng.standard_normal(n)
    y = 0.9 * y / (np.max(np.abs(y)) + 1e-9)
    sf.write(path, y.astype(np.float32), sr)
    return path


def big_world(work: str, n_tracks: int = 6, seconds: float = 30.0,
              bpm: float = 120.0, spread: float = 0.0,
              rebuild: bool = False) -> str:
    """Synthesize + train (cached) a multi-track world of >=4k real units.

    `spread` is the per-track bpm step. spread=0 gives a SINGLE-TEMPO corpus (the
    demo world's character, and a beat-matched DJ set's): unit lengths agree with
    the output tatum, so the render lays units without a phase-vocoder stretch and
    the per-bar cost is the placement loop's. A nonzero spread gives a corpus whose
    tracks disagree on tempo, where EVERY placement is time-stretched and the
    render dominates the bar (measured; see papers/GATE-render-throughput.md)."""
    os.makedirs(work, exist_ok=True)
    tag = f"big_{n_tracks}x{int(seconds)}s_bpm{int(bpm)}_spread{int(spread)}"
    out = os.path.join(work, tag + ".etsworld")
    if os.path.exists(out) and not rebuild:
        log(f"[world] cached big world: {out}")
        return out
    wavs = []
    for i in range(n_tracks):
        p = os.path.join(work, f"{tag}_{i}.wav")
        if not os.path.exists(p):
            _synth_wav(p, seconds=seconds, bpm=bpm + spread * i, seed=i)
        wavs.append(p)
    log(f"[world] synthesized {n_tracks} x {seconds:.0f}s rhythmic WAVs "
        f"(bpm {bpm:.0f} + {spread:.0f}/track); training "
        f"(ingest -> stage-3 -> anchor fit -> build_index)…")
    t0 = time.time()
    from cloud.companion.train_local import build_trained_world
    res = build_trained_world(wavs, out, cloud_url="inproc", seed=0, sweeps=8)
    assert res.get("ok"), res
    log(f"[world] trained in {time.time() - t0:.0f}s -> {out}")
    return out


def world_stats(path: str, is_trained: bool) -> dict:
    from cloud.companion.engine_bridge import StreamPlayer
    p = StreamPlayer(path, seed=0, is_trained=is_trained)
    info = p.world_info()
    idx = p.engine.writer.threader.index
    sizes = [len(v) for v in idx.candidates.values()]
    return {"M": int(info["M"]), "n_bands": int(idx.n_bands),
            "s_phase": int(p.s_phase),
            "tracks": len(p.world.tracks),
            "units": int(sum(len(t.units) for t in p.world.tracks)),
            "pools": len(sizes), "max_pool": max(sizes) if sizes else 0}


# ---------------------------------------------------------------------------
# one produce pass, ALWAYS in a child process
#
# PROCESS ISOLATION IS PART OF THE INSTRUMENT (measured 2026-07-24): running the
# two flag states in ONE process made the throughput comparison meaningless —
# `subscribe()` leaves the warm produce loop running for ETS_WARM_IDLE_S (120s
# default) after the last listener leaves, so the next timed pass shares the core
# with a background renderer, and every pass leaves a ~250 MB audio bank behind.
# The first in-process A/B read 0.21 vs 1.29 bars/s (fast "6x SLOWER"); the same
# code, one pass per process, reads 4.371 vs 4.309. Every measured pass therefore
# runs as `--phase` in its own interpreter with its own env.
# ---------------------------------------------------------------------------

def _program(p, bar: int) -> None:
    """The SAME deterministic control trajectory in both passes: an asymmetric
    region lean, live continuity/novelty/temperature, and all three FIELD-BIAS
    grains (track / unit / (track, role)) — so the reuse vector, the channel-bias
    vector and the continuation head are all non-trivial while rows are compared.
    Bar 0 is left at u=0 (the untilted reduction) on purpose."""
    if bar == 0:
        return
    M = p.M
    p.set_region([0.35 * ((-1.0) ** k) for k in range(M)])
    p.set_continuity(0.4)
    p.set_novelty(0.6)                      # arms the recency term (reuse)
    p.set_temperature(1.0 + 0.25 * (bar % 3))
    tids = [int(t) for t in (p._channel_tids or [])]
    if tids:
        p.set_channel_bias([0.7 if i % 2 == 0 else -0.4 for i in range(len(tids))])
        p.set_track_role_bias({(tids[0], k): 0.5 for k in range(min(M, 3))})
    units = sorted({int(uid) for (_tid, uid)
                    in p.engine.writer.threader.index.unit_role})[:16]
    if units:
        p.set_unit_bias({u: 0.6 if i % 2 == 0 else -0.3 for i, u in enumerate(units)})


def _player(world: str, is_trained: bool, seed: int = 0):
    from cloud.companion.engine_bridge import StreamPlayer
    p = StreamPlayer(world, seed=seed, is_trained=is_trained)
    p.world_info()
    return p


def phase_rows(world: str, is_trained: bool, n_bars: int, seed: int = 0) -> dict:
    """`n_bars` through the REAL produce path: every placement row + the PCM.

    Rows are captured by a behaviour-neutral wrap of `_compose_bar` (it calls the
    original and records the committed BarResult)."""
    p = _player(world, is_trained, seed)
    rows, conts = [], []
    orig_compose = p._compose_bar

    def capture():
        r, sched = orig_compose()
        rows.append([[float(v) for v in row] for row in r.rows])
        conts.append([bool(c) for c in r.continues])
        return r, sched

    p._compose_bar = capture
    pcm = []
    for bar in range(n_bars):
        _program(p, bar)
        b, _roles = p.produce_one_bar()
        pcm.append(b)
    pcm = b"".join(pcm)
    return {"rows": rows, "cont": conts, "pcm_sha": hashlib.sha256(pcm).hexdigest(),
            "pcm_len": len(pcm)}


def phase_loop(world: str, is_trained: bool, n_chunks: int, seed: int = 0,
               timeout: float = 600.0) -> dict:
    """Collect `n_chunks` emissions from the REAL produce loop via subscribe()."""
    p = _player(world, is_trained, seed)
    q = p.subscribe()
    got, deadline = [], time.monotonic() + timeout
    while len(got) < n_chunks and time.monotonic() < deadline:
        try:
            got.append(q.get(timeout=1.0))
        except Exception:
            continue
    p.stop()
    p.unsubscribe(q)
    assert len(got) == n_chunks, f"produce loop delivered {len(got)}/{n_chunks}"
    pcm = b"".join(got)
    return {"pcm_sha": hashlib.sha256(pcm).hexdigest(), "pcm_len": len(pcm),
            "chunks": len(got)}


def phase_bench(world: str, is_trained: bool, n_bars: int, warmup: int = 3,
                seed: int = 0) -> dict:
    """Steady-state produce_one_bar throughput, with the compose/finish split.

    The split is measured by a behaviour-neutral wrap of the two halves (compose
    = settlement + the fiber choice this change touches; finish = the pure render
    + telemetry it does not), so a speedup can be read against the part of the bar
    it can possibly move."""
    p = _player(world, is_trained, seed)
    t = {"compose": 0.0, "finish": 0.0}
    oc, of = p._compose_bar, p._finish_bar

    def compose():
        t0 = time.perf_counter()
        try:
            return oc()
        finally:
            t["compose"] += time.perf_counter() - t0

    def finish(r, sched):
        t0 = time.perf_counter()
        try:
            return of(r, sched)
        finally:
            t["finish"] += time.perf_counter() - t0

    p._compose_bar, p._finish_bar = compose, finish
    for _ in range(warmup):
        p.produce_one_bar()                 # bank warmup + memo fill
    t["compose"] = t["finish"] = 0.0
    t0 = time.perf_counter()
    for _ in range(n_bars):
        p.produce_one_bar()
    dt = time.perf_counter() - t0
    return {"bars_per_s": n_bars / dt, "s_per_bar": dt / n_bars,
            "compose_s_per_bar": t["compose"] / n_bars,
            "finish_s_per_bar": t["finish"] / n_bars,
            "bar_seconds": float(p.engine.writer.bar_seconds)}


# ---------------------------------------------------------------------------
# parent: run a phase in a child interpreter with the flag set
# ---------------------------------------------------------------------------

def child(phase: str, world: str, is_trained: bool, fast: bool, n: int,
          seed: int = 0) -> dict:
    env = dict(os.environ)
    env["ETS_FAST_REALIZE"] = "1" if fast else "0"
    env["ETS_WARM_IDLE_S"] = "5"            # a child never outlives its measurement
    cmd = [sys.executable, os.path.abspath(__file__), "--phase", phase,
           "--world", world, "--n", str(n), "--seed", str(seed)]
    if is_trained:
        cmd.append("--trained")
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"child {phase} (fast={fast}) failed:\n{r.stderr[-3000:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------

def gate_rows(tag: str, world: str, is_trained: bool, n_bars: int) -> bool:
    log(f"[G1:{tag}] {n_bars} bars, placement rows fast-vs-original…")
    f = child("rows", world, is_trained, True, n_bars)
    o = child("rows", world, is_trained, False, n_bars)
    n_rows = sum(len(b) for b in f["rows"])
    ok = f["rows"] == o["rows"]
    if not ok:
        for i, (a, b) in enumerate(zip(f["rows"], o["rows"])):
            if a != b:
                log(f"    FAIL bar {i}: rows differ")
                for x, y in zip(a, b):
                    if x != y:
                        log(f"      fast={x} orig={y}")
                        break
                break
    if f["cont"] != o["cont"]:
        ok = False
        log("    FAIL continuation flags differ")
    log(f"    {n_rows} rows over {len(f['rows'])} bars; rows identical="
        f"{f['rows'] == o['rows']} cont identical={f['cont'] == o['cont']}")
    same_pcm = (f["pcm_sha"] == o["pcm_sha"] and f["pcm_len"] == o["pcm_len"])
    log(f"[G2a:{tag}] direct produce_one_bar PCM: fast={f['pcm_sha'][:16]} "
        f"orig={o['pcm_sha'][:16]} ({f['pcm_len']} bytes) identical={same_pcm}")
    return ok and same_pcm


def gate_loop(tag: str, world: str, is_trained: bool, n_chunks: int) -> bool:
    log(f"[G2b:{tag}] {n_chunks} emissions through the REAL produce loop "
        f"(subscribe)…")
    a = child("loop", world, is_trained, True, n_chunks)
    b = child("loop", world, is_trained, False, n_chunks)
    same = (a["pcm_sha"] == b["pcm_sha"] and a["pcm_len"] == b["pcm_len"])
    log(f"    fast={a['pcm_sha'][:16]} ({a['pcm_len']} bytes)  "
        f"orig={b['pcm_sha'][:16]} ({b['pcm_len']} bytes)  identical={same}")
    return same


def gate_speed(tag: str, world: str, is_trained: bool, n_bars: int,
               required: float = None) -> dict:
    f = child("bench", world, is_trained, True, n_bars)
    o = child("bench", world, is_trained, False, n_bars)
    r = f["bars_per_s"] / o["bars_per_s"]
    cr = (o["compose_s_per_bar"] / f["compose_s_per_bar"]
          if f["compose_s_per_bar"] > 0 else float("nan"))
    verdict = "" if required is None else \
        ("  PASS" if r >= required else f"  FAIL (< {required}x)")
    log(f"[G3:{tag}] {n_bars} bars steady state, one process per path:")
    log(f"    fast {f['bars_per_s']:7.3f} bars/s  ({f['s_per_bar'] * 1e3:8.1f} ms/bar"
        f" = compose {f['compose_s_per_bar'] * 1e3:7.1f} + finish "
        f"{f['finish_s_per_bar'] * 1e3:7.1f})")
    log(f"    orig {o['bars_per_s']:7.3f} bars/s  ({o['s_per_bar'] * 1e3:8.1f} ms/bar"
        f" = compose {o['compose_s_per_bar'] * 1e3:7.1f} + finish "
        f"{o['finish_s_per_bar'] * 1e3:7.1f})")
    log(f"    produce_one_bar speedup={r:.2f}x   compose-half speedup={cr:.2f}x   "
        f"realtime: fast={f['bar_seconds'] / f['s_per_bar']:.2f}x "
        f"orig={o['bar_seconds'] / o['s_per_bar']:.2f}x{verdict}")
    return {"speedup": r, "compose_speedup": cr, "fast": f, "orig": o}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work",
                    default=os.path.join(tempfile.gettempdir(),
                                         "ets_fast_realize_work"),
                    help="cache dir for the synthesized >=4k-unit worlds")
    ap.add_argument("--bars", type=int, default=12, help="bars per identity pass")
    ap.add_argument("--bench-bars", type=int, default=40)
    ap.add_argument("--chunks", type=int, default=8, help="loop emissions (G2b)")
    ap.add_argument("--tracks", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--bpm", type=float, default=120.0)
    ap.add_argument("--spread", type=float, default=0.0,
                    help="per-track bpm step (0 = a single-tempo, beat-matched set)")
    ap.add_argument("--build-world", action="store_true", help="build/train only")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--skip-demo", action="store_true")
    ap.add_argument("--skip-big", action="store_true")
    ap.add_argument("--skip-loop", action="store_true")
    # child-side
    ap.add_argument("--phase", default=None,
                    choices=["rows", "loop", "bench", "stats"])
    ap.add_argument("--world", default=None)
    ap.add_argument("--trained", action="store_true")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if args.phase:                            # ---- child: one measured pass ----
        fn = {"rows": phase_rows, "loop": phase_loop, "bench": phase_bench}
        if args.phase == "stats":
            out = world_stats(args.world, args.trained)
        else:
            out = fn[args.phase](args.world, args.trained, args.n, seed=args.seed)
        print(json.dumps(out))
        return 0

    if args.build_world:
        w = big_world(args.work, args.tracks, args.seconds, args.bpm, args.spread,
                      rebuild=args.rebuild)
        log(f"[world] stats: {world_stats(w, True)}")
        return 0

    ok = True
    demo = os.path.join(ROOT, "demo.etsworld")
    if not args.skip_demo:
        log(f"[world] demo stats: {child('stats', demo, False, True, 0)}")
        ok &= gate_rows("demo", demo, False, args.bars)
        if not args.skip_loop:
            ok &= gate_loop("demo", demo, False, args.chunks)
        gate_speed("demo", demo, False, args.bench_bars)

    if not args.skip_big:
        w = big_world(args.work, args.tracks, args.seconds, args.bpm, args.spread,
                      rebuild=args.rebuild)
        st = child("stats", w, True, True, 0)
        log(f"[world] big stats ({os.path.basename(w)}): {st}")
        assert st["units"] >= 4000, f"big world has only {st['units']} units (<4k)"
        ok &= gate_rows("big", w, True, args.bars)
        if not args.skip_loop:
            ok &= gate_loop("big", w, True, args.chunks)
        sp = gate_speed("big", w, True, args.bench_bars, required=2.0)
        ok &= (sp["speedup"] >= 2.0)

    log("FAST_REALIZE_VERIFY_OK" if ok else "FAST_REALIZE_VERIFY_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
