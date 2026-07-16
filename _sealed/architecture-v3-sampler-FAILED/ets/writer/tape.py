"""The output tape as the (N+1)-th TRACK-TYPED boundary node (connector spec:
THE TAPE PORT).

The connector authority is normative here: "The output tape is the (N+1)-th
track-typed boundary node: identical schema to ingested tracks (units at metrical
slots under a gauge frame), coupled through the same anchor star." This module
fixes that node's SCHEMA and its CLAMP interface; the settlement (``settle.py``)
supplies its free cells and ``realize.py`` reads its coupling out as a Schedule.

Typing (why this is a track-typed node and NOT a decoder):
  * An INGESTED track reaches the anchors by its coupling ``pi_t : (K_t, M)`` and
    lays a FIXED per-prototype metrical-slot histogram ``q_t : (K_t, S)`` — so its
    occupancy ``O_t = pi_t^T q_t : (M, S)`` is fully determined (a fully CLAMPED
    instance).
  * The OUTPUT tape is the same object with the arrow reversed in WHO IS FREE:
    its per-slot role occupancy ``O_tape : (M, S_out)`` is the FREE variable the
    settlement solves, in the field of the SAME frozen anchors (D, a, B, theta).
    Its cells are settled, not clamped. There is NO readout head / world-to-audio
    net: the settled coupling IS the arrangement, and ``realize`` turns it into
    the render's existing ``Schedule`` contract. (connector (i))

The output grid is a real metrical grid (spec §1: the grid is the master clock).
Output slot ``s`` sits at metrical phase bin ``s % S`` — the tape is bar-clocked
exactly like an ingested track, so the frozen anchors' per-phase profile
``theta[:, s % S]`` is the equilibrium field each output bar settles against.

CLAMP INTERFACE (spec §7, invariant I-7 candidate). A clamped cell is the SAME
TYPE as a settled cell: an ``(M,)`` role-occupancy column at an output slot.
Committed past (streaming) and user demands ("this sample at bar 33") are ONE
intervention type — a boundary condition on the settlement — with NO exception
path and NO recovery mode. For the batch first sample nothing is clamped, but the
interface exists and is exercised, so it discharges I-7 structurally the moment a
demand is issued. A demand may be given at ROLE granularity (fix the column) or
at UNIT granularity (fix the exact source unit, whose role column is then implied
and whose realization is forced) — both are the same clamp species, injected
through this one object; there is no other placement-injection channel.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Tuple
import numpy as np

S_PHASE = 8  # metrical phase bins on the bar circle (matches roles.S_SLOTS / f)


@dataclass(frozen=True)
class OutputGrid:
    """The output tape's beat grid = its master clock (spec §1).

    Uniform tatum tiling: slot ``s`` spans ``[s*tatum_len, (s+1)*tatum_len)`` and
    sits at metrical phase bin ``s % S_phase``. This is the SAME kind of grid an
    ingested track carries (``BeatGrid.tatum_boundaries``), so the tape is a
    track-typed node down to its clock.
    """
    sr: int
    tatum_len: int          # output tatum length in samples
    n_slots: int            # S_out
    s_phase: int = S_PHASE

    @property
    def slot_boundaries(self) -> np.ndarray:
        return (np.arange(self.n_slots + 1, dtype=np.int64) * int(self.tatum_len))

    @property
    def total_samples(self) -> int:
        return int(self.n_slots) * int(self.tatum_len)

    def phase_of(self, s: int) -> int:
        return int(s) % int(self.s_phase)

    def phase_row(self) -> np.ndarray:
        """(n_slots,) metrical phase bin of every output slot."""
        return np.arange(self.n_slots, dtype=np.int64) % int(self.s_phase)

    @classmethod
    def for_seconds(cls, sr: int, tatum_len: int, seconds: float) -> "OutputGrid":
        n = max(1, int(round(seconds * sr / float(tatum_len))))
        return cls(sr=int(sr), tatum_len=int(tatum_len), n_slots=int(n))


@dataclass
class ClampSet:
    """The SINGLE intervention channel into the tape (I-7). Two same-species
    demand kinds, both boundary conditions on the one settlement:

      role_columns[s] = (M,) fixed role-occupancy column at output slot s.
      unit_demands[s] = (track_id, unit_id, band) forcing an exact source unit at
                        output slot s; its role column is implied (settled around).

    A ``unit_demands`` entry forces a fixed realization at that slot AND, if a
    matching ``role_columns`` entry is also supplied, pins that slot's occupancy.
    There is deliberately no third field and no bypass: to force anything onto the
    tape you clamp a cell here, exactly as committed history would.
    """
    role_columns: Dict[int, np.ndarray] = field(default_factory=dict)
    unit_demands: Dict[int, Tuple[int, int, int]] = field(default_factory=dict)

    def clamped_slots(self) -> set:
        return set(self.role_columns) | set(self.unit_demands)

    def as_mask_values(self, M: int, n_slots: int) -> Tuple[np.ndarray, np.ndarray]:
        """(mask (n_slots,) bool, values (M, n_slots)): the clamped columns as a
        boundary condition on O_tape. Only ``role_columns`` pin the occupancy;
        a bare ``unit_demand`` fixes realization but lets its column settle unless
        the caller also provided its role column."""
        mask = np.zeros(n_slots, dtype=bool)
        vals = np.zeros((M, n_slots), dtype=float)
        for s, col in self.role_columns.items():
            if not (0 <= s < n_slots):
                raise ValueError(f"clamped slot {s} out of tape bounds [0,{n_slots})")
            col = np.asarray(col, float).reshape(-1)
            if col.shape[0] != M:
                raise ValueError(f"clamp column at slot {s} has wrong role dim")
            mask[s] = True
            vals[:, s] = col
        for s in self.unit_demands:
            if not (0 <= s < n_slots):
                raise ValueError(f"clamped slot {s} out of tape bounds [0,{n_slots})")
        return mask, vals

    def is_empty(self) -> bool:
        return not self.role_columns and not self.unit_demands


@dataclass
class TapeNode:
    """The output-tape boundary node: track-typed schema + its clamp interface.

    Fields mirror an ingested track's role-side schema, coupled through the frozen
    anchor star:
      grid    : the output metrical grid (master clock).
      M       : anchor count (roles) — the shared support the tape couples through.
      clamps  : the single intervention channel (I-7).

    The free cells ``O_tape : (M, n_slots)`` are NOT stored here — they are the
    settlement's output. This object is the node's *type*, not its solved state.
    """
    grid: OutputGrid
    M: int
    clamps: ClampSet = field(default_factory=ClampSet)

    def phase_target(self, theta: np.ndarray, a: np.ndarray) -> np.ndarray:
        """The frozen anchor equilibrium tiled onto the output grid: the field the
        tape settles against. ``theta`` is (M, S_phase) and ``a`` is (M,); the
        result is ``a[k]*theta[k, s % S_phase]`` for every output slot s — the
        bar-periodic world profile, expressed on the tape's own clock."""
        phase = self.grid.phase_row()
        tgt = (a[:, None] * theta)[:, phase]      # (M, n_slots)
        return tgt
