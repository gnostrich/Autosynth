"""PREREG-track-role-bias — SOFT (track × role) SUB-TRACK gate (standalone, PROTOTYPE).

The third field-bias grain (PREREG-track-role-bias) leans track T's candidates SOFTLY
but ONLY inside slots whose settled role is k — the per-candidate addend gains
``β_track_role[(candidate.track_id, k)]`` where k is the slot's settled role (the
``_choose(k, b)`` arg that made the choice set "role-k units in band b"). This is the
first bias keyed on an EMERGENT structure (roles are training-emergent, unlike input-
level track/unit).

WHY IT DODGES THE ROLE WALL (measured in REV3): a PURE role addend is a constant across
a role-k choice set (every candidate shares role k) → it cancels in the softmax (inert).
A (track, role) addend VARIES within the set via the TRACK key (only track-T candidates
get it) → it steers. This gate proves both halves:
  * PULL: biasing cell (T, k) monotonically raises/lowers that cell's OUTPUT fraction
          (rows that are BOTH track T AND settled role k), byte-identical at zero.
  * CONTROL: a PURE role-k bias (ALL tracks in role k, equal) stays BIT-IDENTICAL to
          baseline (inert), while the (T, k) cell bias MOVES. That contrast is the point.

Role assignment is CONSISTENT with the mechanism: each produced row's role is the SLOT
role k that produced it (captured by observing ``_choose``), the same k the addend keys
on. Rare-event instrument (Spearman ρ + endpoints), disclosed — same as the unit gate.

World: prefers the real M=5 ``corpus20.etsworld`` (20 tracks, emergent roles are real
there); falls back to committed ``demo.etsworld`` (M=2) if it will not load.

Usage:  python3 cloud/tools/track_role_bias_verify.py [--world PATH] [--seeds N] [--bars N]
"""
from __future__ import annotations
import argparse, json, os, sys, time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))

import numpy as np

AMPLIFIES = [-1.0, -0.6, -0.3, 0.0, 0.3, 0.6, 1.0]
RHO_MIN = 0.7
_CORPUS20 = os.environ.get(
    "ETS_CORPUS20",
    "/tmp/claude-0/-home-user-Geodesic-Mixing/"
    "4a1c7144-4244-558b-9b4e-b3e828d38fdf/scratchpad/corpus20.etsworld")

# --- slot-role instrumentation: observe (produced track_id, slot role k) ----
# Behaviour-neutral: wraps FiberThreader._choose, calls the original, records the
# returned placement's track_id under the slot role k the mechanism keys on. Every
# non-None _choose return is exactly one produced row (place_slot appends one row per
# non-None choice), so this reconstructs each row's slot role consistently.
_STAT = Counter()
_TOT = [0]


def _install_probe():
    from ets.writer.realize import FiberThreader
    if getattr(FiberThreader._choose, "_tr_probe", False):
        return
    orig = FiberThreader._choose

    def wrapped(self, k, b, psi, bar):
        res = orig(self, k, b, psi, bar)
        if res is not None:
            _STAT[(int(res[0][0]), int(k))] += 1
            _TOT[0] += 1
        return res
    wrapped._tr_probe = True
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


def _load(world_path, seed):
    from ets.engine.worldfile import load_world
    from ets.engine.engine import Engine, resolve_sigma
    wf = load_world(world_path)
    eng = Engine(wf, profile="desktop", seed=seed, sigma=resolve_sigma(wf, None))
    return wf.world, eng


def _measure(world_path, seeds, n_bars, clog):
    """Produce seeds×n_bars fresh-writer bars at field bias `clog`; return the
    (track_id, slot_role) -> count map and total produced rows."""
    from ets.panel.lanes import default_lane_vector
    _STAT.clear(); _TOT[0] = 0
    for sd in seeds:
        world, eng = _load(world_path, sd)
        u = default_lane_vector(world.M)
        for _ in range(n_bars):
            eng.writer.write_bar(tilt=eng._tilt_for(u, channel_logbias=clog))
    return dict(_STAT), _TOT[0]


