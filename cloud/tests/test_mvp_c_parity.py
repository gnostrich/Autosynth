"""MVP-C: training THROUGH the service equals training LOCALLY on the same input.

Local = call the existing anchor-fit directly. Service = encode stage-3 -> run the
service in-process -> decode. The two worlds must match (they are the SAME relocated
training, not a drifting reimplementation).
"""
from __future__ import annotations

import numpy as np

from ets.functional import anchors as an

from cloud.common import encode_job, decode_result
from cloud.service import run_job_inprocess
from cloud.tests.fixtures import make_synthetic_protos

# The anchor-fit is deterministic and stage-3 serialization is exact float64, so
# parity is bit-exact; we assert within a tolerance far tighter than any exam
# tolerance and additionally check bit-exactness where it holds.
EXAM_ATOL = 1e-8


def _local(protos, seed, sweeps, sigma):
    state, info = an.build_world(protos, seed=seed, sweeps=sweeps, sigma=sigma)
    return state, info


def _service(protos, seed, sweeps, sigma):
    job = encode_job(protos, {"seed": seed, "sweeps": sweeps, "sigma": sigma})
    return decode_result(run_job_inprocess(job))


def test_world_parity_local_vs_service():
    protos = make_synthetic_protos(n_tracks=5, K=6, seed=7)
    seed, sweeps, sigma = 0, 8, None

    local_state, local_info = _local(protos, seed, sweeps, sigma)
    result = _service(protos, seed, sweeps, sigma)
    s = result.fstate

    assert s.a.shape[0] == local_state.a.shape[0]
    for name in ("D", "a", "B", "theta"):
        lv = getattr(local_state, name)
        sv = getattr(s, name)
        assert np.allclose(lv, sv, atol=EXAM_ATOL, rtol=0), f"{name} diverged"
    # couplings match too
    assert len(s.pis) == len(local_state.pis)
    for a_pi, b_pi in zip(local_state.pis, s.pis):
        assert np.allclose(a_pi, b_pi, atol=EXAM_ATOL, rtol=0)

    # the receipt's certificate matches the local info
    assert result.receipt["n_anchors"] == local_info["n_anchors"]
    assert np.isclose(result.receipt["F_final"], local_info["F_final"],
                      atol=EXAM_ATOL, rtol=0)
    assert bool(result.receipt["F_monotone"]) == bool(local_info["F_monotone"])


def test_parity_is_bit_exact_on_core_fields():
    protos = make_synthetic_protos(n_tracks=4, K=6, seed=11)
    local_state, _ = _local(protos, 0, 6, None)
    result = _service(protos, 0, 6, None)
    for name in ("D", "a", "B", "theta"):
        assert np.array_equal(getattr(local_state, name), getattr(result.fstate, name)), \
            f"{name} not bit-exact through the service"
