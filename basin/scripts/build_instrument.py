"""Build the instrument (M1 + M3) from the corpus folder.

    python scripts/build_instrument.py [--corpus DIR] [--config config.yaml]

Runs windowing/features, atlas, transfer operator + spectrum + basins (M1),
fits the memory kernel (M3), writes ``instrument.npz`` and the M1 acceptance
plots (``debug/terrain.png``, ``debug/spectrum.png``), and prints the
connectivity report.
"""

from __future__ import annotations

import argparse
import os

import _bootstrap as boot
import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--stems", default=None, choices=["none", "hpss"],
                    help="override features.stems (whole-mix vs HPSS split)")
    ap.add_argument("--out", default=None, help="instrument output path")
    args = ap.parse_args()

    from basin import features, atlas as atlas_mod, operator, kernel as kern
    from basin import debugplots, store

    cfg = boot.load_config(args.config)
    if args.stems is not None:
        cfg["stems"] = args.stems
    paths = boot.corpus_paths(args.corpus)
    if not paths:
        raise SystemExit(f"No audio in corpus folder {args.corpus or 'corpus/'}")
    print(f"[build] {len(paths)} tracks  stems={cfg.get('stems','none')}")

    print("[M1] windowing + features ...")
    corpus = features.build_corpus(paths, cfg)
    print(f"      {corpus.n_windows} windows, {corpus.features.shape[1]} dims")

    print("[M1] atlas (k-means charts + soft assignment) ...")
    atlas = atlas_mod.build_atlas(corpus.features, int(cfg["n_charts"]),
                                  int(cfg["top_memberships"]), seed=args.seed)
    print(f"      {atlas.n_charts} charts, bandwidth={atlas.bandwidth:.4f}")

    print("[M1] transfer operator + spectrum + basins ...")
    built = operator.build(atlas.memberships, corpus.track_bounds,
                           n_basins=cfg["n_basins"], seed=args.seed)
    sp = built.spectrum
    kinds = {}
    for m in sp.modes:
        kinds[m.kind] = kinds.get(m.kind, 0) + 1
    print(f"      macros={len(sp.macro_indices)} (gap_flagged={sp.gap_flagged})"
          f"  basins={built.n_basins}  eig-kinds={kinds}")

    # connectivity report
    cov = built.component_coverage
    print(f"[M1] largest SCC covers {cov*100:.1f}% of window-mass "
          f"({'OK' if cov >= 0.90 else 'ISLANDS — see LEDGER'})")
    if cov < 0.90:
        in_comp = built.largest_component
        island_tracks = []
        for tid, (s, e) in enumerate(corpus.track_bounds):
            charts = np.unique(np.argmax(atlas.memberships[s:e], axis=1))
            if not in_comp[charts].any():
                island_tracks.append(os.path.basename(corpus.track_paths[tid]))
        if island_tracks:
            print("      island tracks:", ", ".join(island_tracks))

    print("[M3] fitting memory kernel ...")
    kfit = kern.fit_kernel(atlas.memberships, sp.psi, corpus.track_bounds,
                           cfg, corpus.track_paths)
    print(f"      order={kfit.order}  cv_error={kfit.cv_error:.4g}")
    for i, (w, note) in enumerate(zip(kfit.omega_hz, kfit.tempo_check)):
        print(f"      mode {i}: f={w:.3f} Hz  [{note}]")

    print("[plots] terrain.png + spectrum.png ...")
    dbg = boot.debug_dir()
    debugplots.terrain(sp.psi, built.chart_basin, atlas.memberships,
                       corpus.track_bounds, os.path.join(dbg, "terrain.png"))
    debugplots.spectrum(sp.eigvals, sp.macro_indices,
                        os.path.join(dbg, "spectrum.png"))

    out = args.out or boot.instrument_path()
    store.save_instrument(out, corpus, atlas, built, kfit, cfg)
    print(f"[done] wrote {out}")


if __name__ == "__main__":
    main()
