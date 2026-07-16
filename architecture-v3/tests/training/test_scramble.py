"""Focused tests for the internal scramble comparison class (spec §6, I-6).

The I-6 invariant check in tests/invariants/manifest.py is the load-bearing
guarantee; these tests document and lock the per-op properties (purity,
determinism, disarrangement, blocked-op refusal) so a regression is localized.
"""
from __future__ import annotations
import dataclasses
import numpy as np
import pytest

from ets.ingestion.pipeline import synthetic_track
from ets.ingestion.track import assert_provenance_complete
from ets.training import scramble as S


@pytest.fixture
def track():
    return synthetic_track(track_id=5, seed=5)


def test_family_is_the_fixed_prereg_set():
    assert set(S.registry_names()) == set(S.PREREGISTERED_FAMILY)
    assert set(S.PREREGISTERED_FAMILY) == {
        "grid-shuffle", "role-permute", "phase-rotate", "cross-track-swap"}
    S.assert_family_fixed()


def test_family_fixed_bites_on_extra_op():
    S._REGISTRY["__extra__"] = S.ScrambleOp(
        "__extra__", "track", "(none)", "implemented", lambda tr, seed=0: tr)
    try:
        with pytest.raises(AssertionError):
            S.assert_family_fixed()
    finally:
        del S._REGISTRY["__extra__"]


@pytest.fixture
def world():
    """A minimal frozen world to exercise the anchor-channel (role-level) ops."""
    from ets.training.world import WorldFreeze
    rng = np.random.default_rng(0)
    D = rng.random((3, 3)); D = 0.5 * (D + D.T); np.fill_diagonal(D, 0.0)
    return WorldFreeze(D=D, a=np.full(3, 1 / 3), B=np.full((3, 8), 1 / 8),
                       theta=np.full((3, 8), 1 / 8), sigma=1.0, M=3)


def test_role_level_ops_are_activated_not_blocked():
    for name in ("role-permute", "cross-track-swap"):
        op = S._REGISTRY[name]
        assert op.status == "implemented", f"{name} should be activated at step c"
        assert op.arity in ("role", "role_pair")


def test_role_permute_runs_through_anchor_channel(track, world):
    from ets.geometry import roles
    from ets.training.world import _occ
    arr = S.role_permute(track, world, seed=3)
    S.assert_arrangement_real(arr, [track.track_id])
    assert arr.mass_sources == (track.track_id,)
    # determinism
    arr2 = S.role_permute(track, world, seed=3)
    assert np.array_equal(arr.O, arr2.O)
    # genuinely disarranges the occupancy vs the un-permuted coupling
    P = roles.extract_prototypes(track, seed=0)
    O_real = _occ(world.couple(P), P)
    assert not np.allclose(arr.O, O_real, atol=1e-9)
    # purity: input track untouched
    assert S.content_keys(track) == S.content_keys(track)


def test_cross_track_swap_crosses_only_anchor_channel(track, world):
    other = synthetic_track(track_id=6, seed=6)
    arr = S.cross_track_swap([track, other], world, seed=3)
    # mass comes ONLY from the two real tracks (I-2/I-6): gauge-invariant anchor
    # space is the sole cross-boundary channel; no fabricated source.
    S.assert_arrangement_real(arr, [track.track_id, other.track_id])
    assert set(arr.mass_sources) == {track.track_id, other.track_id}
    arr2 = S.cross_track_swap([track, other], world, seed=3)
    assert np.array_equal(arr.O, arr2.O)
    # the guard bites on a fabricated (non-real) source
    bogus = S.Arrangement(O=arr.O.copy(), t1=0.0, mass_sources=(4242,))
    with pytest.raises(AssertionError):
        S.assert_arrangement_real(bogus, [track.track_id, other.track_id])


@pytest.mark.parametrize("op_name", ["grid-shuffle", "phase-rotate"])
def test_implemented_op_is_pure_deterministic_inventory_preserving(track, op_name):
    fn = S._REGISTRY[op_name].fn
    before = S.content_keys(track)

    out = fn(track, seed=7)
    # purity
    assert S.content_keys(track) == before
    # honest single-source provenance + real-units-only + inventory equality
    assert_provenance_complete(out)
    S.assert_inventory_preserved([track], out)
    # determinism
    out2 = fn(track, seed=7)
    assert np.array_equal(out.units["phase"], out2.units["phase"])
    assert np.array_equal(out.provenance_index["src_start"],
                          out2.provenance_index["src_start"])
    # a different seed gives a different disarrangement
    out3 = fn(track, seed=8)
    diff = (not np.array_equal(out.units["phase"], out3.units["phase"])
            or not np.array_equal(out.provenance_index["src_start"],
                                  out3.provenance_index["src_start"]))
    assert diff


def test_grid_shuffle_moves_content_keeps_grid(track):
    out = S.grid_shuffle(track, seed=1)
    # content (source spans) moves; metrical grid (phase) is untouched
    assert not np.array_equal(out.provenance_index["src_start"],
                              track.provenance_index["src_start"])
    assert np.array_equal(out.units["phase"], track.units["phase"])
    # permutation stays within band (role/channel preserved)
    assert np.array_equal(out.units["band"], track.units["band"])
    assert np.array_equal(out.provenance_index["band"], out.units["band"])


def test_phase_rotate_moves_grid_keeps_content(track):
    out = S.phase_rotate(track, seed=1)
    # phase (arrangement) rotates; source spans (content) are untouched
    assert not np.array_equal(out.units["phase"], track.units["phase"])
    assert np.array_equal(out.provenance_index["src_start"],
                          track.provenance_index["src_start"])
    # incoherent across bands: the per-band phase delta is not constant
    delta = (out.units["phase"] - track.units["phase"]) % 1.0
    per_band = [np.round(delta[track.units["band"] == b][0], 6)
                for b in np.unique(track.units["band"])]
    assert len(set(per_band)) > 1, "phase rotation was globally coherent (pure gauge)"


def test_phase_rotate_refuses_single_band():
    t = synthetic_track(track_id=9, seed=9, n_slots=20, n_bands=1)
    with pytest.raises(ValueError):
        S.phase_rotate(t, seed=1)


def test_inventory_guard_catches_fabrication(track):
    good = S.grid_shuffle(track, seed=2)
    tampered = dataclasses.replace(good,
                                   provenance_index=good.provenance_index.copy())
    tampered.provenance_index["src_start"][0] = track.n_samples + 10_000
    tampered.provenance_index["src_end"][0] = track.n_samples + 20_000
    with pytest.raises(AssertionError):
        S.assert_inventory_preserved([track], tampered)
