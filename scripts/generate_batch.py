"""Batch (non-causal) first-sample generator (connector: THE TAPE PORT).

Settles a ``--seconds`` output tape from the 20 cached ingested tracks and renders
it to audio + a provenance sidecar. This is the reduced-form writer for the
"lanes constant" case with u=0 (no tilt): the output tape is the (N+1)-th
track-typed boundary node, its per-slot role occupancy settled in the field of the
FROZEN anchors to a Lyapunov F-descent certificate, then read out as the render's
existing ``Schedule`` (no decoder, no static keymap).

PROVISIONAL: LAMBDA in ets/functional/f.py is the pre-calibration weight set
(step d not yet landed). The arrangement QUALITY is not meaningful until those
weights arrive; LAMBDA is read LIVE, so this same script produces the calibrated
output the moment step d commits. What IS meaningful now: the machinery settles to
an F-certificate and renders a valid, fully provenance-traced schedule.

Data (cache + corpus) live in the MAIN checkout and are read by absolute path.

Usage:
    python3 scripts/generate_batch.py --seconds 60 --out samples/settle_first.flac
    python3 scripts/generate_batch.py --seconds 420 --out samples/batch_smoke.flac
"""
from __future__ import annotations
import argparse, glob, json, os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAIN = "/home/user/Geodesic-Mixing"
CACHE = os.path.join(MAIN, "cache/ingest")
CORPUS = os.path.join(MAIN, "corpus")


def _corpus_paths():
    return sorted(glob.glob(os.path.join(CORPUS, "*.mp3")))


def load_tracks():
    from ets.ingestion.pipeline import load
    paths = sorted(glob.glob(os.path.join(CACHE, "track_*.npz")))
    if not paths:
        sys.exit(f"no cached tracks under {CACHE} (run ingestion in the main checkout)")
    return [load(p) for p in paths]


def source_bank_for(schedule, tracks):
    """Materialize the real source units the schedule references (spec §11 sources).
    Loads ONLY the tracks actually placed, each from its corpus audio."""
    from ets.render import load_source_units, SourceUnitBank
    import librosa
    corpus = _corpus_paths()
    used = sorted(set(int(t) for t in schedule.placements["src_track"]))
    by_id = {t.track_id: t for t in tracks}
    bank = SourceUnitBank(sr=int(tracks[0].sr))
    for tid in used:
        track = by_id[tid]
        if tid >= len(corpus):
            sys.exit(f"track_id {tid} has no paired corpus mp3")
        y, _ = librosa.load(corpus[tid], sr=track.sr, mono=True)
        tb = load_source_units(track, y)
        for key in list(tb._units.keys()):
            bank.add(tb._units[key])
    return bank, used


def bar_frame_and_mass(sched, s_phase):
    """Per-bar gauge frame + settled mass, read off the realized Schedule
    (SCHEDULE-side quantities only; see gauge_trace() for the typing note).

    For bar b the frame is the Gauge of the section governing the bar's
    downbeat slot (transpose in semitones on Z_12; phase_shift in slot units on
    the S-slot metrical circle). The bar's settled mass is sum(mass^2) over the
    bar's placements — EXACT on the schedule (registry amendment
    writer-settled-mass-approximation-declared: Sigma mass^2 = settled slot
    mass to machine precision; the rendered-tape energy is only approximate in
    fixed instruments and is deliberately NOT read)."""
    S = int(s_phase)
    n_bars = sched.n_out_slots // S
    transpose = np.zeros(n_bars)
    phase = np.zeros(n_bars)
    mass = np.zeros(n_bars)
    p = sched.placements
    for b in range(n_bars):
        down = b * S
        sec = next(s for s in sched.sections
                   if s.out_slot_start <= down < s.out_slot_end)
        transpose[b] = float(sec.gauge.transpose_semitones)
        phase[b] = float(sec.gauge.phase_shift)
        in_bar = (p["out_slot"] >= down) & (p["out_slot"] < down + S)
        mass[b] = float(np.sum(p["mass"][in_bar] ** 2))
    return transpose, phase, mass


