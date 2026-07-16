#!/usr/bin/env python3
"""Generate a ~30-min psytech set as five ~6-min journeys, in the committed
genre-recipe DNA (streaming engine + low-temperature steered journeys: temp low
for commitment, continuity high, region development across the whole length).

Writes the journeys into samples/genre_set/recipes/longset/ (so the 30-min set is
itself a reproducible, version-controllable recipe), then renders + masters each on
the canonical v1 engine. Deterministic per seed.

    python3 scripts/make_longset.py --render   # write journeys AND render
    python3 scripts/make_longset.py            # write journeys only
"""
from __future__ import annotations
import argparse, json, os, sys, time
import numpy as np

MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPE_DIR = os.path.join(MAIN, "samples", "genre_set", "recipes", "longset")
OUT_DIR = os.path.join(MAIN, "samples", "genre_set", "renders", "longset")
SECONDS = 360.0
BARS = 200                      # ~1.77 s/bar -> ~360s

def region(dom, hi=1.6, base=0.45, second=None, sec_val=0.9):
    v = [base] * 5
    v[dom] = hi
    if second is not None:
        v[second] = sec_val
    return v

def build(seed, arc):
    """arc: list of (bar, lane, value) events. Prepend a committed opening."""
    ev = [{"bar": 0, "lane": "temperature", "value": 0.12},   # low -> committed
          {"bar": 0, "lane": "continuity",  "value": 2.6}]
    ev += arc
    return {"seed": seed, "seconds": SECONDS, "events": ev}

# Five distinct journeys, all in the winning DNA; region develops across the track.
JOURNEYS = {
 "ls_driving": build(131, [
    {"bar": 0,   "lane": "region", "value": region(0, 1.7, 0.45, 4, 0.9)},
    {"bar": 32,  "lane": "region", "value": region(2, 1.6, 0.5)},
    {"bar": 56,  "lane": "novelty","value": 1.0},
    {"bar": 72,  "lane": "region", "value": region(1, 1.7, 0.5, 3, 0.8)},
    {"bar": 104, "lane": "continuity", "value": 3.0},
    {"bar": 112, "lane": "region", "value": region(0, 1.5, 0.5, 4, 1.0)},
    {"bar": 148, "lane": "region", "value": region(3, 1.6, 0.5)},
    {"bar": 176, "lane": "region", "value": region(4, 1.6, 0.5, 0, 0.9)}]),
 "ls_spacious": build(147, [
    {"bar": 0,   "lane": "temperature", "value": 0.09},
    {"bar": 0,   "lane": "continuity",  "value": 3.0},
    {"bar": 0,   "lane": "region", "value": region(4, 1.5, 0.5, 2, 0.9)},
    {"bar": 40,  "lane": "region", "value": region(2, 1.6, 0.5)},
    {"bar": 80,  "lane": "novelty","value": 0.8},
    {"bar": 96,  "lane": "region", "value": region(1, 1.5, 0.55, 4, 0.9)},
    {"bar": 136, "lane": "region", "value": region(3, 1.6, 0.5)},
    {"bar": 172, "lane": "region", "value": region(4, 1.7, 0.5, 2, 0.8)}]),
 "ls_shifting": build(159, [
    {"bar": 0,   "lane": "continuity", "value": 2.2},
    {"bar": 0,   "lane": "region", "value": region(1, 1.6, 0.5)},
    {"bar": 24,  "lane": "region", "value": region(3, 1.6, 0.5)},
    {"bar": 44,  "lane": "temperature", "value": 0.22},
    {"bar": 48,  "lane": "region", "value": region(0, 1.7, 0.5, 2, 0.9)},
    {"bar": 84,  "lane": "region", "value": region(4, 1.6, 0.5)},
    {"bar": 108, "lane": "novelty","value": 1.1},
    {"bar": 120, "lane": "region", "value": region(2, 1.7, 0.5, 0, 0.9)},
    {"bar": 160, "lane": "region", "value": region(1, 1.6, 0.55)}]),
 "ls_deep": build(171, [
    {"bar": 0,   "lane": "temperature", "value": 0.08},
    {"bar": 0,   "lane": "continuity",  "value": 3.0},
    {"bar": 0,   "lane": "region", "value": region(3, 1.6, 0.4)},
    {"bar": 48,  "lane": "region", "value": region(0, 1.5, 0.45, 3, 0.9)},
    {"bar": 96,  "lane": "region", "value": region(4, 1.6, 0.45)},
    {"bar": 144, "lane": "region", "value": region(2, 1.5, 0.5, 4, 0.8)},
    {"bar": 180, "lane": "region", "value": region(3, 1.7, 0.45)}]),
 "ls_ascend": build(188, [
    {"bar": 0,   "lane": "continuity", "value": 2.0},
    {"bar": 0,   "lane": "region", "value": region(0, 1.4, 0.5)},
    {"bar": 40,  "lane": "continuity", "value": 2.5},
    {"bar": 48,  "lane": "region", "value": region(2, 1.6, 0.5, 0, 0.9)},
    {"bar": 88,  "lane": "novelty", "value": 0.9},
    {"bar": 96,  "lane": "region", "value": region(1, 1.6, 0.5)},
    {"bar": 128, "lane": "temperature", "value": 0.28},
    {"bar": 136, "lane": "region", "value": region(4, 1.7, 0.5, 2, 1.0)},
    {"bar": 168, "lane": "continuity", "value": 3.0},
    {"bar": 176, "lane": "region", "value": region(3, 1.7, 0.55)}]),
}


