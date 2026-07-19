"""PREREG-channel-bias-squares — Phase 1 SOFT pull/separability gate (standalone).

Measures whether a SOFT per-channel lean (an additive log-weight on a track's
candidate units inside the Layer-0 fiber choice measure — the distribution over
pooled channels at each beat) pulls the realized output toward that track, on a
REAL committed world. Drives the SAME lean builder (``channel_logbias``) and the
SAME ``_tilt_for`` / ``write_bar`` the live bridge uses — no parallel path, no
render needed (the metric is provenance of the produced rows, r.rows).

This is the operator mechanism correction: NOT a hard I-7 clamp (which pins slots
and trivially "pulls"), but a soft prior the Gibbs settlement reads and works
around — so the real, degeneracy-exposed question is whether the lean pulls at all
or COLLAPSES the way the observable/region lanes did.

WORLD (declared honestly): the prereg names ``scratchpad/corpus20.etsworld`` (20
channels). That asset was UNCOMMITTED and was reverted by a container restart; it
is not in the repo and cannot be rebuilt without its source audio. This gate runs
on the committed, self-contained ``demo.etsworld`` (4 real channels, M=2 anchors) —
the mechanism and metric are corpus-agnostic; only the channel COUNT differs.

Metrics per (channel T, amplify a), over N fresh-writer bars:
  * unit_frac — fraction of realized rows whose provenance track_id == T
                (the prereg's literal metric).
  * mass_frac — mass-weighted fraction (audible presence).
  * slot_frac — fraction of metrical slots whose dominant-mass unit is track T.
  * confusion — full per-track composition at each amplify.

Byte-identity: an all-zero bias yields ``channel_logbias(...) is None`` ⇒ the tilt
is byte-identical to the un-biased tilt ⇒ bit-identical rows AND settled O, bar for
bar (a rendered-audio byte-identity follows: render is I-11 pure).

Usage:  python3 cloud/tools/channel_bias_pull_verify.py [--bars 64] [--out PATH]
"""
from __future__ import annotations
import argparse, json, os, sys, time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))

import numpy as np


def _fresh_engine(world_path, seed):
    from ets.engine.worldfile import load_world
    from ets.engine.engine import Engine, resolve_sigma
    wf = load_world(world_path)
    sigma = resolve_sigma(wf, None)
    eng = Engine(wf, profile="desktop", seed=seed, sigma=sigma)
    return wf.world, eng


def _bias_vec(n, ch, amp):
    v = np.zeros(n, dtype=np.float64)
    v[ch] = float(amp)
    return v


def _measure(world_path, seed, n_bars, ch, amp):
    """Produce n_bars from a FRESH engine at soft bias = amp on channel ch; return
    provenance metrics. Uses channel_logbias + _tilt_for + write_bar as the bridge."""
    from cloud.companion.channel_bias import channel_logbias, channel_tids
    world, eng = _fresh_engine(world_path, seed)
    s_phase = eng.writer.s_phase
    tids = channel_tids(world)
    tid_T = tids[ch]
    bias = _bias_vec(len(tids), ch, amp)
    clog = channel_logbias(bias, tids) if amp > 0.0 else None

    from ets.panel.lanes import default_lane_vector
    u = default_lane_vector(world.M)                 # u=0: isolate the channel lean

    n_rows = n_rows_T = 0
    mass_tot = mass_T = 0.0
    slot_tot = slot_T = 0
    per_track_rows = defaultdict(int)
    for _bar in range(n_bars):
        tilt = eng._tilt_for(u, channel_logbias=clog)
        r = eng.writer.write_bar(tilt=tilt)
        slot_best = {}
        for (slot, tid, uid, sec, mass) in r.rows:
            sl = int(slot) % s_phase
            n_rows += 1
            mass_tot += float(mass)
            per_track_rows[int(tid)] += 1
            if int(tid) == tid_T:
                n_rows_T += 1
                mass_T += float(mass)
            cur = slot_best.get(sl)
            if cur is None or float(mass) > cur[1]:
                slot_best[sl] = (int(tid), float(mass))
        for sl, (tid, _m) in slot_best.items():
            slot_tot += 1
            if tid == tid_T:
                slot_T += 1
    return {
        "channel": ch, "track_id": int(tid_T), "amplify": float(amp),
        "unit_frac": (n_rows_T / n_rows) if n_rows else 0.0,
        "mass_frac": (mass_T / mass_tot) if mass_tot else 0.0,
        "slot_frac": (slot_T / slot_tot) if slot_tot else 0.0,
        "n_rows": n_rows,
        "confusion": {int(k): v / n_rows for k, v in per_track_rows.items()} if n_rows else {},
    }


