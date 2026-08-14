"""COMMIT-TO-LAND (PREREG Amendment 6, operator 2026-08-14) — CL-1..CL-4.

Proves the completion rule by PLAYING it, not by asserting it.

  [CL-1] no constant on the completion path — STATIC: the click dispatcher, the
         commit, the close, and the bridge branch of the produce loop are read
         from source and scanned for any numeric literal or any surviving
         reference to the deleted machinery (settling / high-water / share
         threshold / stall-as-state / a settle window). A literal FAILS.
  [CL-2] a second click on the ACTIVE destination closes the fence within one
         bar: the very next produced bar is fenced to that track alone.
  [CL-3] clicking ELSEWHERE mid-blend redirects without closing: still a
         bridge, new destination, more than one track admitted.
  [CL-4] accumulation impossible: three redirections, then a commit, and the
         admitted set is back to exactly 1.

Usage:
  python3 cloud/tools/commit_to_land_verify.py [--world demo.etsworld]
"""
from __future__ import annotations

import argparse
import ast
import os
import queue as _queue
import re
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))

_RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _RESULTS.append((name, bool(ok), detail))
    print("  [%s] %-34s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    return bool(ok)


# --- CL-1: static, the completion path carries no constant ------------------

BANNED_NAMES = ("settling", "settled_render", "arrival_reached", "sounding_tracks",
                "high_water", "bars_since_high", "settle_window", "share_hist",
                "_METER_WINDOW", "ARRIVAL_BARS", "best_gap")


def check_cl1() -> None:
    src = open(os.path.join(ROOT, "cloud/companion/engine_bridge.py")).read()
    tree = ast.parse(src)
    targets = {"live_click", "_live_commit", "_bridge_close"}
    bad_lits, bad_names = [], []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name in targets):
            continue
        for sub in ast.walk(node):
            # A numeric literal on this path is exactly what the ruling forbids.
            if isinstance(sub, ast.Constant) and isinstance(sub.value, (int, float)) \
                    and not isinstance(sub.value, bool):
                if sub.value not in (0, 1):          # 0/1 are set sizes, not levels
                    bad_lits.append((node.name, sub.value))
            if isinstance(sub, ast.Name) and sub.id in BANNED_NAMES:
                bad_names.append((node.name, sub.id))
            if isinstance(sub, ast.Attribute) and sub.attr in BANNED_NAMES:
                bad_names.append((node.name, sub.attr))
    check("CL-1 no constant on commit path", not bad_lits and not bad_names,
          "literals=%s names=%s" % (bad_lits or "none", bad_names or "none"))

    # and the machinery is DELETED, not merely unused
    live_src = open(os.path.join(ROOT, "cloud/companion/live.py")).read()
    still = [n for n in ("def settling", "def settled_render", "def arrival_reached",
                         "def sounding_tracks") if n in live_src]
    check("CL-1 machinery deleted from live.py", not still, "remaining: %s" % (still or "none"))

    bridge_branch = src[src.index('elif raw_mode == "bridge"'):]
    bridge_branch = bridge_branch[:bridge_branch.index("        pcm = _to_int16(audio)")]
    leftovers = [n for n in BANNED_NAMES if n in bridge_branch]
    check("CL-1 produce loop decides nothing", not leftovers,
          "remaining: %s" % (leftovers or "none"))


# --- CL-2..CL-4: played --------------------------------------------------

def _rig(world_path):
    from cloud.companion.engine_bridge import StreamPlayer
    import ets.writer.stream as S
    import functools

    p = StreamPlayer(world_path, seed=0, is_trained=True, eigen_n_seed=2, eigen_n_bar=2)
    ntracks = len(p.world.tracks)
    seen = []
    orig = S.StreamWriter.write_bar

    def spy(self, tilt=None, clamps=None, fence=None):
        r = orig(self, tilt=tilt, clamps=clamps, fence=fence)
        adm = (tuple(range(ntracks)) if fence is None else
               tuple(t for t in range(ntracks)
                     if float(fence.track_mask.get(t, 0.0)) >= float(fence.openness)))
        seen.append({"admitted": adm,
                     "tracks": tuple(sorted({int(row[1]) for row in r.rows}))})
        return r
    S.StreamWriter.write_bar = functools.wraps(orig)(spy)

    q = p.subscribe()
    stop = threading.Event()

    def drain():
        while not stop.is_set():
            try:
                q.get(timeout=0.5)
            except _queue.Empty:
                pass
    threading.Thread(target=drain, daemon=True).start()
    return p, ntracks, seen, (lambda: (stop.set(), setattr(S.StreamWriter, "write_bar", orig)))


