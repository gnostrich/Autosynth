"""PREREG-track-role-grid — the TRACK × ROLE GRID steering surface (standalone gate).

The Play field is laid out as a labeled matrix: rows = source tracks, columns = roles
k=0..M-1, interior = (track, role) cells. Each grain rides the SEEN-THROUGH jack — the
step that actually weighs that type:

  * CELL (track, role)  -> CASTING / pick lane  (track_role_bias -> the fiber (track,role)
    addend; steers because (track,role) VARIES within a role-k choice set via the track).
  * ROW (track)         -> CASTING / pick lane  (channel_bias -> the track roll-up fiber lean).
  * COLUMN (role k)     -> SETTLEMENT lane       (region: u_region[k] += amp * REGION_SCALE ->
    the O-block occupancy tilt). A PURE role addend is a softmax CONSTANT over a role-k
    choice set (it IS the set's identity) -> INERT in the fiber (the measured role wall);
    role provenance is an O-block property, so a column steers occupancy through REGION only.

REGION_SCALE = the engine's OWN safe-envelope cap ``ets.panel.envelope.SAFE_REGION_MAGNITUDE``
(the value ``set_region`` clamps to and the pad ring is painted at). amp in [-1,1] maps a single
role column linearly onto the full in-range region tilt with no clamp dead-zone — not an
invented gain; it tracks the engine constant and mirrors the amplitude the app already uses.

This gate proves, on a real region-ARMED world (corpus20, M=5; falls back to demo, M=2):
  (a) COLUMN(role k) region push MEASURABLY moves role-k's OUTPUT SHARE (monotone; Spearman
      rho + endpoint gain) — the settlement lane steers occupancy.
  (b) ROW(track) and CELL(track,role) still steer via the PICK (channel_bias / track_role_bias),
      monotone pull, unchanged from their ratified gates.
  (c) BYTE-IDENTICAL when every grain is explicit-empty (region zeros + no fiber addend).
  (d) COLUMN honestly DISARMS on a region-disarmed world: under a region-DISARMED sigma
      (identifiable['region']=False — the exact state the bridge reports as region_armed=False
      and the FE dims the column on), the SAME column push is bit-identical to neutral
      (settles no differently) — the engine's identity-on-unidentifiable backstop.
  (e) All three COEXIST: column (settlement) + row (pick) + cell (pick) each still acts when
      pushed simultaneously.

Usage:  python3 cloud/tools/track_role_grid_verify.py [--world PATH] [--seeds N] [--bars N]
"""
from __future__ import annotations
import argparse, json, os, sys, time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))

import numpy as np

AMPLIFIES = [-1.0, -0.6, -0.3, 0.0, 0.3, 0.6, 1.0]        # column (region) sweep
AMPLIFIES_PICK = [-1.0, -0.5, 0.0, 0.5, 1.0]              # row / cell (pick) sweep
RHO_MIN = 0.7
COEX_COL_AMP = 0.6                                        # non-saturating column push for coexistence
COEX_PICK_AMP = 1.0
_CORPUS20 = os.environ.get(
    "ETS_CORPUS20",
    "/tmp/claude-0/-home-user-Geodesic-Mixing/"
    "4a1c7144-4244-558b-9b4e-b3e828d38fdf/scratchpad/corpus20.etsworld")

# --- slot-role instrumentation: observe (produced track_id, slot role k) -----
# Behaviour-neutral wrap of FiberThreader._choose: each non-None return is exactly one
# produced row, recorded under the slot role k the mechanism keys on.
_STAT = Counter()
_TOT = [0]


def _install_probe():
    from ets.writer.realize import FiberThreader
    if getattr(FiberThreader._choose, "_grid_probe", False):
        return
    orig = FiberThreader._choose

    def wrapped(self, k, b, psi, bar, *args, **kwargs):
        # *args/**kwargs pass through unchanged (e.g. the `slot` param `_choose` gained
        # since this probe was written) — the probe only OBSERVES the call, it must never
        # change which arguments `_choose` receives.
        res = orig(self, k, b, psi, bar, *args, **kwargs)
        if res is not None:
            _STAT[(int(res[0][0]), int(k))] += 1
            _TOT[0] += 1
        return res
    wrapped._grid_probe = True
    wrapped._orig = orig
    FiberThreader._choose = wrapped


