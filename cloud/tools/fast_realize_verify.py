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
    import importlib
    memo = importlib.import_module("ets.render.render").stretch_memo_stats(p._bank)
    return {"bars_per_s": n_bars / dt, "s_per_bar": dt / n_bars,
            "compose_s_per_bar": t["compose"] / n_bars,
            "finish_s_per_bar": t["finish"] / n_bars,
            "bar_seconds": float(p.engine.writer.bar_seconds),
            "warmup": warmup, "memo": memo}


# ---------------------------------------------------------------------------
# parent: run a phase in a child interpreter with the flag set
# ---------------------------------------------------------------------------

CONFIGS = {                       # name -> (fiber fast path, stretch memo)
    "base": (False, False),       # the pre-change engine
    "fiber": (True, False),       # the vectorized fiber choice alone
    "memo": (False, True),        # the fitted-unit stretch memo alone
    "both": (True, True),         # what ships by default
}


def child(phase: str, world: str, is_trained: bool, cfg: str, n: int,
          seed: int = 0, warmup: int = None) -> dict:
    fast, cache = CONFIGS[cfg]
    env = dict(os.environ)
    env["ETS_FAST_REALIZE"] = "1" if fast else "0"
    env["ETS_STRETCH_CACHE"] = "1" if cache else "0"
    env["ETS_WARM_IDLE_S"] = "5"            # a child never outlives its measurement
    cmd = [sys.executable, os.path.abspath(__file__), "--phase", phase,
           "--world", world, "--n", str(n), "--seed", str(seed)]
    if warmup is not None:
        cmd += ["--warmup", str(warmup)]
    if is_trained:
        cmd.append("--trained")
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"child {phase} (cfg={cfg}) failed:\n{r.stderr[-3000:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------

def gate_rows(tag: str, world: str, is_trained: bool, n_bars: int,
              a: str = "both", b: str = "base") -> bool:
    """G1 + G2a: identical placement rows and identical PCM, config a vs b."""
    log(f"[G1:{tag}] {n_bars} bars, placement rows {a} vs {b}…")
    fa = child("rows", world, is_trained, a, n_bars)
    fb = child("rows", world, is_trained, b, n_bars)
    n_rows = sum(len(x) for x in fa["rows"])
    ok = fa["rows"] == fb["rows"]
    if not ok:
        for i, (x, y) in enumerate(zip(fa["rows"], fb["rows"])):
            if x != y:
                log(f"    FAIL bar {i}: rows differ")
                for u, v in zip(x, y):
                    if u != v:
                        log(f"      {a}={u} {b}={v}")
                        break
                break
    if fa["cont"] != fb["cont"]:
        ok = False
        log("    FAIL continuation flags differ")
    log(f"    {n_rows} rows over {len(fa['rows'])} bars; rows identical={ok} "
        f"cont identical={fa['cont'] == fb['cont']}")
    same = (fa["pcm_sha"] == fb["pcm_sha"] and fa["pcm_len"] == fb["pcm_len"])
    log(f"[G2a:{tag}] direct produce_one_bar PCM {a} vs {b}: "
        f"{fa['pcm_sha'][:16]} / {fb['pcm_sha'][:16]} ({fa['pcm_len']} bytes) "
        f"identical={same}")
    return ok and same


def gate_loop(tag: str, world: str, is_trained: bool, n_chunks: int,
              a: str = "both", b: str = "base") -> bool:
    """G2b: identical PCM through the REAL produce loop (subscribe)."""
    log(f"[G2b:{tag}] {n_chunks} emissions through the produce loop, {a} vs {b}…")
    x = child("loop", world, is_trained, a, n_chunks)
    y = child("loop", world, is_trained, b, n_chunks)
    same = (x["pcm_sha"] == y["pcm_sha"] and x["pcm_len"] == y["pcm_len"])
    log(f"    {a}={x['pcm_sha'][:16]} ({x['pcm_len']} bytes)  "
        f"{b}={y['pcm_sha'][:16]} ({y['pcm_len']} bytes)  identical={same}")
    return same


