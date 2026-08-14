#!/usr/bin/env python3
"""Re-train the operator's own corpus into a playable world, IN THE CONTAINER.

The audio and the resulting ~41MB world are the operator's files: they are NOT
committed and NOT redistributable. What IS committed is this script plus
`cloud/fixtures/operator_corpus_receipt.json`, which records every source
file's sha256, the world's shape, and the measurements taken from it — so the
2026-08-14 result can be re-derived from the operator's own copy of the audio
rather than taken on trust.

WHY IT EXISTS: every contradictory answer of 2026-08-14 came from measuring an
audible defect on `demo.etsworld` — 192 units per track, uniform numbering,
seconds of material. A real world has 11k-20k units per track. The difference
is not cosmetic: it is the difference between a world that can exhibit the
cross-track collision class and one that cannot.

Usage:
  python3 scripts/train_operator_corpus.py --audio /tmp/corpus --out /tmp/corpus_world.etsworld
  # then measure:
  ETS_W=/tmp/corpus_world.etsworld python3 cloud/tools/bridge_slot_pin_spread_verify.py
"""
import argparse, glob, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", default="/tmp/corpus",
                    help="directory of the operator's audio (not in this repo)")
    ap.add_argument("--out", default="/tmp/corpus_world.etsworld")
    ap.add_argument("--tracks", type=int, default=10)
    a = ap.parse_args()

    from cloud.companion.train_local import build_trained_world
    paths = sorted(glob.glob(os.path.join(a.audio, "*.mp3")))[:a.tracks]
    if not paths:
        print("no audio found in %s -- this script does not ship the corpus, "
              "point --audio at your own copy" % a.audio)
        return 1
    print("training %d tracks -> %s" % (len(paths), a.out), flush=True)
    t0 = time.time()
    r = build_trained_world(paths, a.out,
                            progress=lambda s: print("  [%5.0fs] %s"
                                                     % (time.time() - t0, s), flush=True))
    print("ok=%s in %.0fs" % (r.get("ok"), time.time() - t0), flush=True)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
