"""Run the G0 gate (spec §13) over the corpus.

Ingests each track, runs beat-clock sanity + reconstruction identity, caches a
compact Track (.npz), and writes per-track + summary records to g0_results.json.

PREREG discipline (builder rule 4): the G0 entry in PREREG.md and its
REGISTRY.jsonl line MUST be committed BEFORE this is run. This script only
executes the pre-registered procedure and records outcomes.

Lean-memory: one track's audio at a time; caches descriptors only (no raw audio).
"""
from __future__ import annotations
import os, sys, glob, json, time, gc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ets.ingestion import g0
from ets.ingestion import pipeline

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = sorted(glob.glob(os.path.join(ROOT, "corpus", "*.mp3")))
CACHE = os.path.join(ROOT, "cache", "ingest")
RESULTS = os.path.join(ROOT, "g0_results.json")


def main(limit=None):
    os.makedirs(CACHE, exist_ok=True)
    records = []
    tracks = CORPUS if limit is None else CORPUS[:limit]
    for tid, path in enumerate(tracks):
        t0 = time.time()
        try:
            track, rec = g0.evaluate(path, track_id=tid)
            pipeline.save(track, os.path.join(CACHE, f"track_{tid:02d}.npz"))
            rec["seconds"] = round(time.time() - t0, 1)
            rec["error"] = None
        except Exception as e:  # a wall (e.g. no measurable pulse) is recorded, not patched
            rec = {"track_id": tid, "path": path, "error": f"{type(e).__name__}: {e}",
                   "G0_pass": False, "seconds": round(time.time() - t0, 1)}
        records.append(rec)
        print(f"[{tid:02d}] {os.path.basename(path)[:40]:40s} "
              f"pass={rec.get('G0_pass')} recon_dB={rec.get('recon_db')} "
              f"align_ms={rec.get('median_align_ms')} pulse={rec.get('pulse_present')} "
              f"{rec.get('seconds')}s")
        gc.collect()

    summary = {
        "n_tracks": len(records),
        "n_pass": int(sum(bool(r.get("G0_pass")) for r in records)),
        "worst_recon_rel_l2": max((r.get("recon_rel_l2", 0.0) for r in records
                                   if r.get("recon_rel_l2") is not None), default=None),
        "worst_align_ms": max((r.get("median_align_ms", 0.0) for r in records
                               if r.get("median_align_ms") not in (None, float("inf"))),
                              default=None),
        "tol_recon_rel_l2": g0.RECON_TOL_RELL2,
        "tol_align_ms": g0.ALIGN_TOL_MS,
        "reg_frac_min": g0.REG_FRAC_MIN,
    }
    out = {"summary": summary, "records": records}
    with open(RESULTS, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nSUMMARY", json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(lim)
