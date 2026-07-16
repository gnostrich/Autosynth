"""Beat clock (spec §2 step 2).

TOOL DECISION (logged per spec requirement): beat_this v1.1.0, checkpoint
'final0', dbn=False. The tool+version is recorded on every BeatGrid it produces
(``BeatGrid.tool``) and cached with the Track, so any downstream artifact can be
traced to the clock that made it.

From beats + downbeats this derives: tempo curve, a tatum grid (each beat
interval subdivided into ``tatums_per_beat`` equal parts), and the metrical
mapping (metrical position on the circle, bar index, metrical level). Wall-clock
seconds do NOT leave this module as a content coordinate: the CLOCK itself is
expressed in sample indices (it is the master clock, spec §1), and units carry
only the metrical coordinate downstream (see track.py). Sample spans reach the
renderer solely through provenance_index.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

TOOL = "beat_this"
TOOL_VERSION = "1.1.0"
CHECKPOINT = "final0"
DBN = False
TATUMS_PER_BEAT = 2   # v0: eighth-note tatums. Fastest metrical level unitized.


@dataclass
class BeatGrid:
    sr: int
    beats: np.ndarray            # sample indices of detected beats
    downbeats: np.ndarray        # sample indices of detected downbeats
    tatum_boundaries: np.ndarray # sample indices, monotone; tiles [grid_start, grid_end]
    tempo_curve: np.ndarray      # bpm per beat interval (len = len(beats)-1)
    beats_per_bar: int           # modal beats-per-bar
    tatums_per_beat: int
    tool: str = field(default=f"{TOOL}=={TOOL_VERSION}/{CHECKPOINT} dbn={DBN}")

    @property
    def grid_start(self) -> int:
        return int(self.tatum_boundaries[0])

    @property
    def grid_end(self) -> int:
        return int(self.tatum_boundaries[-1])


def _modal_beats_per_bar(beats: np.ndarray, downbeats: np.ndarray) -> int:
    if len(downbeats) < 2:
        return 4
    idx = np.searchsorted(beats, downbeats)
    bpb = np.diff(idx)
    bpb = bpb[bpb > 0]
    if len(bpb) == 0:
        return 4
    vals, cnts = np.unique(bpb, return_counts=True)
    return int(vals[np.argmax(cnts)])


def build_grid(beats_sec, downbeats_sec, sr: int,
               tatums_per_beat: int = TATUMS_PER_BEAT) -> BeatGrid:
    """Assemble a BeatGrid from beat_this outputs (times in seconds)."""
    beats = np.asarray(beats_sec, dtype=float)
    downbeats = np.asarray(downbeats_sec, dtype=float)
    beats = np.unique(beats)
    if len(beats) < 2:
        raise ValueError("fewer than 2 beats: no measurable pulse (spec §2 wall)")

    beat_samp = np.round(beats * sr).astype(np.int64)
    down_samp = np.round(downbeats * sr).astype(np.int64)

    # Tatum boundaries: subdivide each consecutive beat interval into tatums_per_beat.
    bounds = [beat_samp[0]]
    for i in range(len(beat_samp) - 1):
        a, b = beat_samp[i], beat_samp[i + 1]
        for j in range(1, tatums_per_beat):
            bounds.append(a + (b - a) * j // tatums_per_beat)
        bounds.append(b)
    tatum_boundaries = np.array(sorted(set(int(x) for x in bounds)), dtype=np.int64)

    ibi = np.diff(beats)
    tempo_curve = 60.0 / np.maximum(ibi, 1e-9)
    bpb = _modal_beats_per_bar(beat_samp, down_samp)

    return BeatGrid(sr=sr, beats=beat_samp, downbeats=down_samp,
                    tatum_boundaries=tatum_boundaries, tempo_curve=tempo_curve,
                    beats_per_bar=bpb, tatums_per_beat=tatums_per_beat)


def onset_refine(tatum_boundaries: np.ndarray, onset_samples: np.ndarray,
                 sr: int, window_ms: float = 30.0) -> np.ndarray:
    """Snap each INTERIOR tatum boundary to the nearest onset within +/-window.

    Snapping preserves tiling: adjacent units share the moved boundary, so the
    grid still contiguously tiles [grid_start, grid_end] and reconstruction stays
    exact. Endpoints (grid_start, grid_end) are never moved. Monotonicity is
    enforced so a snap can never cross a neighbour. Microtiming is intrinsic
    content (spec §3), so the snap window is small (grid stays the clock; onsets
    only sharpen slice edges).
    """
    if len(onset_samples) == 0 or len(tatum_boundaries) < 3:
        return tatum_boundaries.copy()
    w = int(window_ms * 1e-3 * sr)
    onsets = np.sort(np.asarray(onset_samples, dtype=np.int64))
    out = tatum_boundaries.astype(np.int64).copy()
    for i in range(1, len(out) - 1):
        b = out[i]
        j = np.searchsorted(onsets, b)
        cands = []
        if j < len(onsets):
            cands.append(onsets[j])
        if j > 0:
            cands.append(onsets[j - 1])
        if not cands:
            continue
        best = min(cands, key=lambda o: abs(o - b))
        if abs(best - b) <= w and out[i - 1] < best < out[i + 1]:
            out[i] = best
    return out


def metrical_coords(tatum_boundaries: np.ndarray, grid: BeatGrid):
    """Per tatum-slot metrical coordinate: (phase_circular, bar_index, level).

    phase_circular in [0,1): position within the bar on the metrical circle.
    bar_index: integer bar (from downbeats). level: 0 == tatum level (v0, all
    units are tatum level). Returns arrays aligned to slots [i, i+1).
    """
    starts = tatum_boundaries[:-1]
    beat_samp = grid.beats
    down_samp = grid.downbeats if len(grid.downbeats) else beat_samp[::grid.beats_per_bar]
    bpb = max(grid.beats_per_bar, 1)

    # For each slot start: enclosing beat index and fractional position in beat.
    bi = np.searchsorted(beat_samp, starts, side="right") - 1
    bi = np.clip(bi, 0, len(beat_samp) - 2)
    beat_lo = beat_samp[bi]
    beat_hi = beat_samp[bi + 1]
    frac_in_beat = (starts - beat_lo) / np.maximum(beat_hi - beat_lo, 1)

    # Beat position within its bar: beats since most recent downbeat, mod bpb.
    db_idx = np.searchsorted(down_samp, beat_lo, side="right") - 1
    db_idx = np.clip(db_idx, 0, len(down_samp) - 1)
    # count beats between the governing downbeat and this beat
    beat_of_down = np.searchsorted(beat_samp, down_samp[db_idx], side="left")
    beat_in_bar = (bi - beat_of_down) % bpb

    phase = ((beat_in_bar + frac_in_beat) / bpb) % 1.0
    bar_index = db_idx.astype(np.int64)
    level = np.zeros(len(starts), dtype=np.int64)  # tatum level
    return phase.astype(np.float64), bar_index, level
