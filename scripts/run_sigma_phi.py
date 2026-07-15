"""sigma_phi calibration pass [REGISTERED INSTRUMENT] — connector Layer 0.

Measures, for every Layer-0 tilt observable phi_i (ets.connector.phi; lane map
documented there), the equilibrium fluctuation sigma_phi_i under the UNTILTED
writer, and writes the artifact ets/calibration/sigma_phi.json that the engine
consumes via ets.calibration.load_sigma_phi().

WHY sigma IS THE NORMALIZER (FDT, the connector's own scaling law). The tilted
settlement measure per bar is p_lambda(a) prop. p_0(a) * exp(lambda * phi(a)).
Linear response at lambda = 0:

    d<phi>/d lambda |_0  =  Var_0(phi)        (fluctuation-dissipation)

so with the connector's lambda = u / sigma (sigma^2 = Var_0(phi)):

    d<phi>/d u |_0  =  Var_0(phi) / sigma  =  sigma.

A unit knob turn therefore leans the settled expectation of phi_i by exactly
ONE equilibrium standard deviation of phi_i — "knobs read in natural units:
standard fluctuations of lean". sigma (not the variance, not any hand scale)
is the unique normalizer with this property, and it also makes the tilt
invariant to any rescaling of phi's units.

ESTIMATOR (stated precisely):
  * Ensemble: the per-bar arrangements of ONE untilted (u=0) batch settlement,
    realized by the settled-field writer — the writer's actual equilibrium
    output ensemble. Tape length R = the corpus's own bar count (sum over the
    20 frozen tracks of each track's bar count): the ensemble size is the
    corpus evidence scale, not a hand constant. No burn-in is discarded: the
    run-seeding at bar 0 is the untilted writer's real behavior.
  * sigma_phi_i = sample standard deviation of phi_i over the R bars, with
    Bessel correction (ddof=1): the standard unbiased-variance estimator of
    the per-bar marginal fluctuation under stationarity. Bars are correlated
    (runs thread across bars); that inflates estimator error, never the
    estimand — per-observable lag-1 autocorrelation is recorded as honesty.
  * Identifiability: sigma == 0.0 EXACTLY means the observable does not
    fluctuate under the untilted writer and is recorded identifiable=false
    with an R3-style note. NO floor is invented (registry law: a hand floor
    would be a fabricated constant standing where a measurement failed).
    Two exact zeros are expected from first principles at u=0:
      - phi_gauge: the untilted writer emits one identity-gauge section, so
        no frame move exists to fluctuate (same structure as training's R3:
        T5 not corpus-identifiable).
      - phi_density: the u=0 batch settlement is a deterministic MAP descent
        on a bar-periodic field, so the settled occupancy is EXACTLY
        bar-periodic and every O-marginal statistic is pinned; fluctuation at
        u=0 lives only in the fiber (which real unit sits where). A density
        scale becomes measurable only from a sampling (T_s > 0) writer.

BINDING: the artifact carries the sha256 of the frozen world content
(D, a, B, theta + live LAMBDA). Any anchor spawn/prune changes the hash and
invalidates the instrument (connector: re-run on resize).

Registered: REGISTRY.jsonl id sigma-phi-untilted-2026-07-15 (entry committed
before this run). Regeneration: python3 scripts/run_sigma_phi.py
Data (cache) lives in the MAIN checkout, read by absolute path.
"""
from __future__ import annotations
import glob
import hashlib
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAIN = "/home/user/Geodesic-Mixing"
CACHE = os.path.join(MAIN, "cache/ingest")
REGISTRY_ID = "sigma-phi-untilted-2026-07-15"


def _lag1(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    if x.std() == 0.0 or len(x) < 3:
        return float("nan")
    return float(np.corrcoef(x[:-1], x[1:])[0, 1])


def _cache_manifest(paths) -> dict:
    files = {}
    for p in paths:
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        files[os.path.basename(p)] = h.hexdigest()
    agg = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"files": files, "hash": agg}


