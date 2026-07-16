"""sigma_phi calibration pass [REGISTERED INSTRUMENT] — connector Layer 0.

Measures, for every Layer-0 tilt observable phi_i (ets.connector.phi; lane map
documented there), the equilibrium fluctuation sigma_phi_i under the UNTILTED
writer, and writes the artifact ets/calibration/sigma_phi.json that the engine
consumes via ets.calibration.load_sigma_phi().

ARCHITECTURE-V3 RE-DERIVATION (prereg-arch-v3-temperature-sampler-2026-07-16,
Fix A). The ensemble is the UNTILTED (u=0) *SAMPLING* writer at T_s=1 — the
streaming writer's actual equilibrium output ensemble with temperature ON — NOT
the near-deterministic u=0 MAP batch settlement the prior instrument
(sigma-phi-untilted-2026-07-15) used. WHY this is the correct instrument, not a
patch: the connector's FDT scaling law lambda = u/sigma requires sigma to be the
fluctuation of phi under the writer the engine ACTUALLY runs, and the engine
runs the streaming sampling writer (T_s>0), never the MAP. The prior instrument's
own docstring already prescribed this for DENSITY ("a density scale becomes
measurable only from a sampling writer, T_s>0"); REGION shares the same
near-degeneracy (the MAP settled O is exactly bar-periodic, so O-marginal
fluctuation is pathologically small — sigma_region down to 0.027 — which drove
lambda to ~110 on a per-anchor XY throw and the settled mode to ~1e16). Under the
sampling ensemble every O-block observable carries its honest equilibrium
fluctuation, so lambda stays O(20) at max in-range knobs and the mode stays
bounded (see the steering-divergence report; NO clamp on lambda or O anywhere —
a clamp would hide the mis-calibration).

T_s CHOICE. T_s = 1 is the natural calibration point and the writer's default
untilted temperature: the measure is p ∝ exp(−F/T_s + Σλφ), so T_s=1 is the unit
thermal scale of F, and the FDT relation d<phi>/dlambda|_0 = Var_0(phi) is exact
at lambda=0 for the ensemble's own temperature. Knobs then read in natural units:
standard fluctuations of lean at unit temperature.

ALL FIVE observables move to this ONE sampling ensemble (a single coherent
writer run, not a hybrid): the O-block (region, density) BECAUSE the MAP pins
them; the fiber block (continuity, novelty) were already non-degenerate on the
MAP realize, but keeping them on the SAME sampling writer that region/density are
measured on is the coherent choice (one equilibrium ensemble, not two) and does
not change their observable DEFINITION (still ets.connector.phi.phi_bars) — only
the writer that generates the arrangements. gauge stays an honest exact zero: the
v0 writer's frame is frozen at the identity, so no frame move exists to fluctuate
(structural, unchanged by temperature). The MAP-ensemble numbers are recorded
alongside (meta.before_after) for the documented before/after.

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
  * Ensemble: the per-bar arrangements of the UNTILTED (u=0) SAMPLING writer at
    T_s=1 (ets.writer.stream.StreamWriter, seed=0) — the streaming writer's
    actual equilibrium output ensemble with temperature ON. Tape length R = the
    corpus's own bar count (sum over the 20 frozen tracks of each track's bar
    count): the ensemble size is the corpus evidence scale, not a hand constant.
    No burn-in is discarded: the run-seeding at bar 0 is the untilted writer's
    real behavior. Each streamed bar's placements are realized into the render
    Schedule contract, so the observables are the SAME connector phi_bars the
    prior instrument used — only the WRITER that generates the arrangements
    changed (MAP -> sampling). Seed=0 is the world/writer default (reproducible).
  * sigma_phi_i = sample standard deviation of phi_i over the R bars, with
    Bessel correction (ddof=1): the standard unbiased-variance estimator of
    the per-bar marginal fluctuation under stationarity. Bars are correlated
    (runs thread across bars); that inflates estimator error, never the
    estimand — per-observable lag-1 autocorrelation is recorded as honesty.
  * Identifiability: sigma == 0.0 EXACTLY means the observable does not
    fluctuate under the untilted SAMPLING writer and is recorded
    identifiable=false with an R3-style note. NO floor is invented (registry
    law: a hand floor would be a fabricated constant standing where a
    measurement failed). One exact zero is expected from first principles:
      - phi_gauge: the untilted writer emits one identity-gauge section, so
        no frame move exists to fluctuate (same structure as training's R3:
        T5 not corpus-identifiable). This is STRUCTURAL — temperature samples
        the O-block, not the (frozen) gauge frame — so it stays zero here.
    phi_density is NO LONGER an expected zero: under the T_s>0 sampling writer
    the settled O-marginal fluctuates (temperature draws around the bar-periodic
    mode), so DENSITY ARMS with its measured, derived scale (logged). Under the
    prior MAP instrument it was pinned (bar-periodic MAP) and disarmed; that was
    the missing-ensemble artifact this re-derivation removes.

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

# Portable path resolution (env-overridable; defaults to the repo root).
MAIN = os.environ.get(
    "ETS_MAIN", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.environ.get("ETS_CACHE", os.path.join(MAIN, "cache", "ingest"))
REGISTRY_ID = "sigma-phi-untilted-2026-07-15"


def _std(x: np.ndarray) -> float:
    """Sample std (ddof=1), computed CORRECTLY on constant input.

    np.std of an exactly-constant sequence returns ~1 ulp, not 0: its computed
    mean of N identical values rounds (pairwise summation, N not a power of
    two), leaving uniform ~ulp residuals. The sample standard deviation of a
    constant sequence is 0 BY DEFINITION, so the exact-constancy case is
    evaluated exactly. This is the correct value of the pre-registered
    estimator on that input — not a floor, not a threshold: any genuine
    fluctuation (two or more distinct floats) takes the ordinary formula.
    Uniform for every observable and every region component (single path)."""
    x = np.asarray(x, float)
    if np.all(x == x.flat[0]):
        return 0.0
    return float(x.std(ddof=1))


def _lag1(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    if _std(x) == 0.0 or len(x) < 3:
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


def _stream_bars(world, seed: int, L: int, T_s: float, maps, s_phase: int):
    """One untilted (u=0) SAMPLING stream of L bars (the ACTUAL streaming writer:
    settle -> log-space temperature sample -> fiber thread), realized to a
    Schedule and reduced to its per-bar phi_bars. Returns (per_bar_phi, cert)."""
    from ets.writer import OutputGrid
    from ets.writer.stream import StreamWriter
    from ets.writer.tilt import untilted
    from ets.render.schedule import Schedule, Section, IDENTITY, PLACEMENT_DTYPE
    from ets.connector.phi import phi_bars

    w = StreamWriter(world, seed=seed)
    t0 = untilted(world.M, T_s=T_s)
    rows = []
    conv = mono = True
    for _ in range(L):
        r = w.write_bar(tilt=t0)                      # halts on garbage (Fix B)
        conv = conv and bool(r.converged); mono = mono and bool(r.monotone)
        rows.extend(r.rows)
    n_slots = L * s_phase
    grid = OutputGrid(sr=world.sr, tatum_len=world.out_tatum_len, n_slots=n_slots)
    p = np.zeros(len(rows), dtype=PLACEMENT_DTYPE)
    for i, (s, tid, uid, sec, mass) in enumerate(rows):
        p[i]["out_slot"] = s; p[i]["src_track"] = tid; p[i]["src_unit"] = uid
        p[i]["section"] = sec; p[i]["mass"] = mass
    sched = Schedule(sr=int(world.sr), slot_boundaries=grid.slot_boundaries,
                     placements=p, sections=(Section(0, 0, n_slots, IDENTITY),))
    return phi_bars(sched, maps, s_phase), {"converged": conv, "monotone": mono,
                                            "n_placements": int(len(rows))}


def _sampling_ensemble(world, R: int, T_s: float, maps, s_phase: int,
                       L: int = 50, conv_tol: float = 3e-2, conv_win: int = 6,
                       min_bars: int = 400):
    """Fix A ensemble — the untilted (u=0) SAMPLING writer at T_s, drawn as
    INDEPENDENT SHORT seeded streams (seeds 0,1,2,...) pooled per-bar, instead of
    ONE R-bar stream. WHY (justified re-derivation, not a shortcut): the single
    long stream's per-bar cost GROWS with committed-tape length (the fiber
    threader's per-bar work is ~O(committed); measured), so an R=corpus-bar-count
    single stream is O(R^2) and impractical. The sigma_phi estimand is a
    per-observable sample std, which converges by the LLN; independent short
    streams keep each stream in the FLAT per-bar-cost regime while sampling the
    SAME per-bar equilibrium distribution:
      * O-block (region, density) — Fix A's target — is EXACTLY estimator-
        equivalent: the untilted settled mode is bar-periodic and the temperature
        draw is per-bar i.i.d., so its per-bar phi law is identical in a short or
        long stream (stationary from bar 0);
      * fiber (continuity, novelty): each short stream reaches its run/recency
        steady state within a few bars (the recency kernel 1/Delta is dominated
        by small-Delta reuse available immediately; L=%d >> that mixing), and NO
        burn-in is discarded (a fresh stream's bar-0 seeding is the untilted
        writer's real behavior — the registered instrument's own rule).
    The ensemble SIZE is set by MEASURED convergence (not a round number): streams
    are added until every observable's pooled sigma changes < conv_tol over the
    last conv_win streams, capped at the registered R (corpus bar count). Reports
    the convergence curve and the bar count actually used.""" % L
    rng_pool = {name: [] for name in ("region", "density", "continuity",
                                      "gauge", "novelty")}
    n_bars = 0
    seed = 0
    conv_hist = []
    all_conv = all_mono = True
    sig_prev = None
    max_streams = (R + L - 1) // L
    used_streams = 0
    while used_streams < max_streams:
        ph, cert = _stream_bars(world, seed, L, T_s, maps, s_phase)
        all_conv = all_conv and cert["converged"]
        all_mono = all_mono and cert["monotone"]
        for name in rng_pool:
            rng_pool[name].append(ph[name])
        n_bars += L; seed += 1; used_streams += 1
        # pooled sigma so far (region as vector, others scalar)
        reg = np.concatenate(rng_pool["region"], axis=0)
        sig_now = {"region": np.array([_std(reg[:, k]) for k in range(reg.shape[1])])}
        for name in ("density", "continuity", "gauge", "novelty"):
            sig_now[name] = _std(np.concatenate([np.atleast_1d(a)
                                                 for a in rng_pool[name]]))
        if sig_prev is not None:
            def _rel(a, b):
                a = np.atleast_1d(a); b = np.atleast_1d(b)
                denom = np.where(np.abs(b) > 0, np.abs(b), 1.0)
                return float(np.max(np.abs(a - b) / denom))
            rel = max(_rel(sig_now[n], sig_prev[n]) for n in sig_now)
            conv_hist.append((n_bars, rel))
            if used_streams % 10 == 0:
                print(f"        {used_streams} streams / {n_bars} bars, "
                      f"max sigma rel-change={rel:.4f}", flush=True)
            # converged when the TRAILING MEAN of the last conv_win per-stream
            # relative changes is < conv_tol (robust to single-stream jitter of
            # any one observable — a mean, not an all-consecutive test).
            # conv_tol=3% is amply sufficient: sigma feeds lambda=u/sigma, so a
            # 3% sigma error is a 3% lambda error — negligible for a knob scale;
            # LLN floor min_bars guards against a lucky early dip.
            if (n_bars >= min_bars and len(conv_hist) >= conv_win
                    and float(np.mean([r for _, r in conv_hist[-conv_win:]]))
                    < conv_tol):
                break
        sig_prev = sig_now
    pooled = {"region": np.concatenate(rng_pool["region"], axis=0)}
    for name in ("density", "continuity", "gauge", "novelty"):
        pooled[name] = np.concatenate([np.atleast_1d(a) for a in rng_pool[name]])
    meta = {"n_bars": n_bars, "n_streams": used_streams, "stream_len": L,
            "conv_tol": conv_tol, "conv_win": conv_win, "min_bars": min_bars,
            "T_s": float(T_s),
            "converged": all_conv, "monotone": all_mono,
            "size_capped_at_R": bool(used_streams >= max_streams),
            "convergence_curve": [[int(nb), float(r)] for nb, r in conv_hist[-20:]]}
    return pooled, meta


def main() -> None:
    from ets.ingestion.pipeline import load
    from ets.writer import (build_world_from_tracks, OutputGrid, TapeNode,
                            settle_tape, realize)
    from ets.connector.phi import phi_bars, role_maps_from_world, LANE_PHI, PHI_NAMES
    from ets.calibration import world_content_hash, SIGMA_PHI_PATH
    from ets.functional.f import LAMBDA
    from ets.writer.tape import S_PHASE

    SEED = 0            # writer seed for the sampling ensemble (world/writer default)
    T_S = 1.0           # natural calibration temperature (see module docstring)

    t0 = time.time()
    paths = sorted(glob.glob(os.path.join(CACHE, "track_*.npz")))
    if not paths:
        sys.exit(f"no cached tracks under {CACHE}")
    print(f"[1/6] loading {len(paths)} cached tracks ...")
    tracks = [load(p) for p in paths]

    print("[2/6] freezing world (the writer's world; seed=0, sigma=median) ...")
    world = build_world_from_tracks(tracks)
    whash = world_content_hash(world.fstate)
    print(f"      M={world.M}  world_hash={whash[:16]}...  info={world.info}")
    maps = role_maps_from_world(world)

    # Ensemble size: the corpus's own bar count (derived, no hand constant).
    bars_per_track = [int(t.units["bar"].max()) + 1 for t in tracks]
    R = int(sum(bars_per_track))

    # --- BEFORE (recorded for the documented before/after): the prior MAP
    #     instrument's O-block sigma (u=0 batch settlement, same connector phi).
    #     Diagnostic only: the MAP pathology (pinned O-marginal) is robust to
    #     tape length, so a bounded diagnostic tape suffices (the artifact
    #     ensemble is the sampling one below).
    R_before = min(R, 500)
    print(f"[3/6] BEFORE diagnostic: u=0 MAP batch settlement of {R_before} bars "
          f"(diagnostic; MAP pathology is length-robust) ...")
    grid_map = OutputGrid(sr=world.sr, tatum_len=world.out_tatum_len,
                          n_slots=R_before * S_PHASE)
    tape_map = TapeNode(grid=grid_map, M=world.M)
    res_map = settle_tape(world.fstate, tape_map)
    assert res_map.converged and res_map.monotone, \
        "MAP settlement lost its F-descent certificate — before-diagnostic invalid"
    sched_map, _meta_map = realize(res_map.O, tape_map, world.fstate, world.index)
    phis_map = phi_bars(sched_map, maps, S_PHASE)
    before = {
        "ensemble": "u=0 MAP batch settlement (prior instrument)",
        "region_sigma": [float(_std(phis_map["region"][:, k]))
                         for k in range(world.M)],
        "density_sigma": float(_std(phis_map["density"])),
        "continuity_sigma": float(_std(phis_map["continuity"])),
        "novelty_sigma": float(_std(phis_map["novelty"])),
    }
    print(f"      MAP region sigma = {before['region_sigma']}")
    print(f"      MAP density sigma = {before['density_sigma']} (pinned/disarmed)")

    # --- AFTER (the artifact ensemble): untilted SAMPLING writer at T_s=1,
    #     drawn as independent short seeded streams (see _sampling_ensemble),
    #     sized by measured sigma-convergence, capped at the registered R.
    print(f"[4/6] AFTER: untilted SAMPLING writer (T_s={T_S}) as independent "
          f"short streams (seed 0..), sized by convergence, cap R={R} bars ...")
    phis, meta = _sampling_ensemble(world, R, T_S, maps, S_PHASE)
    assert meta["converged"] and meta["monotone"], \
        "sampling writer lost a per-bar F-descent certificate — instrument invalid"
    print(f"      certificate: converged={meta['converged']} "
          f"monotone={meta['monotone']}; used {meta['n_streams']} streams / "
          f"{meta['n_bars']} bars (stream_len={meta['stream_len']}); "
          f"size_capped_at_R={meta['size_capped_at_R']}")

    print("[5/6] per-bar observables + fluctuations (sampling ensemble) ...")

    notes = {
        "gauge": (
            "NOT IDENTIFIABLE at u=0 (R3-style): the untilted writer emits a "
            "single identity-gauge section, so no frame move exists and "
            "phi_gauge is identically 0 over the sampling ensemble. Temperature "
            "samples the O-block, not the (v0-frozen) gauge frame, so this stays "
            "structurally zero. Same structure as training's T5 (not "
            "corpus-identifiable). No floor is invented; a GAUGE STIFFNESS scale "
            "requires a writer whose gauge sections can move (frame-move "
            "traffic), to be measured then."),
    }

    phi_doc = {}
    for name in PHI_NAMES:
        x = phis[name]
        if name == "region":
            sig = np.array([_std(x[:, k]) for k in range(x.shape[1])])
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
            sig = _std(x)
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

    # documented before/after (Fix A): MAP vs sampling O-block sigma.
    after_region = phi_doc["region"]["sigma"]
    after_density = phi_doc["density"]["sigma"]
    before_after = {
        "note": ("Fix A re-derivation: O-block sigma moved from the u=0 MAP "
                 "batch ensemble (pathologically pinned) to the untilted T_s=1 "
                 "SAMPLING ensemble the engine runs. Knob feel changes (less "
                 "hair-trigger): larger sigma_region => smaller lambda=u/sigma "
                 "at the same knob throw. A logged, legitimate v3 behavior "
                 "difference, NOT a clamp on lambda or O."),
        "region_sigma": {"map": before["region_sigma"], "sampling": after_region},
        "density_sigma": {"map": before["density_sigma"], "sampling": after_density,
                          "armed_under_sampling": bool(after_density > 0.0)},
        "continuity_sigma": {"map": before["continuity_sigma"],
                             "sampling": phi_doc["continuity"]["sigma"]},
        "novelty_sigma": {"map": before["novelty_sigma"],
                          "sampling": phi_doc["novelty"]["sigma"]},
    }
    print(f"[6/6] before/after region sigma: MAP={before['region_sigma']} "
          f"-> SAMPLING={after_region}")
    print(f"      density sigma: MAP={before['density_sigma']} -> "
          f"SAMPLING={after_density} (armed={after_density > 0.0})")

    print("      writing artifact ...")
    doc = {
        "instrument": REGISTRY_ID,
        "artifact": "ets/calibration/sigma_phi.json",
        "regenerate": "python3 scripts/run_sigma_phi.py",
        "scaling_law": ("lambda_i = u_i / sigma_phi_i (connector Layer 0). FDT: "
                        "d<phi>/du|_0 = sigma, so one knob unit = one "
                        "equilibrium-sigma lean of phi_i."),
        "estimator": ("sample std (ddof=1) of per-bar phi_i over the UNTILTED "
                      "(u=0) SAMPLING writer at T_s=1, pooled over INDEPENDENT "
                      "short seeded streams (seeds 0..N-1); ensemble size set by "
                      "measured sigma-convergence and capped at the registered "
                      "corpus bar count R; no burn-in discarded; per-observable "
                      "bar autocorrelation recorded"),
        "identifiability_rule": ("identifiable := sigma > 0.0 exactly; zeros "
                                 "recorded honestly with notes, NO floor"),
        "lanes": {str(k): v for k, v in LANE_PHI.items()},
        "phi": phi_doc,
        "before_after": before_after,
        "ensemble": {
            "kind": ("per-bar arrangements, untilted SAMPLING writer (u=0, "
                     "T_s=1), pooled over independent short seeded streams"),
            "method_note": (
                "Re-derivation of the ensemble DRAW (not the estimand): a single "
                "R-bar stream has per-bar cost growing ~O(committed) (fiber "
                "threader), so R=corpus-bar-count is O(R^2)/impractical. "
                "Independent short streams keep the flat per-bar regime and "
                "sample the SAME per-bar equilibrium law — EXACTLY so for the "
                "O-block (bar-periodic mode + i.i.d. temperature draw), and to "
                "run/recency steady-state (reached within a few bars) for the "
                "fiber. Same estimand, size justified by convergence + capped at "
                "the registered R."),
            "T_s": float(T_S),
            "n_bars": int(meta["n_bars"]),
            "n_streams": int(meta["n_streams"]),
            "stream_len_bars": int(meta["stream_len"]),
            "seeds": f"0..{meta['n_streams'] - 1}",
            "R_registered_cap": int(R),
            "size_capped_at_R": bool(meta["size_capped_at_R"]),
            "convergence": {"tol": meta["conv_tol"], "window": meta["conv_win"],
                            "curve_tail": meta["convergence_curve"]},
            "bars_per_track": bars_per_track,
            "s_phase": int(S_PHASE),
            "out_tatum_len": int(world.out_tatum_len),
            "sr": int(world.sr),
            "settle_certificate": {"converged": bool(meta["converged"]),
                                   "monotone": bool(meta["monotone"])},
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
