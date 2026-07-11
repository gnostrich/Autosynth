"""Extract the steering of a given set, and optionally replay it here.

    python scripts/extract_arc.py SET.mp3 [SET_part2.mp3 ...]
        [--instrument PATH] [--out arc.npz]
        [--replay out.flac --minutes 12 --peak 1.5 --seed 5]

Projects the given audio onto the instrument's landscape (same windows,
same features, same whitening as the corpus), separates its motion into
corpus-flow + innovation, and prints/saves the innovation as a lean
schedule over the emergent directions — the set's arc as a knob journey.

--replay renders a NEW set on THIS instrument steered by the extracted
schedule (time-normalized; amplitude scaled so the peak lean is --peak
sigma — a performance gain, printed, since extraction compresses
amplitude: innovation only registers steering while the walk fights the
flow, not once it has arrived).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402

from basin import store, operator, setmap  # noqa: E402
from scripts._bootstrap import instrument_path  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", nargs="+")
    ap.add_argument("--instrument", default=None)
    ap.add_argument("--out", default="renders/extracted_arc.npz")
    ap.add_argument("--replay", default=None)
    ap.add_argument("--minutes", type=float, default=12.0)
    ap.add_argument("--peak", type=float, default=1.5)
    ap.add_argument("--seed", type=int, default=5)
    args = ap.parse_args()

    inst = store.load_instrument(args.instrument or instrument_path())
    corpus, atlas = inst["corpus"], inst["atlas"]
    psi, _ = operator.full_psi(inst["eigvals"], inst["eig_right"])
    cfg = dict(inst["config"])

    print("projecting the set onto the landscape ...")
    parts = [setmap.project_set(p, corpus, atlas, psi, cfg)
             for p in args.audio]
    proj = parts[0]
    for p in parts[1:]:
        for k in ("a", "memberships", "strides", "starts", "raw"):
            proj[k] = np.concatenate([proj[k], p[k]])

    wb = np.asarray(atlas.memberships.argmax(axis=1)).ravel()
    H = corpus.handles
    runs, cur, r = [], None, 0
    for w in range(len(H)):
        same = w > 0 and H[w].track_id == H[w - 1].track_id
        if same and wb[w] == cur:
            r += 1
        else:
            if r:
                runs.append(r)
            cur, r = wb[w], 1
    mean_run = float(np.mean(runs)) if runs else 4.0

    arc = setmap.extract_arc(proj, inst["P"], psi, mean_run)
    lean = arc["lean"]
    T = len(lean)
    strongest = np.argsort(-np.abs(lean).mean(0))[:6]
    print(f"\n{T} windows; strongest steered directions: "
          f"{[int(k) for k in strongest]}")
    print("lean per 10% of the set (strongest 4):")
    for d in range(10):
        seg = lean[int(T * d / 10):int(T * (d + 1) / 10)]
        print(f"  {d*10:3d}-{d*10+10:3d}%: " + "  ".join(
            f"f{int(k)}:{seg[:, k].mean():+.2f}" for k in strongest[:4]))
    np.savez(args.out, lean=lean, strides=proj["strides"],
             a=proj["a"])
    print(f"saved -> {args.out}")

    if args.replay:
        from basin.orbit import Orbit
        from basin.render import GrainReader, render_flow
        import soundfile as sf
        P2 = operator.build_pair_operator(atlas.memberships,
                                          corpus.track_bounds)
        cfg2 = dict(cfg, kappa=0.0, momentum=0.0)
        cfg2["basin_halflife_steps"] = float(np.median(
            [e - s for (s, e) in corpus.track_bounds]))
        sr = int(cfg["sr"])
        o = Orbit(inst["P"], psi, cfg2, kernel=None, seed=args.seed,
                  basins=inst["chart_basin"], P2=P2)
        rd = GrainReader(corpus, atlas.memberships, cfg2, seed=args.seed,
                         stem="mix", shared_cache={}, psi=psi)
        sched = lean / (np.abs(lean).max() + 1e-12) * args.peak
        print(f"replaying: peak lean {args.peak} sigma "
              f"(extraction gain, a performance choice)")
        total = int(args.minutes * 60 * sr)
        est = rd.median_stride()
        # drive the orbit's knob from the time-normalized schedule
        out_chunks = []
        t = 0
        import numpy as _np
        from basin.render import _equal_power_fades
        xfade = int(round(float(cfg2["crossfade_s"]) * sr))
        eq_in, _ = _equal_power_fades(xfade)
        lin = _np.linspace(0, 1, xfade, endpoint=False)[:, None]
        cap = int(total * 1.1) + 8 * xfade
        out = _np.zeros((cap, 2), dtype=_np.float32)
        i = 0
        while t < total:
            frac = t / total
            o.knob = sched[min(int(frac * T), T - 1)]
            st = o.step()
            w = rd.sample_flow(st.a, st.m_full if st.m_full is not None
                               else st.m)
            stride = rd.native_stride(w)
            glen = stride + xfade
            if t + glen < cap:
                g = rd.grain_audio(w, glen).copy()
                if i > 0:
                    g[:xfade] *= eq_in if rd.last_jump else lin
                g[-xfade:] *= (1 - lin)
                out[t:t + glen] += g
            t += stride
            i += 1
        out = out[:total + xfade]
        pk = float(np.max(np.abs(out)) + 1e-9)
        if pk > 0.95:
            out *= 0.95 / pk
        sf.write(args.replay, out, sr)
        print(f"replayed set -> {args.replay}")


if __name__ == "__main__":
    main()
