"""End-to-end ingestion (spec §2): audio -> Track object.

One track at a time; no raw audio is kept in the Track (recomputable from source
via the filterbank), and the cache is compact (descriptors + grid, npz). Never
holds more than one track's audio in memory.
"""
from __future__ import annotations
import os
import numpy as np

from . import filterbank as fb
from . import beatclock as bc
from . import unitize as uz
from .track import (Track, CostStructure, UNIT_DTYPE, PROV_DTYPE)


def _standardize(desc: np.ndarray) -> np.ndarray:
    mu = desc.mean(axis=0, keepdims=True)
    sd = desc.std(axis=0, keepdims=True)
    sd[sd == 0] = 1.0
    return (desc - mu) / sd


def build_track(track_id: int, units_cols, masses, timbre_desc, chroma_desc,
                phase_desc, beat_grid, prov_cols, n_samples, sr,
                rng=None) -> Track:
    """Assemble a Track from already-computed columnar arrays."""
    rng = rng or np.random.default_rng(track_id)
    n = len(masses)
    units = np.zeros(n, dtype=UNIT_DTYPE)
    for name in UNIT_DTYPE.names:
        units[name] = units_cols[name]
    prov = np.zeros(n, dtype=PROV_DTYPE)
    for name in PROV_DTYPE.names:
        prov[name] = prov_cols[name]

    C_timbre = CostStructure.build(track_id, "timbre", _standardize(timbre_desc), rng)
    C_pitch = CostStructure.build(track_id, "pitchclass", chroma_desc, rng)
    C_metrical = CostStructure.build(track_id, "metrical",
                                     phase_desc.reshape(-1, 1), rng)
    return Track(track_id=track_id, units=units, masses=np.asarray(masses, float),
                 C_timbre=C_timbre, C_pitchclass=C_pitch, C_metrical=C_metrical,
                 beat_grid=beat_grid, provenance_index=prov,
                 n_samples=int(n_samples), sr=int(sr))


def ingest(path: str, track_id: int, sr: int = 44100) -> Track:
    """Full pipeline for one audio file -> Track (spec §2)."""
    import librosa
    y, _ = librosa.load(path, sr=sr, mono=True)
    n_samples = len(y)

    # Beat clock (spec §2 step 2). beat_this decision is logged on the grid.
    from beat_this.inference import File2Beats
    f2b = File2Beats(checkpoint_path=bc.CHECKPOINT, dbn=bc.DBN)
    beats_sec, downbeats_sec = f2b(path)
    grid = bc.build_grid(beats_sec, downbeats_sec, sr)

    # onset-refine tatum boundaries within grid (microtiming preserved as content)
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units="samples", hop_length=fb.HOP)
    refined = bc.onset_refine(grid.tatum_boundaries, onsets, sr)
    grid.tatum_boundaries = refined
    phase, bar, level = bc.metrical_coords(refined, grid)

    # STFT-domain banding + descriptors (spec §2 steps 3-5)
    S = fb.stft(y)
    masks = fb.partition_masks(sr)
    mass2d, timbre3d, chroma3d = uz.descriptors_and_mass(S, masks, sr, refined)

    n_slots = len(refined) - 1
    n_bands = masks.shape[0]
    starts = refined[:-1]
    ends = refined[1:]

    # Flatten (slot, band) -> unit rows. Band-major within slot.
    slot_ix = np.repeat(np.arange(n_slots), n_bands)
    band_ix = np.tile(np.arange(n_bands), n_slots)
    uid = np.arange(n_slots * n_bands)

    units_cols = {
        "unit_id": uid, "slot": slot_ix, "band": band_ix,
        "phase": phase[slot_ix], "bar": bar[slot_ix], "level": level[slot_ix],
    }
    prov_cols = {
        "unit_id": uid, "track_id": np.full(len(uid), track_id, np.int64),
        "src_start": np.clip(starts[slot_ix], 0, n_samples),
        "src_end": np.clip(ends[slot_ix], 0, n_samples),
        "band": band_ix,
    }
    masses = mass2d.reshape(-1)
    timbre_desc = timbre3d.reshape(n_slots * n_bands, -1)
    chroma_desc = chroma3d.reshape(n_slots * n_bands, 12)
    phase_desc = phase[slot_ix]

    return build_track(track_id, units_cols, masses, timbre_desc, chroma_desc,
                       phase_desc, grid, prov_cols, n_samples, sr)