def gate_speed(tag: str, world: str, is_trained: bool, n_bars: int,
               warmup: int, required: float = None,
               configs=("base", "fiber", "memo", "both")) -> dict:
    """G3: bars/s for each configuration, one process each, same conditions.

    Reports the compose/finish split (compose = the settlement + fiber choice
    the vectorization touches; finish = the render the memo touches) and, where
    the memo ran, its measured hit rate and resident size — so each half of the
    change is read against the part of the bar it can possibly move."""
    log(f"[G3:{tag}] {n_bars} bars steady state (warmup {warmup}), "
        f"one process per configuration:")
    out = {}
    for cfg in configs:
        d = child("bench", world, is_trained, cfg, n_bars, warmup=warmup)
        out[cfg] = d
        memo = d.get("memo")
        mtxt = ""
        if memo:
            mtxt = (f"  memo {memo['hit_rate'] * 100:5.1f}% hit, "
                    f"{memo['entries']} entries, {memo['bytes'] / 1e6:.0f} MB"
                    + (f", {memo['evictions']} evicted" if memo["evictions"] else ""))
        log(f"    {cfg:6s} {d['bars_per_s']:8.3f} bars/s  "
            f"({d['s_per_bar'] * 1e3:8.1f} ms/bar = compose "
            f"{d['compose_s_per_bar'] * 1e3:7.1f} + finish "
            f"{d['finish_s_per_bar'] * 1e3:8.1f})  "
            f"realtime {d['bar_seconds'] / d['s_per_bar']:6.2f}x{mtxt}")
    base = out.get("base")
    if base:
        for cfg in configs:
            if cfg == "base":
                continue
            r = out[cfg]["bars_per_s"] / base["bars_per_s"]
            verdict = ""
            if required is not None and cfg == "both":
                verdict = "  PASS" if r >= required else f"  FAIL (< {required}x)"
            log(f"    speedup {cfg:6s} vs base: {r:5.2f}x{verdict}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work",
                    default=os.path.join(tempfile.gettempdir(),
                                         "ets_fast_realize_work"),
                    help="cache dir for the synthesized >=4k-unit worlds")
    ap.add_argument("--bars", type=int, default=12, help="bars per identity pass")
    ap.add_argument("--bench-bars", type=int, default=40)
    ap.add_argument("--bench-warmup", type=int, default=20,
                    help="bars produced before timing (the memo's steady state "
                         "is what a live listener hears; 3 measures a cold start)")
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
    ap.add_argument("--skip-speed", action="store_true")
    # child-side
    ap.add_argument("--phase", default=None,
                    choices=["rows", "loop", "bench", "stats"])
    ap.add_argument("--world", default=None)
    ap.add_argument("--trained", action="store_true")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if args.phase:                            # ---- child: one measured pass ----
        if args.phase == "stats":
            out = world_stats(args.world, args.trained)
        elif args.phase == "bench":
            out = phase_bench(args.world, args.trained, args.n,
                              warmup=args.warmup, seed=args.seed)
        elif args.phase == "rows":
            out = phase_rows(args.world, args.trained, args.n, seed=args.seed)
        else:
            out = phase_loop(args.world, args.trained, args.n, seed=args.seed)
        print(json.dumps(out))
        return 0

    if args.build_world:
        w = big_world(args.work, args.tracks, args.seconds, args.bpm, args.spread,
                      rebuild=args.rebuild)
        log(f"[world] stats: {world_stats(w, True)}")
        return 0

    ok = True
    worlds = []
    if not args.skip_demo:
        worlds.append(("demo", os.path.join(ROOT, "demo.etsworld"), False, None))
    if not args.skip_big:
        w = big_world(args.work, args.tracks, args.seconds, args.bpm, args.spread,
                      rebuild=args.rebuild)
        st = child("stats", w, True, "both", 0)
        assert st["units"] >= 4000, f"big world has only {st['units']} units (<4k)"
        tag = "big-single-tempo" if args.spread == 0 else "big-multi-tempo"
        worlds.append((tag, w, True, 2.0))

    for tag, world, trained, required in worlds:
        log(f"[world] {tag}: {child('stats', world, trained, 'both', 0)}")
        # the WHOLE change vs the pre-change engine…
        ok &= gate_rows(tag, world, trained, args.bars, "both", "base")
        # …and each half isolated, so neither can hide the other's drift.
        ok &= gate_rows(tag, world, trained, args.bars, "both", "fiber")
        ok &= gate_rows(tag, world, trained, args.bars, "fiber", "base")
        if not args.skip_loop:
            ok &= gate_loop(tag, world, trained, args.chunks, "both", "base")
        if not args.skip_speed:
            gate_speed(tag, world, trained, args.bench_bars, args.bench_warmup,
                       required=required)

    log("FAST_REALIZE_VERIFY_OK" if ok else "FAST_REALIZE_VERIFY_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
