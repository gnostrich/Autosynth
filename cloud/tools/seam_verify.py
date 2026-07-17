"""Standalone train->YOUR-corpus seam proof (own process, arch-v6 first).

Mirrors instrument_verify.py's pin discipline. Runs the REAL BUILD seam end to end:
synthesize 2 short WAVs -> local ingest -> stage-3 -> CLOUD anchor-fit (LIVE Railway
if the token is present, else inproc) -> verify -> local build_index -> a verified,
CS-clean trained .etsworld referencing the user's LOCAL audio.

It asserts the HONEST state around the σ_φ PLAY WALL (surfaced, not patched):
  [2] CS-1: the exact bytes handed to post_job decode to ONLY stage-3 (no
      track/audio/provenance) — the whole point of the offload.
  [3] the trained world file is a VALID .etsworld and references the user's audio.
  [4] loading it into StreamPlayer RAISES `STALE CALIBRATION` — the wall is REAL:
      a freshly-trained world's hash != the demo's, so the registered σ_φ artifact
      is REFUSED (the engine will not lean on a foreign scale; λ is never invented).
  [5] the calibrated DEMO world still constructs + renders ONE capped bar — the
      companion keeps playing honestly while the trained world's PLAY is blocked.

Render is slow in this sandbox (bank warmup + one bar); that's expected — on real
hardware it's realtime. What matters here is the SEAM, the CS wall, and the honest
σ_φ block, not speed.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = "/home/user/Geodesic-Mixing"
sys.path.insert(0, ROOT)                          # for cloud.*
sys.path.insert(0, ROOT + "/architecture-v6")     # ets = engine-v1 + live cap (WINS)

import numpy as np
import soundfile as sf


def log(m):
    print(m, flush=True)


def _synth_wav(path, sr=44100, seconds=6.0, bpm=120.0, seed=0):
    """A rhythmic, tonal test clip: periodic transients (so beat detection finds a
    grid) over a couple of drifting tones. Not music — just an ingestable signal."""
    rng = np.random.default_rng(seed)
    n = int(sr * seconds)
    t = np.arange(n) / sr
    y = 0.15 * np.sin(2 * np.pi * (110.0 + 20.0 * seed) * t)
    y += 0.10 * np.sin(2 * np.pi * (220.0 + 33.0 * seed) * t)
    # transients on the beat
    step = int(sr * 60.0 / bpm)
    env = np.exp(-np.linspace(0, 40, step))
    for start in range(0, n - step, step):
        click = env * rng.standard_normal(step) * 0.4
        y[start:start + step] += click
    y += 0.01 * rng.standard_normal(n)
    y = 0.9 * y / (np.max(np.abs(y)) + 1e-9)
    sf.write(path, y.astype(np.float32), sr)
    return path


def main():
    tok = Path("/tmp/claude-0/-home-user-Geodesic-Mixing/"
               "7598b5c5-271e-5d2e-8faf-47a6f11f40d7/scratchpad/ets_train_token.txt")
    if tok.exists():
        os.environ["ETS_TRAIN_TOKEN"] = tok.read_text().strip()
        cloud_url = "https://geodesic-mixing-production.up.railway.app"
        log(f"[cloud] LIVE Railway: {cloud_url}")
    else:
        cloud_url = "inproc"
        log("[cloud] token absent -> inproc stand-in")

    work = Path(tempfile.mkdtemp(prefix="ets_seam_"))
    wavs = [_synth_wav(str(work / f"clip{i}.wav"), seed=i, bpm=120 + 8 * i)
            for i in range(2)]
    log(f"[0] synthesized {len(wavs)} WAVs under {work}")

    # --- CS-1 capture: wrap post_job to record the EXACT wire bytes ------------
    import cloud.client.cli as cli
    from cloud.common import decode_job
    real_post = cli.post_job
    captured = {}

    def _cap(job_bytes, service):
        captured["bytes"] = job_bytes
        return real_post(job_bytes, service)

    cli.post_job = _cap

    # --- run the FULL seam -----------------------------------------------------
    from cloud.companion.train_local import build_trained_world
    out_path = str(work / "trained.etsworld")
    log("[1] running the seam: ingest -> stage-3 -> cloud fit -> build_index -> save…")
    res = build_trained_world(wavs, out_path=out_path, cloud_url=cloud_url,
                              seed=0, sweeps=3, sigma=None)
    assert res["ok"] and res["is_trained"] is True, res
    assert Path(out_path).exists(), "no trained .etsworld produced"
    log(f"    receipt: M={int(res['receipt']['n_anchors'])} anchors, "
        f"F_final={float(res['receipt']['F_final']):.6g}; world -> {out_path}")

    # --- CS-1 assertion: ONLY stage-3 crossed the wire -------------------------
    log("[2] CS-1: assert ONLY stage-3 crossed the wire (no track/audio/provenance)…")
    assert "bytes" in captured, "post_job was never called"
    with np.load(__import__("io").BytesIO(captured["bytes"]), allow_pickle=False) as z:
        wire_keys = list(z.files)
    STAGE3 = {"cost", "mass", "slot_hist", "band_profile"}
    for k in wire_keys:
        if k in ("__ets_stage3__", "n_protos"):
            continue
        if k.startswith("param."):
            continue
        assert k[:1] == "p" and "." in k and k.split(".", 1)[0][1:].isdigit(), \
            f"unexpected wire key: {k}"
        assert k.split(".", 1)[1] in STAGE3, f"off-whitelist field on wire: {k}"
    for bad in ("audio", "track", "prov", "src_start", "src_end", "unit", "recipe"):
        assert not any(bad in k.lower() for k in wire_keys), \
            f"{bad!r} reached the wire: {wire_keys}"
    # decode_job (service-side inverse) sees ONLY prototypes + params — nothing else
    protos_dec, params_dec = decode_job(captured["bytes"])
    assert protos_dec and set(params_dec) <= {"seed", "sweeps", "sigma"}, params_dec
    log(f"    wire keys are stage-3 only; decode_job -> {len(protos_dec)} protos, "
        f"params={sorted(params_dec)}")

    # --- the trained world file is valid + references the user's audio ---------
    log("[3] trained world is a valid .etsworld referencing the USER'S local audio…")
    from ets.engine.worldfile import load_world
    wf = load_world(out_path)
    assert wf.sources["kind"] == "corpus", wf.sources
    assert set(wf.sources["paths"].values()) == set(wavs), \
        "trained world must reference the USER'S local audio, nothing else"
    log(f"    world_hash={wf.world_hash[:12]} sources->{sorted(wf.sources['paths'])}")

    # --- the σ_φ PLAY WALL is REAL: load RAISES STALE (no invented scale) -------
    log("[4] loading into StreamPlayer must RAISE STALE CALIBRATION (the σ_φ wall)…")
    from cloud.companion.engine_bridge import StreamPlayer
    raised = None
    try:
        StreamPlayer(out_path, seed=0, is_trained=True)
    except RuntimeError as exc:
        raised = str(exc)
    assert raised is not None and "STALE CALIBRATION" in raised, \
        f"expected the σ_φ staleness wall on load; got: {raised!r}"
    log(f"    wall confirmed: {raised.splitlines()[0][:120]}…")

    # run_train reports this honestly (built=True, playback=blocked), no repoint.
    from cloud.companion.app import Companion
    import shutil
    sess = Path(tempfile.mkdtemp(prefix="ets_seam_sess_"))
    for w in wavs:
        shutil.copy(w, sess / Path(w).name)
    comp = Companion(cloud_url=cloud_url, session_dir=str(sess))
    demo_world = comp.play_world
    tr = comp.run_train(sweeps=3)
    assert tr["ok"] and tr.get("built") and tr.get("playback") == "blocked", tr
    assert tr["is_trained"] is False and comp.play_world == demo_world, \
        "blocked playback must NOT repoint the player away from the demo world"
    log(f"    run_train: built=True, playback=blocked; player stays on the demo world")

    # --- the DEMO world still plays: one real capped bar ------------------------
    log("[5] the calibrated DEMO world still renders ONE capped bar (slow)…")
    demo = StreamPlayer(demo_world, seed=0)
    info = demo.world_info()
    assert info["ready"] and info["is_trained"] is False, info
    demo.set_region([0.0] * info["M"])          # u=0 arrangement
    pcm, roles = demo.produce_one_bar()
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float64) / 32767.0
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    assert samples.size > 0, "no PCM produced from the demo world"
    assert np.all(np.isfinite(samples)) and peak <= 0.61, f"cap breach: peak={peak}"
    assert len(roles) == info["M"] and all(np.isfinite(roles)), roles
    log(f"    demo bar: {samples.size} samples, peak={peak:.3f} (capped)")

    log("SEAM_BUILD_OK_PLAY_BLOCKED_ON_SIGMAPHI")


if __name__ == "__main__":
    main()
