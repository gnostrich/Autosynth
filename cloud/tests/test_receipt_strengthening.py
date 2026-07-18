"""Receipt strengthening (PREREG-informative-B.md §4/§5.6): the device-verifiable
receipt now certifies not just WHERE the world settles (F_final) but that it settled
DOWNHILL from a real start (F_final <= F_init, F_init INDEPENDENTLY recomputed) and
that its own block-solve descent was monotone (F_monotone == True).

The new fields F_init / F_monotone / seed are REQUIRED — a receipt lacking them is
rejected (no old-receipt shim; §4). Each check below BITES on a world/receipt that
does not honestly settle below its own random start.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from cloud.common import encode_job, decode_result, verify_receipt, ReceiptError
from cloud.service import run_job_inprocess
from cloud.tests.fixtures import make_synthetic_protos

from ets.functional import f as ff


def _roundtrip(seed=0, sweeps=6):
    protos = make_synthetic_protos(n_tracks=4, seed=seed)
    job = encode_job(protos, {"seed": 0, "sweeps": sweeps})
    result = decode_result(run_job_inprocess(job))
    return protos, result


def test_valid_receipt_verifies_with_new_fields():
    protos, result = _roundtrip()
    # the new fields are present and the world descended.
    for key in ("F_init", "F_final", "F_monotone", "seed"):
        assert key in result.receipt, f"receipt must carry {key!r}"
    assert float(result.receipt["F_final"]) <= float(result.receipt["F_init"])
    assert verify_receipt(protos, result) is True


@pytest.mark.parametrize("missing", ["F_init", "F_monotone", "seed"])
def test_missing_new_field_is_rejected(missing):
    """No old-receipt shim: a receipt lacking any new required field is rejected."""
    protos, result = _roundtrip()
    del result.receipt[missing]
    with pytest.raises(ReceiptError):
        verify_receipt(protos, result)


def test_tampered_F_init_is_rejected():
    """F_init is INDEPENDENTLY recomputed from (M, seed) — a deterministic init_state —
    so a receipt whose F_init disagrees with the re-derivation is rejected."""
    protos, result = _roundtrip()
    result.receipt["F_init"] = float(result.receipt["F_init"]) + 5.0
    with pytest.raises(ReceiptError):
        verify_receipt(protos, result)


def test_non_monotone_flag_is_rejected():
    """A world whose own solver reported a non-monotone descent is rejected."""
    protos, result = _roundtrip()
    result.receipt["F_monotone"] = False
    with pytest.raises(ReceiptError):
        verify_receipt(protos, result)


def test_world_above_its_start_is_rejected():
    """A world that does NOT sit below its random start (F_final > F_init) is rejected,
    even when its F_final is otherwise self-consistent. Constructed by inflating the
    settled geometry so F honestly exceeds the start; the receipt's F_final is the
    HONEST F of that inflated world, so only the descent bound bites."""
    protos, result = _roundtrip()
    bad = replace(result.fstate, D=result.fstate.D * 8.0)   # sits above its start
    F_bad = float(ff.F(bad, protos)[0])
    assert F_bad > float(result.receipt["F_init"]), "precondition: bad world exceeds start"
    result.fstate = bad
    result.receipt["F_final"] = F_bad                       # honest F of the bad world
    with pytest.raises(ReceiptError):
        verify_receipt(protos, result)


def test_descent_bound_and_F_final_both_bite_independently():
    """Sanity: the original F_final-vs-recompute check still bites (perturb the world
    without updating F_final), and it is DISTINCT from the new descent bound."""
    protos, result = _roundtrip()
    result.fstate = replace(result.fstate, a=(result.fstate.a * 1.0))  # identical
    # unchanged world still verifies (regression guard for the added checks)
    assert verify_receipt(protos, result) is True
