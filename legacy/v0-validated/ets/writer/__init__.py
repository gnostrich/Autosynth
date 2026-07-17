"""Batch (non-causal) writer: the reduced form of the streaming writer for the
"lanes constant" case with u=0 (connector: THE TAPE PORT).

The output tape is the (N+1)-th TRACK-TYPED boundary node, coupled through the
SAME frozen anchor star as the ingested tracks. There is NO decoder: the tape's
settled coupling IS the arrangement, emitted as the render's existing ``Schedule``
contract. The pieces:

  tape.py     — the track-typed node schema + clamp interface (I-7).
  settle.py   — batch settlement of the tape's free cells to an F-descent
                certificate (u=0), reusing f.py's terms + solver's dF/dO.
  realize.py  — the settled occupancy read out as a Schedule (no static keymap).

``generate_batch`` runs settle -> realize and returns the Schedule plus the
F-descent evidence; ``ets.render.render`` executes it into audio + provenance.

The streaming causal writer (spec §7: MZ frontier settlement, per-step stability
certificate, I-8) is a LATER refinement built on this same node and clamp
interface — the batch first sample settles the whole tape at once.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np

from ..functional import anchors as an
from ..geometry import roles
from .tape import OutputGrid, ClampSet, TapeNode, S_PHASE
from .settle import settle_tape, SettleResult
from .realize import build_index, realize, RealizationIndex

__all__ = [
    "OutputGrid", "ClampSet", "TapeNode", "S_PHASE",
    "settle_tape", "SettleResult",
    "build_index", "realize", "RealizationIndex",
    "World", "build_world_from_tracks", "generate_batch",
]


@dataclass
class World:
    """The frozen world the tape settles against: anchors (in ``fstate``) plus the
    per-track prototypes/Tracks needed to materialize roles. Frozen at world-freeze
    (step c); the tape may READ it but grants it no structural authority."""
    fstate: object                 # FState with frozen D, a, B, theta
    protos: list                   # per-track Prototypes
    tracks: list                   # per-track Track
    info: dict                     # build_world diagnostics
    index: RealizationIndex        # role materialization index (built once)
    out_tatum_len: int             # representative output tatum length (samples)
    sr: int

    @property
    def M(self) -> int:
        return int(self.fstate.a.shape[0])


def _representative_tatum_len(tracks) -> int:
    """A representative output tatum length = median over tracks of each track's
    median tatum duration (samples). The output grid is a real metrical clock; this
    keeps output slots the size of real sound-units so most placements need little
    or no stretch."""
    meds = []
    for t in tracks:
        d = np.diff(np.asarray(t.beat_grid.tatum_boundaries, np.int64))
        d = d[d > 0]
        if d.size:
            meds.append(float(np.median(d)))
    return int(round(float(np.median(meds)))) if meds else 22050


def build_world_from_tracks(tracks, sigma: Optional[float] = None,
                            seed: int = 0, sweeps: int = 8) -> World:
    """Freeze the world from ingested tracks: prototypes -> self-sized anchors
    (step c, ``anchors.build_world``) -> role materialization index. ``sigma`` is
    the frozen corpus affinity scale; None uses this set's median (standalone)."""
    protos = [roles.extract_prototypes(t, seed=seed) for t in tracks]
    if sigma is None:
        D = roles.role_distance_matrix(protos)
        off = D[~np.eye(len(D), dtype=bool)]
        sigma = float(np.median(off)) if off.size else 1.0
    fstate, info = an.build_world(protos, seed=seed, sweeps=sweeps, sigma=sigma)
    index = build_index(fstate, protos, tracks)
    return World(fstate=fstate, protos=protos, tracks=tracks, info=info,
                 index=index, out_tatum_len=_representative_tatum_len(tracks),
                 sr=int(tracks[0].sr))


def generate_batch(world: World, seconds: float, u: Optional[np.ndarray] = None,
                   clamps: Optional[ClampSet] = None, band_frac: float = 0.15,
                   max_iter: int = 600) -> dict:
    """Settle a ``seconds``-long output tape in batch (u=0) and realize a Schedule.

    Returns a dict with the ``schedule`` (render input), the ``settle`` result
    (F-descent trace + certificate), the ``tape`` node, and realization ``meta``.
    ``clamps`` is the SINGLE intervention channel (I-7); default = none clamped.
    """
    grid = OutputGrid.for_seconds(world.sr, world.out_tatum_len, seconds)
    tape = TapeNode(grid=grid, M=world.M, clamps=clamps or ClampSet())
    res = settle_tape(world.fstate, tape, u=u, max_iter=max_iter)
    sched, meta = realize(res.O, tape, world.fstate, world.index, band_frac=band_frac)
    return {"schedule": sched, "settle": res, "tape": tape, "realize": meta,
            "grid": grid}