def _byte_identity(world_path, seed, clog, n_bars=12):
    """Rows bit-identical between the un-biased writer and one fed `clog`."""
    from ets.panel.lanes import default_lane_vector
    wa, ea = _load(world_path, seed)
    wb, eb = _load(world_path, seed)
    ua = default_lane_vector(wa.M); ub = default_lane_vector(wb.M)
    for _ in range(n_bars):
        ra = ea.writer.write_bar(tilt=ea._tilt_for(ua))
        rb = eb.writer.write_bar(tilt=eb._tilt_for(ub, channel_logbias=clog))
        if ra.rows != rb.rows or not np.array_equal(ra.O, rb.O):
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default=None)
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--bars", type=int, default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "papers", "track_role_bias_results.json"))
    args = ap.parse_args()

    _install_probe()
    from cloud.companion.channel_bias import (track_role_logbias, field_logbias,
                                              channel_tids, channel_logbias, default_strength)

    # world selection: prefer the real M=5 corpus20, fall back to demo
    world_path = args.world
    if world_path is None:
        world_path = _CORPUS20 if os.path.exists(_CORPUS20) else os.path.join(ROOT, "demo.etsworld")
    t0 = time.time()
    try:
        world, _eng = _load(world_path, 0)
    except Exception as exc:
        print(f"[fallback] {os.path.basename(world_path)} would not load ({type(exc).__name__}: "
              f"{exc}); using demo.etsworld", flush=True)
        world_path = os.path.join(ROOT, "demo.etsworld")
        world, _eng = _load(world_path, 0)
    M = int(world.M)
    tids = channel_tids(world)
    is_corpus = os.path.basename(world_path).startswith("corpus")
    seeds = list(range(args.seeds if args.seeds is not None else (2 if is_corpus else 4)))
    n_bars = args.bars if args.bars is not None else (40 if is_corpus else 64)
    strength = default_strength()
    print(f"world={os.path.basename(world_path)}  M={M}  tracks={len(tids)}  "
          f"seeds={len(seeds)} bars={n_bars}  strength(LAMBDA.T1p)={strength:.3f}", flush=True)

    # baseline cell census -> pick (T,k) with headroom BOTH ways (competition to win
    # AND presence to lose): argmax min(cell, role_total - cell).
    base, tot = _measure(world_path, seeds, n_bars, None)
    role_tot = Counter()
    for (t, k), c in base.items():
        role_tot[k] += c
    (T, K) = max(base, key=lambda cell: min(base[cell], role_tot[cell[1]] - base[cell]))
    base_frac = base[(T, K)] / tot
    print(f"TARGET cell (track {T}, role {K})  baseline={base[(T,K)]}/{tot}={base_frac:.4f}  "
          f"role{K}_total_frac={role_tot[K]/tot:.4f}  (headroom both ways)", flush=True)

    # (T,k) sweep
    curve = []
    for amp in AMPLIFIES:
        cw = track_role_logbias({(T, K): amp}) if amp != 0.0 else None
        clog = field_logbias(track_role=cw)
        st, t = _measure(world_path, seeds, n_bars, clog)
        frac = st.get((T, K), 0) / t if t else 0.0
        curve.append(frac)
        print(f"  amp={amp:>5}  cell_frac={frac:.4f}", flush=True)

    base_c = curve[AMPLIFIES.index(0.0)]
    top, bot = curve[-1], curve[0]
    rho = _spearman(AMPLIFIES, curve)

    # byte-identity @ empty field
    byte_ok = _byte_identity(world_path, 0, field_logbias(track_role=track_role_logbias({})))

    # CONTROL: pure role-K bias (ALL tracks in role K, equal) must be INERT; the (T,K)
    # cell bias must MOVE. Same grain — the difference is keying on ONE track vs ALL.
    pure_role = field_logbias(track_role=track_role_logbias({(int(t), K): 1.0 for t in tids}))
    pure_role_inert = _byte_identity(world_path, 0, pure_role)
    cell_only = field_logbias(track_role=track_role_logbias({(T, K): 1.0}))
    cell_moves = not _byte_identity(world_path, 0, cell_only)

    pull = bool(rho >= RHO_MIN and top > base_c and byte_ok)
    damp = bool(rho >= RHO_MIN and bot < base_c and byte_ok)
    dodge = bool(pure_role_inert and cell_moves)

    verdict = {
        "world": os.path.basename(world_path), "M": M, "n_tracks": len(tids),
        "target_cell": {"track_id": T, "role_k": K}, "seeds": len(seeds), "bars": n_bars,
        "strength_LAMBDA_T1p": strength, "amplifies": AMPLIFIES, "cell_frac_curve": curve,
        "baseline_frac": base_c, "amp1_frac": top, "damp1_frac": bot,
        "pull_gain": top - base_c, "damp_drop": bot - base_c,
        "role_total_frac": role_tot[K] / tot, "spearman_rho": rho, "rho_min": RHO_MIN,
        "role_assignment": "slot role k (the _choose arg = place_slot argmax(col.B[:,b])); "
                           "same k the addend keys on (consistent with the mechanism)",
        "byte_identity_at_zero": byte_ok,
        "control_pure_role_inert": pure_role_inert,
        "control_cell_moves": cell_moves,
        "TRACK_ROLE_PULL": pull, "pull_verdict": ("PULL_HOLDS" if pull else "PULL_NULL"),
        "TRACK_ROLE_DAMP": damp, "damp_verdict": ("DAMP_HOLDS" if damp else "DAMP_NULL"),
        "DODGES_ROLE_WALL": dodge,
        "magnitude_note": ("whole-track pull ~0.2->0.95; single-unit ~0.2%; this "
                           f"(track,role) cell: {base_c:.3f}->{top:.3f} (amp+1), "
                           f"{base_c:.3f}->{bot:.3f} (amp-1)"),
    }
    with open(args.out, "w") as f:
        json.dump(verdict, f, indent=2)

    print("\n=== VERDICT (soft (track x role) SUB-TRACK bias, prototype) ===")
    print(f"  cell (track {T}, role {K}): base={base_c:.4f}  +1={top:.4f} (gain {top-base_c:+.4f})  "
          f"-1={bot:.4f} (drop {bot-base_c:+.4f})")
    print(f"  Spearman rho={rho:.3f} (>= {RHO_MIN})   byte@zero={byte_ok}")
    print(f"  CONTROL: pure-role-K (all tracks) inert={pure_role_inert}   (T,K) cell moves={cell_moves}")
    print(f"  -> TRACK_ROLE {verdict['pull_verdict']} | {verdict['damp_verdict']} | "
          f"DODGES_ROLE_WALL={dodge}   ({time.time()-t0:.1f}s) -> {args.out}")
    return 0 if (pull and damp and dodge) else 2


if __name__ == "__main__":
    sys.exit(main())