def _spearman(x, y):
    def rank(v):
        v = np.asarray(v, float)
        order = np.argsort(v, kind="mergesort")
        r = np.empty(len(v), float); r[order] = np.arange(len(v), dtype=float)
        _, inv, counts = np.unique(v, return_inverse=True, return_counts=True)
        sums = np.zeros(len(counts)); np.add.at(sums, inv, r)
        return (sums / counts)[inv]
    rx, ry = rank(x), rank(y)
    rx -= rx.mean(); ry -= ry.mean()
    d = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float((rx * ry).sum() / d) if d > 0 else 0.0


def _region_scale():
    """REGION_SCALE = the engine's own safe-envelope cap (mirrored by the FE)."""
    from ets.panel.envelope import SAFE_REGION_MAGNITUDE
    return float(SAFE_REGION_MAGNITUDE)


def _disarmed_region_sigma(sig):
    """A region-DISARMED clone of the world's real sigma: identifiable['region']=False,
    the exact all-or-nothing disarm state the bridge reports as region_armed=False. layer0
    then applies the EXACT identity tilt on region (taps settle no differently)."""
    from ets.writer.tilt import SigmaPhi
    ident = dict(sig.identifiable); ident["region"] = False
    return SigmaPhi(region=sig.region, density=sig.density, cont=sig.cont,
                    gauge=sig.gauge, novelty=sig.novelty, identifiable=ident,
                    meta=dict(getattr(sig, "meta", {}) or {}))


def _bars(wf, sig, seed, region_vec, clog, n_bars):
    """Produce n_bars from a FRESH deterministic writer at region lean `region_vec`
    (length-M or None) and fiber addend `clog` (or None). Records the probe stats and
    returns the list of (rows, O) per bar (for byte comparison)."""
    from ets.engine.engine import Engine
    from ets.panel.lanes import default_lane_vector
    eng = Engine(wf, profile="desktop", seed=seed, sigma=sig)
    M = int(wf.world.M)
    u = default_lane_vector(M)
    if region_vec is not None:
        u.resize_region(M)
        u.u_region[:] = np.asarray(region_vec, np.float32)[:M]
    out = []
    for _ in range(n_bars):
        r = eng.writer.write_bar(tilt=eng._tilt_for(u, channel_logbias=clog))
        out.append((r.rows, r.O))
    return out


def _run(wf, sig, seeds, n_bars, region_vec=None, clog=None):
    """Measure the (track_id, slot_role) -> count census over seeds×bars at the given
    region lean + fiber addend. Returns (census dict, total rows)."""
    _STAT.clear(); _TOT[0] = 0
    for sd in seeds:
        _bars(wf, sig, sd, region_vec, clog, n_bars)
    return dict(_STAT), _TOT[0]


def _byte_identical(wf, sig, seed, region_vec, clog, n_bars):
    """True iff a writer fed (region_vec, clog) is bit-identical to the UNTILTED writer."""
    a = _bars(wf, sig, seed, None, None, n_bars)
    b = _bars(wf, sig, seed, region_vec, clog, n_bars)
    if len(a) != len(b):
        return False
    for (ra, Oa), (rb, Ob) in zip(a, b):
        if ra != rb or not np.array_equal(Oa, Ob):
            return False
    return True


def _byte_identical_pair(wf, sig, seed, ra_args, rb_args, n_bars):
    """True iff two writers (each (region_vec, clog)) are bit-identical."""
    a = _bars(wf, sig, seed, ra_args[0], ra_args[1], n_bars)
    b = _bars(wf, sig, seed, rb_args[0], rb_args[1], n_bars)
    if len(a) != len(b):
        return False
    for (ra, Oa), (rb, Ob) in zip(a, b):
        if ra != rb or not np.array_equal(Oa, Ob):
            return False
    return True