def gauge_trace(sched, O, s_phase):
    """STAGE-0 shadow drift-meter split (directive-v1 feature 2): the per-bar
    trace dict for the sidecar. READ-ONLY (I-5/I-14): computed from quantities
    the machine already produced; nothing feeds back. Zero behavior change —
    the audio path never sees this (H-3 test: meters computed vs stubbed =>
    bit-identical audio)."""
    from ets.meters import drift_cv, gauge_slide, loop_g

    S = int(s_phase)
    transpose, phase, mass = bar_frame_and_mass(sched, S)
    n_bars = len(transpose)
    conflated = drift_cv(transpose, phase, phase_modulus=S)   # existing jack
    slide = gauge_slide(transpose, phase, phase_modulus=S, mass=mass)
    lg = loop_g(np.asarray(O)[:, :n_bars * S], S)             # committed bars
    return {
        "instrument": "gauge drift-meter split, STAGE 0 shadow "
                      "(directive-v1 feature 2)",
        "registry_id": "meter-split-gauge-slide-loop-2026-07-15",
        "shadow": True,
        "reads": {
            "slide[g]": "SCHEDULE-side: realized per-section Gauge "
                        "(transpose_semitones on Z_12; phase_shift in slot "
                        "units on the S-slot circle) sampled at each bar "
                        "downbeat; bar masses = sum(mass^2) of the bar's "
                        "placements (exact on the schedule per registry "
                        "writer-settled-mass-approximation-declared).",
            "loop[g]": "SETTLEMENT-side: settled tape occupancy O (the tape "
                       "node's coupling to the anchor star) restricted to "
                       "committed complete bars.",
            "tape_side": "NOTHING — no meter reads rendered audio; rendered "
                         "energies are approximate-in-fixed-instruments per "
                         "the declared amendment and are not meter inputs.",
        },
        "estimators": {
            "slide_key_disp": "composed frame increments reduced to the Z_12 "
                              "minimal signed representative in [-6,6)",
            "slide_phase_charge": "1 - |sum_{tau<=t} m e^{i2pi x}| / sum m "
                                  "over running displacements-from-home x "
                                  "(F's phase-charge quotient, restated)",
            "loop_g": "antisymmetrized committed-cycle defect of star-"
                      "factored bar couplings (G2 loop_defect transplant)",
        },
        "n_bars": int(n_bars),
        "s_phase": S,
        "key_cardinality": 12,
        "per_bar": {
            "bar_settled_mass": mass.tolist(),
            "slide_key_disp": slide.key.per_bar.tolist(),
            "slide_phase_charge": slide.phase.per_bar.tolist(),
            "loop_g": lg.tolist(),
            "conflated_drift_key_running": conflated.key.running.tolist(),
            "conflated_drift_phase_running": conflated.phase.running.tolist(),
        },
        "conflated_totals": conflated.as_dict(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=420.0)
    ap.add_argument("--out", type=str, default="samples/batch_smoke.flac")
    ap.add_argument("--sigma", type=float, default=None,
                    help="frozen corpus affinity scale; default = this set's median")
    ap.add_argument("--max-iter", type=int, default=800)
    args = ap.parse_args()

    import soundfile as sf
    from ets.writer import build_world_from_tracks, generate_batch
    from ets.render import render, RENDER_STRETCH_BACKEND

    out_path = args.out if os.path.isabs(args.out) else os.path.join(MAIN, args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    t0 = time.time()
    print(f"[1/5] loading cached tracks from {CACHE} ...")
    tracks = load_tracks()
    print(f"      {len(tracks)} tracks, sr={tracks[0].sr}")

    print("[2/5] freezing world (prototypes -> self-sized anchors -> role index) ...")
    world = build_world_from_tracks(tracks, sigma=args.sigma)
    print(f"      anchors M={world.M}  build_world={json.dumps(world.info)}")
    print(f"      out_tatum_len={world.out_tatum_len} samples "
          f"(~{world.out_tatum_len/world.sr*1000:.0f} ms)")

    print(f"[3/5] batch settlement of a {args.seconds:.0f}s tape (u=0) ...")
    out = generate_batch(world, seconds=args.seconds, max_iter=args.max_iter)
    res = out["settle"]
    tr = np.asarray(res.trace)
    n_dec = int(np.sum(np.diff(tr) < -1e-12))
    n_inc = int(np.sum(np.diff(tr) > 1e-9))
    print(f"      F-descent: first={tr[0]:.6f} last={tr[-1]:.6f}  "
          f"steps={len(tr)} decreases={n_dec} increases={n_inc}")
    print(f"      certificate: monotone={res.monotone} converged={res.converged} "
          f"n_iter={res.n_iter}")
    print(f"      terms_final={json.dumps({k: round(float(v),6) for k,v in res.terms_final.items()})}")
    print(f"      realize={json.dumps(out['realize'])}")
    sched = out["schedule"]

    print("[4/5] materializing source units + rendering (I-11 applies, never chooses) ...")
    bank, used = source_bank_for(sched, tracks)
    print(f"      source bank: {len(bank)} units from tracks {used}")
    audio, prov = render(sched, bank)
    prov.assert_complete(audio)                       # I-12: every sample traced
    peak = float(np.max(np.abs(audio))) + 1e-12
    audio_n = 0.97 * audio / peak                     # peak-normalize for listening

    print(f"[5/5] writing {out_path} ...")
    sf.write(out_path, audio_n.astype(np.float32), int(sched.sr), format="FLAC")
    side = out_path.rsplit(".", 1)[0] + ".provenance.json"
    prov_summary = {
        "provisional": True,
        "note": "u=0 (no tilt), lanes constant; LAMBDA pre-calibration (step d pending). "
                "Arrangement quality not meaningful yet; machinery + provenance are.",
        "render_backend": RENDER_STRETCH_BACKEND,
        "sr": int(sched.sr),
        "seconds": args.seconds,
        "n_output_slots": int(sched.n_out_slots),
        "n_samples": int(len(audio)),
        "n_placements": int(len(sched.placements)),
        "n_provenance_segments": int(len(prov.segments)),
        "provenance_complete": True,
        "tracks_used": used,
        "anchors_M": world.M,
        "world_info": world.info,
        "F_trace_first": float(tr[0]),
        "F_trace_last": float(tr[-1]),
        "F_monotone": bool(res.monotone),
        "F_converged": bool(res.converged),
        "F_n_iter": int(res.n_iter),
        "terms_final": {k: float(v) for k, v in res.terms_final.items()},
        "LAMBDA_live": dict(__import__("ets.functional.f", fromlist=["LAMBDA"]).LAMBDA),
    }
    with open(side, "w") as f:
        json.dump(prov_summary, f, indent=2)

    # STAGE-0 shadow drift-meter split sidecar (read-only; audio unchanged).
    trace = gauge_trace(sched, out["settle"].O, out["tape"].grid.s_phase)
    trace_path = out_path.rsplit(".", 1)[0] + ".gauge_trace.json"
    with open(trace_path, "w") as f:
        json.dump(trace, f, indent=2)
    print(f"      gauge trace (shadow drift split) -> {trace_path}")
    dur = len(audio) / sched.sr
    print(f"DONE in {time.time()-t0:.1f}s: {out_path}  ({dur:.1f}s audio, "
          f"{len(sched.placements)} placements, provenance -> {side})")


if __name__ == "__main__":
    main()
