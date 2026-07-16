"""MVP-B: the client refuses a returned world whose receipt does not verify.

The receipt is re-derived from the SAME stage-3 input with root ETS's own
functional/anchors code. Any tamper of the world or the receipt is rejected.
"""
from __future__ import annotations

import copy

import numpy as np
import pytest

from cloud.common import (
    encode_job, decode_result, verify_receipt, ReceiptError,
)
from cloud.service import run_job_inprocess
from cloud.tests.fixtures import make_synthetic_protos


def _roundtrip(seed=0, sweeps=6):
    protos = make_synthetic_protos(n_tracks=4, seed=seed)
    job = encode_job(protos, {"seed": 0, "sweeps": sweeps})
    result = decode_result(run_job_inprocess(job))
    return protos, result


def test_untampered_receipt_verifies():
    protos, result = _roundtrip()
    assert verify_receipt(protos, result) is True


def test_tampered_world_D_is_rejected():
    protos, result = _roundtrip()
    result.fstate.D = result.fstate.D + 0.5     # world no longer settles here
    with pytest.raises(ReceiptError):
        verify_receipt(protos, result)


def test_tampered_world_a_is_rejected():
    protos, result = _roundtrip()
    a = result.fstate.a.copy()
    a[0] += 0.3
    result.fstate.a = a / a.sum()
    with pytest.raises(ReceiptError):
        verify_receipt(protos, result)


def test_tampered_coupling_is_rejected():
    protos, result = _roundtrip()
    result.fstate.pis[0] = result.fstate.pis[0] * 1.1
    with pytest.raises(ReceiptError):
        verify_receipt(protos, result)


def test_tampered_F_final_receipt_is_rejected():
    protos, result = _roundtrip()
    result.receipt["F_final"] = float(result.receipt["F_final"]) + 1.0
    with pytest.raises(ReceiptError):
        verify_receipt(protos, result)


def test_tampered_n_anchors_receipt_is_rejected():
    protos, result = _roundtrip()
    result.receipt["n_anchors"] = int(result.receipt["n_anchors"]) + 1
    with pytest.raises(ReceiptError):
        verify_receipt(protos, result)


def test_receipt_bound_to_its_own_job_not_another():
    # A world trained on corpus A must not verify against corpus B's stage-3 input.
    protos_a, result_a = _roundtrip(seed=0)
    protos_b, _ = _roundtrip(seed=99)
    with pytest.raises(ReceiptError):
        verify_receipt(protos_b, result_a)
