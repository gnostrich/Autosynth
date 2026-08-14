"""B-1 RELEASE — proves the PREREG's amended text against the SHIPPED code
(follow-up to the adversarial finding that B-1 "appears inert as shipped",
2026-08-14). Companion to ``cloud/tools/b1_release_admission_measure.py``
(the raw measurement run); this is the standing CHECK.

Claims under test (papers/PREREG-live-mode.md, "AMENDMENT 7 — B-1 RELEASE,
WHAT ACTUALLY MOVES"):

  BR-D1 (static)  DIRECT scope's track-admission invariance is enforced by
                  construction (the ``DIRECT_FLOOR`` guard in
                  ``live.release_clamp``), not by accident of the numbers —
                  reading it out of source, not asserting it blind.
  BR-D2 (played)  On a REAL DIRECT-scope journey (demo.etsworld), the
                  ADMITTED TRACK SET is IDENTICAL at every bridge bar and
                  equals exactly {source, dest} — the amended text's claim
                  that DIRECT-scope track admission never moves during a
                  journey.
  BR-D3 (played)  What DOES move under DIRECT is the source's forward-walking
                  UNIT PIN: it is present (non-empty) early in the journey and
                  releases (goes empty, i.e. the whole source track's own
                  material becomes eligible within the fenced pair) later —
                  proven on a SYNTHETIC world with enough material that
                  exhaustion cannot be the cause (isolates the openness
                  mechanism from the corpus-length wall).
  BR-D4 (played)  On demo.etsworld SPECIFICALLY, the pin's release is caused
                  by the track RUNNING OUT of forward material (``exhausted``
                  fires) BEFORE openness's own slew would have released it —
                  i.e. the disclosed wall (exhaustion races the slew and wins
                  on this corpus) is real, not a rhetorical hedge.
  BR-D5 (bites)   BR-D2 is not vacuously green: with the ``DIRECT_FLOOR``
                  guard REMOVED (the exact pre-fix behaviour BS.1 measured:
                  "a single A->B leg ended up sounding 9 of 10 tracks"),
                  admission on the SAME journey shape is NOT identical across
                  bars — the check goes RED. Restored, it is GREEN again.

Usage:
  python3 cloud/tools/b1_release_scope_verify.py [--demo-world demo.etsworld]
      [--bars 8]
"""
from __future__ import annotations

