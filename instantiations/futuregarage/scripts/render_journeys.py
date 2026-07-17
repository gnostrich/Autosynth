#!/usr/bin/env python3
"""Render a set of knob-journey "tracks" from the futuregarage instantiation.

Loads the fork world ONCE, materializes the source bank ONCE (disk-cached), then
renders each journey via the engine's own offline path (bank injected — pure
convenience, byte-identical to an uncached render) and applies the EXTERNAL
mastering layer per clip. Nothing here changes theory/engine logic: it is the
registered engine render + the opt-in ets.render.master read-stage, driven over a
list of (seed, knob-script) journeys for listening variety.

Run inside the fork:
    PYTHONPATH=<fork> python3 scripts/render_journeys.py --out <dir> [--journeys j.json]
"""
from __future__ import annotations
import argparse, json, os, sys, time
import numpy as np
import soundfile as sf

FORK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, FORK)

from ets.engine.engine import Engine, build_bank, resolve_sigma
from ets.engine.worldfile import load_world
from ets.render.master import master


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="output dir for clips")
    ap.add_argument("--journeys", default=None,
                    help="JSON list of {name,seed,seconds,knobs?}; knobs is a "
                         "path to a knob script. Default: a single u=0 clip.")
    ap.add_argument("--seconds", type=float, default=30.0,
                    help="length for the default single clip")
    ap.add_argument("--lufs", type=float, default=-14.0)
    args = ap.parse_args()

    world_path = os.path.join(FORK, "corpus.etsworld")
    os.makedirs(args.out, exist_ok=True)

    print(f"[futuregarage] load world {world_path}", flush=True)
    wf = load_world(world_path)
    sigma = resolve_sigma(wf, None)     # fork's ets/calibration/sigma_phi.json
    print(f"[futuregarage] world M={wf.world.M} hash={wf.world_hash[:12]} "
          f"sigma_calibrated={sigma is not None}", flush=True)

    t0 = time.time()
    print("[futuregarage] materialize source bank (cached after first build) ...", flush=True)
    bank = build_bank(wf)
    print(f"[futuregarage] bank ready: {len(bank)} units in {time.time()-t0:.0f}s", flush=True)

    if args.journeys:
        journeys = json.load(open(args.journeys))
    else:
        journeys = [{"name": "u0_probe", "seed": 0, "seconds": args.seconds}]

    for j in journeys:
        name, seed, seconds = j["name"], int(j["seed"]), float(j["seconds"])
        kpath = j.get("knobs")
        if kpath and not os.path.isabs(kpath):
            kpath = os.path.join(args.out, kpath)
        ts = time.time()
        try:
            eng = Engine(wf, seed=seed, sigma=sigma)
            res = eng.render_offline(seconds, knob_script=kpath, bank=bank)
            sr = int(res.receipt["sr"])
            ym = master(res.audio, sr, target_lufs=args.lufs)
            out = os.path.join(args.out, f"{name}.flac")
            sf.write(out, ym.astype(np.float32), sr, format="FLAC")
            mb = os.path.getsize(out) / 1e6
            print(f"CLIP_DONE {name} {seconds:.0f}s seed{seed} "
                  f"{time.time()-ts:.0f}s -> {out} ({mb:.1f} MB)", flush=True)
        except Exception as e:
            import traceback
            print(f"CLIP_FAIL {name}: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()

    print("[futuregarage] all journeys done", flush=True)


if __name__ == "__main__":
    main()