# ---- compact cache -------------------------------------------------------

def save(track: Track, path: str) -> None:
    g = track.beat_grid
    np.savez_compressed(
        path,
        track_id=track.track_id, n_samples=track.n_samples, sr=track.sr,
        units=track.units, masses=track.masses, prov=track.provenance_index,
        timbre=track.C_timbre.desc, timbre_norm=track.C_timbre._normalizer,
        chroma=track.C_pitchclass.desc, chroma_norm=track.C_pitchclass._normalizer,
        phase=track.C_metrical.desc, phase_norm=track.C_metrical._normalizer,
        g_beats=g.beats, g_downbeats=g.downbeats, g_tatums=g.tatum_boundaries,
        g_tempo=g.tempo_curve, g_bpb=g.beats_per_bar, g_tpb=g.tatums_per_beat,
        g_tool=g.tool,
    )


def load(path: str) -> Track:
    d = np.load(path, allow_pickle=False)
    grid = bc.BeatGrid(sr=int(d["sr"]), beats=d["g_beats"], downbeats=d["g_downbeats"],
                       tatum_boundaries=d["g_tatums"], tempo_curve=d["g_tempo"],
                       beats_per_bar=int(d["g_bpb"]), tatums_per_beat=int(d["g_tpb"]),
                       tool=str(d["g_tool"]))
    tid = int(d["track_id"])
    ct = CostStructure(tid, "timbre", d["timbre"], float(d["timbre_norm"]))
    cp = CostStructure(tid, "pitchclass", d["chroma"], float(d["chroma_norm"]))
    cm = CostStructure(tid, "metrical", d["phase"], float(d["phase_norm"]))
    return Track(track_id=tid, units=d["units"], masses=d["masses"],
                 C_timbre=ct, C_pitchclass=cp, C_metrical=cm, beat_grid=grid,
                 provenance_index=d["prov"], n_samples=int(d["n_samples"]),
                 sr=int(d["sr"]))


# ---- synthetic Track (tests / invariant checks; no audio, no beat_this) ---

def synthetic_track(track_id: int, n_slots: int = 40, n_bands: int = 8,
                    sr: int = 44100, seed: int | None = None) -> Track:
    """A tiny valid Track built from in-memory arrays. Used by the invariant
    checks so they run fast in CI without audio or the beat model."""
    rng = np.random.default_rng(seed if seed is not None else track_id)
    n = n_slots * n_bands
    hop = sr // 8
    bounds = np.arange(n_slots + 1, dtype=np.int64) * hop
    n_samples = int(bounds[-1])
    slot_ix = np.repeat(np.arange(n_slots), n_bands)
    band_ix = np.tile(np.arange(n_bands), n_slots)
    uid = np.arange(n)
    phase = (slot_ix % 8) / 8.0
    units_cols = {"unit_id": uid, "slot": slot_ix, "band": band_ix,
                  "phase": phase, "bar": slot_ix // 8, "level": np.zeros(n, np.int64)}
    prov_cols = {"unit_id": uid, "track_id": np.full(n, track_id, np.int64),
                 "src_start": bounds[slot_ix], "src_end": bounds[slot_ix + 1],
                 "band": band_ix}
    masses = rng.random(n) + 0.1
    timbre_desc = rng.standard_normal((n, 4))
    chroma_desc = rng.random((n, 12)); chroma_desc /= chroma_desc.sum(1, keepdims=True)
    grid = bc.BeatGrid(sr=sr, beats=bounds[::1], downbeats=bounds[::8],
                       tatum_boundaries=bounds,
                       tempo_curve=np.full(max(n_slots - 1, 1), 120.0),
                       beats_per_bar=8, tatums_per_beat=1)
    return build_track(track_id, units_cols, masses, timbre_desc, chroma_desc,
                       phase, grid, prov_cols, n_samples, sr, rng)