def write_journeys():
    os.makedirs(RECIPE_DIR, exist_ok=True)
    manifest = []
    for name, j in JOURNEYS.items():
        kp = os.path.join(RECIPE_DIR, f"{name}.json")
        json.dump({"events": j["events"]}, open(kp, "w"), indent=1)
        manifest.append({"name": name, "seed": j["seed"], "seconds": j["seconds"],
                         "knobs": f"{name}.json"})
    json.dump(manifest, open(os.path.join(RECIPE_DIR, "longset_journeys.json"), "w"), indent=2)
    print(f"[journeys] wrote {len(manifest)} journeys -> {RECIPE_DIR}")
    return manifest


def render(manifest):
    os.environ.setdefault("ETS_BANK_CACHE", os.path.join(MAIN, "cache", "units"))
    sys.path.insert(0, MAIN)
    import soundfile as sf
    from ets.engine.engine import Engine, build_bank, resolve_sigma
    from ets.engine.worldfile import load_world
    from ets.render.master import master
    os.makedirs(OUT_DIR, exist_ok=True)
    wf = load_world(os.path.join(MAIN, "corpus.etsworld"))
    sigma = resolve_sigma(wf, None)
    t0 = time.time(); bank = build_bank(wf)
    print(f"[render] bank ready: {len(bank)} units in {time.time()-t0:.0f}s", flush=True)

    def gaps(a, sr):
        sil = np.abs(a) < 1e-3; ml = int(0.15*sr); i=0; n=len(sil); g=0
        while i < n:
            if sil[i]:
                j=i
                while j<n and sil[j]: j+=1
                if j-i>=ml: g+=1
                i=j
            else: i+=1
        return g

    for m in manifest:
        ts = time.time()
        kp = os.path.join(RECIPE_DIR, m["knobs"])
        eng = Engine(wf, seed=int(m["seed"]), sigma=sigma)
        res = eng.render_offline(float(m["seconds"]), knob_script=kp, bank=bank)
        a = np.asarray(res.audio); sr = int(res.receipt["sr"])
        g = gaps(a, sr)
        out = os.path.join(OUT_DIR, f"{m['name']}_MASTERED.flac")
        sf.write(out, master(a, sr), sr)
        print(f"TRACK {m['name']} seed {m['seed']}: {m['seconds']:.0f}s gaps={g} "
              f"peak={float(np.max(np.abs(a))):.2f} finite={bool(np.all(np.isfinite(a)))} "
              f"in {time.time()-ts:.0f}s -> {out}", flush=True)
    print("LONGSET_DONE", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()
    manifest = write_journeys()
    if args.render:
        render(manifest)


if __name__ == "__main__":
    main()
