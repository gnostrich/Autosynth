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
    ap.add_argument("--gamma", type=float, default=None,
                    help="wanderlust override (restlessness; default from config)")
    ap.add_argument("--couple", type=float, default=None,
                    help="multi-voice mutual-pull override (default from config)")
    ap.add_argument("--momentum", type=float, default=None,
                    help="momentum-orbit strength override (0 = off)")
    ap.add_argument("--instrument", default=None, help="instrument .npz path")
    ap.add_argument("--voices", default="mix",
                    help="comma list of concurrent voices from "
                         "{mix,harmonic,percussive}; e.g. harmonic,percussive")
    ap.add_argument("--mode", default="flow", choices=["flow", "hop"],
                    help="flow = corpus momentum + walk-as-field (emergent "
                         "transitions); hop = legacy per-step region sampling")
    args = ap.parse_args()

    from basin import store
    from basin.orbit import Orbit
    from basin.render import (GrainReader, render, render_voices,
                              render_flow, render_flow_voices)

    inst = store.load_instrument(args.instrument or boot.instrument_path())
    cfg = dict(inst["config"])
    if args.kappa is not None:
        cfg["kappa"] = args.kappa
    if args.gamma is not None:
        cfg["gamma"] = args.gamma
    if args.couple is not None:
        cfg["couple"] = args.couple
    if args.momentum is not None:
        cfg["momentum"] = args.momentum

    psi = inst["psi"]
    P = inst["P"]
    corpus = inst["corpus"]
    atlas = inst["atlas"]
    kernel = inst["kernel"]

    n_steps = int(round(args.minutes * 60.0 / float(cfg["step_s"])))
    knob = build_knob(args.macro, psi.shape[1], psi)
    voices = [v.strip() for v in args.voices.split(",") if v.strip()]

    print(f"[render] {args.minutes} min = {n_steps} steps, seed={args.seed}, "
          f"kappa={cfg['kappa']}, knob_nonzero={np.count_nonzero(knob)}, "
          f"voices={voices}, mode={args.mode}")

    shared: dict = {}
    modes = (inst["eigvals"], inst["eig_right"])
    if args.mode == "flow":
        orbits, readers = [], []
        for vi, stem in enumerate(voices):
            vseed = args.seed + 101 * vi
            orbits.append(Orbit(P, psi, cfg, knob_vector=knob, kernel=kernel,
                                seed=vseed, modes=modes))
            readers.append(GrainReader(corpus, atlas.memberships, cfg,
                                       seed=vseed, stem=stem,
                                       shared_cache=shared, psi=psi))
        if len(voices) == 1:
            audio = render_flow(orbits[0], readers[0], n_steps, cfg)
        else:
            audio = render_flow_voices(orbits, readers, n_steps, cfg)
        for vi, r in enumerate(readers):
            rate = r.n_flow_jumps / max(1, r.n_flow_steps)
            print(f"         voice {vi} ({voices[vi]}): jump rate "
                  f"{rate:.2%} ({r.n_flow_jumps} jumps/{r.n_flow_steps} steps)")
    elif voices == ["mix"]:
        orbit = Orbit(P, psi, cfg, knob_vector=knob, kernel=kernel,
                      seed=args.seed)
        states = orbit.run(n_steps)
        reader = GrainReader(corpus, atlas.memberships, cfg, seed=args.seed)
        audio = render(states, reader, cfg)
    else:
        # Polyphonic hop mode: independent walkers, per-step region sampling.
        states_list, readers = [], []
        for vi, stem in enumerate(voices):
            vseed = args.seed + 101 * vi
            orbit = Orbit(P, psi, cfg, knob_vector=knob, kernel=kernel,
                          seed=vseed)
            states_list.append(orbit.run(n_steps))
            readers.append(GrainReader(corpus, atlas.memberships, cfg,
                                       seed=vseed, stem=stem,
                                       shared_cache=shared))
            print(f"         voice {vi}: stem={stem} seed={vseed}")
        audio = render_voices(states_list, readers, cfg)

    out = args.out or boot.project_dir() + "/set.wav"
    # 16-bit PCM — universally playable. float64 WAV (soundfile's default for a
    # float64 array) is silently unplayable in many players/browsers.
    sf.write(out, audio, int(cfg["sr"]), subtype="PCM_16")
    print(f"[done] wrote {out} ({len(audio)/int(cfg['sr']):.1f}s)")


if __name__ == "__main__":
    main()
