#!/usr/bin/env python3
"""Load the source bank ONCE, render many knob-journeys from it, master each.
One ~12-min bank load, then each journey is a fast render+master. Pure
convenience over the engine's own render path (bank injected via the new
render_offline(bank=...) param) — no theory/engine-logic change; byte-identical."""
import json, os, sys, time
import numpy as np
import soundfile as sf

MAIN = "/home/user/Geodesic-Mixing"
sys.path.insert(0, MAIN)
from ets.engine.engine import Engine, build_bank, resolve_sigma
from ets.engine.worldfile import load_world
from ets.render.master import master

SCRATCH = sys.argv[1]
WORLD = os.path.join(MAIN, "corpus.etsworld")
JOURNEYS = json.load(open(os.path.join(SCRATCH, "batch_journeys.json")))
os.makedirs(os.path.join(SCRATCH, "deliver"), exist_ok=True)

print("[batch] loading world + full bank ONCE ...", flush=True)
t0 = time.time()
wf = load_world(WORLD)                      # load once, reuse across journeys
sigma = resolve_sigma(wf, None)
bank = build_bank(wf)                       # full corpus bank, materialized once
print(f"[batch] bank ready: {len(bank)} units in {time.time()-t0:.0f}s", flush=True)

for j in JOURNEYS:
    name, seed, seconds = j["name"], int(j["seed"]), float(j["seconds"])
    kpath = os.path.join(SCRATCH, j["knobs"])
    ts = time.time()
    try:
        eng = Engine(wf, seed=seed, sigma=sigma)           # fresh per-seed writer
        res = eng.render_offline(seconds, knob_script=kpath, bank=bank)
        sr = int(res.receipt["sr"])
        ym = master(res.audio, sr)
        out = os.path.join(SCRATCH, "deliver", f"{name}_MASTERED.flac")
        sf.write(out, ym, sr)
        print(f"CLIP DONE {out}  ({seconds:.0f}s seed {seed} in {time.time()-ts:.0f}s)",
              flush=True)
    except Exception as e:
        import traceback
        print(f"CLIP FAIL {name}: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()

print("[batch] all journeys done", flush=True)
