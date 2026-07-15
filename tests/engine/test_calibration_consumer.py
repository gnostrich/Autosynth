"""Consumer side of the registered σ_φ calibration instrument (owned by the
concurrent ets.calibration feature). Two layers:

  (1) ALWAYS RUN — the disarmed-lane law on the tilt map itself: a lane whose
      scale the instrument marked unidentifiable (σ=0, identifiable=False —
      the honest MAP-writer measurement for DENSITY and GAUGE) applies NO tilt
      (λ undefined ≠ λ huge ≠ λ floored), still transmits u, and is surfaced
      on the TiltTerms; a lean on it changes NOTHING in the settled tape.

  (2) INTEGRATION with the real registered artifact — skipped with reason
      until ets.calibration merges (agreed contract: load_sigma_phi(),
      world_content_hash(fstate), cal.sigma/identifiable/lane_phi/world_hash;
      the engine's staleness guard refuses a hash mismatch).
"""
from __future__ import annotations
import numpy as np
import pytest

from ets.panel.lanes import default_lane_vector
from ets.writer.stream import StreamWriter
from ets.writer.tilt import SigmaPhi, layer0
from tests.harness.worldtools import build_synthetic_world, measure_sigma_inline


@pytest.fixture(scope="module")
def world():
    return build_synthetic_world()


def _disarmed_sigma(world):
    """A SigmaPhi shaped like the registered corpus artifact: region/cont/
    novelty identifiable, density+gauge measured σ=0 & unidentifiable."""
    m = measure_sigma_inline(world, n_bars=12)
    return SigmaPhi(region=np.asarray(m["region"], float),
                    density=0.0, cont=float(m["cont"]), gauge=0.0,
                    novelty=float(m["novelty"]),
                    identifiable={"density": False, "gauge": False})


def test_disarmed_lane_applies_no_tilt_and_is_surfaced(world):
    sig = _disarmed_sigma(world)
    u0 = default_lane_vector(world.M)
    u1 = default_lane_vector(world.M)
    u1.u_density = 3.0                       # lean on the DISARMED lane
    t0, t1 = layer0(u0, sig), layer0(u1, sig)
    assert t1.disarmed == ("density",)
    assert t1.degenerate == ()               # NOT the σ=0-constant theorem case
    assert t1.lam_density == 0.0             # no invented scale, no huge λ
    a = [StreamWriter(world, seed=8).write_bar(tilt=t0) for _ in range(1)][0]
    b = [StreamWriter(world, seed=8).write_bar(tilt=t1) for _ in range(1)][0]
    assert np.array_equal(a.O, b.O) and a.rows == b.rows, \
        "a disarmed lane influenced the settlement"
    # identifiable lanes still act through the same SigmaPhi.
    u2 = default_lane_vector(world.M)
    u2.u_continuity = -3.0
    t2 = layer0(u2, sig)
    assert t2.lam_cont != 0.0 and not t2.disarmed


def test_registered_artifact_integration():
    try:
        from ets.calibration import load_sigma_phi, world_content_hash  # noqa
    except ImportError:
        pytest.skip("ets.calibration not merged yet (concurrent feature); "
                    "engine load path is coded against the agreed contract "
                    "(ets.engine.engine.resolve_sigma) and exercised by the "
                    "disarmed-lane law above")
    cal = load_sigma_phi()
    if cal is None:
        pytest.skip("ets.calibration merged but no artifact registered yet")
    # the agreed contract shape
    assert "region" in cal.sigma and "continuity" in cal.sigma \
        and "novelty" in cal.sigma
    assert cal.identifiable.get("density") is False
    assert cal.identifiable.get("gauge") is False
    assert len(cal.world_hash) >= 12
