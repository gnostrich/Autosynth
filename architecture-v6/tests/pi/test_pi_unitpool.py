"""PI unit-pool telemetry bite (the classical-sampler drill, engine + wire side).

The drill-in overlay is fed by a NEW read-only telemetry message, /ets/unitpool:
one datagram per role carrying that role's drill pool — the units RANKED by their
anchor-profile weight on the role's anchor (B[i, band]), each with its anchor
profile B[:, band]. These bites pin:

  * the pool is SOFT, not a partition — each role independently keeps its top-N by
    its own column of B; membership overlaps and is never removed cross-role;
  * the reduction is READ-ONLY — it is a pure function of the frozen world, so a
    fixed-seed offline render is byte-identical whether or not it runs, and it
    mutates nothing (the frozen B is untouched);
  * the wire format round-trips emitter -> TelemetryReceiver back to the same
    (unit_id, track_id, band, profile) records the overlay steers on.

Everything here is the engine's OUTBOUND monitor direction (spec §9/§12): values
in, wire out, nothing loops back into control/settlement (I-1/I-5).
"""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

TOP_N = 24


def _load(worldfile_path):
    wf_mod = pytest.importorskip("ets.engine.worldfile")
    eng_mod = pytest.importorskip("ets.engine.engine")
    wf = wf_mod.load_world(worldfile_path)
    return wf, eng_mod


def _all_units(world):
    """(unit_id, track_id, band) for every unit, honouring the band range — the
    same enumeration role_unit_pool uses, recomputed independently here."""
    n_bands = int(np.asarray(world.fstate.B).shape[1])
    out = []
    for tr in world.tracks:
        prov = tr.provenance_index
        for uid, band in zip(np.asarray(prov["unit_id"], int).tolist(),
                             np.asarray(prov["band"], int).tolist()):
            if 0 <= band < n_bands:
                out.append((int(uid), int(tr.track_id), int(band)))
    return out


def test_pool_is_soft_topN_by_own_column_not_a_partition(worldfile_path):
    """Each role's pool is INDEPENDENTLY the top-N units by its own column of B
    (B[i, band]); no unit is removed from role j because it also ranks in role i.
    That independence is precisely 'soft pool, overlap allowed, not a partition'."""
    wf, eng = _load(worldfile_path)
    world = wf.world
    B = np.asarray(world.fstate.B, float)
    M = B.shape[0]

    pools = eng.role_unit_pool(world, top_n=TOP_N)
    assert set(pools) == set(range(M))

    units = _all_units(world)
    for i in range(M):
        # independent recomputation: stable top-N by this role's column.
        want = sorted(units, key=lambda u: -float(B[i, u[2]]))[:TOP_N]
        got = pools[i]
        assert len(got) == min(TOP_N, len(units))
        assert [(u, t, b) for (u, t, b, _p) in got] == want, \
            f"role {i} pool is not the independent top-N by B[{i}, band]"
        # ranking is non-increasing in the role's own anchor weight ...
        weights = [float(B[i, b]) for (_u, _t, b, _p) in got]
        assert all(weights[k] >= weights[k + 1] for k in range(len(weights) - 1))
        # ... and every entry carries its true anchor profile B[:, band].
        for (_u, _t, b, prof) in got:
            assert np.allclose(np.asarray(prof, float), B[:, b])


def test_pool_membership_overlaps_across_roles(worldfile_path):
    """A unit may live in more than one role's pool (soft, not exclusive). With a
    world whose one anchor wins every band's argmax, the pools are not disjoint;
    the union is strictly smaller than the sum of the pool sizes."""
    wf, eng = _load(worldfile_path)
    pools = eng.role_unit_pool(wf.world, top_n=TOP_N)
    per_role_ids = [{(u, t, b) for (u, t, b, _p) in pools[i]} for i in pools]
    total = sum(len(s) for s in per_role_ids)
    union = set().union(*per_role_ids) if per_role_ids else set()
    # if the pools were an exclusive partition, union == total; overlap => union < total.
    assert len(union) < total, "pools are disjoint — that is a partition, not a soft pool"


def test_pool_reduction_is_read_only_render_byte_identical(worldfile_path):
    """The reduction touches nothing downstream: a fixed-seed offline render is
    byte-identical whether or not the pool/count reductions run, and the frozen B
    is not mutated. (Each render uses a FRESH engine — the writer is stateful — so
    identity witnesses determinism, exactly as the PI sound guard does.)"""
    wf, eng = _load(worldfile_path)

    def _fresh_render():
        engine = eng.Engine(wf, seed=0, sigma=eng.resolve_sigma(wf))
        return engine.render_offline(1.0)

    a = _fresh_render()
    B_before = np.array(wf.world.fstate.B, copy=True)

    # run the new read-only reductions (what the engine emits at startup).
    _ = eng.role_unit_pool(wf.world, top_n=TOP_N)
    _ = eng.role_unit_counts(wf.world)

    b = _fresh_render()
    B_after = np.asarray(wf.world.fstate.B)

    assert np.array_equal(B_before, B_after), "role_unit_pool mutated frozen B"
    assert np.array_equal(a.audio, b.audio), "reduction perturbed the audio path"
    sha_a = hashlib.sha256(a.audio.tobytes()).hexdigest()
    assert sha_a == a.receipt["audio_sha256"] == b.receipt["audio_sha256"]


def test_unitpool_roundtrips_emitter_to_receiver(worldfile_path):
    """The /ets/unitpool wire format survives a real emitter -> receiver hop back
    into the same (unit_id, track_id, band, profile) records the overlay uses."""
    udp = pytest.importorskip("pythonosc.udp_client")
    osc_io = pytest.importorskip("ets.engine.osc_io")
    from ets.instrument.feed import TelemetryReceiver

    wf, eng = _load(worldfile_path)
    world = wf.world
    pool0 = eng.role_unit_pool(world, top_n=TOP_N)[0]

    captured = {}
    rec = TelemetryReceiver(
        on_unitpool=lambda role, units: captured.__setitem__(role, units), port=0)
    try:
        emitter = osc_io.MeterEmitter("127.0.0.1", rec.bound_port)
        emitter.unitpool(0, world.M, pool0)
        assert rec.handle_once(timeout=2.0), "no /ets/unitpool datagram handled"
    finally:
        rec.stop()

    got = captured.get(0)
    assert got is not None and len(got) == len(pool0)
    for sent, recv in zip(pool0, got):
        uid, tid, band, prof = sent
        assert recv["unit_id"] == int(uid)
        assert recv["track_id"] == int(tid)
        assert recv["band"] == int(band)
        assert np.allclose(np.asarray(recv["profile"], float), np.asarray(prof, float))
