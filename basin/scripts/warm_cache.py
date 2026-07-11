"""Pre-warm the audio caches so live play never stalls.

Pays every one-time cost offline: mp3 decode → mmap npy (mix), NMF split →
channel flacs, flac → mmap npy per channel. After this, any track/channel
switch during live play or rendering costs ~0.5 ms (mmap re-open).

By default warms the MIX tier only (the one-flow default voice; ~120 MB
per track). Pass --channels to also pre-convert every channel to npy —
NOTE: that costs ~1 GB of disk PER TRACK (8 channels x ~130 MB); without
it, channels convert lazily (~0.6 s once per channel-track) when first
played in counterpoint mode.

Usage: python scripts/warm_cache.py [--instrument PATH] [--channels]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402

from basin import store, operator  # noqa: E402
from basin.render import GrainReader  # noqa: E402
from scripts._bootstrap import instrument_path  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instrument", default=None)
    ap.add_argument("--channels", action="store_true",
                    help="also pre-convert channel npys (heavy on disk)")
    args = ap.parse_args()
    path = args.instrument or instrument_path()
    inst = store.load_instrument(path)
    corpus = inst["corpus"]
    cfg = dict(inst["config"])
    psi, _ = operator.full_psi(inst["eigvals"], inst["eig_right"])
    n_ch = int(getattr(corpus, "n_channels", 0) or 0)
    stems = ["mix"] + ([f"ch{k}" for k in range(n_ch)]
                       if args.channels else [])
    shared: dict = {}
    readers = {s: GrainReader(corpus, inst["atlas"].memberships, cfg,
                              seed=0, stem=s, shared_cache=shared, psi=psi)
               for s in stems}
    t00 = time.time()
    for t in range(corpus.n_tracks):
        t0 = time.time()
        for s in stems:
            readers[s]._track_audio(t)
        # keep memory flat: mmaps re-open instantly, drop everything
        shared.clear()
        print(f"track {t:2d}: {time.time() - t0:5.1f}s "
              f"({len(stems)} stems)", flush=True)
    print(f"done in {(time.time() - t00) / 60:.1f} min — "
          f"all switches are now ~0.5 ms")


if __name__ == "__main__":
    main()
