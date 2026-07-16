"""Streaming writer (spec §7) + Layer-0 tilt + temperature + I-8 stability.

What these pin:
  * per-bar frontier settlement carries its F-descent certificate (I-8 half 1);
  * committed bars are never rewritten (the writer only appends);
  * DETERMINISM: same (world, tilt trajectory, seed) ⇒ identical bars (H-8 core);
  * the Layer-0 map acts with the right FDT signs (region/density/cont/novelty);
  * TEMPERATURE is real sampling looseness: T_s ↓ ⇒ φ fluctuation ↓;
  * degenerate lanes (σ_φ=0, e.g. GAUGE on a frozen-frame world) tilt as the
    exact identity — any lean value produces the identical tape;
  * uncalibrated worlds REFUSE nonzero leans (no λ is ever invented);
  * I-8: working-state growth is bounded by material heard, and the guard BITES.
"""
from __future__ import annotations
import numpy as np
import pytest

from ets.writer import ClampSet
from ets.writer.stream import StreamHalt, StreamWriter
from ets.writer.tilt import (SigmaPhi, TiltTerms, WorldNotCalibrated, layer0,
                             untilted)
from ets.panel.lanes import default_lane_vector
from tests.harness.worldtools import build_synthetic_world, measure_sigma_inline


@pytest.fixture(scope="module")
def world():
    return build_synthetic_world()


@pytest.fixture(scope="module")
def sigma(world):
    return SigmaPhi.from_mapping(measure_sigma_inline(world, n_bars=16))


def _run(world, n_bars, tilt, seed=5):
    w = StreamWriter(world, seed=seed)
    return [w.write_bar(tilt=tilt) for _ in range(n_bars)]


def test_per_bar_certificate_and_append_only(world):
    w = StreamWriter(world, seed=1)
    first = w.write_bar()
    O0 = first.O.copy()
    rows0 = list(first.rows)
    for _ in range(4):
        r = w.write_bar()
        assert r.converged and r.monotone, "frontier bar lost its certificate"
    # committed bar 0 is untouched by later writing (the result object is the
    # commitment; nothing holds a mutable reference into it).
    assert np.array_equal(first.O, O0) and list(first.rows) == rows0
    assert [*range(5)] == [0, 1, 2, 3, 4][: w.bar]  # bars only append


def test_stream_is_deterministic_given_seed(world, sigma):
    u = default_lane_vector(world.M)
    u.u_density = 1.0
    tilt = layer0(u, sigma)
    a = _run(world, 6, tilt, seed=9)
    b = _run(world, 6, tilt, seed=9)
    for ra, rb in zip(a, b):
        assert np.array_equal(ra.O, rb.O)
        assert ra.rows == rb.rows
    c = _run(world, 6, tilt, seed=10)
    assert any(not np.array_equal(ra.O, rc.O) for ra, rc in zip(a, c)), \
        "different seed produced an identical tape (sampling is fake?)"


def test_layer0_fdt_signs(world, sigma):
    """Leaning a lane moves its own φ upward relative to untilted (the Doob
    tilt's defining property), for each non-degenerate direction lane."""
    n = 10
    base = _run(world, n, untilted(world.M))

    def mean_phi(results, key, comp=None):
        vals = [r.phi[key] if comp is None else float(r.phi[key][comp])
                for r in results]
        return float(np.mean(vals))

    # region: lean anchor 0 up
    u = default_lane_vector(world.M); u.u_region[0] = 2.0
    r = _run(world, n, layer0(u, sigma))
    assert mean_phi(r, "region", 0) > mean_phi(base, "region", 0)

    # density
    u = default_lane_vector(world.M); u.u_density = 2.0
    r = _run(world, n, layer0(u, sigma))
    assert mean_phi(r, "density") > mean_phi(base, "density")

    # continuity: negative lean = recombination (fewer continuation events)
    u = default_lane_vector(world.M); u.u_continuity = -3.0
    r = _run(world, n, layer0(u, sigma))
    assert mean_phi(r, "cont") < mean_phi(base, "cont")

    # novelty statistic: positive lean tilts toward REUSE (φ_novelty up)
    u = default_lane_vector(world.M); u.u_novelty = 3.0
    r = _run(world, n, layer0(u, sigma))
    assert mean_phi(r, "novelty") > mean_phi(base, "novelty")