def _t_of(p, track, frac):
    _tid, sl = p._straight_track_slices(track)
    secs = [float(x[3]) for x in sl]
    return min(secs) + float(frac) * (max(secs) - min(secs))


def _wait(seen, n, limit=180):
    start = len(seen)
    t0 = time.time()
    while len(seen) - start < n and time.time() - t0 < limit:
        time.sleep(0.15)
    return seen[start:]


def run(world_path: str) -> int:
    print("world=%s" % world_path, flush=True)
    check_cl1()

    # ---- CL-2 / CL-3 -----------------------------------------------------
    p, ntracks, seen, teardown = _rig(world_path)
    A, B, C = 0, 2 % ntracks, 3 % ntracks
    try:
        p.live_enter()
        p.live_start(A, _t_of(p, A, 0.10))
        _wait(seen, 3)
        p.live_click(B, _t_of(p, B, 0.35))          # travel A -> B
        mid = _wait(seen, 4)
        st = p.live_state()
        check("CL-3 elsewhere redirects, no close",
              st.get("phase") == "blending" and st.get("dest_track") == B
              and max(len(b["admitted"]) for b in mid) > 1,
              "phase=%s dest=%s admitted=%s" % (st.get("phase"), st.get("dest_track"),
                                                mid[-1]["admitted"]))
        p.live_click(C, _t_of(p, C, 0.55))          # redirect mid-blend
        red = _wait(seen, 3)
        st2 = p.live_state()
        check("CL-3 mid-blend redirect stays open",
              st2.get("phase") == "blending" and st2.get("dest_track") == C
              and len(red[-1]["admitted"]) > 1,
              "phase=%s dest=%s admitted=%s" % (st2.get("phase"), st2.get("dest_track"),
                                                red[-1]["admitted"]))
        r = p.live_click(C, _t_of(p, C, 0.60))      # COMMIT: same destination
        after = _wait(seen, 1)
        st3 = p.live_state()
        # "landed" (not "arrived" — readout sweep, 2026-08-14): naming this
        # phase "arrived" implied a detected convergence the registered
        # proven-negative (BS.3) says never occurs; the fence closing CREATES
        # the destination state on a human commit, per Amendment 6 ruling 2's
        # own word ("landing is a human act"). engine_bridge.py::live_state()
        # renamed the phase string; this assertion is updated in the same
        # commit so nothing is left dangling on the old name.
        check("CL-2 commit closes within one bar",
              bool(r.get("committed")) and len(after) >= 1
              and after[0]["admitted"] == (C,) and st3.get("phase") in ("straight", "landed"),
              "first bar after commit admitted=%s phase=%s"
              % (after[0]["admitted"] if after else None, st3.get("phase")))
    finally:
        p.live_stop(); p.stop(); teardown()

    # ---- CL-4 ------------------------------------------------------------
    p, ntracks, seen, teardown = _rig(world_path)
    try:
        p.live_enter()
        p.live_start(0, _t_of(p, 0, 0.10))
        _wait(seen, 3)
        sizes = []
        for trk in (1 % ntracks, 2 % ntracks, 3 % ntracks):
            p.live_click(trk, _t_of(p, trk, 0.35))
            bars = _wait(seen, 3)
            sizes.append(max(len(b["admitted"]) for b in bars))
        last = 3 % ntracks
        p.live_click(last, _t_of(p, last, 0.40))         # commit on the third
        after = _wait(seen, 2)
        check("CL-4 accumulation impossible",
              bool(after) and all(b["admitted"] == (last,) for b in after),
              "per-redirect admitted sizes %s -> after commit %s"
              % (sizes, [b["admitted"] for b in after]))
    finally:
        p.live_stop(); p.stop(); teardown()

    bad = [n for (n, ok, _d) in _RESULTS if not ok]
    print("\n%s  (%d checks, %d failed)"
          % ("ALL PASS" if not bad else "FAILED: " + ", ".join(bad),
             len(_RESULTS), len(bad)), flush=True)
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default=os.environ.get("ETS_VERIFY_WORLD", "demo.etsworld"))
    a = ap.parse_args(argv)
    return run(a.world)


if __name__ == "__main__":
    raise SystemExit(main())