def _role_share(census, tot, k):
    return (sum(c for (t, kk), c in census.items() if kk == k) / tot) if tot else 0.0


def _track_share(census, tot, T):
    return (sum(c for (t, kk), c in census.items() if t == T) / tot) if tot else 0.0


def _cell_share(census, tot, T, K):
    return (census.get((T, K), 0) / tot) if tot else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default=None)
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--bars", type=int, default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "papers", "track_role_grid_results.json"))
    args = ap.parse_args()

    _install_probe()
    from ets.engine.worldfile import load_world
    from ets.engine.engine import resolve_sigma
    from cloud.companion.channel_bias import (track_role_logbias, field_logbias,
                                              channel_tids, channel_logbias, default_strength)

    world_path = args.world
    if world_path is None:
        world_path = _CORPUS20 if os.path.exists(_CORPUS20) else os.path.join(ROOT, "demo.etsworld")
    t0 = time.time()
    try:
        wf = load_world(world_path)
    except Exception as exc:
        print(f"[fallback] {os.path.basename(world_path)} would not load "
              f"({type(exc).__name__}: {exc}); using demo.etsworld", flush=True)
        world_path = os.path.join(ROOT, "demo.etsworld")
        wf = load_world(world_path)
    sig = resolve_sigma(wf, None)
    M = int(wf.world.M)
    tids = channel_tids(wf.world)
    is_corpus = os.path.basename(world_path).startswith("corpus")
    seeds = list(range(args.seeds if args.seeds is not None else (2 if is_corpus else 4)))
    n_bars = args.bars if args.bars is not None else (24 if is_corpus else 48)
    n_byte = 8
    SCALE = _region_scale()
    region_armed = bool(sig is not None and sig.is_identifiable("region"))
    print(f"world={os.path.basename(world_path)}  M={M}  tracks={len(tids)}  "
          f"seeds={len(seeds)} bars={n_bars}  REGION_SCALE={SCALE}  region_armed={region_armed}  "
          f"strength(LAMBDA.T1p)={default_strength():.3f}", flush=True)

    # baseline census -> targets. K = the region column with headroom AND the highest
    # identified region sigma (most steerable). T = the track with the most headroom BOTH
    # ways inside role K (competition to win, presence to lose) — used for row AND cell.
    base, tot = _run(wf, sig, seeds, n_bars)
    role_tot = Counter()
    for (t, k), c in base.items():
        role_tot[k] += c
    sr = np.asarray(sig.region, float).reshape(-1) if sig is not None else np.ones(M)
    cand_K = [k for k in range(M) if 0.02 < (role_tot[k] / tot if tot else 0) < 0.98]
    if not cand_K:
        cand_K = list(range(M))
    K = max(cand_K, key=lambda k: float(sr[k]) if k < sr.size else 0.0)
    role_cells = [(t, base.get((t, K), 0)) for t in tids]
    T = max(role_cells, key=lambda tc: min(tc[1], role_tot[K] - tc[1]))[0]
    print(f"TARGET column role K={K} (baseline role share={role_tot[K]/tot:.4f}, "
          f"sigma.region[K]={float(sr[K]) if K < sr.size else 0:.4f})  "
          f"row/cell track T={T} (cell (T,K) baseline={base.get((T,K),0)}/{tot}={_cell_share(base,tot,T,K):.4f})",
          flush=True)

    # (a) COLUMN region sweep on role K -> role-K output share
    col_curve = []
    for amp in AMPLIFIES:
        rv = np.zeros(M, np.float32)
        if amp != 0.0:
            rv[K] = amp * SCALE
        st, tt = _run(wf, sig, seeds, n_bars, region_vec=rv)
        col_curve.append(_role_share(st, tt, K))
        print(f"  COLUMN amp={amp:>5}  role{K}_share={col_curve[-1]:.4f}", flush=True)
    col_base = col_curve[AMPLIFIES.index(0.0)]
    col_top, col_bot = col_curve[-1], col_curve[0]
    col_rho = _spearman(AMPLIFIES, col_curve)
    col_pull = bool(region_armed and col_rho >= RHO_MIN and col_top > col_base and col_bot < col_base)

    # (b) ROW steer (channel_bias / pick) -> track T share
    row_curve = []
    for amp in AMPLIFIES_PICK:
        clog = field_logbias(track=channel_logbias(
            [amp if t == T else 0.0 for t in tids], tids)) if amp != 0.0 else None
        st, tt = _run(wf, sig, seeds, n_bars, clog=clog)
        row_curve.append(_track_share(st, tt, T))
        print(f"  ROW    amp={amp:>5}  track{T}_share={row_curve[-1]:.4f}", flush=True)
    row_base = row_curve[AMPLIFIES_PICK.index(0.0)]
    row_rho = _spearman(AMPLIFIES_PICK, row_curve)
    row_pull = bool(row_rho >= RHO_MIN and row_curve[-1] > row_base)

    # (b) CELL steer (track_role_bias / pick) -> cell (T,K) share
    cell_curve = []
    for amp in AMPLIFIES_PICK:
        clog = field_logbias(track_role=track_role_logbias({(T, K): amp})) if amp != 0.0 else None
        st, tt = _run(wf, sig, seeds, n_bars, clog=clog)
        cell_curve.append(_cell_share(st, tt, T, K))
        print(f"  CELL   amp={amp:>5}  cell(T,K)_share={cell_curve[-1]:.4f}", flush=True)
    cell_base = cell_curve[AMPLIFIES_PICK.index(0.0)]
    cell_rho = _spearman(AMPLIFIES_PICK, cell_curve)
    cell_pull = bool(cell_rho >= RHO_MIN and cell_curve[-1] > cell_base)

    # (c) BYTE-IDENTICAL at explicit-empty grid (region zeros + no fiber addend)
    byte_ok = _byte_identical(wf, sig, seeds[0], np.zeros(M, np.float32),
                              field_logbias(), n_byte)

    # (d) COLUMN honest disarm: same push under a region-DISARMED sigma is bit-identical
    sig_dis = _disarmed_region_sigma(sig) if sig is not None else None
    rv_push = np.zeros(M, np.float32); rv_push[K] = 1.0 * SCALE
    if sig_dis is not None:
        col_disarm_inert = _byte_identical_pair(wf, sig_dis, seeds[0],
                                                (rv_push, None), (None, None), n_byte)
        # confirm the SAME push is NOT inert under the ARMED sigma (the contrast)
        col_armed_moves = not _byte_identical_pair(wf, sig, seeds[0],
                                                   (rv_push, None), (None, None), n_byte)
    else:
        col_disarm_inert, col_armed_moves = False, False

    # (e) COEXISTENCE: column (settlement) + row (pick) + cell (pick) each still acts
    rv_co = np.zeros(M, np.float32); rv_co[K] = COEX_COL_AMP * SCALE
    clog_co = field_logbias(
        track=channel_logbias([COEX_PICK_AMP if t == T else 0.0 for t in tids], tids),
        track_role=track_role_logbias({(T, K): COEX_PICK_AMP}))
    st_neutral, tn = base, tot
    st_col, tc = _run(wf, sig, seeds, n_bars, region_vec=rv_co)
    st_all, ta = _run(wf, sig, seeds, n_bars, region_vec=rv_co, clog=clog_co)
    coex_col_acts = bool(region_armed and _role_share(st_col, tc, K) > _role_share(st_neutral, tn, K))
    coex_cell_acts = bool(_cell_share(st_all, ta, T, K) > _cell_share(st_col, tc, T, K))
    coex_row_acts = bool(_track_share(st_all, ta, T) > _track_share(st_col, tc, T))
    coex_fiber_changes_draw = not _byte_identical_pair(wf, sig, seeds[0],
                                                       (rv_co, None), (rv_co, clog_co), n_byte)
    coexist = bool(coex_col_acts and coex_cell_acts and coex_row_acts and coex_fiber_changes_draw)

    verdict = {
        "world": os.path.basename(world_path), "M": M, "n_tracks": len(tids),
        "seeds": len(seeds), "bars": n_bars, "REGION_SCALE": SCALE,
        "REGION_SCALE_basis": "ets.panel.envelope.SAFE_REGION_MAGNITUDE (the set_region clamp / "
                              "pad-ring cap); amp in [-1,1] -> full in-range single-column region tilt",
        "region_armed": region_armed,
        "target_column_role_K": K, "target_row_cell_track_T": T,
        "sigma_region_K": float(sr[K]) if K < sr.size else None,
        # (a) COLUMN -> settlement
        "column_amplifies": AMPLIFIES, "column_rolek_share_curve": col_curve,
        "column_base": col_base, "column_amp1": col_top, "column_ampneg1": col_bot,
        "column_pull_gain": col_top - col_base, "column_damp_drop": col_bot - col_base,
        "column_spearman_rho": col_rho, "COLUMN_STEERS_SETTLEMENT": col_pull,
        # (b) ROW / CELL -> pick
        "pick_amplifies": AMPLIFIES_PICK,
        "row_trackT_share_curve": row_curve, "row_base": row_base, "row_spearman_rho": row_rho,
        "ROW_STEERS_PICK": row_pull,
        "cell_share_curve": cell_curve, "cell_base": cell_base, "cell_spearman_rho": cell_rho,
        "CELL_STEERS_PICK": cell_pull,
        # (c) byte-identity
        "BYTE_IDENTICAL_NEUTRAL": bool(byte_ok),
        # (d) disarm
        "column_disarm_inert": col_disarm_inert, "column_armed_moves": col_armed_moves,
        "COLUMN_HONEST_DISARM": bool(col_disarm_inert and col_armed_moves),
        # (e) coexistence
        "coex_col_role_share": {"neutral": _role_share(st_neutral, tn, K),
                                "col_only": _role_share(st_col, tc, K)},
        "coex_cell_share": {"col_only": _cell_share(st_col, tc, T, K),
                            "all_three": _cell_share(st_all, ta, T, K)},
        "coex_track_share": {"col_only": _track_share(st_col, tc, T),
                             "all_three": _track_share(st_all, ta, T)},
        "coex_col_acts": coex_col_acts, "coex_cell_acts": coex_cell_acts,
        "coex_row_acts": coex_row_acts, "coex_fiber_changes_draw": coex_fiber_changes_draw,
        "ALL_THREE_COEXIST": coexist,
    }
    overall = bool(col_pull and row_pull and cell_pull and byte_ok
                   and verdict["COLUMN_HONEST_DISARM"] and coexist)
    verdict["GRID_VERDICT"] = "PASS" if overall else "FAIL"
    with open(args.out, "w") as f:
        json.dump(verdict, f, indent=2)

    print("\n=== VERDICT (track × role GRID) ===")
    print(f"  (a) COLUMN role{K}: base={col_base:.4f} +1={col_top:.4f} -1={col_bot:.4f}  "
          f"rho={col_rho:.3f}  -> STEERS_SETTLEMENT={col_pull}")
    print(f"  (b) ROW track{T}:  base={row_base:.4f} +1={row_curve[-1]:.4f}  rho={row_rho:.3f}  -> {row_pull}")
    print(f"      CELL (T,K):    base={cell_base:.4f} +1={cell_curve[-1]:.4f}  rho={cell_rho:.3f}  -> {cell_pull}")
    print(f"  (c) BYTE-IDENTICAL neutral = {byte_ok}")
    print(f"  (d) COLUMN disarm inert (region off) = {col_disarm_inert}  |  armed moves = {col_armed_moves}")
    print(f"  (e) COEXIST: col_acts={coex_col_acts} cell_acts={coex_cell_acts} "
          f"row_acts={coex_row_acts} fiber_changes_draw={coex_fiber_changes_draw}")
    print(f"  -> GRID_VERDICT = {verdict['GRID_VERDICT']}   ({time.time()-t0:.1f}s) -> {args.out}")
    return 0 if overall else 2


if __name__ == "__main__":
    sys.exit(main())
