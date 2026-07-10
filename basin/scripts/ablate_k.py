"""M3 acceptance — the falsifiability gate: kernel on vs off.

    python scripts/ablate_k.py [--minutes 3] [--pairs 5]

Same seed, same knobs, K-on vs K-off; renders per seed pair. Objective metric:
autocorrelation of the output's onset-strength envelope at the fitted kernel
periods ω_j, compared K-on vs K-off vs corpus ground truth. K-on should move
*toward* the corpus. Results are printed and appended to LEDGER.md; the blind
A/B subjective notes are filled in by a human listener.

Honest outcomes, all acceptable:
  (a) K restores phrasing (moves toward corpus)  → theory load-bearing
  (b) no measurable difference                    → a result, pivot needed
  (c) K destabilizes                              → clamp radius / lower order
"""

from __future__ import annotations

import argparse
import os

import _bootstrap as boot
import numpy as np
import soundfile as sf


def onset_autocorr_at(audio: np.ndarray, sr: int, hop: int,
                      periods_s: list) -> np.ndarray:
    """Normalized onset-envelope autocorrelation sampled at ``periods_s``."""
    import librosa
    env = librosa.onset.onset_strength(y=audio.astype(float), sr=sr,
                                       hop_length=hop)
    env = env - env.mean()
    n = len(env)
    if n < 4 or np.allclose(env, 0):
        return np.zeros(len(periods_s))
    full = np.correlate(env, env, mode="full")[n - 1:]
    full = full / (full[0] + 1e-12)
    vals = []
    for T in periods_s:
        lag = T * sr / hop
        if lag < 1 or lag >= n - 1:
            vals.append(0.0)
            continue
        lo = int(np.floor(lag))
        frac = lag - lo
        vals.append(float((1 - frac) * full[lo] + frac * full[lo + 1]))
    return np.asarray(vals)


def corpus_reference(corpus, sr: int, hop: int, periods_s: list) -> np.ndarray:
    """Ground-truth onset autocorr at the fitted periods, averaged over tracks."""
    import librosa
    vals = []
    for p in corpus.track_paths:
        y, _ = librosa.load(p, sr=sr, mono=True)
        vals.append(onset_autocorr_at(y, sr, hop, periods_s))
    return np.mean(vals, axis=0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--pairs", type=int, default=5)
    ap.add_argument("--clamp", action="store_true",
                    help="clamp kernel spectral radius (outcome-(c) guard)")
    ap.add_argument("--instrument", default=None, help="instrument .npz path")
    args = ap.parse_args()

    from basin import store
    from basin.orbit import Orbit
    from basin.render import GrainReader, render

    inst = store.load_instrument(args.instrument or boot.instrument_path())
    cfg = dict(inst["config"])
    psi, P = inst["psi"], inst["P"]
    corpus, atlas, kernel = inst["corpus"], inst["atlas"], inst["kernel"]
    sr, hop = int(cfg["sr"]), int(cfg["hop"])

    if kernel is None or kernel.order == 0 or not kernel.omega_hz:
        raise SystemExit("Instrument has no usable kernel; rebuild first.")
    if args.clamp:
        kernel.clamp_spectral_radius()

    # Sample only at *measurable* fitted periods: a period must be at least a
    # couple of steps and short enough that the autocorrelation of a render of
    # this length is defined at that lag. Overdamped modes (ω≈0 → period → ∞)
    # carry no phrase-scale oscillation and are reported, not scored.
    render_s = args.minutes * 60.0
    step_s = float(cfg["step_s"])
    all_periods = [1.0 / f if f > 1e-6 else float("inf") for f in kernel.omega_hz]
    measurable = sorted({round(T, 2) for T in all_periods
                         if 2 * step_s <= T <= 0.5 * render_s})
    n_overdamped = sum(1 for T in all_periods if T > 0.5 * render_s)
    periods_s = measurable
    print(f"[ablate] {len(kernel.omega_hz)} kernel modes: "
          f"{len(periods_s)} measurable, {n_overdamped} overdamped/too-slow")
    print("[ablate] measured periods (s):",
          ", ".join(f"{T:.2f}" for T in periods_s) or "(none)")
    if not periods_s:
        raise SystemExit("No kernel mode has a measurable phrase-scale period; "
                         "the objective metric cannot discriminate — report in "
                         "LEDGER as outcome (b).")
    ref = corpus_reference(corpus, sr, hop, periods_s)
    print("[ablate] corpus ground-truth autocorr:", np.round(ref, 4))

    n_steps = int(round(args.minutes * 60.0 / float(cfg["step_s"])))
    on_all, off_all = [], []
    unstable = 0
    for pair in range(args.pairs):
        seed = pair
        rows = {}
        for label, kap, ker in (("off", 0.0, None), ("on", float(cfg["kappa"]), kernel)):
            c = dict(cfg, kappa=kap)
            orbit = Orbit(P, psi, c, kernel=ker, seed=seed)
            states = orbit.run(n_steps)
            reader = GrainReader(corpus, atlas.memberships, c, seed=seed)
            audio = render(states, reader, c)
            if not np.all(np.isfinite(audio)):
                unstable += 1
                audio = np.nan_to_num(audio)
            sf.write(os.path.join(boot.project_dir(),
                                  f"ablate_{label}_seed{seed}.wav"), audio, sr)
            rows[label] = onset_autocorr_at(audio, sr, hop, periods_s)
        on_all.append(rows["on"])
        off_all.append(rows["off"])
        d_on = np.abs(rows["on"] - ref).mean()
        d_off = np.abs(rows["off"] - ref).mean()
        print(f"  seed {seed}: |on−corpus|={d_on:.4f}  |off−corpus|={d_off:.4f}"
              f"  {'K helps' if d_on < d_off else 'K neutral/hurts'}")

    on_m = np.mean(on_all, axis=0)
    off_m = np.mean(off_all, axis=0)
    d_on = float(np.abs(on_m - ref).mean())
    d_off = float(np.abs(off_m - ref).mean())
    verdict = ("(a) K moves toward corpus — theory load-bearing"
               if d_on < d_off - 1e-4 else
               "(b) no clear objective difference — a result, not a failure")
    if unstable:
        verdict = "(c) K destabilized some renders — consider --clamp / lower order"

    report = (
        "\n## M3 ablation (auto-appended)\n"
        f"- renders: {args.pairs} seed pairs × {args.minutes} min, kappa={cfg['kappa']}\n"
        f"- measured periods (s): {[round(float(T),2) for T in periods_s]}"
        f"  ({n_overdamped} overdamped modes excluded)\n"
        f"- corpus autocorr:  {np.round(ref,4).tolist()}\n"
        f"- K-off autocorr:   {np.round(off_m,4).tolist()}  (mean |Δ|={d_off:.4f})\n"
        f"- K-on autocorr:    {np.round(on_m,4).tolist()}  (mean |Δ|={d_on:.4f})\n"
        f"- objective verdict: {verdict}\n"
        f"- subjective blind A/B notes: _TODO human listener_\n"
    )
    print(report)
    ledger = os.path.join(boot.project_dir(), "LEDGER.md")
    with open(ledger, "a") as f:
        f.write(report)
    print(f"[done] appended objective result to {ledger}")


if __name__ == "__main__":
    main()
