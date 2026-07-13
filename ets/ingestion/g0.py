"""G0 gate (spec §13): ingestion + beat-clock sanity + reconstruction identity.

G0 has two halves, both pre-registered in PREREG.md before any run:
  (i)  beat-clock sanity: pulse present + grid-to-onset alignment + meter.
  (ii) unit reconstruction identity: scheduling a track's own units at their own
       slots (identity transform, rectangular overlap-add) reproduces the track
       within tolerance.

NOTE on (ii) — CORRECTED characterization (see PREREG.md "G0 CORRECTION NOTE",
registry g0-correction-2026-07-13). What (ii) ACTUALLY certifies:
  1. filterbank perfect-reconstruction (partition of unity): sum_k band_k == y;
  2. the shipped grid is a VALID MONOTONE TILING of [first tatum, last tatum]
     (no overlap / no double-count). A broken tiling (non-monotone boundaries)
     bites: it double-counts and leaves the reconstruction != source (verified:
     rel_l2 ~ 0.6, recon_ok=False on a non-monotone grid);
  3. covered_fraction = fraction of wall-clock spanned by the metrical grid.
It does NOT discriminate interior slot PLACEMENT: any monotone re-placement of
the interior boundaries (even fully random within [gs,ge]) yields BIT-IDENTICAL
reconstruction error — the forward overlap-add depends only on the endpoints and
the filterbank PR, never on where interior slots sit or on units/provenance.
Interior slot placement (are slots on the audio's real events?) is discriminated
by G0(i) grid->onset ALIGNMENT, not by this reconstruction identity. Structural
note: an interior HOLE is impossible under forward-fill of consecutive boundary
pairs, so (ii) guards tiling integrity (overlap/monotonicity), while SPAN
coverage is the separately-reported covered_fraction. Reported to the auditor,
not hidden.

These thresholds are the pre-registered tolerances; they are NOT consumed by any
objective (I-5) — this module is instrumentation only.
"""
from __future__ import annotations
import numpy as np

from . import filterbank as fb
from . import beatclock as bc
from .pipeline import build_track
from . import unitize as uz

# --- pre-registered tolerances (mirror PREREG.md G0 entry) ---
MIN_BEATS = 32
REG_FRAC_MIN = 0.80          # fraction of IBIs within [0.5,2.0]x median
ALIGN_TOL_MS = 50.0          # median beat->onset distance bound
ALIGN_SEARCH_MS = 100.0      # search window for "aligned" beats
RECON_TOL_RELL2 = 1e-3       # reconstruction relative L2 (-60 dB)


def beat_clock_sanity(grid: bc.BeatGrid, onset_samples: np.ndarray) -> dict:
    beats = grid.beats.astype(float)
    sr = grid.sr
    n_beats = len(beats)
    ibi = np.diff(beats)
    med = float(np.median(ibi)) if len(ibi) else 0.0
    reg_frac = float(np.mean((ibi >= 0.5 * med) & (ibi <= 2.0 * med))) if med > 0 else 0.0
    pulse_present = (n_beats >= MIN_BEATS) and (reg_frac >= REG_FRAC_MIN)

    # grid -> onset alignment
    aligned_frac, med_align_ms = 0.0, float("inf")
    if len(onset_samples):
        on = np.sort(onset_samples.astype(float))
        j = np.searchsorted(on, beats)
        dist = np.full(n_beats, np.inf)
        for k in range(n_beats):
            cands = []
            if j[k] < len(on):
                cands.append(on[j[k]])
            if j[k] > 0:
                cands.append(on[j[k] - 1])
            if cands:
                dist[k] = min(abs(c - beats[k]) for c in cands)
        dist_ms = dist / sr * 1e3
        search = ALIGN_SEARCH_MS
        within = dist_ms[dist_ms <= search]
        aligned_frac = float(len(within) / n_beats)
        med_align_ms = float(np.median(within)) if len(within) else float("inf")

    return {
        "n_beats": n_beats,
        "median_bpm": (60.0 / (med / sr)) if med > 0 else 0.0,
        "regular_frac": reg_frac,
        "pulse_present": bool(pulse_present),
        "beats_per_bar_mode": int(grid.beats_per_bar),
        "median_align_ms": med_align_ms,
        "aligned_frac": aligned_frac,
        "align_ok": bool(med_align_ms <= ALIGN_TOL_MS),
    }


