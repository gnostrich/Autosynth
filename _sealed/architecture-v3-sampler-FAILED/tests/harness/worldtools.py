"""Test scaffolding: small synthetic worlds + world files for engine/harness
tests (fast, audio-free corpus: unit audio is seeded noise, one unit-length
buffer per (track, unit) — enough to exercise settle→sample→thread→render→
provenance end to end).

Also provides an INLINE σ_φ measurement for synthetic worlds: it RUNS the
untilted writer and measures the per-bar fluctuation of each φ — a measured
quantity for the test world, never an invented scale (the REGISTERED corpus
calibration artifact is a separate instrument owned by ets.calibration; tests
must not depend on it).
"""
from __future__ import annotations
import numpy as np

from ets.ingestion.pipeline import synthetic_track
from ets import writer as W
from ets.render import SourceUnit, SourceUnitBank
from ets.writer.stream import StreamWriter
from ets.writer.tilt import untilted


def build_synthetic_world(n_tracks: int = 4, n_slots: int = 24, seed: int = 0):
    tracks = [synthetic_track(track_id=t, n_slots=n_slots, seed=seed + t)
              for t in range(n_tracks)]
    return W.build_world_from_tracks(tracks, sigma=0.5)


def embedded_bank_for(world, seed: int = 1234) -> SourceUnitBank:
    """One seeded-noise buffer per real unit, unit length = the world's output
    tatum (equal lengths -> identity-stretch render path; fast)."""
    rng = np.random.default_rng(seed)
    L = int(world.out_tatum_len)
    bank = SourceUnitBank(sr=int(world.sr))
    for tr in world.tracks:
        for uid in tr.units["unit_id"].astype(int):
            bank.add(SourceUnit(track_id=int(tr.track_id), unit_id=int(uid),
                                band=0, src_start=0, src_end=L,
                                audio=rng.standard_normal(L), sr=int(world.sr)))
    return bank


def measure_sigma_inline(world, n_bars: int = 24, seed: int = 7) -> dict:
    """MEASURED per-observable fluctuation of φ under the untilted writer
    (T_s=1), for THIS synthetic world. ddof=1 std over the per-bar samples."""
    w = StreamWriter(world, seed=seed)
    t0 = untilted(world.M)
    phis = [w.write_bar(tilt=t0).phi for _ in range(n_bars)]
    region = np.stack([np.asarray(p["region"], float) for p in phis])
    return {
        "region": np.std(region, axis=0, ddof=1).tolist(),
        "density": float(np.std([p["density"] for p in phis], ddof=1)),
        "cont": float(np.std([p["cont"] for p in phis], ddof=1)),
        "gauge": float(np.std([p["gauge"] for p in phis], ddof=1)),
        "novelty": float(np.std([p["novelty"] for p in phis], ddof=1)),
        "meta": {"kind": "inline-test-measurement", "n_bars": n_bars,
                 "seed": seed},
    }


def write_synthetic_worldfile(path: str, seed: int = 0,
                              with_sigma: bool = True) -> str:
    """A complete .etsworld artifact (embedded bank + measured σ_φ)."""
    from ets.engine.worldfile import save_world
    world = build_synthetic_world(seed=seed)
    bank = embedded_bank_for(world)
    sigma = measure_sigma_inline(world) if with_sigma else None
    return save_world(path, world, {"kind": "embedded", "bank": bank},
                      sigma_phi=sigma)
