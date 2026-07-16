"""Track object (spec §2 schema) and within-track cost structure.

Schema (verbatim spec §2):
  { units, masses, C_timbre, C_pitchclass (quotiented by transposition),
    C_metrical (circular), beat_grid, provenance_index }

Two invariants are compiled in here (spec §14):

I-2  gauge law — no coordinate crosses a track boundary; only normalized
     intrinsic cost structure exists. Enforced structurally: every CostStructure
     is bound to ONE track_id, holds a PRIVATE descriptor array, exposes cost
     only for within-track index pairs, is normalized within-track (so absolute
     coordinate magnitude — a gauge quantity — cannot leak), and pitch/phase are
     quotiented by their gauge group. ``require_within_track`` is the single
     sanctioned combiner and raises across tracks.

I-12 provenance — every unit resolves to (track, unit, source-span) via
     provenance_index; ``assert_provenance_complete`` is the executable check.

Units carry ONLY the metrical coordinate (phase, bar, level) downstream; the
wall-clock sample span lives exclusively in provenance_index (spec §2 step 2).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np

# Columnar dtype for units: metrical coordinate + band/slot identity. NO sample
# span here (that is provenance-only), NO raw audio (recomputable from source).
UNIT_DTYPE = np.dtype([
    ("unit_id", np.int64),
    ("slot", np.int64),      # tatum slot index within the track
    ("band", np.int64),      # filterbank band index
    ("phase", np.float64),   # metrical position on the circle, [0,1)
    ("bar", np.int64),       # bar index
    ("level", np.int64),     # metrical level (0 == tatum, v0)
])

PROV_DTYPE = np.dtype([
    ("unit_id", np.int64),
    ("track_id", np.int64),
    ("src_start", np.int64),  # source sample span [src_start, src_end)
    ("src_end", np.int64),
    ("band", np.int64),       # transform applied at ingestion: filterbank band
])


def _rms_pairwise_normalizer(cost_fn, n: int, rng: np.random.Generator,
                             n_pairs: int = 2000) -> float:
    """Robust within-track scale from a random subsample of pairs (O(n_pairs)).

    Avoids any N^2 materialization. Returns an RMS-of-cost scale so that after
    dividing, the typical within-track cost is ~1 (normalized intrinsic
    structure, I-2)."""
    if n < 2:
        return 1.0
    i = rng.integers(0, n, size=n_pairs)
    j = rng.integers(0, n, size=n_pairs)
    m = i != j
    if not np.any(m):
        return 1.0
    d = np.array([cost_fn(int(a), int(b)) for a, b in zip(i[m], j[m])])
    d = d[np.isfinite(d)]
    s = float(np.sqrt(np.mean(d ** 2))) if len(d) else 1.0
    return s if s > 0 else 1.0


@dataclass
class CostStructure:
    """Within-track cost, represented as (private descriptors + a metric).

    The dense N-by-N matrix is never materialized (N ~ 1e4 makes it ~1 GB); the
    matrix is fully DETERMINED by ``desc`` + ``kind`` and reproducible via
    ``cost``/``row``. This is a representation choice, not a second authority: no
    coordinate leaves the track (bound track_id, private array, within-track
    normalization). ``materialize`` exists for small blocks / tests only.
    """
    track_id: int
    kind: str                    # "timbre" | "pitchclass" | "metrical"
    desc: np.ndarray             # (n_units, d) PRIVATE descriptors
    _normalizer: float = 1.0

    @property
    def n(self) -> int:
        return self.desc.shape[0]

    def _raw(self, i: int, j: int) -> float:
        if self.kind == "timbre":
            return float(np.linalg.norm(self.desc[i] - self.desc[j]))
        if self.kind == "pitchclass":
            # transposition quotient: min over the 12 cyclic rotations
            a, b = self.desc[i], self.desc[j]
            best = np.inf
            for r in range(12):
                d = np.linalg.norm(a - np.roll(b, r))
                if d < best:
                    best = d
            return float(best)
        if self.kind == "metrical":
            # circular distance on the metrical circle, in [0,2]
            dphi = 2.0 * np.pi * (float(self.desc[i, 0]) - float(self.desc[j, 0]))
            return float(1.0 - np.cos(dphi))
        raise ValueError(self.kind)

    def cost(self, i: int, j: int) -> float:
        """Normalized within-track cost between units i and j (same track)."""
        return self._raw(i, j) / self._normalizer

    def row(self, i: int) -> np.ndarray:
        return np.array([self.cost(i, j) for j in range(self.n)])

    def materialize(self, cap: int = 4000) -> np.ndarray:
        if self.n > cap:
            raise MemoryError(
                f"refusing to materialize {self.n}x{self.n} cost (cap {cap}); "
                "use cost()/row() — the matrix is implicit by design (I-2)")
        M = np.zeros((self.n, self.n))
        for i in range(self.n):
            for j in range(self.n):
                M[i, j] = self.cost(i, j)
        return M

    @classmethod
    def build(cls, track_id: int, kind: str, desc: np.ndarray,
              rng: Optional[np.random.Generator] = None) -> "CostStructure":
        rng = rng or np.random.default_rng(track_id)
        cs = cls(track_id=track_id, kind=kind, desc=np.ascontiguousarray(desc))
        cs._normalizer = _rms_pairwise_normalizer(cs._raw, cs.n, rng)
        return cs


def require_within_track(a: CostStructure, b: CostStructure) -> None:
    """The ONLY sanctioned way to relate two cost structures. Raises across
    tracks — no coordinate/cost may bridge a track boundary (I-2)."""
    if a.track_id != b.track_id:
        raise ValueError(
            f"cross-track cost forbidden (I-2): {a.track_id} != {b.track_id}")


@dataclass
class Track:
    track_id: int
    units: np.ndarray            # structured, UNIT_DTYPE
    masses: np.ndarray           # (n_units,) float, perceptual energy/salience
    C_timbre: CostStructure
    C_pitchclass: CostStructure  # quotiented by transposition
    C_metrical: CostStructure    # circular
    beat_grid: object            # BeatGrid
    provenance_index: np.ndarray # structured, PROV_DTYPE
    n_samples: int               # source length (for provenance bounds check)
    sr: int


def assert_provenance_complete(track: Track) -> None:
    """I-12: every unit resolves to (track, unit, source-span), spans valid."""
    u = track.units
    p = track.provenance_index
    assert len(p) == len(u), "provenance rows != units"
    assert np.array_equal(np.sort(u["unit_id"]), np.arange(len(u))), \
        "unit_ids must cover range(n_units) exactly"
    assert np.array_equal(p["unit_id"], u["unit_id"]), "provenance unit_id misaligned"
    assert np.all(p["track_id"] == track.track_id), "provenance track_id mismatch"
    assert np.all(p["src_start"] < p["src_end"]), "empty/negative source span"
    assert np.all(p["src_start"] >= 0) and np.all(p["src_end"] <= track.n_samples), \
        "source span out of source bounds"
    assert np.array_equal(p["band"], u["band"]), "provenance band misaligned"
