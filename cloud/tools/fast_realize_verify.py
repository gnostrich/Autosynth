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
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)                          # for cloud.*
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))   # arch-v6 engine WINS

import numpy as np                                                       # noqa: E402


def log(m):
    print(m, flush=True)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


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
              rebuild: bool = False) -> str:
    """Synthesize + train (cached) a multi-track world of >=4k real units."""
    os.makedirs(work, exist_ok=True)
    out = os.path.join(work, "big.etsworld")
    if os.path.exists(out) and not rebuild:
        log(f"[world] cached big world: {out}")
        return out
    wavs = []
    for i in range(n_tracks):
        p = os.path.join(work, f"big{i}.wav")
        if not os.path.exists(p):
            _synth_wav(p, seconds=seconds, bpm=112.0 + 7.0 * i, seed=i)
        wavs.append(p)
    log(f"[world] synthesized {n_tracks} x {seconds:.0f}s rhythmic WAVs; training "
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
# one produce pass (rows + PCM) under a deterministic lane/field program
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


def produce_pass(world: str, is_trained: bool, n_bars: int, fast: bool,
                 seed: int = 0):
    """Run `n_bars` through the REAL produce path; return (rows, pcm bytes).

    `rows` is captured by a behaviour-neutral wrap of `_compose_bar` (it calls
    the original and records the committed BarResult's rows + continues)."""
    os.environ["ETS_FAST_REALIZE"] = "1" if fast else "0"
    from cloud.companion.engine_bridge import StreamPlayer
    p = StreamPlayer(world, seed=seed, is_trained=is_trained)
    p.world_info()
    rows, conts = [], []
    orig_compose = p._compose_bar

    def capture():
        r, sched = orig_compose()
        rows.append(tuple(tuple(x) for x in r.rows))
        conts.append(tuple(bool(c) for c in r.continues))
        return r, sched

    p._compose_bar = capture
    pcm = []
    for bar in range(n_bars):
        _program(p, bar)
        b, _roles = p.produce_one_bar()
        pcm.append(b)
    return rows, conts, b"".join(pcm)


def loop_pass(world: str, is_trained: bool, n_chunks: int, fast: bool,
              seed: int = 0, timeout: float = 240.0) -> bytes:
    """Collect `n_chunks` emissions from the REAL produce loop via subscribe()."""
    os.environ["ETS_FAST_REALIZE"] = "1" if fast else "0"
    from cloud.companion.engine_bridge import StreamPlayer
    p = StreamPlayer(world, seed=seed, is_trained=is_trained)
    p.world_info()
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
    return b"".join(got)


def bars_per_second(world: str, is_trained: bool, fast: bool, n_bars: int,
                    warmup: int = 3, seed: int = 0) -> float:
    os.environ["ETS_FAST_REALIZE"] = "1" if fast else "0"
    from cloud.companion.engine_bridge import StreamPlayer
    p = StreamPlayer(world, seed=seed, is_trained=is_trained)
    p.world_info()
    for _ in range(warmup):
        p.produce_one_bar()                 # bank warmup + memo fill
    t0 = time.perf_counter()
    for _ in range(n_bars):
        p.produce_one_bar()
    return n_bars / (time.perf_counter() - t0)


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------

def gate_rows(tag: str, world: str, is_trained: bool, n_bars: int) -> bool:
    log(f"[G1:{tag}] {n_bars} bars, placement rows fast-vs-original…")
    rf, cf, pf = produce_pass(world, is_trained, n_bars, fast=True)
    ro, co, po = produce_pass(world, is_trained, n_bars, fast=False)
    n_rows = sum(len(b) for b in rf)
    ok = True
    if len(rf) != len(ro):
        log(f"    FAIL bar count {len(rf)} != {len(ro)}"); return False
    for i, (a, b) in enumerate(zip(rf, ro)):
        if a != b:
            ok = False
            log(f"    FAIL bar {i}: rows differ")
            for j, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    log(f"      row {j}: fast={x} orig={y}")
                    break
            break
    if cf != co:
        ok = False
        log("    FAIL continuation flags differ")
    log(f"    {n_rows} rows over {len(rf)} bars; rows identical={rf == ro} "
        f"cont identical={cf == co}")
    log(f"[G2a:{tag}] direct produce_one_bar PCM: fast={sha(pf)} orig={sha(po)} "
        f"({len(pf)} bytes) identical={pf == po}")
    return ok and (pf == po)


def gate_loop(tag: str, world: str, is_trained: bool, n_chunks: int) -> bool:
    log(f"[G2b:{tag}] {n_chunks} emissions through the REAL produce loop "
        f"(subscribe)…")
    a = loop_pass(world, is_trained, n_chunks, fast=True)
    b = loop_pass(world, is_trained, n_chunks, fast=False)
    log(f"    fast={sha(a)} ({len(a)} bytes)  orig={sha(b)} ({len(b)} bytes)  "
        f"identical={a == b}")
    return a == b


def gate_speed(tag: str, world: str, is_trained: bool, n_bars: int,
               required: float = None) -> float:
    f = bars_per_second(world, is_trained, True, n_bars)
    o = bars_per_second(world, is_trained, False, n_bars)
    r = f / o
    verdict = "" if required is None else \
        ("  PASS" if r >= required else f"  FAIL (< {required}x)")
    log(f"[G3:{tag}] {n_bars} bars steady state: fast={f:.3f} bars/s  "
        f"orig={o:.3f} bars/s  speedup={r:.2f}x{verdict}")
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work",
                    default=os.path.join(tempfile.gettempdir(),
                                         "ets_fast_realize_work"),
                    help="cache dir for the synthesized >=4k-unit world")
    ap.add_argument("--bars", type=int, default=12, help="bars per identity pass")
    ap.add_argument("--bench-bars", type=int, default=40)
    ap.add_argument("--chunks", type=int, default=8, help="loop emissions (G2b)")
    ap.add_argument("--tracks", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--build-world", action="store_true", help="build/train only")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--skip-big", action="store_true")
    ap.add_argument("--skip-loop", action="store_true")
    args = ap.parse_args()

    if args.build_world:
        w = big_world(args.work, args.tracks, args.seconds, rebuild=args.rebuild)
        log(f"[world] stats: {world_stats(w, True)}")
        return 0

    demo = os.path.join(ROOT, "demo.etsworld")
    log(f"[world] demo stats: {world_stats(demo, False)}")
    ok = True
    ok &= gate_rows("demo", demo, False, args.bars)
    if not args.skip_loop:
        ok &= gate_loop("demo", demo, False, args.chunks)
    demo_speed = gate_speed("demo", demo, False, args.bench_bars)

    big_speed = None
    if not args.skip_big:
        w = big_world(args.work, args.tracks, args.seconds, rebuild=args.rebuild)
        st = world_stats(w, True)
        log(f"[world] big stats: {st}")
        assert st["units"] >= 4000, f"big world has only {st['units']} units (<4k)"
        ok &= gate_rows("big", w, True, args.bars)
        if not args.skip_loop:
            ok &= gate_loop("big", w, True, args.chunks)
        big_speed = gate_speed("big", w, True, args.bench_bars, required=2.0)
        ok &= (big_speed >= 2.0)

    log(f"[summary] identity={'OK' if ok else 'BROKEN'}  demo speedup="
        f"{demo_speed:.2f}x  big speedup="
        f"{'n/a' if big_speed is None else f'{big_speed:.2f}x'}")
    log("FAST_REALIZE_VERIFY_OK" if ok else "FAST_REALIZE_VERIFY_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
