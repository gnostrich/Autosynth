"""PREREG-field-bias-REV3 — SOFT UNIT-grain pull/damp gate (standalone).

REV3 (multi-grain, 2026-07-19): the soft fiber lean now resolves per candidate as
``β_track[track_id] + β_unit[unit_id]`` — the TRACK roll-up plus the UNIT grain (the
operator's ultimate "channel", a beat-normalized sound unit). This gate measures the
UNIT grain: does biasing ONE unit raise/lower ITS OWN provenance share, softly,
byte-identically at zero? It drives the SAME builders (``grain_logbias`` /
``field_logbias``) and the SAME ``_tilt_for`` / ``write_bar`` the live bridge uses —
no parallel path, no render needed (the metric is provenance of the produced rows).

INSTRUMENT (disclosed in the prereg): a single unit's provenance is a RARE-EVENT
statistic (~0.7% of rows on demo, where M=2 makes each choice set ~100 units wide), so
its per-step deltas sit below sampling noise while the endpoints move materially — the
pull concentrates at |amplify|→1. The noise-robust operationalization of "monotonically
raises/lowers" is the SPEARMAN rank correlation ρ(amplify, share) over the full
bidirectional sweep, plus endpoint ordering. This is instrument design for a rare-event
statistic, not a loosened threshold.

ROLE WALL (surfaced, not gated as a pull): a per-candidate ROLE addend is inert at the
fiber measure — within one choice set every candidate shares the settled role k (chosen
by the O-block, place_slot k=argmax(col·B[:,b])), so a role addend is a softmax constant
that cancels. This gate CONFIRMS the wall empirically (a per-choice-set-constant addend
is bit-identical to baseline). Role steers via the O-block REGION lane, not the fiber.

Byte-identity: an all-zero field yields ``field_logbias(...) is None`` ⇒ the tilt is
byte-identical to the un-biased tilt ⇒ bit-identical rows AND settled O, bar for bar.

Usage:  python3 cloud/tools/field_bias_unit_verify.py [--bars 96] [--seeds 4] [--out PATH]
"""
from __future__ import annotations
import argparse, json, os, sys, time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))

import numpy as np

AMPLIFIES = [-1.0, -0.6, -0.3, 0.0, 0.3, 0.6, 1.0]
RHO_MIN = 0.7            # strong positive rank trend (prereg-fixed)


def _fresh_engine(world_path, seed):
    from ets.engine.worldfile import load_world
    from ets.engine.engine import Engine, resolve_sigma
    wf = load_world(world_path)
    eng = Engine(wf, profile="desktop", seed=seed, sigma=resolve_sigma(wf, None))
    return wf.world, eng


def _spearman(x, y):
    """Spearman ρ = Pearson on ranks (no scipy dependency). Average ties."""
    def rank(v):
        v = np.asarray(v, float)
        order = np.argsort(v, kind="mergesort")
        r = np.empty(len(v), float)
        r[order] = np.arange(len(v), dtype=float)
        # average ranks for ties
        _, inv, counts = np.unique(v, return_inverse=True, return_counts=True)
        sums = np.zeros(len(counts)); np.add.at(sums, inv, r)
        means = sums / counts
        return means[inv]
    rx, ry = rank(x), rank(y)
    rx -= rx.mean(); ry -= ry.mean()
    denom = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float((rx * ry).sum() / denom) if denom > 0 else 0.0


def _unit_share(world_path, seeds, n_bars, target):
    """TARGET unit's provenance share (fraction of realized rows) at the current
    field bias, averaged over `seeds` fresh writers × `n_bars` bars each."""
    from ets.panel.lanes import default_lane_vector
    return_clog = _unit_share.clog
    hit = tot = 0
    for sd in seeds:
        world, eng = _fresh_engine(world_path, sd)
        u = default_lane_vector(world.M)
        for _ in range(n_bars):
            r = eng.writer.write_bar(tilt=eng._tilt_for(u, channel_logbias=return_clog))
            for (_s, tid, uid, _sec, _m) in r.rows:
                tot += 1
                if (int(tid), int(uid)) == target:
                    hit += 1
    return hit / tot if tot else 0.0
