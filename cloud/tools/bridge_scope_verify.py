"""BRIDGE SCOPE (S-1..S-4 / BS-1..BS-4) — END-TO-END, IN PROCESS, NO NETWORK.

Answers the operator's question — "is the transition routing through other
tracks?" — the only way it can honestly be answered: by PLAYING a journey and
reading, bar by bar, which tracks actually received placements.

  [BS-0] a bridge actually       BEFORE any of BS-1..BS-4 are evaluated: at
         happened                least one bar was composed with LIVE in
                                 "bridge" mode toward the clicked destination,
                                 AND both the carried (source) track and the
                                 destination track actually drew placement
                                 mass across those bars. A bar set where only
                                 one track ever places is not a crossing, and
                                 a click that landed on idle/off (which routes
                                 through ``live_start`` — a JUMP, never
                                 ``_live_bridge_click``) never opens a bridge
                                 at all. FAILS LOUDLY, never skips, when this
                                 minimum evidence is absent — see the 2026-08-14
                                 adversarial-audit finding this guard exists to
                                 catch (BS-1 was measured PASSing over a
                                 transition log that was pure single-track
                                 straight play, ``t2=1.00``, because the tool
                                 asserted nothing about whether a bridge had
                                 actually formed).
  [BS-1] DIRECT holds the pair   during an A->B journey, EVERY bar VERIFIED
                                 (BS-0) to have been composed under the bridge
                                 fence has placement mass on {A, B} only. One
                                 such bar with a third track's material FAILS.
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

CLICK TIMING AND HOLD LENGTHS ARE DERIVED, NOT GUESSED (no new magic numbers):
  * click-B's delay (``--bars-before``, default derived) is HALF of the
    source track's own measured playable-bar count from the click point
    (``_playable_bars``, a pure simulation of ``live.bar_window``'s own
    forward-walking exhaustion rule over the track's STORED slice spans) —
    so by construction the click lands while LIVE is still in "straight"
    mode on the source, never after it has idled. Clicking late enough to
    outlive the source's own material is exactly what produced BS-1's
    vacuous PASS (the default was a fixed ``6``, one bar past this demo
    world's own ~3-bar straight-mode run from a near-start click).
  * the post-click hold (``--bars-after``, default derived) waits for the
    ENGINE'S OWN measured placement dominance (``p._last_shares`` — the same
    quantity THE PAIR RULE reads) to actually shift away from the source
    track, capped at a disclosed multiple of the number of bars the
    REGISTERED release law (``ets.panel.envelope.RegionSlew`` /
    ``live.release_step``, the SAME stepper the bridge itself steps every
    bar) takes to walk openness 1.0 -> 0.0. An explicit ``--bars-after``
    instead holds that many bars flat, unconditionally (e.g. for a fixed
    A/B comparison).

Writes the journey's audio to WAV so the transitions can be HEARD, with a
timestamped log of every click and every bar's per-track shares.

Usage:
  python3 cloud/tools/bridge_scope_verify.py [--world demo.etsworld]
      [--bars-before N] [--bars-after N] [--out /tmp/bridge.wav] [--open]

  (omit --bars-before/--bars-after entirely for the derived defaults; pass
  them explicitly to override — e.g. ``--bars-before 6`` deliberately clicks
  late enough on demo.etsworld to exhaust the source first, which is the
  BS-0 guard's own negative-control case: it must FAIL LOUDLY, not pass.)
"""
from __future__ import annotations

