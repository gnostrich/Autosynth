"""I-1 and I-9, now that the guarded features (Layer-0 tilt + engine runtime)
exist. (The invariant MANIFEST status flags live in tests/invariants/manifest.py,
owned by a concurrent feature branch this cycle — these are the executable
checks; the one-line PENDING→ENFORCED flag flip is an orchestrator
reconciliation noted in the session report.)

I-1 single tilt jack: no control path into the writer except the h-transform
tilt. Structural: the writer package's entry points take control ONLY as
`tilt` (typed TiltTerms, produced solely by the Layer-0 map — see also
tests/harness/test_h6_panel_exhaustive.py C-3 teeth); a non-TiltTerms control
is refused at runtime (bite).

I-9 frozen F-weights: run-time controls are tilt parameters only; the LIVE
f.LAMBDA equals the REGISTERED training artifact (training_results.json,
REGISTRY train-nce-revr1-2026-07-13) — frozen after training, and no runtime
package (engine/panel/writer) writes it (the write-scan lives in
tests/invariants/test_i9_no_runtime_mutation.py and covers ets/ recursively,
including the new engine package)."""
from __future__ import annotations
import json
import pathlib

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_i1_nontilt_control_is_refused_at_runtime():
    from ets.writer import settle_tape, TiltTerms
    from ets.writer.tape import OutputGrid, TapeNode
    from tests.harness.worldtools import build_synthetic_world
    world = build_synthetic_world()
    grid = OutputGrid(sr=world.sr, tatum_len=world.out_tatum_len, n_slots=8)
    tape = TapeNode(grid=grid, M=world.M)
    with pytest.raises(TypeError):
        settle_tape(world.fstate, tape, tilt={"density": 1.0})   # not TiltTerms
    with pytest.raises(TypeError):
        settle_tape(world.fstate, tape, tilt=np.ones(5))
    # the sanctioned object passes.
    from ets.writer import untilted
    res = settle_tape(world.fstate, tape, tilt=untilted(world.M))
    assert res.converged


def test_i9_live_lambda_equals_registered_training_artifact():
    from ets.functional import f as ff
    with open(ROOT / "training_results.json") as fh:
        artifact = json.load(fh)
    assert artifact["verdict"].startswith("PASS"), \
        "training artifact is not a PASS — LAMBDA has no authority"
    emitted = artifact["lambda_emitted"]
    for key in ("T2", "T3", "T4", "T1p", "T5"):
        assert ff.LAMBDA[key] == emitted[key], (
            f"live LAMBDA[{key}]={ff.LAMBDA[key]!r} != registered "
            f"{emitted[key]!r} — F weights are not frozen-after-training (I-9)")


def test_i9_engine_and_panel_never_write_lambda():
    """Reuse the repo-wide write-scan on the NEW runtime packages explicitly
    (belt over the recursive test's braces): engine + panel + writer sources
    contain no LAMBDA assignment."""
    from tests.invariants.test_i9_no_runtime_mutation import _lambda_writes
    for pkg in ("engine", "panel", "writer"):
        for p in sorted((ROOT / "ets" / pkg).rglob("*.py")):
            writes = _lambda_writes(p.read_text())
            assert not writes, f"{p}: writes LAMBDA at lines {writes} (I-9)"
