"""PREREG-channel-bias-squares — the SOFT per-channel bias contract (CI teeth).

The channel-bias mechanism is a SOFT lean folded into the ONE TiltTerms the writer
consumes (``channel_logbias`` on the fiber choice measure). Its two load-bearing
guarantees, pinned here out-of-process (the arch-v6 engine is kept out of the cloud
interpreter, like test_freeze_only_byte_identity):

  BYTE-IDENTITY  an all-zero bias ⇒ ``channel_logbias(...) is None`` ⇒ the tilt is
                 byte-identical to the un-biased tilt ⇒ produced rows AND settled O
                 are bit-identical, bar for bar (⇒ rendered audio is byte-identical,
                 render being I-11 pure).
  PULL           a nonzero bias on a channel MEASURABLY pulls the realized output's
                 provenance toward that channel's track (the Phase-1 H1 result) — so
                 the mechanism is live, not a silent no-op.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


_DUMP = r"""
import sys, json
sys.path.insert(0, r"%s")
sys.path.insert(0, r"%s/architecture-v6")
import numpy as np
from ets.engine.worldfile import load_world
from ets.engine.engine import Engine, resolve_sigma
from ets.panel.lanes import default_lane_vector
from cloud.companion.channel_bias import channel_logbias, channel_tids

def _engine(seed=0):
    wf = load_world("demo.etsworld")
    return wf.world, Engine(wf, seed=seed, sigma=resolve_sigma(wf, None))

# all-zero bias must produce NO lean object
w0, e0 = _engine()
tids = channel_tids(w0)
zero_is_none = channel_logbias(np.zeros(len(tids)), tids) is None

# byte-identity: unbiased writer vs writer fed the all-zero lean, bar for bar
wa, ea = _engine(); wb, eb = _engine()
ua = default_lane_vector(wa.M); ub = default_lane_vector(wb.M)
identical = True
for _ in range(6):
    ra = ea.writer.write_bar(tilt=ea._tilt_for(ua))
    clog = channel_logbias(np.zeros(len(tids)), tids)     # -> None
    rb = eb.writer.write_bar(tilt=eb._tilt_for(ub, channel_logbias=clog))
    if ra.rows != rb.rows or not np.array_equal(ra.O, rb.O):
        identical = False; break

# pull: bias channel 0 hard; measure track-0 provenance fraction vs baseline
def _frac(clog, n=48):
    w, e = _engine()
    u = default_lane_vector(w.M)
    tot = hit = 0
    for _ in range(n):
        r = e.writer.write_bar(tilt=e._tilt_for(u, channel_logbias=clog))
        for (_s, tid, _u, _sec, _m) in r.rows:
            tot += 1; hit += (int(tid) == tids[0])
    return hit / tot if tot else 0.0

base = _frac(None)
bias = _frac(channel_logbias([1.0] + [0.0]*(len(tids)-1), tids))

print(json.dumps({"zero_is_none": zero_is_none, "identical": identical,
                  "base": base, "bias": bias, "n_channels": len(tids)}))
""" % (str(_ROOT), str(_ROOT))


def _dump():
    r = subprocess.run([sys.executable, "-c", _DUMP], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"subprocess failed:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_zero_bias_is_byte_identical_and_nonzero_bias_pulls():
    d = _dump()
    assert d["n_channels"] >= 2, "need >=2 channels to test a per-channel pull"
    assert d["zero_is_none"], "all-zero bias must build no lean (None), not an empty tilt"
    assert d["identical"], (
        "all-zero channel bias must leave the writer byte-identical (rows + settled "
        "O bit-identical) — the mechanism is default-off")
    assert d["bias"] >= d["base"] + 0.10, (
        f"a full bias on channel 0 must materially pull provenance toward its track "
        f"(baseline {d['base']:.3f} -> biased {d['bias']:.3f})")