def _byte_identity(world_path, seed, n_bars=8):
    """All-zero bias ⇒ channel_logbias is None ⇒ tilt byte-identical to the
    un-biased tilt ⇒ rows AND settled O bit-identical, bar for bar."""
    from cloud.companion.channel_bias import channel_logbias, channel_tids
    from ets.panel.lanes import default_lane_vector
    wa, ea = _fresh_engine(world_path, seed)
    wb, eb = _fresh_engine(world_path, seed)
    tids = channel_tids(wb)
    zero = np.zeros(len(tids))
    ua = default_lane_vector(wa.M)
    ub = default_lane_vector(wb.M)
    ok = True
    clog_seen_none = True
    for _bar in range(n_bars):
        ra = ea.writer.write_bar(tilt=ea._tilt_for(ua))              # never biased
        clog = channel_logbias(zero, tids)                          # -> None
        if clog is not None:
            clog_seen_none = False
        rb = eb.writer.write_bar(tilt=eb._tilt_for(ub, channel_logbias=clog))
        if ra.rows != rb.rows or not np.array_equal(ra.O, rb.O):
            ok = False
            break
    return {"zero_bias_rows_and_O_bit_identical": ok and clog_seen_none,
            "n_bars": n_bars}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default=os.path.join(ROOT, "demo.etsworld"))
    ap.add_argument("--bars", type=int, default=64)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(ROOT, "papers",
                                                  "channel_bias_pull_results.json"))
    args = ap.parse_args()

    t0 = time.time()
    from cloud.companion.channel_bias import channel_tids, default_strength
    world, eng = _fresh_engine(args.world, args.seed)
    s_phase = eng.writer.s_phase
    tids = channel_tids(world)
    n_ch = len(tids)
    amplifies = [0.0, 0.3, 0.6, 1.0]
    strength = default_strength()
    print(f"world={os.path.basename(args.world)}  channels={n_ch}  s_phase={s_phase}  "
          f"bars/condition={args.bars}  strength(LAMBDA.T1p)={strength:.3f}", flush=True)

    curves = {}
    for ch in range(n_ch):
        row = []
        for amp in amplifies:
            m = _measure(args.world, args.seed, args.bars, ch, amp)
            row.append(m)
            print(f"  ch{ch} (track {m['track_id']}) amp={amp:>3}  "
                  f"unit={m['unit_frac']:.3f} mass={m['mass_frac']:.3f} "
                  f"slot={m['slot_frac']:.3f}", flush=True)
        curves[ch] = row

    byte = _byte_identity(args.world, args.seed)

    def _monotone(vals):
        return all(vals[i + 1] >= vals[i] - 1e-9 for i in range(len(vals) - 1))
    per_ch = {}
    for ch in range(n_ch):
        unit = [curves[ch][i]["unit_frac"] for i in range(len(amplifies))]
        mass = [curves[ch][i]["mass_frac"] for i in range(len(amplifies))]
        slot = [curves[ch][i]["slot_frac"] for i in range(len(amplifies))]
        per_ch[ch] = {
            "track_id": curves[ch][0]["track_id"],
            "unit_frac": unit, "mass_frac": mass, "slot_frac": slot,
            "unit_monotone": _monotone(unit), "mass_monotone": _monotone(mass),
            "slot_monotone": _monotone(slot),
            "unit_gain": unit[-1] - unit[0], "mass_gain": mass[-1] - mass[0],
            "slot_gain": slot[-1] - slot[0],
            "confusion_amp1": curves[ch][-1]["confusion"],
        }
    top = len(amplifies) - 1
    diag_dominant = all(
        curves[ch][top]["confusion"].get(per_ch[ch]["track_id"], 0.0)
        == max(curves[ch][top]["confusion"].values())
        for ch in range(n_ch)) if n_ch else False

    MATERIAL = 0.10          # min unit_frac gain amp0->amp1 to call the pull "material"
    monos = [per_ch[ch]["unit_monotone"] for ch in range(n_ch)]
    gains = [per_ch[ch]["unit_gain"] for ch in range(n_ch)]
    # H1 (soft): the lean pulls provenance toward the channel, monotonically, on
    # MOST channels (a per-channel disarm is allowed — some channels may be mushy),
    # materially, distinct (diagonal-dominant), byte-identical at zero.
    n_material = sum(1 for g in gains if g >= MATERIAL)
    n_mono = sum(1 for m in monos if m)
    h1 = bool(n_material >= max(1, (n_ch + 1) // 2)      # majority pull materially
              and n_mono >= max(1, (n_ch + 1) // 2)
              and diag_dominant
              and byte["zero_bias_rows_and_O_bit_identical"])

    verdict = {
        "world": os.path.basename(args.world),
        "n_channels": n_ch, "s_phase": s_phase, "bars_per_condition": args.bars,
        "amplifies": amplifies, "strength_LAMBDA_T1p": strength,
        "mechanism": "SOFT per-channel fiber-measure lean (channel_logbias); "
                     "no clamp, nothing pinned, generative.",
        "per_channel": per_ch,
        "byte_identity": byte,
        "distinctness": {"confusion_diagonal_dominant": diag_dominant,
                         "amp1_unit_frac": [per_ch[ch]["unit_frac"][-1]
                                            for ch in range(n_ch)]},
        "material_threshold": MATERIAL,
        "n_channels_material": n_material, "n_channels_monotone": n_mono,
        "H1": h1, "verdict": ("H1_HOLDS" if h1 else "H0_NULL"),
    }
    with open(args.out, "w") as f:
        json.dump(verdict, f, indent=2)
    print("\n=== VERDICT (soft channel bias) ===")
    print(f"  channels pulling materially (unit_gain>={MATERIAL}): {n_material}/{n_ch}")
    print(f"  channels monotone: {n_mono}/{n_ch}   diag_dominant={diag_dominant}")
    print(f"  byte-identical@zero-bias (rows+O): {byte['zero_bias_rows_and_O_bit_identical']}")
    print(f"  -> {verdict['verdict']}   ({time.time()-t0:.1f}s)  -> {args.out}")
    return 0 if h1 else 2


if __name__ == "__main__":
    sys.exit(main())
