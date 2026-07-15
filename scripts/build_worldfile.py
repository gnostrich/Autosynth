"""Build the frozen-corpus WORLD FILE the engine loads (`--world`).

Freezes the world from the 20 cached ingested tracks (the same
build_world_from_tracks the batch generator uses — anchors, prototypes,
realization index), records the corpus mp3 paths for deterministic source
materialization ("corpus" sources — unit audio is re-derived by the fixed
filterbank reconstruction, no choices), embeds NO σ_φ (the registered corpus
calibration artifact is a separate instrument, ets/calibration/sigma_phi.json,
loaded by the engine via ets.calibration at startup), and writes
<out>.etsworld with its content hash (the H-8 world key).

Data (cache + corpus) live in the MAIN checkout, read by absolute path.

Usage:
    python3 scripts/build_worldfile.py --out corpus.etsworld
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAIN = "/home/user/Geodesic-Mixing"
CACHE = os.path.join(MAIN, "cache/ingest")
CORPUS = os.path.join(MAIN, "corpus")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(MAIN, "corpus.etsworld"))
    ap.add_argument("--sigma", type=float, default=None,
                    help="frozen corpus affinity scale; default = set median")
    args = ap.parse_args()

    from ets.ingestion.pipeline import load
    from ets.writer import build_world_from_tracks
    from ets.engine.worldfile import save_world

    t0 = time.time()
    paths = sorted(glob.glob(os.path.join(CACHE, "track_*.npz")))
    if not paths:
        sys.exit(f"no cached tracks under {CACHE}")
    tracks = [load(p) for p in paths]
    print(f"[1/3] {len(tracks)} cached tracks loaded")

    world = build_world_from_tracks(tracks, sigma=args.sigma)
    print(f"[2/3] world frozen: M={world.M} anchors, "
          f"tatum={world.out_tatum_len} samples, info={json.dumps(world.info)}")

    mp3s = sorted(glob.glob(os.path.join(CORPUS, "*.mp3")))
    src_paths = {int(t.track_id): mp3s[int(t.track_id)] for t in tracks}
    digest = save_world(args.out, world,
                        {"kind": "corpus", "paths": src_paths}, sigma_phi=None)
    print(f"[3/3] {args.out} written in {time.time()-t0:.1f}s")
    print(f"world sha256: {digest}")


if __name__ == "__main__":
    main()
