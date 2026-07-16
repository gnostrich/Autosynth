"""Feature tests for the batch (non-causal) writer — the reduced form of the
streaming writer for the "lanes constant" case with u=0 (connector: THE TAPE
PORT). Fast + audio-free: a small frozen world is built from synthetic tracks so
the settlement, its F-descent certificate, realization, and the clamp interface
are exercised without the beat model or the corpus.

What these pin:
  * BATCH SETTLEMENT reaches a Lyapunov F-descent certificate (monotone, converged).
  * NO DECODER: the settled coupling realizes DIRECTLY into the render's Schedule,
    which renders to audio with COMPLETE provenance (I-12) — no readout head.
  * NO STATIC KEYMAP: placements move when the settled occupancy moves.
  * SINGLE CONTROL JACK (I-1 partial): the only control entry is the tilt u; u=0 is
    the reduced form and a non-zero u raises (Layer-0 map is a parallel build).
  * LAMBDA IS LIVE: changing f.LAMBDA changes the settled equilibrium (step-d
    weights auto-apply through f.py, no writer edit).
  * CLAMP INTERFACE (I-7): role-column and unit-demand clamps are honored.
"""
from __future__ import annotations
import numpy as np
import pytest

from ets.ingestion.pipeline import synthetic_track
from ets.functional import f as ff
from ets import writer as W
from ets.writer import ClampSet
from ets.render import render, SourceUnit, SourceUnitBank


@pytest.fixture(scope="module")
def world():
    tracks = [synthetic_track(track_id=t, n_slots=24, seed=t) for t in range(4)]
    return W.build_world_from_tracks(tracks, sigma=0.5)


def _bank_for(schedule, tatum_len, seed=0):
    """A minimal source bank: unit-length random audio for every referenced unit.
    Equal-length units => the render's identity-gauge path (no phase vocoder),
    keeping the test fast; it still exercises overlap-add + provenance."""
    rng = np.random.default_rng(seed)
    bank = SourceUnitBank(sr=44100)
    for r in schedule.placements:
        key = (int(r["src_track"]), int(r["src_unit"]))
        if key not in bank:
            bank.add(SourceUnit(track_id=key[0], unit_id=key[1], band=0,
                                src_start=0, src_end=tatum_len,
                                audio=rng.standard_normal(tatum_len), sr=44100))
    return bank


# --- batch settlement: the Lyapunov F-descent certificate -------------------

def test_settlement_reaches_F_certificate(world):
    out = W.generate_batch(world, seconds=4.0)
    res = out["settle"]
    tr = np.asarray(res.trace)
    assert res.monotone, f"F not monotone: {np.sum(np.diff(tr) > 1e-9)} increases"
    assert tr[-1] <= tr[0], "F did not descend"
    assert res.converged, "settlement did not reach the convergence certificate"
    # the O-dependent single-functional terms are all real and finite.
    for k in ("T2", "T3", "T4", "F_O"):
        assert np.isfinite(res.terms_final[k])


def test_settled_occupancy_shape(world):
    out = W.generate_batch(world, seconds=4.0)
    O = out["settle"].O
    assert O.shape == (world.M, out["grid"].n_slots)
    assert np.all(O >= 0), "occupancy must be non-negative mass"


# --- no decoder: settled coupling -> Schedule -> audio + provenance ----------

def test_realize_renders_with_complete_provenance(world):
    out = W.generate_batch(world, seconds=4.0)
    sched = out["schedule"]
    assert len(sched.placements) > 0, "empty schedule"
    # the schedule is well-formed by construction (Schedule.__post_init__).
    assert sched.total_samples == out["grid"].total_samples
    bank = _bank_for(sched, world.out_tatum_len)
    audio, prov = render(sched, bank)
    prov.assert_complete(audio)                        # I-12: every sample traced
    assert np.any(np.abs(audio) > 0), "rendered tape is silent"


def test_identity_gauge_only_at_u0(world):
    """u=0, lanes constant => one identity section (no transpose/phase/loudness)."""
    from ets.render.schedule import Gauge
    out = W.generate_batch(world, seconds=3.0)
    secs = out["schedule"].sections
    assert len(secs) == 1 and secs[0].gauge == Gauge()


# --- no static keymap: placements follow the settled field ------------------

def test_lambda_is_live(world):
    """Changing f.LAMBDA (the step-d weights) changes the settled equilibrium — the
    weights are read LIVE through f.py, so calibrated weights auto-apply here with
    no writer edit (I-4/I-9: one frozen-at-train F, read not re-implemented)."""
    O0 = W.generate_batch(world, seconds=4.0)["settle"].O.copy()
    saved = dict(ff.LAMBDA)
    try:
        ff.LAMBDA["T3"] = saved["T3"] * 6.0     # strengthen masking
        ff.LAMBDA["T4"] = saved["T4"] * 0.1     # weaken continuity
        O1 = W.generate_batch(world, seconds=4.0)["settle"].O
    finally:
        ff.LAMBDA.clear(); ff.LAMBDA.update(saved)
    assert not np.allclose(O0, O1), \
        "settled occupancy did not move with LAMBDA (weights not live?)"


