"""Render a set by orbiting the instrument (M2, optionally with M3 memory).

    python scripts/render_set.py --minutes 3 --seed 0 [--out set.wav]
        [--macro I VALUE ...]   knob bias on macro I (in σ units)
        [--kappa K]             memory strength (default: config; 0 = pure M2)

The knob test (M2 acceptance): render macro-1 bias +2 vs −2 from the same
seed and listen for a consistent, audible difference.
"""

from __future__ import annotations

import argparse

import _bootstrap as boot
import numpy as np
import soundfile as sf


def build_knob(macro_args, n_macros, psi):
    """Knob vector in macro (diffusion) coords; σ units scaled by ψ spread."""
    knob = np.zeros(n_macros)
    if not macro_args:
        return knob
    sigma = psi.std(0) + 1e-9
    for i in range(0, len(macro_args), 2):
        idx, val = int(macro_args[i]), float(macro_args[i + 1])
        if 0 <= idx < n_macros:
            knob[idx] = val * sigma[idx]
    return knob


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--macro", nargs="*", default=[],
                    help="pairs: MACRO_INDEX VALUE_IN_SIGMA ...")
    ap.add_argument("--kappa", type=float, default=None)
    args = ap.parse_args()

    from basin import store
    from basin.orbit import Orbit
    from basin.render import GrainReader, render

    inst = store.load_instrument(boot.instrument_path())
    cfg = dict(inst["config"])
    if args.kappa is not None:
        cfg["kappa"] = args.kappa

    psi = inst["psi"]
    P = inst["P"]
    corpus = inst["corpus"]
    atlas = inst["atlas"]
    kernel = inst["kernel"]

    n_steps = int(round(args.minutes * 60.0 / float(cfg["step_s"])))
    knob = build_knob(args.macro, psi.shape[1], psi)

    print(f"[render] {args.minutes} min = {n_steps} steps, seed={args.seed}, "
          f"kappa={cfg['kappa']}, knob_nonzero={np.count_nonzero(knob)}")

    orbit = Orbit(P, psi, cfg, knob_vector=knob, kernel=kernel, seed=args.seed)
    states = orbit.run(n_steps)

    reader = GrainReader(corpus, atlas.memberships, cfg, seed=args.seed)
    audio = render(states, reader, cfg)

    out = args.out or boot.project_dir() + "/set.wav"
    sf.write(out, audio, int(cfg["sr"]))
    print(f"[done] wrote {out} ({len(audio)/int(cfg['sr']):.1f}s)")


if __name__ == "__main__":
    main()