def test_temperature_scales_fluctuation(world):
    hot = _run(world, 12, untilted(world.M, T_s=1.0))
    cold = _run(world, 12, untilted(world.M, T_s=1e-3))
    sd_hot = np.std([r.phi["density"] for r in hot], ddof=1)
    sd_cold = np.std([r.phi["density"] for r in cold], ddof=1)
    assert sd_cold < 0.25 * sd_hot, (
        f"T_s did not scale settlement looseness (hot {sd_hot}, cold {sd_cold})")


def test_degenerate_lane_is_exact_identity(world, sigma):
    """σ_φgauge = 0 on a frozen-frame world (measured, not asserted): the
    GAUGE lane's tilt is then the exact identity — ANY lean leaves the tape
    bit-identical. This is the degenerate-exponential-tilt theorem, not a
    fallback branch."""
    assert sigma.gauge == 0.0, "fixture: v0 writer should have a frozen frame"
    u0 = default_lane_vector(world.M)
    u1 = default_lane_vector(world.M); u1.u_gauge = 3.0
    t0, t1 = layer0(u0, sigma), layer0(u1, sigma)
    assert t1.degenerate == ("gauge",)
    a = _run(world, 5, t0, seed=21)
    b = _run(world, 5, t1, seed=21)
    for ra, rb in zip(a, b):
        assert np.array_equal(ra.O, rb.O) and ra.rows == rb.rows


def test_uncalibrated_world_refuses_leans(world):
    u = default_lane_vector(world.M); u.u_density = 0.5
    with pytest.raises(WorldNotCalibrated):
        layer0(u, None)
    # the untilted writer needs no scale — allowed without calibration.
    t = layer0(default_lane_vector(world.M), None)
    assert t.is_untilted


def test_anchor_count_mismatch_refused(world, sigma):
    u = default_lane_vector(world.M + 1); u.u_region[0] = 1.0
    with pytest.raises(ValueError):
        layer0(u, sigma)


def test_clamps_are_boundary_conditions_in_stream(world):
    """I-7 in streaming: a role-column clamp within the frontier bar pins that
    cell (settled AND sampled around it stays pinned), same species as batch."""
    w = StreamWriter(world, seed=2)
    col = np.zeros(world.M); col[0] = 1.0
    r = w.write_bar(clamps=ClampSet(role_columns={3: col.copy()}))
    assert np.allclose(r.O[:, 3], col), "stream clamp not honored"
    w2 = StreamWriter(world, seed=2)
    r2 = w2.write_bar()
    assert not np.allclose(r2.O[:, 3], col), "clamp check vacuous"


# --- I-8: bounded state growth + halt-and-report ------------------------------

def test_i8_state_bounded_by_material_on_stationary_input(world):
    """Spec §7: 'state dimension must track McMillan degree of material heard,
    not elapsed time'. Exact form of the law, asserted bar by bar: the working
    state never exceeds (distinct real units actually heard so far) + (runs in
    flight ≤ bands) + (one bar of pending) + constants — so on stationary input
    the state can grow ONLY while new material is still being heard, never with
    elapsed time itself."""
    w = StreamWriter(world, seed=3)
    heard = set()
    n_bands = int(world.fstate.B.shape[1])
    per_bar_pending = n_bands * w.s_phase
    for _ in range(24):
        r = w.write_bar()
        heard |= {(t, u) for (_s, t, u, _sec, _m) in r.rows}
        material_bound = len(heard) + n_bands + per_bar_pending + 2
        assert w.state_size() <= material_bound, (
            f"bar {r.bar}: state {w.state_size()} exceeds material-heard bound "
            f"{material_bound} — growing with time, not material (I-8)")
    assert w.state_size() <= w.state_bound(), "state exceeded the corpus bound"


def test_i8_guard_bites_on_injected_growth(world):
    """Non-vacuity: artificially inflating the working state beyond the
    material bound makes the writer HALT AND REPORT (StreamHalt), proving the
    I-8 guard is real."""
    w = StreamWriter(world, seed=4)
    w.write_bar()
    for k in range(w.state_bound() + 1):
        w.threader.last_used[(999_000, k)] = 0     # phantom "material"
    with pytest.raises(StreamHalt):
        w.write_bar()
