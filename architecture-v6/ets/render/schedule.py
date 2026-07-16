"""The Schedule contract (spec §11 input; gauge per spec §3, §5 T5).

A ``Schedule`` is the ONLY input the render consumes besides the source units
themselves. It is produced by the writer / equilibrium-object (other builders);
this module fixes its SHAPE so the render can be written against it now.

A Schedule is two things and nothing else:

  1. PLACEMENT — an assignment of SOURCE UNITS -> OUTPUT SLOTS on the output beat
     grid, each carrying its SETTLED MASS. ``placements`` says, for each output
     slot, which source (track, unit) is laid there and with what settled
     amplitude. This is the whole "what goes where, how loud" content; the render
     only *applies* it (I-11).

  2. GAUGE, PER SECTION — a global transposition, beat-phase shift, and loudness
     scale (spec §3 gauge group) attached to a contiguous run of output slots.
     The gauge is SECTION-GLOBAL by construction: ``Gauge`` has no per-unit field
     and the render has no way to ask for one. This is spec §5 T5 compiled in:
     "per-section global transposition/phase choice; never per-unit chromatic
     correction." A per-unit chromatic correction is not merely discouraged here
     — it is unrepresentable.

MASS IS NOT GAUGE. The per-placement ``mass`` is SETTLEMENT OUTPUT — the settled
energy of the (slot, band) cell the placement realizes, expressed as the
amplitude factor that conserves the slot's settled mass (see realize()). It is
part of "what the equilibrium said", exactly like which unit goes where; the
render applies it multiplicatively with the section gauge loudness. The gauge
loudness_scale remains the ONLY loudness the gauge group acts with, and it stays
section-global (spec §5 T5): mass is not a per-unit gauge field, it is the
settled field itself reaching the tape. A writer that wanted a per-unit gauge
correction still has no representation for one.

The output grid is expressed in output-sample indices (``slot_boundaries``); the
grid IS the master clock of the output tape (spec §1). Nothing here scores,
ranks, or selects — a Schedule is inert data.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple
import numpy as np

# One placement row = "at output slot ``out_slot`` lay source unit
# (src_track, src_unit) at settled amplitude ``mass``, governed by section
# ``section``". No gauge field lives here: gauge is section-global (spec §5 T5),
# never per-placement. ``mass`` is not gauge — it is settlement output (the
# settled energy of the placement's (slot, band) cell, carried as the amplitude
# factor that conserves the slot's settled mass; see module docstring and
# ets.writer.realize). mass = 1.0 is the neutral value (hand-built schedules).
PLACEMENT_DTYPE = np.dtype([
    ("out_slot", np.int64),   # index into the output grid's slots
    ("src_track", np.int64),  # source Track id
    ("src_unit", np.int64),   # source unit id within that track
    ("section", np.int64),    # index into ``sections`` governing this placement
    ("mass", np.float64),     # settled amplitude factor (settlement output)
])


@dataclass(frozen=True)
class Gauge:
    """A section-global gauge frame (spec §3 gauge group action).

    transpose_semitones : global transposition on the pitch-class circle.
    phase_shift         : beat-phase shift, as a fraction of the governed output
                          slot (grid-relative, dimensionless — a gauge quantity,
                          not a wall-clock offset). The render turns it into a
                          sample offset using each placement's own slot length.
    loudness_scale      : loudness scale (>= 0).

    There is deliberately NO per-unit field. The gauge is applied identically to
    every unit in its section (spec §5 T5). ``IDENTITY`` is the neutral element.
    """
    transpose_semitones: float = 0.0
    phase_shift: float = 0.0
    loudness_scale: float = 1.0

    def __post_init__(self):
        if not np.isfinite(self.transpose_semitones):
            raise ValueError("transpose_semitones must be finite")
        if not np.isfinite(self.phase_shift):
            raise ValueError("phase_shift must be finite")
        if not (np.isfinite(self.loudness_scale) and self.loudness_scale >= 0.0):
            raise ValueError("loudness_scale must be finite and >= 0")


IDENTITY = Gauge()  # no transpose, no phase shift, unit loudness


@dataclass(frozen=True)
class Section:
    """A contiguous run of output slots [out_slot_start, out_slot_end) under one
    gauge. Sections carry the gauge; placements only reference a section by index.
    """
    section_id: int
    out_slot_start: int   # inclusive
    out_slot_end: int     # exclusive
    gauge: Gauge


@dataclass
class Schedule:
    """Assignment of source units -> output slots + per-section gauge (spec §11).

    Fields:
      sr              : output sample rate.
      slot_boundaries : (n_out_slots + 1,) int64 output-grid sample indices,
                        strictly monotone. slot s spans
                        [slot_boundaries[s], slot_boundaries[s+1]).
      placements      : structured array (PLACEMENT_DTYPE).
      sections        : tuple[Section, ...], indexed by placement['section'].

    Validation (in __post_init__) makes malformed schedules unconstructable:
    strictly-monotone grid, in-range slots, and every placement's section must
    actually govern that placement's slot. Nothing here is a runtime "choice";
    it is a well-formedness contract.
    """
    sr: int
    slot_boundaries: np.ndarray
    placements: np.ndarray
    sections: Tuple[Section, ...]

    def __post_init__(self):
        self.slot_boundaries = np.ascontiguousarray(self.slot_boundaries, dtype=np.int64)
        self.placements = np.ascontiguousarray(self.placements, dtype=PLACEMENT_DTYPE)
        self.sections = tuple(self.sections)

        b = self.slot_boundaries
        if b.ndim != 1 or len(b) < 2:
            raise ValueError("slot_boundaries must be a 1-D array of >= 2 samples")
        if not np.all(np.diff(b) > 0):
            raise ValueError("slot_boundaries must be strictly monotone (a valid "
                             "output tiling; mirrors the ingest grid law)")
        n_slots = len(b) - 1

        if len(self.sections) == 0:
            raise ValueError("a schedule needs at least one section (the gauge)")
        for k, sec in enumerate(self.sections):
            if not isinstance(sec.gauge, Gauge):
                raise TypeError("section gauge must be a Gauge (section-global; "
                                "no per-unit gauge exists, spec §5 T5)")
            if not (0 <= sec.out_slot_start < sec.out_slot_end <= n_slots):
                raise ValueError(f"section {k} range out of grid bounds")

        p = self.placements
        if len(p) == 0:
            return
        if not np.all(np.isfinite(p["mass"])) or not np.all(p["mass"] >= 0.0):
            raise ValueError("placement mass must be finite and >= 0 (settled "
                             "amplitude factor)")
        os = p["out_slot"]
        sid = p["section"]
        if not (np.all(os >= 0) and np.all(os < n_slots)):
            raise ValueError("placement out_slot out of grid bounds")
        if not (np.all(sid >= 0) and np.all(sid < len(self.sections))):
            raise ValueError("placement section index out of range")
        sec_start = np.array([s.out_slot_start for s in self.sections], np.int64)
        sec_end = np.array([s.out_slot_end for s in self.sections], np.int64)
        if not (np.all(sec_start[sid] <= os) and np.all(os < sec_end[sid])):
            raise ValueError("a placement's section does not govern its out_slot "
                             "(gauge/section binding broken)")

    @property
    def n_out_slots(self) -> int:
        return len(self.slot_boundaries) - 1

    @property
    def total_samples(self) -> int:
        return int(self.slot_boundaries[-1])

    # -- the degenerate schedule: the render analogue of the G0 identity -------
    @classmethod
    def degenerate(cls, track) -> "Schedule":
        """Every unit of ``track`` at its OWN slot, identity gauge, output grid ==
        the track's own tatum grid. Rendering this must reproduce the track
        (the render analogue of the G0 reconstruction identity, spec §13).

        This is a *producer example*, not a render behavior: it hand-builds the
        trivial schedule the writer would emit for "play this track back".
        """
        bounds = np.ascontiguousarray(track.beat_grid.tatum_boundaries, np.int64)
        n_slots = len(bounds) - 1
        u = track.units
        p = np.zeros(len(u), dtype=PLACEMENT_DTYPE)
        p["out_slot"] = u["slot"]
        p["src_track"] = track.track_id
        p["src_unit"] = u["unit_id"]
        p["section"] = 0
        p["mass"] = 1.0          # neutral: playback carries no settled field
        sections = (Section(0, 0, n_slots, IDENTITY),)
        return cls(sr=track.sr, slot_boundaries=bounds, placements=p, sections=sections)
