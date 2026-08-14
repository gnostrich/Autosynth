"""THE PAIR RULE (operator, 2026-08-14) — PR-1..PR-6.

A bridge is ALWAYS EXACTLY TWO TRACKS, {from, to}, and a mid-bridge reroute
REPLACES the pair rather than extending it.

  [PR-1] pair-size          admitted set is exactly 2 on every bridge bar and
                            exactly 1 on every straight-play bar, across a
                            3-redirect run. Any size 3+ FAILS.
  [PR-2] replacement        after a reroute the abandoned track is absent from
                            the admitted set on the VERY NEXT bar.
  [PR-3] from-is-measured   with a known mixed state, `from` equals the
                            dominant-mass track at the click bar. Driven by
                            planting a state whose dominant track is NOT the
                            session's own `track`, so a stale/hardcoded `from`
                            cannot pass.
  [PR-4] no-history         static: no accumulation structure and no
                            decay/trend/window logic on the admission path.
  [PR-5] commit-collapses   commit closes to exactly the destination (size 1).
  [PR-6] physics untouched  under a FIXED pair (one click, no reroute) the
                            produced tape is byte-identical to the pre-change
                            build. Run with --baseline-pcm to write the
                            reference from a checkout of the old commit, then
                            with --check-pcm here.

Usage:
  python3 cloud/tools/pair_rule_verify.py [--world demo.etsworld]
      [--baseline-pcm PATH | --check-pcm PATH]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import queue as _queue
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))

_RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _RESULTS.append((name, bool(ok), detail))
    print("  [%s] %-28s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    return bool(ok)


def _rig(world_path, seed=0):
    from cloud.companion.engine_bridge import StreamPlayer
    import ets.writer.stream as S
    import functools

    p = StreamPlayer(world_path, seed=seed, is_trained=True,
                     eigen_n_seed=2, eigen_n_bar=2)
    n = len(p.world.tracks)
    seen = []
    orig = S.StreamWriter.write_bar

    def spy(self, tilt=None, clamps=None, fence=None):
        r = orig(self, tilt=tilt, clamps=clamps, fence=fence)
        adm = (tuple(range(n)) if fence is None else
               tuple(t for t in range(n)
                     if float(fence.track_mask.get(t, 0.0)) >= float(fence.openness)))
        seen.append({"fenced": fence is not None, "admitted": adm,
                     "tracks": tuple(sorted({int(x[1]) for x in r.rows}))})
        return r
    S.StreamWriter.write_bar = functools.wraps(orig)(spy)

    q = p.subscribe()
    pcm = bytearray()
    stop = threading.Event()

    def drain():
        while not stop.is_set():
            try:
                pcm.extend(q.get(timeout=0.5))
            except _queue.Empty:
                pass
    threading.Thread(target=drain, daemon=True).start()

    def done():
        stop.set()
        S.StreamWriter.write_bar = orig
    return p, n, seen, pcm, done


def _t_of(p, track, frac):
    _tid, sl = p._straight_track_slices(track)
    secs = [float(x[3]) for x in sl]
    return min(secs) + frac * (max(secs) - min(secs))


def _wait(seen, k, limit=180):
    start = len(seen)
    t0 = time.time()
    while len(seen) - start < k and time.time() - t0 < limit:
        time.sleep(0.15)
    return seen[start:]


# --- PR-4: static ---------------------------------------------------------

def check_pr4():
    src = open(os.path.join(ROOT, "cloud/companion/engine_bridge.py")).read()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_live_bridge_click")
    # Read the CODE, not the prose: identifiers, attributes and call targets.
    # Scanning raw text would flag the comments that EXPLAIN the absence of
    # history, which is the check fooling itself rather than biting.
    BANNED = {"deque", "append", "_leg_drawn", "_live_share_hist", "sounding_tracks",
              "settling", "union", "history", "window", "decay", "trend"}
    banned = []
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Name) and sub.id in BANNED:
            banned.append(sub.id)
        elif isinstance(sub, ast.Attribute) and sub.attr in BANNED:
            banned.append(sub.attr)
        elif isinstance(sub, (ast.AugAssign,)) and isinstance(sub.op, ast.BitOr):
            banned.append("|= (set union)")
    check("PR-4 no-history on admission", not banned, "found: %s" % (banned or "none"))
    check("PR-4 no accumulation structure",
          "_leg_drawn" not in src and "_live_share_hist" not in src,
          "leg set / share window absent from the whole module")


def run(world_path, baseline_pcm=None, check_pcm=None) -> int:
    print("world=%s" % world_path, flush=True)
    check_pr4()

    # ---- PR-6: fixed-pair tape hash --------------------------------------
    if baseline_pcm or check_pcm:
        p, n, seen, pcm, done = _rig(world_path)
        try:
            p.live_enter()
            p.live_start(0, _t_of(p, 0, 0.10))
            _wait(seen, 3)
            p.live_click(2 % n, _t_of(p, 2 % n, 0.35))     # ONE click: pair fixed
            _wait(seen, 10)
        finally:
            p.live_stop(); p.stop(); done()
        h = hashlib.sha256(bytes(pcm)).hexdigest()
        if baseline_pcm:
            open(baseline_pcm, "w").write(h + "\n")
            print("BASELINE %s  %s" % (h[:16], baseline_pcm), flush=True)
            return 0
        want = open(check_pcm).read().strip()
        check("PR-6 physics untouched", h == want,
              "fixed-pair tape sha256 %s vs baseline %s" % (h[:16], want[:16]))

    # ---- PR-1 / PR-2 / PR-5: a 3-redirect run then a commit --------------
    p, n, seen, _pcm, done = _rig(world_path)
    A, B, C, D = 0, 1 % n, 2 % n, 3 % n
    try:
        p.live_enter()
        p.live_start(A, _t_of(p, A, 0.10))
        straight = _wait(seen, 3)
        pairs = []
        p.live_click(B, _t_of(p, B, 0.30))
        leg1 = _wait(seen, 4); pairs.append(p.live_state().get("admitted"))
        p.live_click(C, _t_of(p, C, 0.40))
        leg2 = _wait(seen, 4); pairs.append(p.live_state().get("admitted"))
        p.live_click(D, _t_of(p, D, 0.50))
        leg3 = _wait(seen, 4); pairs.append(p.live_state().get("admitted"))
        p.live_click(D, _t_of(p, D, 0.55))                  # COMMIT
        after = _wait(seen, 2)

        bridge_bars = [b for b in (leg1 + leg2 + leg3) if b["fenced"]]
        sizes = sorted({len(b["admitted"]) for b in bridge_bars})
        check("PR-1 bridge bars admit 2", sizes == [2],
              "%d bridge bars, admitted sizes %s" % (len(bridge_bars), sizes))
        s_sizes = sorted({len(b["admitted"]) for b in straight if b["fenced"]})
        check("PR-1 straight bars admit 1", s_sizes == [1],
              "straight admitted sizes %s" % s_sizes)

        # PR-2: the track abandoned at each reroute is gone on the next bar
        drops = []
        for prev, nxt in ((leg1, leg2), (leg2, leg3)):
            was = set(prev[-1]["admitted"])
            now = set(next(b for b in nxt if b["fenced"])["admitted"])
            drops.append((sorted(was), sorted(now), sorted(was - now)))
        check("PR-2 reroute replaces the pair",
              all(d[2] and not (set(d[0]) <= set(d[1])) for d in drops),
              " ; ".join("%s -> %s (dropped %s)" % d for d in drops))

        check("PR-5 commit collapses to 1",
              bool(after) and all(b["admitted"] == (D,) for b in after if b["fenced"]),
              "after commit: %s" % [b["admitted"] for b in after])
        print("  pairs at each click: %s" % pairs, flush=True)
    finally:
        p.live_stop(); p.stop(); done()

    # ---- PR-3: `from` is the dominant track, not the session's own -------
    p, n, seen, _pcm, done = _rig(world_path)
    try:
        p.live_enter()
        p.live_start(A, _t_of(p, A, 0.10))
        _wait(seen, 2)
        # Plant a measured state whose dominant track is NOT self._live["track"]:
        # a stale or hardcoded `from` would take the session's track and fail.
        planted = {int(A): 0.20, int(C): 0.80}
        with p._live_lock:
            p._last_shares = dict(planted)
        p.live_click(B, _t_of(p, B, 0.30))
        _wait(seen, 2)
        st = p.live_state()
        adm = tuple(st.get("admitted") or ())
        check("PR-3 from is measured",
              set(adm) == {int(C), int(B)} and st.get("source_track") == int(C),
              "planted dominant=t%d (session track=t%d) -> from=%s admitted=%s"
              % (C, A, st.get("source_track"), list(adm)))
    finally:
        p.live_stop(); p.stop(); done()

    bad = [nm for (nm, ok, _d) in _RESULTS if not ok]
    print("\n%s  (%d checks, %d failed)"
          % ("ALL PASS" if not bad else "FAILED: " + ", ".join(bad),
             len(_RESULTS), len(bad)), flush=True)
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default=os.environ.get("ETS_VERIFY_WORLD", "demo.etsworld"))
    ap.add_argument("--baseline-pcm")
    ap.add_argument("--check-pcm")
    a = ap.parse_args(argv)
    return run(a.world, a.baseline_pcm, a.check_pcm)


if __name__ == "__main__":
    raise SystemExit(main())