def main() -> None:
    from ets.ingestion.pipeline import load
    from ets.writer import (build_world_from_tracks, OutputGrid, TapeNode,
                            settle_tape, realize)
    from ets.connector.phi import phi_bars, role_maps_from_world, LANE_PHI, PHI_NAMES
    from ets.calibration import world_content_hash, SIGMA_PHI_PATH
    from ets.functional.f import LAMBDA
    from ets.writer.tape import S_PHASE

    t0 = time.time()
    paths = sorted(glob.glob(os.path.join(CACHE, "track_*.npz")))
    if not paths:
        sys.exit(f"no cached tracks under {CACHE}")
    print(f"[1/5] loading {len(paths)} cached tracks ...")
    tracks = [load(p) for p in paths]

    print("[2/5] freezing world (the writer's world; seed=0, sigma=median) ...")
    world = build_world_from_tracks(tracks)
    whash = world_content_hash(world.fstate)
    print(f"      M={world.M}  world_hash={whash[:16]}...  info={world.info}")

    # Ensemble size: the corpus's own bar count (derived, no hand constant).
    bars_per_track = [int(t.units["bar"].max()) + 1 for t in tracks]
    R = int(sum(bars_per_track))
    print(f"[3/5] untilted (u=0) batch settlement of R={R} bars "
          f"({R * S_PHASE} slots) ...")
    grid = OutputGrid(sr=world.sr, tatum_len=world.out_tatum_len,
                      n_slots=R * S_PHASE)
    tape = TapeNode(grid=grid, M=world.M)
    res = settle_tape(world.fstate, tape)   # u=None: the untilted reduced form
    assert res.converged and res.monotone, \
        "untilted settlement failed its F-descent certificate — instrument invalid"
    sched, meta = realize(res.O, tape, world.fstate, world.index)
    print(f"      certificate: converged={res.converged} monotone={res.monotone} "
          f"n_iter={res.n_iter}; {meta['n_placements']} placements")

    print("[4/5] per-bar observables + fluctuations ...")
    maps = role_maps_from_world(world)
    phis = phi_bars(sched, maps, S_PHASE)

    notes = {
        "gauge": (
            "NOT IDENTIFIABLE at u=0 (R3-style): the untilted writer emits a "
            "single identity-gauge section, so no frame move exists and "
            "phi_gauge is identically 0 over the ensemble. Same structure as "
            "training's T5 (not corpus-identifiable). No floor is invented; a "
            "GAUGE STIFFNESS scale requires a writer whose gauge sections can "
            "move (frame-move traffic), to be measured then."),
        "density": (
            "NOT IDENTIFIABLE at u=0 (R3-style): the u=0 batch settlement is "
            "a deterministic MAP descent on a bar-periodic anchor field, so "
            "the settled occupancy is EXACTLY bar-periodic and the bar's "
            "total scheduled mass (an O-marginal) is pinned to a constant; "
            "untilted fluctuation exists only in the fiber (unit identities). "
            "No floor is invented; a DENSITY scale becomes measurable from a "
            "sampling writer (TEMPERATURE T_s > 0 ensemble), which does not "
            "exist yet."),
    }

    phi_doc = {}
    for name in PHI_NAMES:
        x = phis[name]
        if name == "region":
            sig = x.std(axis=0, ddof=1)
            mu = x.mean(axis=0)
            ident = (sig > 0.0)
            entry = {"lane": 1, "sigma": [float(v) for v in sig],
                     "mean": [float(v) for v in mu],
                     "identifiable": [bool(v) for v in ident],
                     "lag1_autocorr": [_lag1(x[:, k]) for k in range(x.shape[1])]}
            if not ident.all():
                entry["note"] = ("component(s) with sigma == 0.0 exactly: not "
                                 "identifiable at u=0; no floor invented")
        else:
            sig = float(x.std(ddof=1))
            mu = float(x.mean())
            entry = {"lane": {"density": 2, "continuity": 3, "gauge": 4,
                              "novelty": 5}[name],
                     "sigma": sig, "mean": mu, "identifiable": sig > 0.0,
                     "lag1_autocorr": _lag1(x)}
            if sig == 0.0:
                entry["note"] = notes.get(name, "sigma == 0.0 exactly: not "
                                          "identifiable at u=0; no floor invented")
        phi_doc[name] = entry
        s_repr = entry["sigma"]
        print(f"      phi_{name:11s} sigma={s_repr} identifiable={entry['identifiable']}")

    print("[5/5] writing artifact ...")
    doc = {
        "instrument": REGISTRY_ID,
        "artifact": "ets/calibration/sigma_phi.json",
        "regenerate": "python3 scripts/run_sigma_phi.py",
        "scaling_law": ("lambda_i = u_i / sigma_phi_i (connector Layer 0). FDT: "
                        "d<phi>/du|_0 = sigma, so one knob unit = one "
                        "equilibrium-sigma lean of phi_i."),
        "estimator": ("sample std (ddof=1) of per-bar phi_i over the untilted "
                      "(u=0) batch settlement's realized bars; ensemble size = "
                      "corpus bar count; no burn-in discarded; bar "
                      "autocorrelation recorded per observable"),
        "identifiability_rule": ("identifiable := sigma > 0.0 exactly; zeros "
                                 "recorded honestly with notes, NO floor"),
        "lanes": {str(k): v for k, v in LANE_PHI.items()},
        "phi": phi_doc,
        "ensemble": {
            "kind": "per-bar arrangements, untilted batch settlement (u=0)",
            "n_bars": R,
            "bars_per_track": bars_per_track,
            "s_phase": int(S_PHASE),
            "n_slots": int(grid.n_slots),
            "out_tatum_len": int(world.out_tatum_len),
            "sr": int(world.sr),
            "settle_certificate": {"converged": bool(res.converged),
                                   "monotone": bool(res.monotone),
                                   "n_iter": int(res.n_iter)},
            "n_placements": int(meta["n_placements"]),
        },
        "world": {
            "hash": whash,
            "M": int(world.M),
            "build": "ets.writer.build_world_from_tracks(tracks, seed=0, sigma=None->median)",
            "info": {k: float(v) if isinstance(v, (int, float)) else v
                     for k, v in world.info.items()},
            "lambda": {k: float(v) for k, v in LAMBDA.items()},
            "cache": _cache_manifest(paths),
        },
        "ts": time.strftime("%Y-%m-%d"),
    }
    with open(SIGMA_PHI_PATH, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    print(f"DONE in {time.time() - t0:.1f}s -> {SIGMA_PHI_PATH}")


if __name__ == "__main__":
    main()
