"""Trace generation for the Stage-1 conflation-regression analysis
(directive amendment stage1-delete-conflated-jack; ONE-SHOT, read-only
w.r.t. all engine code).

FROZEN as of the Stage-1 deletion commit (directive-v1 Feature 2 Stage 1):
this script calls the production ``gauge_trace()`` LIVE (by design, see
below), and that function no longer computes or exports the
``conflated_drift_*_running`` fields this script reads at lines ~198-208
(the conflated jack was DELETED outright, evidence-clean, per the analysis
this very script's output fed — REGISTRY conflation-regression-
stage1-2026-07-15). Re-running this script against the post-deletion tree
will KeyError. This is not a bug to patch: per REGISTRY discipline
(instruments are never edited-in-place to match new code; a new question is
a new pre-registered run), this file is retained UNMODIFIED as the exact
record of the procedure that produced analysis/traces/*.gauge_trace.json —
those frozen output files, and analysis/conflation_regression.json/.py which
only read them back, are unaffected by this note or by the deletion.

DECLARED (the faithful move, stated once): Stage 0 merged the trace
MACHINERY but banked NO production trace over the corpus, so this driver
GENERATES the traces using the registered instrument AS-IS — zero engine
code changes; the trace is produced by ``gauge_trace()`` loaded from
``scripts/generate_batch.py`` itself (the sidecar's production site, the
same load idiom as tests/meters/test_gauge_split.py H-3), on the output
of the registered entry points ``build_world_from_tracks`` /
``generate_batch`` over the 20 cached corpus tracks, with clamp
configurations reusing the tests/writer fixture patterns (I-7: the ONE
sanctioned intervention species) at production scale (60 s tapes).

RENDER NOT RUN (declared): every ``gauge_trace`` input — the realized
Schedule, the settled occupancy O, s_phase — is produced UPSTREAM of the
render, and the merged H-3 evidence proves render/meter independence in
both directions (bit-identical audio with meters computed vs stubbed; no
audio-path module imports ets.meters). The trace bytes are therefore
identical with or without rendering; skipping the render changes wall
clock only, never the instrument's output.

Configurations (all at u=0 — the only writer that exists; the Layer-0
tilt map is a parallel build and settle_tape raises on nonzero u):

  u0_unclamped          expected DEGENERATE (slide=0, loop~0,
                        conflated~0); reported anyway — the degenerate
                        case is evidence the split loses nothing at idle.
  role_clamp_single     verbatim test_role_column_clamp_is_pinned
                        pattern: one one-hot role column (mass 1.0) at
                        slot 4, on a 60 s tape.
  role_clamp_downbeats  the same clamp species at production density:
                        a one-hot role column at every bar downbeat,
                        role rotating (bar % M), column mass = the frozen
                        anchor field's own slot mass at that phase
                        (sum_k a_k theta[k, phase] — derived from the
                        world, no hand constant), so the clamp is
                        mass-neutral and only the ROLE PROFILE moves.
  unit_demand_sparse    verbatim test_unit_demand_is_placed_verbatim
                        pattern at production scale: one unit demand per
                        8 bars (deterministic real (track, unit) picks).
  mixed_role_and_unit   both species together (I-7: one type, no third).

Output: analysis/traces/<config>.gauge_trace.json — the registered trace
dict EMBEDDED INTACT under "trace", wrapped with run metadata (config,
clamp summary, grid geometry incl. bar_seconds, F-descent certificate).

Usage:  python3 analysis/run_conflation_traces.py [--seconds 60]
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TRACE_DIR = os.path.join(ROOT, "analysis", "traces")


def _load_generate_batch_module():
    """Load scripts/generate_batch.py so gauge_trace() is the production
    code itself (tests/meters/test_gauge_split.py H-3 idiom), not a copy."""
    path = os.path.join(ROOT, "scripts", "generate_batch.py")
    spec = importlib.util.spec_from_file_location("gb_production", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _configs(world, n_slots: int, s_phase: int):
    """The clamp configurations (fixture patterns at production scale).
    Returns [(name, ClampSet, human summary)]."""
    from ets.writer import ClampSet

    M = world.M
    S = int(s_phase)
    n_bars = n_slots // S
    fs = world.fstate

    # -- role_clamp_single: verbatim writer-fixture pattern ------------------
    col = np.zeros(M)
    col[0] = 1.0
    single = ClampSet(role_columns={4: col.copy()})

    # -- role_clamp_downbeats: same species, production density --------------
    # column mass = the frozen anchor field's own slot mass at that phase
    # (mass-neutral; only the role profile is intervened on).
    field_slot_mass = (fs.a[:, None] * fs.theta).sum(axis=0)   # (S,) per phase
    down_cols = {}
    for b in range(n_bars):
        s = b * S
        c = np.zeros(M)
        c[b % M] = float(field_slot_mass[s % S])
        down_cols[s] = c
    downbeats = ClampSet(role_columns=down_cols)

    # -- unit_demand_sparse: verbatim fixture pattern, one per 8 bars --------
    # deterministic real (track, unit) picks: track b/8 mod N, its unit #5
    # (the fixture's pick), band read from the unit row.
    demands = {}
    for j, b in enumerate(range(0, n_bars, 8)):
        tr = world.tracks[j % len(world.tracks)]
        u = tr.units
        row = min(5, len(u) - 1)
        demands[b * S + 2] = (int(tr.track_id), int(u["unit_id"][row]),
                              int(u["band"][row]))
    unit_sparse = ClampSet(unit_demands=dict(demands))

    # -- mixed: both species together (I-7 — one type, no third) -------------
    half = {s: c for s, c in down_cols.items() if (s // S) % 2 == 0}
    mixed = ClampSet(role_columns=half, unit_demands=dict(demands))

    return [
        ("u0_unclamped", ClampSet(), "no clamps (expected degenerate)"),
        ("role_clamp_single", single,
         "one-hot role column, mass 1.0, slot 4 (verbatim writer fixture)"),
        ("role_clamp_downbeats", downbeats,
         f"one-hot role column at every bar downbeat, role = bar % {M}, "
         "column mass = frozen anchor-field slot mass (mass-neutral)"),
        ("unit_demand_sparse", unit_sparse,
         f"{len(demands)} unit demands, one per 8 bars (fixture pattern)"),
        ("mixed_role_and_unit", mixed,
         f"{len(half)} downbeat role columns (even bars) + "
         f"{len(demands)} unit demands"),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--max-iter", type=int, default=800)  # production script value
    args = ap.parse_args()

    from ets.writer import build_world_from_tracks, generate_batch, OutputGrid

    gb = _load_generate_batch_module()
    os.makedirs(TRACE_DIR, exist_ok=True)

    t0 = time.time()
    print("[1/3] loading cached tracks (registered loader) ...")
    tracks = gb.load_tracks()
    print(f"      {len(tracks)} tracks, sr={tracks[0].sr}")

    print("[2/3] freezing world (production defaults: sigma=None->median, seed=0) ...")
    world = build_world_from_tracks(tracks, sigma=None)
    print(f"      anchors M={world.M}  out_tatum_len={world.out_tatum_len}")

    grid = OutputGrid.for_seconds(world.sr, world.out_tatum_len, args.seconds)
    print(f"      grid: n_slots={grid.n_slots} s_phase={grid.s_phase} "
          f"n_bars={grid.n_slots // grid.s_phase}")

    print("[3/3] settling + tracing configurations ...")
    for name, clamps, summary in _configs(world, grid.n_slots, grid.s_phase):
        t1 = time.time()
        out = generate_batch(world, seconds=args.seconds, clamps=clamps,
                             max_iter=args.max_iter)
        res = out["settle"]
        sched = out["schedule"]
        s_phase = out["tape"].grid.s_phase
        trace = gb.gauge_trace(sched, res.O, s_phase)   # the registered instrument
        tat = int(out["tape"].grid.tatum_len)
        wrapped = {
            "run": {
                "config": name,
                "clamp_summary": summary,
                "n_clamped_role_columns": len(clamps.role_columns),
                "n_unit_demands": len(clamps.unit_demands),
                "seconds": args.seconds,
                "u": 0,
                "sr": int(sched.sr),
                "tatum_len": tat,
                "s_phase": int(s_phase),
                "bar_seconds": float(s_phase) * tat / float(sched.sr),
                "n_out_slots": int(sched.n_out_slots),
                "n_placements": int(len(sched.placements)),
                "F_first": float(res.trace[0]),
                "F_last": float(res.trace[-1]),
                "F_monotone": bool(res.monotone),
                "F_converged": bool(res.converged),
                "n_iter": int(res.n_iter),
                "render_run": False,
                "render_note": "every gauge_trace input is upstream of render "
                               "(H-3: render/meter independence proven); trace "
                               "bytes identical with or without rendering",
            },
            "trace": trace,
        }
        path = os.path.join(TRACE_DIR, f"{name}.gauge_trace.json")
        with open(path, "w") as f:
            json.dump(wrapped, f, indent=1)
        lg = np.asarray(trace["per_bar"]["loop_g"])
        ck = np.asarray(trace["per_bar"]["conflated_drift_key_running"])
        cp = np.asarray(trace["per_bar"]["conflated_drift_phase_running"])
        sk = np.asarray(trace["per_bar"]["slide_key_disp"])
        sp = np.asarray(trace["per_bar"]["slide_phase_charge"])
        print(f"      {name}: bars={trace['n_bars']} monotone={res.monotone} "
              f"converged={res.converged} "
              f"max|loop|={np.max(np.abs(lg)):.3e} "
              f"max|slide_key|={np.max(np.abs(sk)):.3e} "
              f"max|slide_phase|={np.max(np.abs(sp)):.3e} "
              f"max|confl_key|={np.max(np.abs(ck)):.3e} "
              f"max|confl_phase|={np.max(np.abs(cp)):.3e} "
              f"[{time.time()-t1:.1f}s]")
    print(f"DONE in {time.time()-t0:.1f}s -> {TRACE_DIR}")


if __name__ == "__main__":
    main()