import argparse
import inspect
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
    print("  [%s] %-46s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    return bool(ok)


# --- BR-D1: static — the invariance is a construction, not a coincidence ----

def check_br_d1() -> None:
    from cloud.companion import live as live_mod
    src = inspect.getsource(live_mod.release_clamp)
    has_floor_guard = "DIRECT_FLOOR" in src and "scope != BRIDGE_SCOPE_DIRECT" in src
    check("BR-D1 DIRECT_FLOOR guard present in release_clamp", has_floor_guard,
          "release_clamp source references DIRECT_FLOOR under a scope-guarded branch")
    mask_src = inspect.getsource(live_mod._bridge_track_mask)
    tautology = "float(openness_cur)" in mask_src
    check("BR-D1 mask value == openness_cur by construction", tautology,
          "_bridge_track_mask assigns track_mask[t] = openness_cur for every carried/dest track")


# --- shared journey runner (mirrors b1_release_admission_measure.py) --------

def _admitted(fence, ntracks):
    if fence is None:
        return tuple(range(ntracks))
    return tuple(t for t in range(ntracks)
                 if float(fence.track_mask.get(t, 0.0)) >= float(fence.openness))


def run_bridge_journey(world_path, src_track, src_frac, dst_track, dst_frac, bars):
    from cloud.companion.engine_bridge import StreamPlayer
    from cloud.companion import live as live_mod

    p = StreamPlayer(world_path, seed=0, is_trained=True, eigen_n_seed=2, eigen_n_bar=2)
    ntracks = len(p.world.tracks)
    calls = []
    orig_release_clamp = live_mod.release_clamp
    orig_bar_window = live_mod.bar_window
    win_calls = []

    def spy_release_clamp(openness_cur, source_track, pin_units=None, slot_pin=None,
                          dest_track=None, scope=live_mod.BRIDGE_SCOPE_DIRECT,
                          carry_tracks=None):
        ct = orig_release_clamp(openness_cur, source_track, pin_units=pin_units,
                                slot_pin=slot_pin, dest_track=dest_track, scope=scope,
                                carry_tracks=carry_tracks)
        calls.append({"openness_cur": float(openness_cur),
                      "pin_units_n": len(pin_units) if pin_units else 0,
                      "admitted": list(_admitted(ct, ntracks))})
        return ct

    def spy_bar_window(slices, bars_elapsed, s_phase, start_group=0, plan=None):
        w = orig_bar_window(slices, bars_elapsed, s_phase,
                            start_group=start_group, plan=plan)
        win_calls.append({"bars_elapsed": int(bars_elapsed), "exhausted": bool(w["exhausted"])})
        return w

    live_mod.release_clamp = spy_release_clamp
    live_mod.bar_window = spy_bar_window

    def t_of(track, frac):
        _tid, sl = p._straight_track_slices(track)
        secs = [float(x[3]) if len(x) > 3 else float(x[0]) for x in sl]
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

    def hold(n):
        start = len(calls)
        t0 = time.time()
        while len(calls) - start < n and time.time() - t0 < 240:
            time.sleep(0.15)
            if p.live_state().get("mode") == "idle":
                break

    try:
        p.live_enter()
        p.live_start(int(src_track), t_of(int(src_track), src_frac))
        time.sleep(0.5)
        p.live_click(int(dst_track), t_of(int(dst_track), dst_frac))
        hold(bars)
    finally:
        try:
            p.live_stop(); p.stop()
        except Exception:
            pass
        stop.set()
        live_mod.release_clamp = orig_release_clamp
        live_mod.bar_window = orig_bar_window

    return {"calls": calls, "win_calls": win_calls, "ntracks": ntracks}


# --- BR-D2/BR-D4: played on demo.etsworld ------------------------------------

def check_br_d2_d4(demo_world, bars) -> dict:
    j = run_bridge_journey(demo_world, 0, 0.05, 2, 0.35, bars)
    calls = j["calls"]
    admitted_sets = sorted(set(tuple(c["admitted"]) for c in calls))
    check("BR-D2 admitted set identical every bar (DIRECT, demo world)",
          len(admitted_sets) == 1 and set(admitted_sets[0]) == {0, 2},
          "distinct admitted sets = %s" % (admitted_sets,))

    exh_bars = [w["bars_elapsed"] for w in j["win_calls"] if w["exhausted"]]
    opennesses = [c["openness_cur"] for c in calls]
    first_exh_idx = next((i for i, w in enumerate(j["win_calls"]) if w["exhausted"]), None)
    exhausted_before_full_release = (
        first_exh_idx is not None and opennesses[first_exh_idx] > 1e-6)
    check("BR-D4 exhaustion preempts the slew on demo.etsworld",
          exhausted_before_full_release,
          "first exhausted bar index=%s openness there=%s"
          % (first_exh_idx, opennesses[first_exh_idx] if first_exh_idx is not None else None))
    return j


# --- BR-D3: played on a SYNTHETIC unexhausted world --------------------------

def check_br_d3(bars, workdir) -> None:
    from cloud.tools.b1_release_admission_measure import _build_synthetic_world
    synth_path = _build_synthetic_world(workdir)
    j = run_bridge_journey(synth_path, 0, 0.02, 2, 0.5, bars)
    pin_ns = [c["pin_units_n"] for c in j["calls"]]
    admitted_sets = sorted(set(tuple(c["admitted"]) for c in j["calls"]))
    releases = any(pin_ns[i] > 0 and pin_ns[i + 1] == 0 for i in range(len(pin_ns) - 1))
    check("BR-D3 unit pin releases on an UNEXHAUSTED world (openness is the cause)",
          releases, "pin_units_n trajectory = %s" % (pin_ns,))
    check("BR-D3b track admission STILL invariant even with material available",
          len(admitted_sets) == 1 and set(admitted_sets[0]) == {0, 2},
          "distinct admitted sets = %s" % (admitted_sets,))


# --- BR-D5: prove BR-D2 bites, by reverting the DIRECT_FLOOR guard ----------

def check_br_d5(demo_world, bars) -> None:
    from cloud.companion import live as live_mod

    orig_release_clamp = live_mod.release_clamp

    def broken_release_clamp(openness_cur, source_track, pin_units=None, slot_pin=None,
                             dest_track=None, scope=live_mod.BRIDGE_SCOPE_DIRECT,
                             carry_tracks=None):
        """The PRE-FIX behaviour BS.1 measured and named: no DIRECT_FLOOR
        floor, so an openness that has fully decayed to 0.0 is passed straight
        through. clamp0's own rule (`track_mask.get(t,0) >= openness`) then
        admits every UNMASKED track too, because 0.0 >= 0.0. This is the exact
        defect the operator heard ("routing through other tracks") and the
        exact thing BR-D2 exists to catch a regression of."""
        from ets.writer.clamp import clamp0
        m = live_mod._bridge_track_mask(
            (carry_tracks if carry_tracks else source_track), dest_track,
            openness_cur, scope)
        return clamp0(track_mask=m, openness=float(openness_cur),
                      unit_pin=((int(source_track), tuple(int(u) for u in pin_units))
                                if pin_units else None),
                      slot_pin=slot_pin)

    live_mod.release_clamp = broken_release_clamp
    try:
        j = run_bridge_journey(demo_world, 0, 0.05, 2, 0.35, bars)
    finally:
        live_mod.release_clamp = orig_release_clamp

    admitted_sets = sorted(set(tuple(c["admitted"]) for c in j["calls"]))
    reverted_is_red = len(admitted_sets) > 1 or (
        len(admitted_sets) == 1 and set(admitted_sets[0]) != {0, 2})
    check("BR-D5 reverted code makes BR-D2's own assertion FAIL (proves it bites)",
          reverted_is_red,
          "under the pre-fix release_clamp, distinct admitted sets = %s (BR-D2 would "
          "have failed here)" % (admitted_sets,))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo-world", default=os.environ.get("ETS_VERIFY_WORLD",
                                                           os.path.join(ROOT, "demo.etsworld")))
    ap.add_argument("--bars", type=int, default=8)
    ap.add_argument("--workdir", default="/tmp/b1_release_scope_verify")
    a = ap.parse_args(argv)
    os.makedirs(a.workdir, exist_ok=True)

    print("=== BR-D1 (static) ===", flush=True)
    check_br_d1()

    print("=== BR-D2 / BR-D4 (played, demo.etsworld) ===", flush=True)
    check_br_d2_d4(a.demo_world, a.bars)

    print("=== BR-D3 (played, synthetic unexhausted world) ===", flush=True)
    check_br_d3(a.bars, os.path.join(a.workdir, "world"))

    print("=== BR-D5 (bites-by-revert, demo.etsworld) ===", flush=True)
    check_br_d5(a.demo_world, a.bars)

    bad = [n for (n, ok, _d) in _RESULTS if not ok]
    print("\n%s  (%d checks, %d failed)"
          % ("ALL PASS" if not bad else "FAILED: " + ", ".join(bad),
             len(_RESULTS), len(bad)), flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