_unit_share.clog = None


def _pick_target(world_path, seed, n_bars):
    """Pick a real unit_id from static_field()['unit_pools'] that actually appears
    as a candidate with nonzero baseline occurrence — the pool unit with the highest
    baseline provenance share (the honest 'most-heard' unit, so it has headroom in
    both directions)."""
    _w, eng = _fresh_engine(world_path, seed)
    # the UNIT grain roster, from the SAME reduction static_field()['unit_pools'] serves
    from ets.engine.engine import role_unit_pool
    pools = role_unit_pool(_w)   # {role: [(unit_id, track_id, band, profile), ...]}
    pool_units = {(int(e[1]), int(e[0]))          # (track_id, unit_id)
                  for role in pools.values() for e in role}
    # baseline provenance census
    from ets.panel.lanes import default_lane_vector
    u = default_lane_vector(_w.M)
    c = Counter(); tot = 0
    for _ in range(n_bars):
        r = eng.writer.write_bar(tilt=eng._tilt_for(u))
        for (_s, tid, uid, _sec, _m) in r.rows:
            tot += 1; c[(int(tid), int(uid))] += 1
    # highest-baseline unit that is also in a unit pool (nonzero occurrence)
    for (unit, n) in c.most_common():
        if unit in pool_units and n > 0:
            return unit, n / tot, len(pool_units)
    # fallback: highest-baseline unit at all (still a real candidate)
    unit, n = c.most_common(1)[0]
    return unit, n / tot, len(pool_units)


def _byte_identity(world_path, seed, n_bars=8):
    """All-zero field ⇒ field_logbias is None ⇒ tilt byte-identical to the un-biased
    tilt ⇒ rows AND settled O bit-identical, bar for bar."""
    from cloud.companion.channel_bias import field_logbias, grain_logbias
    from ets.panel.lanes import default_lane_vector
    wa, ea = _fresh_engine(world_path, seed)
    wb, eb = _fresh_engine(world_path, seed)
    ua = default_lane_vector(wa.M); ub = default_lane_vector(wb.M)
    ok = True
    seen_none = True
    for _ in range(n_bars):
        ra = ea.writer.write_bar(tilt=ea._tilt_for(ua))
        clog = field_logbias(track=None, unit=grain_logbias({}))   # -> None
        if clog is not None:
            seen_none = False
        rb = eb.writer.write_bar(tilt=eb._tilt_for(ub, channel_logbias=clog))
        if ra.rows != rb.rows or not np.array_equal(ra.O, rb.O):
            ok = False; break
    return {"zero_field_rows_and_O_bit_identical": ok and seen_none, "n_bars": n_bars}


