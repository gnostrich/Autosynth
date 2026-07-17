"""Measure the per-bar PRODUCTION time of the untilted writer on THIS host and
derive the declared latency L for a registered profile (PREREG: "Latency
profile table"; buffer math in ets.engine.latency — L = ceil(max T_prod /
T_bar) + 1, never taste).

Production = exactly what the live loop does per bar: frontier settle +
temperature sample + fiber threading (StreamWriter.write_bar) + per-bar render
(the same render_schedule call). Source-bank materialization is STARTUP cost
(the live engine preloads before the clock starts) and is reported separately,
not inside T_prod.

Usage:
    python3 scripts/measure_latency_profile.py --world corpus.etsworld \
        --profile desktop --bars 16 --out latency_desktop.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", required=True)
    ap.add_argument("--profile", default="desktop")
    ap.add_argument("--bars", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import platform
    from ets.engine.engine import bar_schedule, build_bank
    from ets.engine.latency import PROFILES, derive_L
    from ets.engine.worldfile import load_world
    from ets.render import render as render_schedule
    from ets.writer.stream import StreamWriter
    from ets.writer.tilt import untilted

    wf = load_world(args.world)
    world = wf.world
    prof = PROFILES[args.profile]
    w = StreamWriter(world, seed=args.seed)
    tilt = untilted(world.M)

    print(f"[1/3] writing {args.bars} untilted bars (timed) ...")
    bars, write_t = [], []
    for _ in range(args.bars):
        t0 = time.perf_counter()
        bars.append(w.write_bar(tilt=tilt))
        write_t.append(time.perf_counter() - t0)

    used = sorted({int(t) for r in bars for (_s, t, _u, _sec, _m) in r.rows})
    print(f"[2/3] materializing bank for tracks {used} (startup cost, "
          "excluded from T_prod) ...")
    t0 = time.perf_counter()
    bank = build_bank(wf, track_ids=set(used))
    bank_t = time.perf_counter() - t0

    print(f"[3/3] rendering {args.bars} bars (timed) ...")
    render_t = []
    for r in bars:
        sched = bar_schedule(world, r.rows, w.s_phase)
        t0 = time.perf_counter()
        render_schedule(sched, bank)
        render_t.append(time.perf_counter() - t0)

    t_prod = [a + b for a, b in zip(write_t, render_t)]
    deriv = derive_L(t_prod, w.bar_seconds)
    record = {
        "instrument": "latency-profile measurement (scripts/measure_latency_profile.py)",
        "profile": prof.name,
        "profile_params": {"sr": prof.sr, "blocksize": prof.blocksize,
                           "n_warmup": prof.n_warmup,
                           "device_latency_ms": 1000 * prof.device_latency_s},
        "host": {"platform": platform.platform(),
                 "python": platform.python_version()},
        "world_sha256": wf.world_hash,
        "seed": args.seed,
        "n_bars": args.bars,
        "bar_seconds": w.bar_seconds,
        "t_write_s": write_t,
        "t_render_s": render_t,
        "t_prod_s": t_prod,
        "bank_startup_s": bank_t,
        "tracks_materialized": used,
        "derivation": deriv,
    }
    print(json.dumps({k: v for k, v in record.items()
                      if k not in ("t_write_s", "t_render_s", "t_prod_s")},
                     indent=2))
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(record, fh, indent=2)
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
