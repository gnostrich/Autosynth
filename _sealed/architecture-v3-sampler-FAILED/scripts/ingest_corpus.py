#!/usr/bin/env python3
"""Ingest the corpus mp3s into the cache the world-build reads (spec §2).

Runs each corpus track through ingestion (beat clock -> filterbank ->
unitization) and writes cache/ingest/track_NN.npz, the canonical inputs
scripts/build_worldfile.py freezes the world from. Track id = sorted-filename
order (must stay stable across ingest -> world -> render).

Paths default to the repo root and are env-overridable (ETS_MAIN / ETS_CACHE /
ETS_CORPUS), same convention as build_worldfile.py.

    python scripts/ingest_corpus.py          # ingest corpus/*.mp3 -> cache/ingest
    python scripts/ingest_corpus.py --force  # re-ingest even if a .npz exists
"""
from __future__ import annotations
import argparse
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAIN = os.environ.get(
    "ETS_MAIN", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.environ.get("ETS_CACHE", os.path.join(MAIN, "cache", "ingest"))
CORPUS = os.environ.get("ETS_CORPUS", os.path.join(MAIN, "corpus"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="re-ingest tracks whose .npz already exists")
    args = ap.parse_args()

    from ets.ingestion.pipeline import ingest, save

    os.makedirs(CACHE, exist_ok=True)
    mp3s = sorted(glob.glob(os.path.join(CORPUS, "*.mp3")))
    if not mp3s:
        sys.exit(f"no mp3s under {CORPUS} (set ETS_CORPUS or stage the corpus)")
    print(f"ingesting {len(mp3s)} tracks from {CORPUS} -> {CACHE}")

    t0 = time.time()
    for track_id, path in enumerate(mp3s):
        out = os.path.join(CACHE, f"track_{track_id:02d}.npz")
        if os.path.exists(out) and not args.force:
            print(f"  [{track_id:02d}] cached, skip ({os.path.basename(path)})")
            continue
        ts = time.time()
        track = ingest(path, track_id)
        save(track, out)
        print(f"  [{track_id:02d}] {os.path.basename(path)} "
              f"-> {os.path.basename(out)} ({time.time()-ts:.1f}s)")

    n = len(glob.glob(os.path.join(CACHE, "track_*.npz")))
    print(f"done: {n} tracks in cache ({time.time()-t0:.1f}s). "
          f"Next: python scripts/build_worldfile.py --out corpus.etsworld")


if __name__ == "__main__":
    main()
