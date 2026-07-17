"""Pure display models for the instrument half (no Qt, no trained-object import).

Everything here READS data the engine already produced and turns it into facts a
widget can paint:

  * provenance segments  → which (source-track, source-unit) cells sound, where;
  * a playhead sample    → what is sounding "now" (the now-playing readout);
  * per-source-track activity → which pads light up, and in what colour.

CRITICAL BOUNDARY (F3-B door): this module imports NOTHING from ets.render /
ets.engine / ets.writer / ets.functional / ets.geometry. It consumes a
provenance-shaped numpy STRUCTURED ARRAY by COLUMN NAME. The column-name
contract (`_PROV_FIELDS`) is a read-side agreement, not an import — so no monitor
code path can reach settlement, F, render, or provenance-generation. The engine
produces `ets.render.provenance.PROV_SEG_DTYPE`; we only read its columns.

Grouping honesty (a disclosed wall — see PREREG-feature3.md report): the pad
grid keys on SOURCE TRACK, because that is what provenance natively carries and
what the tape diagram colours by. The region-tilt LANE is over anchors, not
tracks; the two indices do not join in any state the engine emits (provenance
carries track/unit; occupancy carries anchor/slot), so pad light-up (track) and
the region tap surface (anchor) are kept as the two honest, separately-sourced
views rather than fabricating a track→anchor join out of the trained geometry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# The provenance columns we read. A NAME contract with
# ets.render.provenance.PROV_SEG_DTYPE, deliberately NOT an import of it.
_PROV_FIELDS: Tuple[str, ...] = (
    "out_start", "out_end", "src_track", "src_unit", "mass")


@dataclass(frozen=True)
class SoundingCell:
    """One provenance segment as a display fact: a source unit that contributed
    to output samples [out_start, out_end) with a settled mass (amplitude)."""
    src_track: int
    src_unit: int
    out_start: int
    out_end: int
    mass: float


def _as_prov_array(segments) -> np.ndarray:
    seg = np.asarray(segments)
    names = seg.dtype.names
    if names is None or not set(_PROV_FIELDS) <= set(names):
        raise TypeError(
            "segments is not a provenance-shaped structured array "
            f"(need columns {_PROV_FIELDS}, got {names})")
    return seg


def sounding_cells(segments) -> List[SoundingCell]:
    """Every provenance segment as a `SoundingCell` (read-only projection)."""
    seg = _as_prov_array(segments)
    return [SoundingCell(int(r["src_track"]), int(r["src_unit"]),
                         int(r["out_start"]), int(r["out_end"]), float(r["mass"]))
            for r in seg]


def cells_at(segments, sample: int) -> List[SoundingCell]:
    """The cells sounding AT one output sample (the playhead). Many-to-one:
    overlap-add means several units may cover the same sample."""
    s = int(sample)
    seg = _as_prov_array(segments)
    mask = (seg["out_start"] <= s) & (s < seg["out_end"])
    hit = seg[mask]
    return [SoundingCell(int(r["src_track"]), int(r["src_unit"]),
                         int(r["out_start"]), int(r["out_end"]), float(r["mass"]))
            for r in hit]


# --- colour: a stable palette keyed by source track (the tape-diagram colours) -
# Deterministic per track id (golden-angle hue walk); no per-input tuning, no
# hidden state. Returned as 0..255 RGB so a Qt widget or a test can use it.
def track_palette(track_id: int) -> Tuple[int, int, int]:
    h = (int(track_id) * 0.61803398875) % 1.0          # golden-angle hue
    # simple HSV(h, 0.65, 0.95) → RGB, integer, dependency-free.
    s, v = 0.65, 0.95
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    r, g, b = [(v, t, p), (q, v, p), (p, v, t),
               (p, q, v), (t, p, v), (v, p, q)][i % 6]
    return int(r * 255), int(g * 255), int(b * 255)


@dataclass
class PadModel:
    """Material as MPC-style pads — ONE per SOURCE TRACK (F3.1). Pads light from
    provenance the engine already emits; a decay makes the light 'breathe' with
    real-time activity. Pure display: no lane, no emit, no writer.

    `observe(cells)` folds the currently-sounding cells into a per-track activity
    level (summed settled mass, normalised). `decay(factor)` eases the lights
    down between observations so a pad that just stopped fades rather than snaps.
    """
    activity: Dict[int, float] = field(default_factory=dict)   # track_id → 0..1
    _peak: float = 1e-9                                          # running mass norm

    @property
    def tracks(self) -> List[int]:
        return sorted(self.activity)

    def decay(self, factor: float = 0.6) -> None:
        for t in list(self.activity):
            self.activity[t] *= float(factor)

    def observe(self, cells: Sequence[SoundingCell]) -> None:
        """Fold a set of sounding cells into pad activity. A track absent from
        `cells` keeps its (decayed) level; a track present adds its mass."""
        by_track: Dict[int, float] = {}
        for c in cells:
            by_track[c.src_track] = by_track.get(c.src_track, 0.0) + c.mass
        if by_track:
            self._peak = max(self._peak, max(by_track.values()))
        for t, m in by_track.items():
            lvl = self.activity.get(t, 0.0) + m / self._peak
            self.activity[t] = float(min(1.0, lvl))

    def lit(self, threshold: float = 1e-3) -> List[int]:
        """Track ids whose pad is currently lit (activity above threshold)."""
        return sorted(t for t, a in self.activity.items() if a > threshold)

    def colour(self, track_id: int) -> Tuple[int, int, int]:
        return track_palette(track_id)


@dataclass
class TapeModel:
    """The scrolling output tape / now-playing strip (F3.3).

    Holds the provenance of the produced output (committed + settled frontier)
    and a playhead sample. Cells are coloured by source track from their existing
    provenance tag; the now-playing readout is DRIVEN by provenance (cells_at),
    never recomputed from the writer.
    """
    segments: object = None                 # provenance-shaped structured array
    n_samples: int = 0
    sr: int = 1
    committed_samples: int = 0              # [0, committed) = committed past;
                                            # [committed, n_samples) = L-bar frontier
    playhead: int = 0

    def set_provenance(self, segments, n_samples: int, sr: int) -> None:
        self.segments = _as_prov_array(segments)
        self.n_samples = int(n_samples)
        self.sr = int(sr)

    def set_frontier(self, committed_samples: int) -> None:
        self.committed_samples = int(committed_samples)

    def set_playhead(self, sample: int) -> None:
        self.playhead = int(max(0, min(self.n_samples, sample)))

    def now_playing(self) -> List[SoundingCell]:
        """Cells sounding at the playhead — the now-playing readout (provenance,
        not recomputed)."""
        if self.segments is None:
            return []
        return cells_at(self.segments, self.playhead)

    def now_playing_tracks(self) -> List[int]:
        return sorted({c.src_track for c in self.now_playing()})

    def cell_spans(self):
        """(track, unit, out_start, out_end, colour) for every cell — the tape
        cells a widget draws, coloured by source track."""
        out = []
        for c in sounding_cells(self.segments) if self.segments is not None else []:
            out.append((c.src_track, c.src_unit, c.out_start, c.out_end,
                        track_palette(c.src_track)))
        return out


@dataclass
class MonitorState:
    """The read-only monitor bundle shared by the instrument widgets. A feeder
    (offline render result, or an in-process production tap) writes into this;
    the widgets read it. It holds NO handle to the writer/emitter — it is the
    display counterpart to ets.panel.meters.MeterState."""
    pads: PadModel = field(default_factory=PadModel)
    tape: TapeModel = field(default_factory=TapeModel)
    write_frontier_bar: int = 0            # highest settled bar (monitor readout)
    playhead_bar: int = 0                  # where the transport is listening
