"""Feature tests for the ingestion pipeline (spec §2) and G0 reconstruction.

Fast + deterministic: uses synthetic audio and hand-built grids, so no audio
files and no beat model are needed. The corpus run of G0 lives in scripts/.
"""
from __future__ import annotations
import numpy as np
import pytest

from ets.ingestion import filterbank as fb
from ets.ingestion import beatclock as bc
from ets.ingestion import unitize as uz
from ets.ingestion import g0
from ets.ingestion.pipeline import synthetic_track, build_track
from ets.ingestion.track import (assert_provenance_complete, require_within_track,
                                 CostStructure)

SR = 44100


def _synth_audio(seconds=4.0, sr=SR, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sr)) / sr
    y = (0.5 * np.sin(2 * np.pi * 110 * t) + 0.3 * np.sin(2 * np.pi * 440 * t)
         + 0.2 * np.sin(2 * np.pi * 3000 * t) + 0.05 * rng.standard_normal(len(t)))
    return y.astype(np.float32)


def _synth_grid(seconds=4.0, sr=SR, bpm=120):
    beats = np.arange(0, seconds, 60.0 / bpm)
    downbeats = beats[::4]
    return bc.build_grid(beats, downbeats, sr)


# --- filterbank: perfect reconstruction (partition of unity) ---------------

def test_masks_partition_of_unity():
    masks = fb.partition_masks(SR)
    colsum = masks.sum(0)
    assert np.allclose(colsum, 1.0, atol=1e-12)
    assert masks.shape[0] == fb.N_BANDS


def test_band_sum_reconstructs_signal():
    y = _synth_audio()
    S = fb.stft(y)
    masks = fb.partition_masks(SR)
    recon = sum(fb.band_signal(S, masks, k, len(y)) for k in range(fb.N_BANDS))
    rel = np.sqrt(np.mean((recon - y) ** 2)) / np.sqrt(np.mean(y ** 2))
    assert rel < 1e-4


# --- tatum grid: tiling + onset-refine preserves tiling --------------------

def test_tatum_grid_tiles_contiguously():
    grid = _synth_grid()
    b = grid.tatum_boundaries
    assert np.all(np.diff(b) > 0), "tatum boundaries must be strictly increasing"


def test_onset_refine_preserves_tiling_and_endpoints():
    grid = _synth_grid()
    b0 = grid.tatum_boundaries.copy()
    onsets = np.array([b0[3] + 200, b0[5] - 150, b0[8] + 50])
    refined = bc.onset_refine(b0, onsets, SR)
    assert refined[0] == b0[0] and refined[-1] == b0[-1], "endpoints moved"
    assert np.all(np.diff(refined) > 0), "refinement broke monotone tiling"


# --- unitization descriptors ------------------------------------------------

def test_descriptors_shapes_and_chroma_normalized():
    y = _synth_audio()
    grid = _synth_grid()
    S = fb.stft(y)
    masks = fb.partition_masks(SR)
    mass, timbre, chroma = uz.descriptors_and_mass(S, masks, SR, grid.tatum_boundaries)
    n_slots = len(grid.tatum_boundaries) - 1
    assert mass.shape == (n_slots, fb.N_BANDS)
    assert timbre.shape[:2] == (n_slots, fb.N_BANDS)
    assert chroma.shape == (n_slots, fb.N_BANDS, 12)
    s = chroma.sum(axis=2)
    assert np.all((np.abs(s - 1.0) < 1e-6) | (s < 1e-9)), "chroma not L1-normalized"


# --- G0 reconstruction identity (part ii) ----------------------------------

def test_reconstruction_identity_within_tolerance():
    y = _synth_audio()
    grid = _synth_grid()
    rec = g0.reconstruction_identity(y, grid, SR)
    assert rec["recon_ok"], rec
    assert rec["recon_rel_l2"] < g0.RECON_TOL_RELL2


def test_reconstruction_test_bites_on_coverage_gap():
    # remove a run of interior boundaries -> a large uncovered hole -> big error.
    y = _synth_audio()
    grid = _synth_grid()
    b = grid.tatum_boundaries
    mid = len(b) // 2
    grid.tatum_boundaries = np.concatenate([b[:mid - 2], b[mid + 2:]])
    # reconstruct but only over slots that now skip the hole
    S = fb.stft(y)
    masks = fb.partition_masks(SR)
    out = np.zeros(len(y))
    for k in range(fb.N_BANDS):
        bk = fb.band_signal(S, masks, k, len(y))
        for s in range(len(grid.tatum_boundaries) - 1):
            a, c = int(grid.tatum_boundaries[s]), int(grid.tatum_boundaries[s + 1])
            if c - a > SR // 2:      # skip the artificial jumbo slot (the hole)
                continue
            out[a:c] += bk[a:c]
    gs, ge = int(grid.tatum_boundaries[0]), int(grid.tatum_boundaries[-1])
    rel = np.sqrt(np.mean((out[gs:ge] - y[gs:ge]) ** 2)) / np.sqrt(np.mean(y[gs:ge] ** 2))
    assert rel > g0.RECON_TOL_RELL2, "coverage gap not detected — test is vacuous"


# --- Track schema + provenance + cost structure ----------------------------

def test_track_has_exact_schema():
    t = synthetic_track(track_id=3)
    for f in ("units", "masses", "C_timbre", "C_pitchclass", "C_metrical",
              "beat_grid", "provenance_index"):
        assert hasattr(t, f), f"Track missing schema field {f}"


def test_provenance_complete_and_nonvacuous():
    t = synthetic_track(track_id=4)
    assert_provenance_complete(t)
    t.provenance_index["src_start"][0] = t.provenance_index["src_end"][0]  # empty span
    with pytest.raises(AssertionError):
        assert_provenance_complete(t)


def test_cross_track_cost_forbidden():
    a = synthetic_track(track_id=10)
    b = synthetic_track(track_id=11)
    require_within_track(a.C_timbre, a.C_timbre)
    with pytest.raises(ValueError):
        require_within_track(a.C_timbre, b.C_timbre)


def test_pitchclass_transposition_quotient():
    a = synthetic_track(track_id=12)
    C = a.C_pitchclass
    base = C.cost(1, 4)
    C.desc[4] = np.roll(C.desc[4], 5)
    assert abs(C.cost(1, 4) - base) < 1e-9


def test_metrical_circular():
    a = synthetic_track(track_id=13)
    C = a.C_metrical
    C.desc[0, 0], C.desc[1, 0] = 0.02, 0.98
    # circular distance between 0.02 and 0.98 is small (~0.04 apart on the circle)
    assert C.cost(0, 1) < C.cost(0, 2) or C.cost(0, 1) < 0.2


def test_materialize_refuses_large():
    desc = np.random.default_rng(0).standard_normal((5000, 4))
    C = CostStructure.build(1, "timbre", desc)
    with pytest.raises(MemoryError):
        C.materialize(cap=4000)