import argparse
import functools
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
    print("  [%s] %-28s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    return bool(ok)


def _shares(rows) -> dict:
    from cloud.companion import live as live_mod
    return live_mod.track_shares(rows)


def _playable_bars(live_mod, slices, s_phase: int, start_group: int, plan: dict) -> int:
    """PURE simulation of ``live.bar_window``'s own forward-walking exhaustion
    rule (the same call ``_compose_bar`` makes every bar): how many bars of
    STRAIGHT-mode material this click position can supply before the window
    reports ``exhausted``. Derived entirely from the track's OWN stored slice
    spans (via ``plan``/``start_group``, already measured off the track) —
    never a guessed or hardcoded bar count."""
    n = 0
    while True:
        win = live_mod.bar_window(slices, n, s_phase,
                                  start_group=start_group, plan=plan)
        if win["exhausted"]:
            return n
        n += 1


def _release_bars(live_mod) -> int:
    """PURE simulation of the REGISTERED release law (``live.release_step``,
    which steps ``ets.panel.envelope.RegionSlew`` at its REGISTERED
    ``SLEW_MAX_STEP``) from openness 1.0 down to 0.0 — the exact number of
    bars a bridge's own B-1 release takes on this engine build. Used as the
    tool's default post-click hold length so the release always gets a
    chance to finish inside the measurement window, without inventing a
    hold-length constant of our own."""
    o, n = 1.0, 0
    while o > 0.0 and n < 10000:
        o = live_mod.release_step(o)
        n += 1
    return n


def _assert_bridge_occurred(label: str, dest_track: int, compose_log: dict,
                            shares_by_bar: dict, click_snapshot: dict):
    """THE BS-0 GUARD (item 1 of the fix). Minimum evidence that a bridge
    toward ``dest_track`` actually happened, read off the SYNCHRONOUS
    write_bar spy (never polled/tagged from outside, so it cannot race the
    produce loop):

      1. a non-empty set of bars whose ``_compose_bar`` fenced them with
         LIVE in "bridge" mode toward this destination, AND
      2. across those bars, BOTH the carried (source) track and the
         destination track actually placed nonzero mass — a bar set where
         only one side of the pair ever sounds is straight play wearing a
         bridge's clothes, not a crossing.

    Returns ``(ok, bars)`` — ``bars`` is the verified bridge-fenced bar set,
    reused by the BS-1/BS-2 off-pair-mass check so that check never runs
    over an unverified bar. FAILS LOUDLY (via ``check``) rather than ever
    silently skipping the bars beneath it."""
    bars = sorted(b for b, info in compose_log.items()
                  if info["mode"] == "bridge" and info["dest"] == dest_track)
    if not bars:
        ok = check(label, False,
                   "NO bar was ever composed with LIVE in 'bridge' mode toward "
                   "track %d — the click did not open a bridge. p._bridge "
                   "immediately after the click: %r (mode at click time "
                   "implied by an empty dict = the click landed on idle/off, "
                   "so live_click routed to live_start — a JUMP, not "
                   "_live_bridge_click)" % (dest_track, click_snapshot))
        return ok, ()
    drew: dict = {}
    for b in bars:
        sh = shares_by_bar.get(b, {})
        src = compose_log[b]["source"]
        for t in (src, dest_track):
            if t is None:
                continue
            drew[int(t)] = drew.get(int(t), 0.0) + float(sh.get(int(t), 0.0))
    both_drawn = len(drew) >= 2 and all(v > 0.0 for v in drew.values())
    ok = check(label, both_drawn,
              "%d bridge-fenced bars toward track %d, mass drawn by the pair: %s%s"
              % (len(bars), dest_track, {k: round(v, 4) for k, v in drew.items()},
                 "" if both_drawn else
                 " — only one side of the pair ever placed; not a crossing"))
    return ok, (bars if both_drawn else ())


def run(world_path: str, bars_before, bars_after, out_wav: str, scope: str) -> int:
    from cloud.companion.engine_bridge import StreamPlayer
    from cloud.companion import live as live_mod
    from ets.writer.clamp import ClampTerms

    os.environ["ETS_BRIDGE_SCOPE"] = scope
    print("world=%s  scope=%s" % (world_path, scope), flush=True)
    p = StreamPlayer(world_path, seed=0, is_trained=True,
                     eigen_n_seed=2, eigen_n_bar=2)
    ntracks = len(p.world.tracks)
    A, B, C = 0, 2 % ntracks, 3 % ntracks
    # CLICK POSITIONS INSIDE THE MATERIAL: a t past a track's last slice makes
    # the forward window exhaust immediately. Measured per world, not assumed
    # (the demo world's slices span ~1s, a real set's span minutes).
    def _span(tr):
        _tid, sl = p._straight_track_slices(tr)
        # TIME IS COLUMN 0, NOT 3. track_unit_slices rows are
    # [t0_s, t1_s, unit_id, mass, q] -- column 3 is MASS. Every tool
    # written on 2026-08-14 read column 3 as seconds, so every 'click at
    # 30%% into the track' actually indexed the mass range and resolved to
    # whatever slice that number happened to hit (usually the very start).
        secs = [float(x[0]) for x in sl]
        return sl, min(secs), max(secs)
    sl_a, lo_a, hi_a = _span(A)
    sl_b, lo_b, hi_b = _span(B)
    _sl_c, lo_c, hi_c = _span(C)
    t_a = lo_a + 0.05 * (hi_a - lo_a)
    t_b = lo_b + 0.30 * (hi_b - lo_b)
    t_c = lo_c + 0.60 * (hi_c - lo_c)

    # --- DERIVE bars_before / bars_after from the WORLD ITSELF (item 2) ----
    # bars_before: half of track A's OWN measured playable-bar count from
    # t_a — guarantees (the produce loop's compose/finish run strictly
    # serially in this build, see _compose_bar/_finish_bar; there is no
    # pipeline lag to out-run) that click B lands while LIVE is still in
    # "straight" mode on A rather than after it has idled off the end of A's
    # material — the exact precondition BS-0 exists to catch when violated.
    j0_a = live_mod.resolve_start_index(sl_a, t_a)
    start_group_a = live_mod.group_of_index(sl_a, j0_a)
    plan_a = live_mod.build_plan(sl_a)
    playable_a = _playable_bars(live_mod, sl_a, p.s_phase, start_group_a, plan_a)
    release_bars = _release_bars(live_mod)
    derived_before = bars_before is None
    derived_after = bars_after is None
    if derived_before:
        bars_before = playable_a // 2
    if derived_after:
        bars_after = release_bars
    print("tracks=%d  A=%d@%.2fs B=%d@%.2fs C=%d@%.2fs  W=%d" %
          (ntracks, A, t_a, B, t_b, C, t_c, p._METER_WINDOW), flush=True)
    print("A's own playable straight-bars from t_a=%d  release law=%d bars  "
          "-> bars_before=%d%s bars_after=%d%s" %
          (playable_a, release_bars, bars_before,
           " (derived)" if derived_before else " (explicit)", bars_after,
           " (derived)" if derived_after else " (explicit)"), flush=True)

    # THE ENGINE'S OWN TRANSPORT, not hand-cranked bars. `live_start` starts the
    # produce loop; driving `produce_one_bar` alongside it composes bars OUTSIDE
    # the transport gate and therefore with no fence at all — a measurement
    # artefact that reads exactly like the defect under test. So: subscribe like
    # a browser does, and tap `_finish_bar` for each bar's REAL placement rows
    # (the same feed live_state and the heatmap read).
    import threading, queue as _queue
    pcm = bytearray()
    log = []            # (bar, seconds, label, shares) — display only
    shares_by_bar = {}  # bar -> {track_id: share} — the ONLY input to the checks
    bar_i = [0]
    tag = ["idle"]
    _orig_finish = p._finish_bar

    def _tap(r, sched):
        out = _orig_finish(r, sched)
        sh = _shares(list(r.rows))
        shares_by_bar[int(r.bar)] = sh
        log.append((bar_i[0], len(pcm) / 2.0 / 44100.0, tag[0], sh))
        bar_i[0] += 1
        return out
    p._finish_bar = _tap

    # THE BS-0 SPY (item 1): wraps the writer's OWN write_bar — the exact call
    # `_compose_bar` makes — so what is recorded is SYNCHRONOUS with
    # composition. Both `_compose_bar` branches (straight/bridge) mutate
    # `self._live` / `self._bridge` under `self._live_lock` BEFORE calling
    # write_bar, so reading them here, at the call, is the mode/pair THIS bar
    # was actually fenced under — no polling, no race against the produce
    # loop (unlike tagging bars from an external thread, the bug class BS-1's
    # vacuous pass came from). `functools.wraps` preserves the ORIGINAL
    # signature (including its `ClampTerms`-annotated parameter) so
    # `live.clamp_kwarg_name`'s introspection — which `_compose_bar` calls on
    # this very attribute every bar — keeps resolving correctly through the
    # wrapper.
    _orig_write_bar = p.engine.writer.write_bar
    compose_log = {}     # bar -> {"mode", "source", "dest", "track_mask"}

    @functools.wraps(_orig_write_bar)
    def _write_bar_spy(*args, **kwargs):
        with p._live_lock:
            mode_now = p._live.get("mode")
            br = dict(p._bridge) if p._bridge else None
        fence = None
        for v in kwargs.values():
            if isinstance(v, ClampTerms):
                fence = v
                break
        r = _orig_write_bar(*args, **kwargs)
        compose_log[int(r.bar)] = {
            "mode": mode_now,
            "source": (br or {}).get("source_track"),
            "dest": (br or {}).get("dest_track"),
            "track_mask": dict(getattr(fence, "track_mask", {}) or {}),
        }
        return r
    p.engine.writer.write_bar = _write_bar_spy

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
            elif p.live_state().get("mode") == "idle":
                # The passage ran off the end of the track and LIVE idled by
                # design (LM-9). This is EXPECTED for the "A" straight-play
                # phase whenever it is deliberately held past its own
                # material (e.g. an explicit --bars-before override) — not a
                # stall. Move on; BS-0 will judge what actually got composed.
                print("   %-10s idled after %d bars (window exhausted)"
                      % (label, bar_i[0] - (target - bars)), flush=True)
                return
            elif time.time() - stalled_since > 90:
                import faulthandler
                print("\nSTALLED %.0fs at bar %d during %s — thread dump:"
                      % (time.time() - stalled_since, bar_i[0], label), flush=True)
                faulthandler.dump_traceback()
                print("last_error=%r" % (getattr(p, "last_error", None),), flush=True)
                stalled_since = time.time()
        print("   %-10s %d bars, %.1fs audio, %.0fs wall"
              % (label, bars, len(pcm) / 2.0 / 44100.0, time.time() - t0), flush=True)

    def hold_until_dominant_shift(avoid_track, cap_bars, label):
        """BS-4's `from` (THE PAIR RULE, P-2) is deliberately an UNSMOOTHED
        single-bar read — "the dominant placement mass in the bar this click
        lands on" — so a mid-bridge re-click can only look "not
        stale/hardcoded" against the first click if the run has actually
        reached a bar where a DIFFERENT track is winning. A fixed bar count
        derived only from the release law (``release_bars``) is not enough
        to guarantee that (measured: near-50/50 single-bar swings for
        several bars even after release fully completes) — so hold bars
        until the ENGINE'S OWN measured dominance (``p._last_shares``, the
        exact quantity P-2 reads) actually differs from ``avoid_track``,
        capped so a world that genuinely never lets the destination win
        reports that honestly instead of hanging."""
        tag[0] = label
        start_bar = bar_i[0]
        t0 = time.time()
        last, stalled_since = bar_i[0], time.time()
        while bar_i[0] - start_bar < cap_bars and time.time() - t0 < 600:
            time.sleep(0.2)
            if bar_i[0] != last:
                last, stalled_since = bar_i[0], time.time()
                sh = dict(p._last_shares)
                if sh:
                    dom = max(sh.items(), key=lambda kv: kv[1])[0]
                    if int(dom) != int(avoid_track):
                        print("   %-10s dominance shifted to track %d after %d bars"
                              % (label, dom, bar_i[0] - start_bar), flush=True)
                        return
            elif p.live_state().get("mode") == "idle":
                print("   %-10s idled after %d bars (window exhausted)"
                      % (label, bar_i[0] - start_bar), flush=True)
                return
            elif time.time() - stalled_since > 90:
                import faulthandler
                print("\nSTALLED %.0fs at bar %d during %s — thread dump:"
                      % (time.time() - stalled_since, bar_i[0], label), flush=True)
                faulthandler.dump_traceback()
                print("last_error=%r" % (getattr(p, "last_error", None),), flush=True)
                stalled_since = time.time()
        print("   %-10s held %d bars, dominance never left track %d"
              % (label, bar_i[0] - start_bar, avoid_track), flush=True)

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
    if derived_after:
        # DERIVED default: don't just hold a fixed bar count -- wait for the
        # engine's OWN measured placement to actually favor someone other
        # than A, so BS-4's later "not stale" comparison has real evidence
        # to react to (see hold_until_dominant_shift's docstring). Capped at
        # a disclosed multiple of the registered release law (how long one
        # full release takes) rather than an invented flat number.
        avoid = int(carry_at_B[0]) if carry_at_B else int(A)
        hold_until_dominant_shift(avoid, release_bars * 4, "A->B")
    else:
        hold(bars_after, "A->B")

    # --- BS-4: mid-bridge re-click ----------------------------------------
    # THE PAIR RULE: `from` is the dominant track of the bar the click lands on,
    # and the pair is REPLACED rather than extended (per-leg carry is deleted).
    _sh = dict(p._last_shares)
    _sh.pop(int(C), None)
    sounding_before = ((max(_sh.items(), key=lambda kv: kv[1])[0],) if _sh else ())
    print("CLICK C: live_click(track=%d)  <- mid-bridge re-click" % C, flush=True)
    click_c_at = len(pcm) / 2.0 / 44100.0
    p.live_click(C, t_c)
    br1 = dict(p._bridge or {})
    carry_at_C = tuple(br1.get("carry_tracks") or ())
    # Same derived release-law hold as the first leg (item 2: no separate
    # invented constant for the second leg).
    hold(release_bars, "B->C")

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

    # BS-0 (item 1): the bridge must be PROVEN to have happened before either
    # BS-1 or BS-2 is allowed to say anything about off-pair mass. This is
    # the guard the adversarial audit found missing — it is what makes BS-1
    # able to FAIL instead of vacuously reporting "off-pair mass: none" over
    # a bar set that was never actually fenced as a bridge.
    guard1_ok, leg1_bars = _assert_bridge_occurred(
        "BS-0 bridge occurred (A->B)", B, compose_log, shares_by_bar, br0)

    if not guard1_ok:
        check("BS-1 direct holds pair" if scope == "direct" else "BS-2 open leaves pair",
              False, "SKIPPED-AS-FAIL: no verified bridge bars exist to check "
                     "off-pair mass over — see BS-0 above")
    else:
        stray = {}
        for b in leg1_bars:
            pair = {compose_log[b]["source"], compose_log[b]["dest"]}
            for t, v in shares_by_bar.get(b, {}).items():
                if int(t) not in pair and v > 0.0:
                    stray[int(t)] = stray.get(int(t), 0.0) + float(v)
        if scope == "direct":
            check("BS-1 direct holds pair", not stray,
                  "%d verified bridge bars, off-pair mass: %s"
                  % (len(leg1_bars), stray or "none"))
        else:
            check("BS-2 open leaves pair", bool(stray),
                  "%d verified bridge bars, off-pair tracks: %s"
                  % (len(leg1_bars), sorted(stray) or "none — DIRECT proves nothing"))

    check("BS-3 scope is journey data",
          guard1_ok and scope_at_start == scope and scope_at_end == scope,
          "start=%s end=%s%s" % (scope_at_start, scope_at_end,
                                 "" if guard1_ok else " (no verified bridge — see BS-0)"))

    guard2_ok, _leg2_bars = _assert_bridge_occurred(
        "BS-0 bridge occurred (->C)", C, compose_log, shares_by_bar, br1)

    want = tuple(sounding_before) or (int(B),)
    check("BS-4 pair = dominant+dest", guard2_ok and carry_at_C == want,
          "dominant=%s -> carry=%s (want %s)%s"
          % (list(sounding_before), list(carry_at_C), list(want),
             "" if guard2_ok else " (no verified bridge — see BS-0)"))
    check("BS-4 not stale/hardcoded", guard2_ok and carry_at_C != carry_at_B,
          "carry at B=%s, at C=%s%s" % (list(carry_at_B), list(carry_at_C),
                                        "" if guard2_ok else " (no verified bridge — see BS-0)"))

    # --- the transition log (what the audio contains, when) ----------------
    print("\nTRANSITION LOG", flush=True)
    for (b, s, lbl, sh) in log:
        cm = compose_log.get(b, {})
        print("  %6.1fs  bar %3d  %-10s mode=%-9s%s %s"
              % (s, b, lbl, cm.get("mode"),
                 (" pair=(%s,%s)" % (cm.get("source"), cm.get("dest"))
                  if cm.get("mode") == "bridge" else ""),
                 " ".join("t%d=%.2f" % (k, v) for k, v in sorted(sh.items()))),
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
    # No fixed default: bars-before/after are DERIVED from the world's own
    # measured material (see run()'s "DERIVE" section) unless explicitly
    # overridden here — a hardcoded default that outlives one world's own
    # material is exactly what produced BS-1's vacuous pass.
    ap.add_argument("--bars-before", type=int, default=None)
    ap.add_argument("--bars-after", type=int, default=None)
    ap.add_argument("--out", default="/tmp/bridge_journey.wav")
    ap.add_argument("--open", action="store_true",
                    help="run the OPEN-scope journey instead of DIRECT")
    a = ap.parse_args(argv)
    return run(a.world, a.bars_before, a.bars_after, a.out,
               "open" if a.open else "direct")


if __name__ == "__main__":
    raise SystemExit(main())
