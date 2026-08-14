"""BRIDGE SCOPE (S-1..S-4 / BS-1..BS-4) — END-TO-END, IN PROCESS, NO NETWORK.

Answers the operator's question — "is the transition routing through other
tracks?" — the only way it can honestly be answered: by PLAYING a journey and
reading, bar by bar, which tracks actually received placements.

  [BS-1] DIRECT holds the pair   during an A->B journey, EVERY produced bar's
                                 placement mass lands on {A, B} only. One bar
                                 with a third track's material FAILS the check.
  [BS-2] same path, different    the OPEN journey runs the identical code path
         data                    and is allowed to sound the corpus; if OPEN
                                 never leaves the pair the DIRECT result proves
                                 nothing, so this is reported, not asserted.
  [BS-3] scope is journey data   the scope recorded at journey start is the one
                                 the fence used for every bar of it.
  [BS-4] mid-bridge re-click     the admitted set equals sounding-over-W plus
                                 the new destination — computed from measured
                                 placement, and it PRUNES once a track stops
                                 sounding. A stale/hardcoded set fails.

Writes the journey's audio to WAV so the transitions can be HEARD, with a
timestamped log of every click and every bar's per-track shares.

Usage:
  python3 cloud/tools/bridge_scope_verify.py [--world demo.etsworld]
      [--bars-before 8] [--bars-after 24] [--out /tmp/bridge.wav] [--open]
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))   # arch-v6 owns `import ets`

import numpy as np

_RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _RESULTS.append((name, bool(ok), detail))
    print("  [%s] %-24s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    return bool(ok)


def _shares(rows) -> dict:
    from cloud.companion import live as live_mod
    return live_mod.track_shares(rows)


def run(world_path: str, bars_before: int, bars_after: int, out_wav: str,
        scope: str) -> int:
    from cloud.companion.engine_bridge import StreamPlayer
    from cloud.companion import live as live_mod

    os.environ["ETS_BRIDGE_SCOPE"] = scope
    print("world=%s  scope=%s" % (world_path, scope), flush=True)
    p = StreamPlayer(world_path, seed=0, is_trained=True,
                     eigen_n_seed=2, eigen_n_bar=2)
    ntracks = len(p.world.tracks)
    A, B, C = 0, 2 % ntracks, 3 % ntracks
    # CLICK POSITIONS INSIDE THE MATERIAL: a t past a track's last slice makes
    # the forward window exhaust immediately, LIVE idles by design, and the next
    # click lands on idle -> no bridge is ever created. Measured per world, not
    # assumed (the demo world's slices span ~1s, a real set's span minutes).
    def _span(tr):
        _tid, sl = p._straight_track_slices(tr)
        secs = [float(x[3]) for x in sl]
        return min(secs), max(secs)
    lo_a, hi_a = _span(A); lo_b, hi_b = _span(B); lo_c, hi_c = _span(C)
    t_a = lo_a + 0.05 * (hi_a - lo_a)
    t_b = lo_b + 0.30 * (hi_b - lo_b)
    t_c = lo_c + 0.60 * (hi_c - lo_c)
    print("tracks=%d  A=%d@%.2fs B=%d@%.2fs C=%d@%.2fs  W=%d"
          % (ntracks, A, t_a, B, t_b, C, t_c, p._METER_WINDOW), flush=True)

    # THE ENGINE'S OWN TRANSPORT, not hand-cranked bars. `live_start` starts the
    # produce loop; driving `produce_one_bar` alongside it composes bars OUTSIDE
    # the transport gate and therefore with no fence at all — a measurement
    # artefact that reads exactly like the defect under test. So: subscribe like
    # a browser does, and tap `_finish_bar` for each bar's REAL placement rows
    # (the same feed live_state and the heatmap read).
    import threading, queue as _queue
    pcm = bytearray()
    log = []            # (bar, seconds, tag, shares)
    bar_i = [0]
    tag = ["idle"]
    _orig_finish = p._finish_bar

    def _tap(r, sched):
        out = _orig_finish(r, sched)
        sh = _shares(list(r.rows))
        log.append((bar_i[0], len(pcm) / 2.0 / 44100.0, tag[0], sh))
        bar_i[0] += 1
        return out
    p._finish_bar = _tap

    q = p.subscribe()
    stop_ev = threading.Event()

    def _drain():
        while not stop_ev.is_set():
            try:
                pcm.extend(q.get(timeout=0.5))
            except _queue.Empty:
                continue
    th = threading.Thread(target=_drain, daemon=True)
    th.start()

    def hold(bars, label):
        """Let the ENGINE produce `bars` bars at its own pace. If it stops
        producing, DUMP EVERY THREAD rather than hanging silently — a bridge
        that halts the produce loop is exactly the failure worth catching."""
        tag[0] = label
        target = bar_i[0] + bars
        t0 = time.time()
        last, stalled_since = bar_i[0], time.time()
        while bar_i[0] < target and time.time() - t0 < 600:
            time.sleep(0.2)
            if bar_i[0] != last:
                last, stalled_since = bar_i[0], time.time()
            elif time.time() - stalled_since > 90:
                import faulthandler
                print("\nSTALLED %.0fs at bar %d during %s — thread dump:"
                      % (time.time() - stalled_since, bar_i[0], label), flush=True)
                faulthandler.dump_traceback()
                print("last_error=%r" % (getattr(p, "last_error", None),), flush=True)
                stalled_since = time.time()
        print("   %-10s %d bars, %.1fs audio, %.0fs wall"
              % (label, bars, len(pcm) / 2.0 / 44100.0, time.time() - t0), flush=True)

    # --- the journey -------------------------------------------------------
    p.live_enter()
    print("CLICK A: live_start(track=%d)" % A, flush=True)
    p.live_start(A, t_a)
    hold(bars_before, "A")

    print("CLICK B: live_click(track=%d)  <- the transition" % B, flush=True)
    click_b_at = len(pcm) / 2.0 / 44100.0
    p.live_click(B, t_b)
    br0 = dict(p._bridge or {})
    scope_at_start = br0.get("scope")
    carry_at_B = tuple(br0.get("carry_tracks") or ())
    hold(bars_after, "A->B")

    # --- BS-4: mid-bridge re-click ----------------------------------------
    sounding_before = live_mod.sounding_tracks(list(p._live_share_hist),
                                               p._METER_WINDOW)
    print("CLICK C: live_click(track=%d)  <- mid-bridge re-click" % C, flush=True)
    click_c_at = len(pcm) / 2.0 / 44100.0
    p.live_click(C, t_c)
    br1 = dict(p._bridge or {})
    carry_at_C = tuple(br1.get("carry_tracks") or ())
    hold(max(4, p._METER_WINDOW // 2), "B->C")

    scope_at_end = dict(p._bridge or {}).get("scope")
    p.live_stop()
    p.stop()
    stop_ev.set()
    th.join(timeout=3)

    # --- WAV ---------------------------------------------------------------
    data = bytes(pcm)
    with open(out_wav, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, 44100, 44100 * 2, 2, 16))
        f.write(b"data" + struct.pack("<I", len(data)) + data)
    print("\nWROTE %s  (%.1fs)  clicks at %.1fs (A->B) and %.1fs (B->C)"
          % (out_wav, len(data) / 2.0 / 44100.0, click_b_at, click_c_at), flush=True)

    # --- checks ------------------------------------------------------------
    print("\nCHECKS", flush=True)
    ab = [(b, s, sh) for (b, s, tag, sh) in log if tag == "A->B"]
    stray = {}
    for (_b, _s, sh) in ab:
        for t, v in sh.items():
            if int(t) not in (A, B) and v > 0.0:
                stray[int(t)] = stray.get(int(t), 0.0) + float(v)
    pair_only = not stray
    if scope == "direct":
        check("BS-1 direct holds pair", pair_only,
              "%d bars, off-pair mass: %s" % (len(ab), stray or "none"))
    else:
        check("BS-2 open leaves pair", bool(stray),
              "%d bars, off-pair tracks: %s"
              % (len(ab), sorted(stray) or "none — DIRECT proves nothing"))

    check("BS-3 scope is journey data",
          scope_at_start == scope and scope_at_end == scope,
          "start=%s end=%s" % (scope_at_start, scope_at_end))

    want = tuple(sorted((set(sounding_before) | {int(B)}) - {int(C)})) or (int(B),)
    check("BS-4 admitted = sounding+dest", carry_at_C == want,
          "sounding_over_W=%s -> carry=%s (want %s)"
          % (list(sounding_before), list(carry_at_C), list(want)))
    check("BS-4 not stale/hardcoded", carry_at_C != carry_at_B,
          "carry at B=%s, at C=%s" % (list(carry_at_B), list(carry_at_C)))

    # --- the transition log (what the audio contains, when) ----------------
    print("\nTRANSITION LOG", flush=True)
    for (b, s, tag, sh) in log:
        print("  %6.1fs  bar %3d  %-10s %s"
              % (s, b, tag, " ".join("t%d=%.2f" % (k, v) for k, v in sorted(sh.items()))),
              flush=True)

    bad = [n for (n, ok, _d) in _RESULTS if not ok]
    print("\n%s  (%d checks, %d failed)"
          % ("ALL PASS" if not bad else "FAILED: " + ", ".join(bad),
             len(_RESULTS), len(bad)), flush=True)
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default=os.environ.get("ETS_VERIFY_WORLD",
                                                      "demo.etsworld"))
    ap.add_argument("--bars-before", type=int, default=6)
    ap.add_argument("--bars-after", type=int, default=20)
    ap.add_argument("--out", default="/tmp/bridge_journey.wav")
    ap.add_argument("--open", action="store_true",
                    help="run the OPEN-scope journey instead of DIRECT")
    a = ap.parse_args(argv)
    return run(a.world, a.bars_before, a.bars_after, a.out,
               "open" if a.open else "direct")


if __name__ == "__main__":
    raise SystemExit(main())
