"""H-8 / PREREG-informative-B.md §5.5: the informative-B change touches the FREEZE
path ONLY, so an EXISTING committed world renders BYTE-IDENTICAL.

An .etsworld is a pickle of a World carrying its OWN frozen fstate.B; loading
unpickles that stored B and ``anchors.build_world`` is NEVER called on load. So the
freeze-B change cannot reach an already-frozen world. This test pins that two ways,
out-of-process (a real render imports the arch-v6 engine, kept out of the cloud
interpreter, like test_web_field_payload):

  * DETERMINISM: two u=0 renders of demo.etsworld are bit-identical and the world
    hash is stable;
  * UNREACHABILITY: with ``anchors.build_world`` AND ``coupling_weighted_B`` patched
    to RAISE, the same u=0 render still succeeds and yields the SAME audio — proving
    the freeze code is not on the load/render path, so no existing world can change.

(The literal before/after equality across the pre-edit tag was also measured during
the build and reported; this committed test enforces the guarantee going forward.)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


_DUMP = r"""
import sys, json, hashlib
sys.path.insert(0, r"%s")
sys.path.insert(0, r"%s/architecture-v6")
import numpy as np
from ets.engine.worldfile import load_world
from ets.engine.engine import Engine, build_bank, resolve_sigma
import ets.functional.anchors as _an

def _render():
    wf = load_world("demo.etsworld")
    sigma = resolve_sigma(wf, None); bank = build_bank(wf)
    eng = Engine(wf, seed=0, sigma=sigma)
    a = np.ascontiguousarray(np.asarray(eng.render_offline(8.0, bank=bank).audio),
                             dtype=np.float32)
    return wf.world_hash, hashlib.sha256(a.tobytes()).hexdigest()

h1, s1 = _render()
h2, s2 = _render()                       # determinism

# UNREACHABILITY: the freeze code must never run on the load/render path.
def _boom(*a, **k):
    raise RuntimeError("build_world/coupling_weighted_B must NOT be called on render")
_an.build_world = _boom
_an.coupling_weighted_B = _boom
h3, s3 = _render()                       # succeeds only if freeze code is off-path

print(json.dumps({"h1": h1, "h2": h2, "h3": h3, "s1": s1, "s2": s2, "s3": s3}))
""" % (str(_ROOT), str(_ROOT))


def _dump():
    r = subprocess.run([sys.executable, "-c", _DUMP], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"subprocess failed:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_existing_world_renders_byte_identical_and_freeze_is_off_path():
    d = _dump()
    assert d["h1"] == d["h2"] == d["h3"], "world hash must be stable across loads"
    assert d["s1"] == d["s2"], "u=0 render must be deterministic (bit-identical)"
    assert d["s3"] == d["s1"], (
        "render with freeze code patched-to-raise must be byte-identical -> the "
        "informative-B change is not on the load/render path (H-8 holds)")
