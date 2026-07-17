"""Standalone train->play+steer-YOUR-corpus seam proof (own process, arch-v6 first).

Mirrors instrument_verify.py's pin discipline. Runs the REAL seam end to end:
synthesize 2 short WAVs -> local ingest -> stage-3 -> CLOUD anchor-fit (LIVE Railway
if the token is present, else inproc) -> verify -> local build_index -> MEASURE this
corpus's own σ_φ -> embed it -> a verified, CS-clean trained .etsworld that PLAYS and
STEERS, referencing the user's LOCAL audio.

Steps:
  [2] CS-1: the exact bytes handed to post_job decode to ONLY stage-3 (no
      track/audio/provenance) — the whole point of the offload.
  [3] the trained world file is a VALID .etsworld referencing the user's audio, and
      `resolve_sigma` returns the EMBEDDED per-corpus σ_φ (NO STALE raise — the
      registered demo-world artifact is never consulted).
  [4] StreamPlayer(trained, is_trained=True).world_info()["is_trained"] is True.
  [5] a u=0 bar AND a nonzero region-steer bar both render finite + eardrum-capped,
      and the steered arrangement DIFFERS from u=0 — steering is LIVE (the embedded
      σ_φ armed the region lane), with density/gauge disarmed at u=0 (measured).

Render is slow in this sandbox (bank warmup + bars); that's expected — on real
hardware it's realtime. What matters is the SEAM, the CS wall, and that the trained
world plays AND steers on its OWN measured σ_φ.
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


def _synth_wav(path, sr=44100, seconds=12.0, bpm=120.0, seed=0):
    """A rhythmic, NON-STATIONARY test clip: percussion on the beat + a melodic
    sequence that steps through a per-track scale so DIFFERENT BARS carry different
    role content. That bar-to-bar variety is what makes the untilted (u=0) settlement
    fluctuate region φ (so the measured per-corpus σ_φ ARMS the region lane, as on a
    real corpus) — not music, just a non-degenerate ingestable signal."""
    rng = np.random.default_rng(seed)
    n = int(sr * seconds)
    t = np.arange(n) / sr
    y = np.zeros(n)
    step = int(sr * 60.0 / bpm)                          # one beat
    # per-track distinct scale + timbre (harmonic count) so tracks yield distinct anchors
    base = 110.0 * (2.0 ** (seed / 3.0))
    scale = base * np.array([1.0, 9 / 8, 5 / 4, 4 / 3, 3 / 2, 5 / 3, 15 / 8, 2.0])
    n_harm = 2 + seed                                    # different timbre per track
    click_env = np.exp(-np.linspace(0, 40, step))
    beat = 0
    for start in range(0, n - step, step):
        # a different scale degree each beat -> bars differ from one another
        f = scale[(beat * (seed + 1)) % len(scale)]
        seg = np.zeros(step)
        tt = np.arange(step) / sr
        tone_env = np.exp(-np.linspace(0, 6, step))
        for h in range(1, n_harm + 1):
            seg += (0.16 / h) * np.sin(2 * np.pi * f * h * tt) * tone_env
        seg += click_env * rng.standard_normal(step) * 0.30   # percussion transient
        y[start:start + step] += seg
        beat += 1
    y += 0.01 * rng.standard_normal(n)
    y = 0.9 * y / (np.max(np.abs(y)) + 1e-9)
    sf.write(path, y.astype(np.float32), sr)
    return path


def _real_clips(work, n=4, seconds=45.0, offset=45.0, sr=44100):
    """Trim segments from DISTINCT real corpus tracks (the actual use case: a DJ
    ingesting real audio). Real music has the irregular multi-section structure that
    makes region φ fluctuate at u=0, so the measured per-corpus σ_φ ARMS the region
    lane — the companion's single steer control. Clips are long enough (45s → a few
    hundred bars across the set) that region φ genuinely fluctuates; very short clips
    (~18s) settle to a bar-constant region and disarm it (a measured fact). Returns
    [] if no corpus/ is present (caller falls back to synthetic)."""
    import glob
    import librosa
    srcs = sorted(glob.glob(os.path.join(ROOT, "corpus", "*.mp3")))
    if len(srcs) < n:
        return []
    picks = [srcs[i] for i in np.linspace(0, len(srcs) - 1, n).astype(int)]
    out = []
    for i, s in enumerate(picks):
        y, _ = librosa.load(s, sr=sr, mono=True, offset=offset, duration=seconds)
        y = 0.9 * y / (np.max(np.abs(y)) + 1e-9)
        p = str(work / f"real{i}.wav")
        sf.write(p, y.astype(np.float32), sr)
        out.append(p)
    return out


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
    wavs = _real_clips(work)
    if wavs:
        log(f"[0] trimmed {len(wavs)} REAL corpus clips (45s each) under {work}")
    else:
        wavs = [_synth_wav(str(work / f"clip{i}.wav"), seed=i, bpm=120 + 8 * i)
                for i in range(3)]
        log(f"[0] no corpus/ found -> synthesized {len(wavs)} WAVs under {work}")

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

    # --- valid world file + resolve_sigma returns the EMBEDDED per-corpus σ_φ ----
    log("[3] valid .etsworld referencing the user's audio + EMBEDDED σ_φ (no STALE)…")
    from ets.engine.worldfile import load_world
    from ets.engine.engine import resolve_sigma, disarmed_lanes
    wf = load_world(out_path)
    assert wf.sources["kind"] == "corpus", wf.sources
    assert set(wf.sources["paths"].values()) == set(wavs), \
        "trained world must reference the USER'S local audio, nothing else"
    assert wf.sigma_phi is not None, "trained world must embed its own σ_φ"
    sigma = resolve_sigma(wf)                    # must NOT raise STALE; uses embedded
    assert sigma is not None, "resolve_sigma returned no σ_φ for the trained world"
    dis = disarmed_lanes(sigma)
    armed = [ln for ln in ("region", "cont", "novelty") if ln not in dis]
    assert "region" in armed, f"region lane must be ARMED by the embedded σ_φ; disarmed={dis}"
    log(f"    world_hash={wf.world_hash[:12]} armed={armed} disarmed(u=0)={dis}")

    # --- is_trained truthful + plays + STEERS -----------------------------------
    log("[4] StreamPlayer(trained, is_trained=True): world_info is_trained is True…")
    from cloud.companion.engine_bridge import StreamPlayer
    from ets.panel.envelope import SAFE_REGION_MAGNITUDE as CAP
    p0 = StreamPlayer(out_path, seed=0, is_trained=True)
    info = p0.world_info()
    assert info["ready"] and info["is_trained"] is True, info
    M = info["M"]
    log(f"    world_info: M={M} sr={info['sr']} is_trained={info['is_trained']}")

    log("[5] u=0 bar AND a nonzero region-steer bar: both capped, arrangements DIFFER…")
    p0.set_region([0.0] * M)                     # u=0 arrangement
    pcm0, roles0 = p0.produce_one_bar()
    ps = StreamPlayer(out_path, seed=0, is_trained=True)   # fresh state, same seed
    steer = [(-1.0) ** k * 0.6 * CAP for k in range(M)]    # decisive asymmetric region lean
    ps.set_region(steer)
    pcms, roless = ps.produce_one_bar()
    for tag, pcm in (("u=0", pcm0), ("steer", pcms)):
        s = np.frombuffer(pcm, dtype="<i2").astype(np.float64) / 32767.0
        peak = float(np.max(np.abs(s))) if s.size else 0.0
        assert s.size > 0 and np.all(np.isfinite(s)) and peak <= 0.61, \
            f"{tag} bar cap/finite breach: size={s.size} peak={peak}"
        log(f"    {tag:5s} bar: {s.size} samples, peak={peak:.3f} (capped)")
    assert pcm0 != pcms, ("steered arrangement is identical to u=0 — steering is a "
                          "NO-OP (the embedded σ_φ did not arm the region lane)")
    log("    steered arrangement DIFFERS from u=0 → steering is LIVE on the trained world")

    log("SEAM_BUILD_PLAY_STEER_OK")


if __name__ == "__main__":
    main()