def test_no_static_keymap_unit_follows_settled_column(world):
    """NO STATIC KEYMAP: which unit fills a slot is ROUTED by that slot's SETTLED
    role column through the materialization index — it is not a fixed (slot->unit)
    table. Drive ``realize`` with two occupancies that differ only in which role is
    active; the realized units change accordingly. (Tested on ``realize`` directly
    with a controlled index so the routing is isolated from synthetic-world role
    degeneracy.)"""
    from ets.writer import realize, RealizationIndex
    from ets.writer.tape import OutputGrid, TapeNode

    M = world.M
    n_bands = int(world.fstate.B.shape[1])
    assert M >= 2, "need >=2 roles to distinguish routing"
    # a controlled index: role r's material is unit id 1000*r + b in band b.
    unit_of = {(r, b): (7, 1000 * r + b) for r in range(M) for b in range(n_bands)}
    index = RealizationIndex(unit_of=unit_of, role_track={r: 7 for r in range(M)},
                             M=M, n_bands=n_bands)
    grid = OutputGrid.for_seconds(world.sr, world.out_tatum_len, 2.0)
    tape = TapeNode(grid=grid, M=M)

    def units_when_role(r):
        O = np.full((M, grid.n_slots), 1e-9)
        O[r, :] = 1.0                                  # role r active everywhere
        sched, _ = realize(O, tape, world.fstate, index)
        return {int(x) for x in sched.placements["src_unit"]}

    ua, ub = units_when_role(0), units_when_role(M - 1)
    assert ua and ub, "no placements produced"
    assert ua != ub, "realized units invariant to the settled role (static keymap?)"
    # and they route to the expected role bands (0..n_bands vs 1000*(M-1)+..).
    assert max(ua) < 1000, "role-0 routing leaked into another role's units"
    assert min(ub) >= 1000 * (M - 1), "role routing did not follow the settled column"


# --- single control jack (I-1): the Layer-0 TiltTerms is the only entry ------

def test_control_enters_only_as_tilt_terms(world):
    """A raw array is NOT a control: the settlement accepts control only as the
    Layer-0 TiltTerms type (I-1/C-3 typing tooth), and the explicit untilted
    TiltTerms is bit-identical to the tilt=None reduced form."""
    with pytest.raises(TypeError):
        W.generate_batch(world, seconds=2.0,
                         tilt=np.array([1.0, 0.0, 0.0, 0.0, 0.0]))
    a = W.generate_batch(world, seconds=2.0, tilt=W.untilted(world.M))
    b = W.generate_batch(world, seconds=2.0, tilt=None)
    assert np.array_equal(a["settle"].O, b["settle"].O)


def test_tilt_moves_the_settled_field_in_the_leaned_direction(world):
    """The Doob tilt acts: a positive REGION lean on anchor k raises anchor k's
    settled bar occupancy (φ_region[k]); a positive DENSITY lean raises total
    scheduled mass (φ_density). FDT sign sanity of the Layer-0 map."""
    M = world.M
    base = W.generate_batch(world, seconds=3.0)["settle"].O
    lam = np.zeros(M); lam[0] = 2.0
    t_region = W.TiltTerms(lam_region=lam, lam_density=0.0, lam_cont=0.0,
                           lam_gauge=0.0, lam_novelty=0.0, T_s=1.0)
    O_r = W.generate_batch(world, seconds=3.0, tilt=t_region)["settle"].O
    assert O_r[0].sum() > base[0].sum(), "region lean did not raise its anchor"

    t_dense = W.TiltTerms(lam_region=np.zeros(M), lam_density=2.0, lam_cont=0.0,
                          lam_gauge=0.0, lam_novelty=0.0, T_s=1.0)
    O_d = W.generate_batch(world, seconds=3.0, tilt=t_dense)["settle"].O
    assert O_d.sum() > base.sum(), "density lean did not raise scheduled mass"


# --- clamp interface (I-7 feature side) -------------------------------------

def test_role_column_clamp_is_pinned(world):
    M = world.M
    col = np.zeros(M); col[0] = 1.0
    out = W.generate_batch(world, seconds=3.0,
                           clamps=ClampSet(role_columns={4: col.copy()}))
    assert np.allclose(out["settle"].O[:, 4], col)


def test_unit_demand_is_placed_verbatim(world):
    tid, uid = int(world.tracks[2].track_id), int(world.tracks[2].units["unit_id"][5])
    out = W.generate_batch(world, seconds=3.0,
                           clamps=ClampSet(unit_demands={6: (tid, uid, 0)}))
    p = out["schedule"].placements
    at6 = p[p["out_slot"] == 6]
    assert any(int(r["src_track"]) == tid and int(r["src_unit"]) == uid for r in at6)


def test_bar_periodicity_at_u0_is_expected(world):
    """HONEST PROPERTY (not a defect): the untilted, unclamped batch equilibrium is
    bar-periodic — column s and column s+S_phase settle to the same role mass. This
    is the stationary u=0 output; movement requires tilt/clamps/planner. Pinning it
    as a test keeps anyone from 'fixing' the loop by injecting a hidden second
    authority."""
    from ets.writer.tape import S_PHASE
    out = W.generate_batch(world, seconds=6.0)
    O = out["settle"].O
    n = O.shape[1]
    # compare a mid-tape bar to the next bar (avoid the wrap boundary).
    s = S_PHASE * 2
    if s + 2 * S_PHASE <= n:
        assert np.allclose(O[:, s:s + S_PHASE], O[:, s + S_PHASE:s + 2 * S_PHASE],
                           atol=1e-6), "u=0 equilibrium unexpectedly non-periodic"
