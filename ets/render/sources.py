"""Source-unit materialization: the ``sources`` half of ``render``'s input.

The Track cache stores NO raw audio (spec §2: units are recomputable from the
source via the fixed filterbank). So the actual audio of each unit — the real
material the render lays down — is reconstructed here from (source audio + the
track's provenance spans + the filterbank). This reconstruction is DETERMINISTIC
and CHOICELESS: it is exactly the ingest-side band decomposition
(``fb.band_signal``) sliced to each unit's provenance span. It scores nothing and
selects nothing; it only *reproduces* the material the schedule will reference.

This is the render-path analogue of the G0 reconstruction: band k of the source
is ``istft(masked STFT)``; unit (slot, band)'s audio is that band on the unit's
sample span. Because the masks are a partition of unity, summing every band-unit
on a slot returns the source on that slot exactly.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple
import numpy as np

from ets.ingestion import filterbank as fb


@dataclass(frozen=True)
class SourceUnit:
    """One real source unit's audio + its identity/provenance."""
    track_id: int
    unit_id: int
    band: int
    src_start: int
    src_end: int
    audio: np.ndarray   # mono, float64, at sr; length == src_end - src_start
    sr: int


class SourceUnitBank:
    """A pool of real source units keyed by (track_id, unit_id). Inert lookup —
    the render asks it for material by identity; it never ranks or chooses."""

    def __init__(self, sr: int):
        self.sr = int(sr)
        self._units: Dict[Tuple[int, int], SourceUnit] = {}

    def add(self, su: SourceUnit) -> None:
        self._units[(su.track_id, su.unit_id)] = su

    def get(self, track_id: int, unit_id: int) -> SourceUnit:
        return self._units[(int(track_id), int(unit_id))]

    def __contains__(self, key) -> bool:
        return (int(key[0]), int(key[1])) in self._units

    def __len__(self) -> int:
        return len(self._units)


def load_source_units(track, audio: np.ndarray) -> SourceUnitBank:
    """Materialize every unit of ``track`` from its source ``audio``.

    Deterministic: STFT -> partition-of-unity bands -> slice each band on the
    unit's provenance span. No decision is taken; this is pure reconstruction.
    """
    sr = int(track.sr)
    y = np.asarray(audio, dtype=np.float64)
    S = fb.stft(y)
    masks = fb.partition_masks(sr)
    n_bands = masks.shape[0]
    bands = [fb.band_signal(S, masks, k, len(y)) for k in range(n_bands)]

    bank = SourceUnitBank(sr)
    prov = track.provenance_index
    for row in prov:
        uid = int(row["unit_id"])
        band = int(row["band"])
        a = int(row["src_start"])
        b = int(row["src_end"])
        seg = np.ascontiguousarray(bands[band][a:b], dtype=np.float64)
        bank.add(SourceUnit(track_id=track.track_id, unit_id=uid, band=band,
                            src_start=a, src_end=b, audio=seg, sr=sr))
    return bank