def reconstruction_identity(y: np.ndarray, grid: bc.BeatGrid, sr: int) -> dict:
    """Overlap-add each band's units at their own slots; compare to source over
    the grid-covered span. Iterates slots so any tiling gap/overlap shows up."""
    S = fb.stft(y)
    masks = fb.partition_masks(sr)
    n_bands = masks.shape[0]
    bounds = grid.tatum_boundaries
    gs, ge = int(bounds[0]), int(bounds[-1])
    out = np.zeros(len(y))
    for k in range(n_bands):
        bk = fb.band_signal(S, masks, k, len(y))
        for s in range(len(bounds) - 1):
            a, b = int(bounds[s]), int(bounds[s + 1])
            out[a:b] += bk[a:b]
    ref = y[gs:ge]
    rec = out[gs:ge]
    denom = np.sqrt(np.mean(ref ** 2)) + 1e-12
    rel = float(np.sqrt(np.mean((rec - ref) ** 2)) / denom)
    peak = float(np.max(np.abs(rec - ref)))
    covered = (ge - gs) / max(len(y), 1)
    return {
        "recon_rel_l2": rel,
        "recon_db": 20 * np.log10(rel + 1e-300),
        "recon_peak_abs": peak,
        "covered_fraction": float(covered),
        "recon_ok": bool(rel <= RECON_TOL_RELL2),
    }


def evaluate(path: str, track_id: int):
    """Ingest one track and run both G0 halves. Returns (Track, record).

    Runs the beat model once and reuses the STFT so G0 does not double the cost.
    """
    import librosa
    y, _ = librosa.load(path, sr=44100, mono=True)
    sr = 44100
    n_samples = len(y)

    from beat_this.inference import File2Beats
    f2b = File2Beats(checkpoint_path=bc.CHECKPOINT, dbn=bc.DBN)
    beats_sec, downbeats_sec = f2b(path)
    grid = bc.build_grid(beats_sec, downbeats_sec, sr)
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units="samples", hop_length=fb.HOP)
    grid.tatum_boundaries = bc.onset_refine(grid.tatum_boundaries, onsets, sr)

    # sanity uses the (refined) clock + onsets
    sanity = beat_clock_sanity(grid, onsets)
    recon = reconstruction_identity(y, grid, sr)

    # assemble Track from the same STFT (so the cached object matches what G0 saw)
    phase, bar, level = bc.metrical_coords(grid.tatum_boundaries, grid)
    S = fb.stft(y)
    masks = fb.partition_masks(sr)
    mass2d, timbre3d, chroma3d = uz.descriptors_and_mass(
        S, masks, sr, grid.tatum_boundaries)
    n_slots = len(grid.tatum_boundaries) - 1
    n_bands = masks.shape[0]
    starts, ends = grid.tatum_boundaries[:-1], grid.tatum_boundaries[1:]
    slot_ix = np.repeat(np.arange(n_slots), n_bands)
    band_ix = np.tile(np.arange(n_bands), n_slots)
    uid = np.arange(n_slots * n_bands)
    units_cols = {"unit_id": uid, "slot": slot_ix, "band": band_ix,
                  "phase": phase[slot_ix], "bar": bar[slot_ix], "level": level[slot_ix]}
    prov_cols = {"unit_id": uid, "track_id": np.full(len(uid), track_id, np.int64),
                 "src_start": np.clip(starts[slot_ix], 0, n_samples),
                 "src_end": np.clip(ends[slot_ix], 0, n_samples), "band": band_ix}
    track = build_track(track_id, units_cols, mass2d.reshape(-1),
                        timbre3d.reshape(n_slots * n_bands, -1),
                        chroma3d.reshape(n_slots * n_bands, 12), phase[slot_ix],
                        grid, prov_cols, n_samples, sr)

    record = {"track_id": track_id, "path": path, "n_units": int(len(uid)),
              "tool": grid.tool, **sanity, **recon}
    record["G0_pass"] = bool(sanity["pulse_present"] and sanity["align_ok"]
                             and recon["recon_ok"])
    return track, record
