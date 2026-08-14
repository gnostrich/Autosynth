"""BRIDGE ADMISSION — MEASUREMENT ONLY (operator directive, 2026-08-14).

No rule is proposed, fitted, or implemented here. This runs journeys, records
what actually happened per bar, and reports it. Specifically:

  * per-bar ADMITTED SET (read off the fence handed to the writer, not from the
    mode's intent) and its size;
  * per-bar PER-TRACK placement share (read off the produced bar's rows);
  * for redirections: the share history of the track being LEFT BEHIND (the
    interrupted leg's source) against the track still CARRYING the crossing
    (the interrupted leg's destination), so the question "is there any
    separation between them" can be answered from data;
  * the same for a plain 2-track journey, the case that already works.

The separation question is answered with a rank statistic that assumes nothing
about shape and needs no smoothing constant: the probability that a randomly
drawn bar's share for the left-behind track exceeds one for the carrying track
(Mann-Whitney U / AUC). 0.5 means the two are indistinguishable bar to bar;
1.0 or 0.0 means perfectly separated. It is reported, not thresholded.

Usage:
  python3 cloud/tools/bridge_admission_measure.py [--world demo.etsworld]
      [--bars 22] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import queue as _queue

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))   # arch-v6 owns `import ets`

import numpy as np


def _auc(a, b) -> float:
    """P(x from `a` > y from `b`) + 0.5 P(tie) — the rank statistic, computed
    directly. No binning, no kernel, no window: nothing to tune."""
    a = [float(x) for x in a]
    b = [float(x) for x in b]
    if not a or not b:
        return float("nan")
    wins = ties = 0
    for x in a:
        for y in b:
            if x > y:
                wins += 1
            elif x == y:
                ties += 1
    return (wins + 0.5 * ties) / float(len(a) * len(b))


def _admitted(fence, ntracks):
    """The tracks THIS bar's fence actually admits — evaluated with the
    carrier's own rule, on the object the writer received."""
    if fence is None:
        return tuple(range(ntracks))          # no fence: the whole corpus
    return tuple(t for t in range(ntracks)
                 if float(fence.track_mask.get(t, 0.0)) >= float(fence.openness))


def run_journey(world_path, legs, bars_per_leg, label):
    """One journey. `legs` is [(track, frac_into_track), ...]: the first is the
    opening click, each subsequent one is a click made while the previous leg is
    still in flight. Returns the per-bar record."""
    from cloud.companion.engine_bridge import StreamPlayer
    import ets.writer.stream as S
    import functools

    p = StreamPlayer(world_path, seed=0, is_trained=True,
                     eigen_n_seed=2, eigen_n_bar=2)
    ntracks = len(p.world.tracks)
    rec = []
    tag = ["pre"]

    orig = S.StreamWriter.write_bar

    def spy(self, tilt=None, clamps=None, fence=None):
        r = orig(self, tilt=tilt, clamps=clamps, fence=fence)
        tot = 0.0
        per = {}
        for (_s, tid, _u, _sec, m) in r.rows:
            tot += float(m)
            per[int(tid)] = per.get(int(tid), 0.0) + float(m)
        shares = {t: (m / tot) for t, m in per.items()} if tot > 0 else {}
        adm = _admitted(fence, ntracks)
        rec.append({"leg": tag[0], "admitted": list(adm), "n_admitted": len(adm),
                    "fenced": fence is not None,
                    "shares": {int(k): round(float(v), 4) for k, v in shares.items()}})
        return r
    S.StreamWriter.write_bar = functools.wraps(orig)(spy)

    def t_of(track, frac):
        _tid, sl = p._straight_track_slices(track)
        # TIME IS COLUMN 0, NOT 3. track_unit_slices rows are
    # [t0_s, t1_s, unit_id, mass, q] -- column 3 is MASS. Every tool
    # written on 2026-08-14 read column 3 as seconds, so every 'click at
    # 30%% into the track' actually indexed the mass range and resolved to
    # whatever slice that number happened to hit (usually the very start).
    secs = [float(x[0]) for x in sl]
        return min(secs) + float(frac) * (max(secs) - min(secs))

    q = p.subscribe()
    stop = threading.Event()

    def drain():
        while not stop.is_set():
            try:
                q.get(timeout=0.5)
            except _queue.Empty:
                pass
    threading.Thread(target=drain, daemon=True).start()

    def hold(n, name):
        tag[0] = name
        start = len(rec)
        t0 = time.time()
        while len(rec) - start < n and time.time() - t0 < 180:
            time.sleep(0.15)
            if p.live_state().get("mode") == "idle":
                break

    try:
        p.live_enter()
        first_track, first_frac = legs[0]
        p.live_start(int(first_track), t_of(int(first_track), first_frac))
        hold(3, "leg0-straight")
        click_bars = []
        for i, (trk, frac) in enumerate(legs[1:], start=1):
            click_bars.append(len(rec))
            p.live_click(int(trk), t_of(int(trk), frac))
            hold(bars_per_leg, "leg%d" % i)
    finally:
        try:
            p.live_stop()
            p.stop()
        except Exception:
            pass
        stop.set()
        S.StreamWriter.write_bar = orig

    return {"label": label, "legs": [[int(t), float(f)] for t, f in legs],
            "click_bars": click_bars, "ntracks": ntracks, "bars": rec}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default=os.environ.get("ETS_VERIFY_WORLD",
                                                      "demo.etsworld"))
    ap.add_argument("--bars", type=int, default=22)
    ap.add_argument("--out", default="/tmp/bridge_admission")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)

    # 5 journeys: three plain 2-track crossings (the working case, different
    # pairs and entry points) and two 3-track redirections.
    PLAN = [
        ("2track-0to2", [(0, 0.10), (2, 0.35)]),
        ("2track-1to3", [(1, 0.10), (3, 0.35)]),
        ("2track-3to0", [(3, 0.10), (0, 0.35)]),
        ("3track-0to2to3", [(0, 0.10), (2, 0.35), (3, 0.60)]),
        ("3track-1to0to2", [(1, 0.10), (0, 0.30), (2, 0.55)]),
    ]
    out = []
    for label, legs in PLAN:
        print("running %s ..." % label, flush=True)
        j = run_journey(a.world, legs, a.bars, label)
        out.append(j)
        print("   %d bars recorded" % len(j["bars"]), flush=True)

    path = os.path.join(a.out, "journeys.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print("WROTE %s" % path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
