#!/usr/bin/env python3
"""Measure the DEPLOYED train + playback peak RSS — the honest capacity number.

Why this exists: papers/CAPACITY_STUDY.md §2 originally measured `cap_single.py`,
whose sequence materialises the audio bank (`build_bank`) INLINE during the train,
while the ingest/STFT transients are still resident -> a ~3.5-4x-bank peak. The
DEPLOYED path is different: `cloud.companion.train_local.build_trained_world` (what
`/api/train` calls) never builds the bank; the bank is built LAZILY at first playback
(`StreamPlayer.produce_one_bar`). So the real service has TWO smaller peaks, not one
big one. This tool measures BOTH on the exact deployed code, so the capacity claim is
reproducible rather than modelled.

Run (from repo root):
    python3 cloud/tools/train_peak_verify.py <dir-of-wavs> [--dtype float16|float32]

The corpus dir is any folder of audio files (the operator's own audio is NOT
committed; point this at demo assets or a local corpus). Prints train peak, playback
peak, and the resident bank delta. Read-only w.r.t. the engine; no world is shared.
"""
import os
import sys
import glob
import time
import threading
import argparse


def _rss_mb() -> float:
    for line in open("/proc/self/status"):
        if line.startswith("VmRSS"):
            return int(line.split()[1]) / 1024
    return 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus_dir", help="folder of audio files to train on")
    ap.add_argument("--dtype", default="float16", choices=["float16", "float32"],
                    help="ETS_BANK_DTYPE for the playback bank (default float16)")
    ap.add_argument("--out", default=None, help="where to write the .etsworld")
    args = ap.parse_args()

    os.environ["ETS_BANK_DTYPE"] = args.dtype
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # arch-v6 engine first on the path, exactly like the companion's -m import order.
    sys.path.insert(0, os.path.join(root, "architecture-v6"))
    sys.path.insert(0, root)

    wavs = sorted(glob.glob(os.path.join(args.corpus_dir, "*")))
    wavs = [w for w in wavs if w.lower().endswith((".wav", ".flac", ".mp3", ".ogg", ".m4a"))]
    if not wavs:
        print("no audio files in %s" % args.corpus_dir)
        return 2
    out = args.out or os.path.join(args.corpus_dir, "_train_peak_probe.etsworld")

    peak = [0.0]
    stop = [False]

    def _mon():
        while not stop[0]:
            r = _rss_mb()
            if r > peak[0]:
                peak[0] = r
            time.sleep(0.05)

    threading.Thread(target=_mon, daemon=True).start()

    from cloud.companion.train_local import build_trained_world
    from cloud.companion.engine_bridge import StreamPlayer

    print("=== DEPLOYED train+play peak (%d files, dtype=%s) ===" % (len(wavs), args.dtype))
    t0 = time.time()
    res = build_trained_world(wavs, out, cloud_url="inproc", seed=0, sweeps=8)
    train_peak = peak[0]
    print("TRAIN  peak RSS = %.0f MB  (build_trained_world -> the /api/train path; NO bank built here)"
          % train_peak)

    p = StreamPlayer(out, is_trained=True)
    before = _rss_mb()
    p.produce_one_bar()          # materialises the lazy audio bank
    for _ in range(3):
        p.produce_one_bar()
    play_peak = peak[0]
    stop[0] = True
    print("PLAY   peak RSS = %.0f MB  (lazy bank materialised at first produce_one_bar)" % play_peak)
    print("bank delta      = %.0f MB  (playback resident - pre-bank)" % (_rss_mb() - before))
    print("train ok=%s  M=%s  elapsed=%.0fs" %
          (res.get("ok"), res.get("M", "?"), time.time() - t0))
    try:
        os.remove(out)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
