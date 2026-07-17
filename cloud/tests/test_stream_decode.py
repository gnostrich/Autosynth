"""STREAM DECODE — the /api/stream byte contract the FE decodes is FAITHFUL to the
engine's produced bars (guards the "live site plays white noise" defect class).

The FE's audio path (index.html) assumes: Content-Type audio/wav, a WAV header that
declares MONO 16-bit PCM at the world sample rate, then a body of int16 little-endian
samples. This test reproduces the real demo engine through the SAME per-listener
fan-out the server streams and asserts:

  (a) chunk lengths are whole int16-sample multiples (2 bytes/frame, mono);
  (b) a listener joining the stream starts on a BAR/sample boundary — the first body
      chunk equals a whole produced bar, not a mid-bar splice;
  (c) the streamed bytes are byte-identical to what produce_one_bar yields for the
      same (deterministic, u=0) bars — the fan-out neither reframes nor re-dtypes;
  (d) the WAV header declares mono / 16-bit / world sr (what the FE decodes as);
  (e) spectral-flatness sanity: the demo bar is NOT pure-white-noise-flat, AND its
      flatness matches the CANONICAL offline render (so the live path adds no noise).

The engine is loaded in a SUBPROCESS so its render/decoder imports never enter the
pytest interpreter (keeps the in-process import-graph invariants order-independent).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_DEMO = _ROOT / "demo.etsworld"

pytestmark = pytest.mark.skipif(
    not _DEMO.exists(),
    reason="demo.etsworld not present (gitignored on some clones)")


_PROBE = r'''
import json, time, queue
import numpy as np
from pathlib import Path
from cloud.companion.engine_bridge import StreamPlayer   # pins arch-v6 engine first

DEMO = r"__DEMO_PATH__"

def flatness(a):
    a = np.asarray(a, dtype=np.float64)
    A = np.abs(np.fft.rfft(a)) + 1e-9
    return float(np.exp(np.log(A).mean()) / A.mean())

# deterministic produced bars (fresh player, u=0)
pa = StreamPlayer(DEMO, seed=0)
produced = [pa.produce_one_bar()[0] for _ in range(3)]

# the streamed path (a fresh player: same seed -> same deterministic bars)
pc = StreamPlayer(DEMO, seed=0)
gen = pc.stream_chunks()
header = next(gen)
streamed = []
t0 = time.time()
for chunk in gen:
    streamed.append(chunk)
    if len(streamed) >= 3 or time.time() - t0 > 60:
        break
pc.stop()

# canonical offline render flatness (the reference the live path must match)
off = pa.engine.render_offline(2.0).audio

# WAV header fields (little-endian): channels @20, bits @34, sr @24
import struct
channels = struct.unpack_from("<H", header, 22)[0]
sr_hdr   = struct.unpack_from("<I", header, 24)[0]
bits     = struct.unpack_from("<H", header, 34)[0]

s0 = np.frombuffer(streamed[0], dtype="<i2")
out = {
  "streamed_equals_produced": [s == p for s, p in zip(streamed, produced)],
  "whole_sample": [len(s) % 2 == 0 for s in streamed],
  "header_channels": int(channels),
  "header_bits": int(bits),
  "header_sr": int(sr_hdr),
  "world_sr": int(pc.sr),
  "first_chunk_is_a_whole_bar": (len(streamed[0]) == len(produced[0])),
  "flatness_stream": flatness(s0),
  "flatness_offline": flatness(off),
  "stream_rms": float(np.sqrt((s0.astype(np.float64) ** 2).mean())),
}
print("PROBE_JSON:" + json.dumps(out))
'''.replace("__DEMO_PATH__", str(_DEMO))


def _run_probe():
    r = subprocess.run([sys.executable, "-c", _PROBE], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"probe failed:\n{r.stdout}\n{r.stderr}"
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("PROBE_JSON:")]
    assert line, f"probe emitted no JSON:\n{r.stdout}\n{r.stderr}"
    return json.loads(line[0][len("PROBE_JSON:"):])


def test_stream_is_faithful_mono_pcm_not_white_noise():
    d = _run_probe()
    # (c) the fan-out streams byte-identical produced bars (no reframe / no dtype swap)
    assert all(d["streamed_equals_produced"]), \
        "streamed bytes diverge from produce_one_bar — the fan-out reframes/re-dtypes"
    # (a) whole int16-sample chunks
    assert all(d["whole_sample"]), "a streamed chunk is not a whole int16-sample multiple"
    # (b) a joining listener starts on a bar boundary
    assert d["first_chunk_is_a_whole_bar"], "the stream does not start on a bar boundary"
    # (d) the header the FE decodes as: mono, 16-bit, world sr
    assert d["header_channels"] == 1, f"stream must be mono (got {d['header_channels']} ch)"
    assert d["header_bits"] == 16, f"stream must be 16-bit (got {d['header_bits']})"
    assert d["header_sr"] == d["world_sr"], \
        f"header sr {d['header_sr']} != world sr {d['world_sr']} (FE decodes at world sr)"
    # (e) spectral sanity: the demo bar is real signal, not pure white noise, and the
    #     live stream matches the canonical offline render (the path adds no noise).
    assert d["stream_rms"] > 1.0, "the streamed bar is silent"
    assert d["flatness_stream"] < 0.97, \
        f"the streamed demo bar is white-noise-flat ({d['flatness_stream']:.3f})"
    assert abs(d["flatness_stream"] - d["flatness_offline"]) < 0.05, \
        (f"live-stream flatness {d['flatness_stream']:.3f} diverges from the canonical "
         f"offline render {d['flatness_offline']:.3f} — the live path added noise")