def _role_wall(world_path, seed, n_bars=16):
    """MEASURED role wall: a per-choice-set-CONSTANT addend (bias EVERY track by the
    same +β) is exactly the constant a role bias contributes within any one choice
    set. It must leave the produced rows BIT-IDENTICAL to baseline — proving a role
    addend is inert at the fiber measure (role steers via the O-block region lane)."""
    from cloud.companion.channel_bias import channel_logbias, field_logbias, channel_tids
    from ets.panel.lanes import default_lane_vector
    wa, ea = _fresh_engine(world_path, seed)
    wb, eb = _fresh_engine(world_path, seed)
    tids = channel_tids(wb)
    const = field_logbias(track=channel_logbias(np.ones(len(tids)), tids))  # +β to every track
    ua = default_lane_vector(wa.M); ub = default_lane_vector(wb.M)
    identical = True
    for _ in range(n_bars):
        ra = ea.writer.write_bar(tilt=ea._tilt_for(ua))
        rb = eb.writer.write_bar(tilt=eb._tilt_for(ub, channel_logbias=const))
        if ra.rows != rb.rows:
            identical = False; break
    return {"const_addend_bit_identical_to_baseline": identical, "n_bars": n_bars}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default=os.path.join(ROOT, "demo.etsworld"))
    ap.add_argument("--bars", type=int, default=96)
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--out", default=os.path.join(ROOT, "papers", "field_bias_unit_results.json"))
    args = ap.parse_args()

    from cloud.companion.channel_bias import grain_logbias, field_logbias, default_strength
    t0 = time.time()
    seeds = list(range(args.seeds))
    strength = default_strength()

    target, base_share, n_pool = _pick_target(args.world, 0, args.bars)
    tid_t, uid_t = target
    print(f"world={os.path.basename(args.world)}  unit_pool_size={n_pool}  "
          f"strength(LAMBDA.T1p)={strength:.3f}  seeds={args.seeds} bars={args.bars}", flush=True)
    print(f"TARGET unit (track {tid_t}, unit {uid_t})  baseline share={base_share:.4f}", flush=True)

    curve = []
    for amp in AMPLIFIES:
        uw = grain_logbias({uid_t: amp}) if amp != 0.0 else None
        _unit_share.clog = field_logbias(unit=uw)
        s = _unit_share(args.world, seeds, args.bars, target)
        curve.append(s)
        print(f"  amp={amp:>5}  share={s:.4f}   clog={_unit_share.clog}", flush=True)
    _unit_share.clog = None

    base = curve[AMPLIFIES.index(0.0)]
    top = curve[-1]
    bot = curve[0]
    rho = _spearman(AMPLIFIES, curve)

    byte = _byte_identity(args.world, 0)
    role = _role_wall(args.world, 0)
    byte_ok = byte["zero_field_rows_and_O_bit_identical"]

    unit_pull = bool(rho >= RHO_MIN and top > base and byte_ok)
    unit_damp = bool(rho >= RHO_MIN and bot < base and byte_ok)
    role_wall = bool(role["const_addend_bit_identical_to_baseline"])

    verdict = {
        "world": os.path.basename(args.world),
        "target_unit": {"track_id": tid_t, "unit_id": uid_t},
        "unit_pool_size": n_pool, "strength_LAMBDA_T1p": strength,
        "seeds": args.seeds, "bars_per_condition": args.bars,
        "amplifies": AMPLIFIES, "unit_share_curve": curve,
        "baseline_share": base, "amp1_share": top, "damp1_share": bot,
        "pull_gain": top - base, "damp_drop": bot - base,
        "spearman_rho": rho, "rho_min": RHO_MIN,
        "mechanism": "SOFT multi-grain fiber lean (channel_logbias tagged {track,unit}); "
                     "per-candidate addend = beta_track[tid]+beta_unit[uid]; no clamp, "
                     "nothing pinned, generative. UNIT = the operator's ultimate 'channel'.",
        "byte_identity": byte,
        "role_wall": {**role,
                      "note": "role is inert at the fiber measure (constant per choice "
                              "set); role steers via the O-block REGION lane, not a fiber "
                              "addend — see PREREG-field-bias-REV3 role wall."},
        "UNIT_PULL": unit_pull, "unit_pull_verdict": ("UNIT_PULL_HOLDS" if unit_pull else "UNIT_PULL_NULL"),
        "UNIT_DAMP": unit_damp, "unit_damp_verdict": ("UNIT_DAMP_HOLDS" if unit_damp else "UNIT_DAMP_NULL"),
        "ROLE_WALL_CONFIRMED": role_wall,
    }
    with open(args.out, "w") as f:
        json.dump(verdict, f, indent=2)

    print("\n=== VERDICT (soft UNIT-grain field bias, REV3) ===")
    print(f"  target unit share:  base={base:.4f}  +1={top:.4f} (gain {top-base:+.4f})  "
          f"-1={bot:.4f} (drop {bot-base:+.4f})")
    print(f"  Spearman rho(amplify,share) = {rho:.3f}   (>= {RHO_MIN} required)")
    print(f"  byte-identical@zero-field (rows+O): {byte_ok}")
    print(f"  ROLE WALL (const addend bit-identical to baseline): {role_wall}")
    print(f"  -> UNIT_PULL {verdict['unit_pull_verdict']} | UNIT_DAMP {verdict['unit_damp_verdict']} "
          f"| ROLE_WALL_CONFIRMED {role_wall}   ({time.time()-t0:.1f}s) -> {args.out}")
    return 0 if (unit_pull and unit_damp and role_wall) else 2


if __name__ == "__main__":
    sys.exit(main())
