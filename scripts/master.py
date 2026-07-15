#!/usr/bin/env python3
"""Master an already-rendered tape (EXTERNAL output layer — see ets/render/master.py).

Standalone so any render — batch (generate_batch --master also does it inline) or
engine offline — can be mastered after the fact without touching the render path.

    python scripts/master.py in.flac out.flac [--lufs -14]
"""
from __future__ import annotations
import argparse
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, __file__.rsplit("/", 2)[0])
from ets.render.master import master


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--lufs", type=float, default=-14.0)
    args = ap.parse_args()

    y, sr = sf.read(args.inp)
    if y.ndim > 1:
        y = y.mean(axis=1)
    ym = master(y, sr, target_lufs=args.lufs)
    sf.write(args.out, ym, sr)

    w = 25 * sr
    def spread(a):
        r = np.array([np.sqrt(np.mean(a[i:i + w] ** 2))
                      for i in range(0, len(a) - w, w)])
        r = r[r > 1e-5]
        return 20 * np.log10(r.max() / r.min()) if len(r) else 0.0
    print(f"mastered {args.inp} -> {args.out}")
    print(f"  loud-to-quiet spread: {spread(y):.1f} dB -> {spread(ym):.1f} dB  "
          f"(target {args.lufs} LUFS)")


if __name__ == "__main__":
    main()
