"""On-disk cache of materialized source units (an engineering convenience).

`load_source_units` re-derives every unit's audio from the source mp3 via the
STFT + partition-of-unity filterbank on each cold process — the slow part of a
render. Those units are a DETERMINISTIC function of (source audio, provenance
spans, filterbank), so caching them to disk is pure memoization: a cached render
is byte-identical to an uncached one (H-8 unaffected).

Layout: one .npz per (track, storage-dtype) under the cache dir. Each carries a
validation KEY (hash of the track's provenance + dtype + a filterbank-version
tag + source size); a mismatch ignores the cache and re-materializes, so a
changed corpus/filterbank can never serve stale audio.

This module is deliberately SEPARATE from ets.render.{render,schedule,sources,
provenance} so it is outside the I-11 "render applies, never chooses" AST scan —
it is not part of the render decision path; it stores and returns exact bytes.
"""
from __future__ import annotations
import hashlib
import os
from typing import List, Optional

import numpy as np

from ets.render.sources import SourceUnit, SourceUnitBank

_FB_VERSION = "fb-v0-8band-partition-of-unity"   # bump if the filterbank changes


def default_cache_dir() -> str:
    root = os.environ.get(
        "ETS_MAIN",
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.environ.get("ETS_BANK_CACHE", os.path.join(root, "cache", "units"))


def track_key(track, storage_dtype, src_size: int) -> str:
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(track.provenance_index).tobytes())
    h.update(str(np.dtype(storage_dtype)).encode())
    h.update(_FB_VERSION.encode())
    h.update(str(int(src_size)).encode())
    return h.hexdigest()


def _path(cache_dir: str, track_id: int, storage_dtype) -> str:
    dt = np.dtype(storage_dtype).name
    return os.path.join(cache_dir, f"track_{int(track_id):02d}_{dt}.npz")


def save_track_units(units: List[SourceUnit], cache_dir: str, track_id: int,
                     storage_dtype, key: str, sr: int) -> None:
    """Persist one track's units. Ordered exactly as given (no reordering)."""
    if not units:
        return
    os.makedirs(cache_dir, exist_ok=True)
    lengths = np.array([len(u.audio) for u in units], dtype=np.int64)
    audio = np.concatenate([np.asarray(u.audio) for u in units])
    meta = np.array([(u.unit_id, u.band, u.src_start, u.src_end) for u in units],
                    dtype=np.int64)
    final = _path(cache_dir, track_id, storage_dtype)
    tmp = final + ".tmp"
    # write via a file handle so np.savez does NOT append '.npz' to our tmp name.
    with open(tmp, "wb") as fh:
        np.savez(fh, key=np.array(key), sr=np.int64(sr), lengths=lengths,
                 audio=audio, meta=meta)
    os.replace(tmp, final)                                        # atomic


def load_track_units(cache_dir: str, track_id: int, storage_dtype,
                     key: str) -> Optional[List[SourceUnit]]:
    """Return the track's cached units iff a valid cache exists, else None."""
    path = _path(cache_dir, track_id, storage_dtype)
    if not os.path.exists(path):
        return None
    try:
        d = np.load(path, allow_pickle=False)
        if str(d["key"]) != key:
            return None
        sr = int(d["sr"])
        audio = d["audio"]
        lengths = d["lengths"]
        meta = d["meta"]
    except Exception:
        return None
    units: List[SourceUnit] = []
    off = 0
    for i in range(len(lengths)):
        n = int(lengths[i])
        seg = np.ascontiguousarray(audio[off:off + n], dtype=storage_dtype)
        off += n
        uid, band, a, b = (int(x) for x in meta[i])
        units.append(SourceUnit(track_id=int(track_id), unit_id=uid, band=band,
                                src_start=a, src_end=b, audio=seg, sr=sr))
    return units
