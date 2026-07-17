"""Standalone Phase-2 render-path proof (own process, arch-v6 engine first).

Runs the REAL engine, so bar production is slow in this sandbox — that's expected;
on real hardware it's realtime. Proves: construction, the single-control door at
the bridge level, the WAV header, and one produced bar (eardrum-capped + telemetry).
Also proves geometry parity: a companion train (arch-v6 geometry) verifies against
the deployed root-engine Railway service.
"""
import os, sys, struct
from pathlib import Path
ROOT = "/home/user/Geodesic-Mixing"
sys.path.insert(0, ROOT)                         # for cloud.*
sys.path.insert(0, ROOT + "/architecture-v6")    # ets = engine-v1 + live cap (index 0 WINS)
import numpy as np
def log(m): print(m, flush=True)

WORLD = ROOT + "/corpus.etsworld"
from cloud.companion.engine_bridge import StreamPlayer

log("[1] construct StreamPlayer (loads world; no bank yet)…")
p = StreamPlayer(WORLD, seed=0)
info = p.world_info()
assert info["ready"] and info["M"] >= 1 and info["sr"] > 0, info
log(f"    world_info: M={info['M']} sr={info['sr']} bar={info['bar_seconds']:.3f}s")

log("[2] single-control door (bridge level): only set_region mutates the lane…")
before = p._region.copy()
_ = p.world_info(); _ = p.wav_header(); _ = p._current_lane(); _ = p.telemetry
assert np.array_equal(p._region, before), "a non-steer call mutated the settlement input!"
p.set_region([0.2] * info["M"])
assert not np.array_equal(p._region, before), "set_region did not change the lane"
p.set_region([999.0] * info["M"])   # clamp check
try:
    from ets.panel.envelope import SAFE_REGION_MAGNITUDE as CAP
except Exception:
    CAP = 1.0
assert float(np.max(np.abs(p._region))) <= CAP + 1e-4, "region not clamped to safe envelope"
log(f"    only set_region mutates the lane; clamp to |{CAP}| holds")

log("[3] WAV header well-formed…")
h = p.wav_header()
assert h[:4] == b"RIFF" and h[8:12] == b"WAVE" and h[36:40] == b"data"
sr_hdr = struct.unpack("<I", h[24:28])[0]
assert sr_hdr == info["sr"], (sr_hdr, info["sr"])
log(f"    RIFF/WAVE/data ok, sr={sr_hdr}, 16-bit mono")

log("[4] produce ONE real bar (slow: bank warmup + render)…")
p.set_region([0.0] * info["M"])          # u=0 arrangement
pcm, roles = p.produce_one_bar()
samples = np.frombuffer(pcm, dtype="<i2").astype(np.float64) / 32767.0
peak = float(np.max(np.abs(samples))) if samples.size else 0.0
assert samples.size > 0, "no PCM produced"
assert np.all(np.isfinite(samples)) and peak <= 0.61, f"cap breach: peak={peak}"
assert len(roles) == info["M"] and all(np.isfinite(roles)), roles
log(f"    bar: {samples.size} samples, peak={peak:.3f} (capped), roles(len={len(roles)})={[round(x,2) for x in roles]}")

log("[5] geometry parity: companion train (arch-v6) -> Railway (root engine) verifies…")
tok = Path("/tmp/claude-0/-home-user-Geodesic-Mixing/7598b5c5-271e-5d2e-8faf-47a6f11f40d7/scratchpad/ets_train_token.txt")
if tok.exists():
    os.environ["ETS_TRAIN_TOKEN"] = tok.read_text().strip()
    from cloud.companion.app import Companion
    from cloud.client.cli import save_prototypes
    from cloud.tests.fixtures import make_synthetic_protos
    import tempfile
    sess = tempfile.mkdtemp(prefix="ets_parity_")
    save_prototypes(sess + "/protos.npz", make_synthetic_protos(4, 6, 0))
    comp = Companion(cloud_url="https://geodesic-mixing-production.up.railway.app",
                     session_dir=sess)
    out = comp.run_train(sweeps=3)
    assert out["ok"], out
    log(f"    companion(arch-v6) -> Railway(root) VERIFIED: M={int(out['receipt']['n_anchors'])} anchors")
else:
    log("    (token file absent; skipped live parity)")

log("PHASE2_RENDER_PATH_OK")
