"""BRIDGE PIN TRACK — the fence's ``unit_pin`` must name the SAME track its
units actually come from (2026-08-14 adversarial-audit finding, pre-fix).

``StreamPlayer._compose_bar``'s bridge branch cuts the forward window
(``pin_units``/``slot_pin``) from ``live["slices"]`` — the SESSION track's own
stored slices (set once at ``live_start`` and never reassigned across a
bridge/reroute) — but stamped the resulting fence as
``unit_pin=(source_track, pin_units)`` where ``source_track`` was
``self._bridge["source_track"]``, THE PAIR RULE's MEASURED dominant-mass
track. On a plain first click the two agree (the dominant track when nothing
else is sounding IS the session track), which is why this hid through every
existing check. A mid-bridge REROUTE recomputes the measured `from` from
freshly observed placement shares and can move it to a different track while
``live["track"]``/``live["slices"]`` stay frozen at the original session
track — so the fence ends up pinning one track's real unit ids under
ANOTHER track's name.

It is invisible on any world whose tracks share overlapping unit-id ranges
(every stock/demo world here: every track numbers 0..N-1) because a
"borrowed" id from the wrong track often happens to also name a real unit on
the named track. This fixture uses a SYNTHETIC world built with DISJOINT
per-track unit-id ranges (track t's ids live in [t*100000, t*100000+n)) so a
cross-track pin cannot hide: any unit_pin naming the wrong track will name
units that track provably does not own.

Every bar this fixture inspects is composed by an EXPLICIT, counted call to
``StreamPlayer._compose_bar``/``produce_one_bar`` — ``StreamPlayer.start`` is
stubbed to a no-op so the real-time background produce loop never runs. There
is no thread, no polling wait and no real-time race: which bar carries which
fence is fully determined by how many times this script calls compose, not by
wall-clock timing.

  [BPT-1] scenario diverges   after a mid-bridge reroute, the measured `from`
                               (``self._bridge["source_track"]``) and the
                               session track (``self._live["track"]``, the
                               track the forward window is actually cut from)
                               are DIFFERENT tracks — otherwise this fixture
                               would prove nothing.
  [BPT-2] pin names its owner every bridge bar's ``unit_pin``, when present,
                               names a track_id that is the REAL owner of
                               EVERY one of its pinned unit ids (checked
                               against the world's own, disjoint, per-track
                               id sets — never inferred).
  [BPT-3] common case          when NO reroute has happened (the measured
          untouched            `from` and the session track agree, the
                               ordinary case), BOTH a pure straight-play
                               passage AND a single-click bridge produce
                               tape BYTE-IDENTICAL to a reference hash —
                               proof, not assertion, that the fix changes
                               nothing when there is nothing to fix. Compare
                               with --baseline-pcm (write, on the pre-fix
                               tree) then --check-pcm (verify, on the fixed
                               tree).

Usage:
  python3 cloud/tools/bridge_pin_track_verify.py
      [--baseline-pcm PATH | --check-pcm PATH] [--keep-world]

There is no --world flag: the whole point is that no committed/demo world can
show this defect (every stock world numbers units 0..N-1 per track, so a
cross-track pin borrows ids that usually still resolve to something on the
wrong track). This tool always builds its own disjoint-id synthetic world.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))   # arch-v6 owns `import ets`

_RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _RESULTS.append((name, bool(ok), detail))
    print("  [%s] %-32s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    return bool(ok)


# --- the disjoint-id synthetic world -----------------------------------

_OFFSET = 100_000   # >> any track's real unit count; guarantees disjoint ranges
_N_SLOTS = 400       # >> s_phase * (bars this fixture composes); the window
                     # must never exhaust mid-run or the bridge branch falls
                     # back to silent_fence (no unit_pin to inspect at all)


def _disjoint_world(n_tracks: int = 4, seed: int = 0):
    """A world exactly like ``tests.harness.worldtools.build_synthetic_world``
    except each track's real unit ids are shifted into its OWN disjoint
    range — ``synthetic_track`` itself numbers every track 0..n-1 identically
    (checked; it has no track-id offset to opt into), so the shift is applied
    here, on the returned in-memory arrays, before the world is frozen. This
    does not touch ``ets/ingestion/pipeline.py`` — it is fixture-side control
    of the ids, exactly as directed."""
    from ets.ingestion.pipeline import synthetic_track
    from ets import writer as W
    tracks = []
    for t in range(n_tracks):
        tr = synthetic_track(track_id=t, n_slots=_N_SLOTS, n_bands=4, seed=seed + t)
        off = t * _OFFSET
        tr.units["unit_id"] = tr.units["unit_id"] + off
        tr.provenance_index["unit_id"] = tr.provenance_index["unit_id"] + off
        tracks.append(tr)
    return W.build_world_from_tracks(tracks, sigma=0.5), tracks


def _write_disjoint_worldfile(path: str, seed: int = 0) -> dict:
    """Writes the embedded .etsworld and returns {track_id: {real unit ids}},
    read straight off the frozen world (never invented) for BPT-2 to check
    a pin's claimed units against."""
    from tests.harness.worldtools import embedded_bank_for, measure_sigma_inline
    from ets.engine.worldfile import save_world
    world, _tracks = _disjoint_world(seed=seed)
    bank = embedded_bank_for(world)
    sigma = measure_sigma_inline(world, n_bars=6)
    save_world(path, world, {"kind": "embedded", "bank": bank}, sigma_phi=sigma)
    return {int(tr.track_id): set(int(u) for u in tr.units["unit_id"])
            for tr in world.tracks}


# --- the rig: SYNCHRONOUS, no thread, no real-time race -----------------

def _rig(world_path, seed=0):
    """A StreamPlayer with its background produce loop disabled. Every bar
    this script cares about is composed by an explicit call this script
    makes itself — ``live_start``/``live_click`` still call ``self.start()``
    internally (unchanged production code), but with ``start`` stubbed that
    is a no-op, so no thread ever races the main thread's bar-by-bar control."""
    from cloud.companion.engine_bridge import StreamPlayer
    import ets.writer.stream as S

    p = StreamPlayer(world_path, seed=seed, is_trained=True,
                     eigen_n_seed=2, eigen_n_bar=2)
    p.start = lambda: None

    fences = []
    orig = S.StreamWriter.write_bar

    def spy(self, tilt=None, clamps=None, fence=None):
        r = orig(self, tilt=tilt, clamps=clamps, fence=fence)
        fences.append(fence)
        return r
    S.StreamWriter.write_bar = functools.wraps(orig)(spy)

    def done():
        S.StreamWriter.write_bar = orig
    return p, fences, done


def _t_of(p, track, frac):
    _tid, sl = p._straight_track_slices(track)
    secs = [float(x[3]) for x in sl]
    return min(secs) + frac * (max(secs) - min(secs))


# --- BPT-1 / BPT-2: a mid-bridge reroute that forces from != session ----

def _check_pin_names_owner(world_path, real_ids):
    p, fences, done = _rig(world_path)
    try:
        p.live_enter()
        p.live_start(0, _t_of(p, 0, 0.10))
        p.live_click(1, _t_of(p, 1, 0.30))       # leg 1: 0 -> 1 (from == session,
        p._compose_bar()                         # the ordinary/common case) — ONE bar
                                                  # under the original, undiverged pair.

        # Plant a measured state whose dominant track is neither the session
        # track (0) nor the reroute's own destination (3) — the SAME
        # plant-and-observe technique cloud/tools/pair_rule_verify.py's PR-3
        # check uses to prove `from` is measured, not the session's own
        # remembered track.
        with p._live_lock:
            p._last_shares = {0: 0.1, 1: 0.05, 2: 0.9}
        p.live_click(3, _t_of(p, 3, 0.40))       # REROUTE: dest 1 -> 3, from -> 2
        r, _sched = p._compose_bar()             # the bar this fixture asserts on

        with p._live_lock:
            sess_track = p._live.get("track")
            br = dict(p._bridge) if p._bridge else {}
        check("BPT-1 scenario diverges",
              sess_track == 0 and br.get("source_track") == 2,
              "session track=%s measured from=%s (must differ for this "
              "fixture to test anything)" % (sess_track, br.get("source_track")))

        fence = fences[-1]
        if fence is None or fence.unit_pin is None:
            check("BPT-2 bridge fence pin names its own track", False,
                  "the reroute bar (bar=%s) carried no unit_pin at all — "
                  "cannot check" % int(r.bar))
        else:
            tid, units = fence.unit_pin
            owns = real_ids.get(int(tid), set())
            foreign = [int(u) for u in units if int(u) not in owns]
            check("BPT-2 bridge fence pin names its own track", not foreign,
                  "reroute bar's fence pin_track=%s n_units=%d n_foreign=%d "
                  "sample=%s" % (tid, len(units), len(foreign), foreign[:5]))
    finally:
        p.live_stop()
        done()


# --- BPT-4: slot_pin is keyed PER TRACK, not by slot alone (2026-08-14) --
#
# `unit_pin` (BPT-1/BPT-2 above) is one carrier field naming ONE track. This
# is the SIBLING defect the operator ruled on the same day: `slot_pin` used
# to be keyed by slot ALONE (`{slot: (unit_ids,)}`), so a bridge's two
# forward-walking windows shared one map entry per slot — either member
# could satisfy the OTHER member's slot from its own material. On worlds
# that number every track 0..N-1 identically (every stock/demo world here)
# this let a track roam: measured, straight-play spread inside a bar 55-63,
# the same bridge bar's spread 87-185 out of a 192-unit track once the two
# windows diverged. `slot_pin` is now keyed `{(track_id, slot): (unit_ids,)}`.
#
# This world's DISJOINT ids cannot reproduce the numeric-collision symptom
# above (no id ever repeats across tracks here, so a slot-only union could
# not admit a "foreign" id by coincidence) — that manifestation is proven on
# the OVERLAPPING-id grid in architecture-v6/tests/writer/test_fence_monotone.
# py::test_slot_pin_is_track_scoped, matching how demo.etsworld/
# synthetic_track actually number tracks. What THIS fixture proves, on the
# REAL engine's own produced fence (not a hand-built ClampTerms), is the
# STRUCTURAL property the numeric-collision bug depends on: that the emitted
# slot_pin is genuinely per-track-keyed end to end, through bar_window's
# per-window output and engine_bridge.py's merge, not just in a unit test of
# _admits alone. BPT-4d additionally reconstructs what the RETIRED slot-only
# union would have produced for the same bar, so the track-identity loss it
# had is visible even though this world's disjoint numbering does not let it
# misroute an admission.

def _check_slot_pin_track_scoped(world_path, real_ids):
    from cloud.companion import live as live_mod
    p, fences, done = _rig(world_path)
    try:
        p.live_enter()
        p.live_start(0, _t_of(p, 0, 0.10))
        p.live_click(1, _t_of(p, 1, 0.30))        # single click, no reroute: both
        p._compose_bar()                          # windows are freshly built together
        fence = fences[-1]
        sp = None if fence is None else fence.slot_pin
        check("BPT-4a slot_pin keys are (track, slot) tuples",
              bool(sp) and all(isinstance(k, tuple) and len(k) == 2 for k in sp),
              "n_entries=%d sample_keys=%s" % (len(sp or {}), list((sp or {}).keys())[:6]))
        if not sp:
            check("BPT-4b every entry's units belong to its own key's track", False,
                  "no slot_pin on this bar — cannot check")
            check("BPT-4c fixture is non-vacuous (>=2 tracks share a slot index)",
                  False, "no slot_pin on this bar — cannot check")
            return
        foreign = []
        for (tid, _sl), uids in sp.items():
            owns = real_ids.get(int(tid), set())
            foreign.extend(int(u) for u in uids if int(u) not in owns)
        check("BPT-4b every entry's units belong to its own key's track",
              not foreign, "n_entries=%d n_foreign=%d sample=%s"
              % (len(sp), len(foreign), foreign[:5]))

        slots_by_track: dict = {}
        for (tid, sl) in sp:
            slots_by_track.setdefault(int(tid), set()).add(int(sl))
        tracks_here = sorted(slots_by_track)
        shared = (set.intersection(*slots_by_track.values())
                  if len(slots_by_track) >= 2 else set())
        check("BPT-4c fixture is non-vacuous (>=2 tracks share a slot index)",
              len(tracks_here) >= 2 and bool(shared),
              "tracks=%s shared_slot_indices=%s" % (tracks_here, sorted(shared)[:5]))

        # BPT-4d: reconstruct the RETIRED slot-only union for the same bar
        # (bypassing the fixed merge code, computing it the way the struck
        # code did) and show it collapses two tracks' windows into one entry
        # per shared slot — the structural defect, even though this world's
        # disjoint numbering keeps it from misrouting an admission by id
        # collision (that symptom needs the OVERLAPPING-id grid instead).
        with p._live_lock:
            wins = dict((p._bridge or {}).get("windows") or {})
        old_union: dict = {}
        for tid, w in wins.items():
            if not w.get("slices"):
                continue
            bw = live_mod.bar_window(w["slices"], int(w.get("bars", 0)) - 1,
                                     p.s_phase, start_group=int(w.get("start_group", 0)),
                                     plan=w.get("plan"))
            if bw["exhausted"]:
                continue
            for sl, uids in (bw.get("slot_pin") or {}).items():
                old_union[int(sl)] = tuple(sorted(
                    set(old_union.get(int(sl), ())) | set(int(u) for u in uids)))
        collapsed = [sl for sl, uids in old_union.items()
                    if len({t for t in tracks_here
                            if any(int(u) in real_ids.get(t, set()) for u in uids)}) >= 2]
        check("BPT-4d retired scheme (context, not a pass/fail on the fix)",
              True, "slot-only union would have merged %d track(s)' windows into "
              "%d shared slot entries (e.g. slot %s -> %d units from %d tracks) "
              "-- the new (track,slot) keying gives each track its OWN entry "
              "instead" % (len(tracks_here), len(collapsed),
                           collapsed[0] if collapsed else "-",
                           len(old_union.get(collapsed[0], ())) if collapsed else 0,
                           2 if collapsed else 0))
    finally:
        p.live_stop()
        done()


# --- BPT-3: common case (no reroute) — byte-identical tape ---------------

def _straight_tape(world_path, seed=0, n_bars=8) -> bytes:
    """A pure straight-play passage — no bridge click at all. Never touches
    ``_compose_bar``'s bridge branch (this fix's only changed code), so this
    is the control: it must hash identically before and after the fix."""
    p, _fences, done = _rig(world_path)
    pcm = bytearray()
    try:
        p.live_enter()
        p.live_start(0, _t_of(p, 0, 0.10))
        for _ in range(n_bars):
            b, _roles = p.produce_one_bar()
            pcm.extend(b)
    finally:
        p.live_stop()
        done()
    return bytes(pcm)


def _single_click_bridge_tape(world_path, seed=0, n_bars=8) -> bytes:
    """A single bridge click, no reroute — the common case this fix must
    leave untouched: `from` (measured) and the session track agree by
    construction (nothing but the session track has sounded yet)."""
    p, _fences, done = _rig(world_path)
    pcm = bytearray()
    try:
        p.live_enter()
        p.live_start(0, _t_of(p, 0, 0.10))
        for _ in range(3):
            b, _roles = p.produce_one_bar()
            pcm.extend(b)
        p.live_click(1, _t_of(p, 1, 0.30))       # ONE click: from == session track
        for _ in range(n_bars):
            b, _roles = p.produce_one_bar()
            pcm.extend(b)
    finally:
        p.live_stop()
        done()
    return bytes(pcm)


def run(baseline_pcm=None, check_pcm=None, keep_world=False) -> int:
    tmpdir = tempfile.mkdtemp(prefix="bridge_pin_track_")
    world_path = os.path.join(tmpdir, "disjoint.etsworld")
    real_ids = _write_disjoint_worldfile(world_path, seed=0)
    print("world=%s (disjoint per-track unit ids, ranges: %s)"
          % (world_path,
             {tid: (min(ids), max(ids)) for tid, ids in real_ids.items()}),
          flush=True)

    if baseline_pcm or check_pcm:
        h_straight = hashlib.sha256(_straight_tape(world_path)).hexdigest()
        h_bridge = hashlib.sha256(_single_click_bridge_tape(world_path)).hexdigest()
        if baseline_pcm:
            open(baseline_pcm, "w").write("%s\n%s\n" % (h_straight, h_bridge))
            print("BASELINE straight=%s bridge=%s  %s"
                  % (h_straight[:16], h_bridge[:16], baseline_pcm), flush=True)
        else:
            lines = open(check_pcm).read().split()
            want_straight, want_bridge = lines[0], lines[1]
            check("BPT-3a straight play untouched", h_straight == want_straight,
                  "straight-play tape sha256 %s vs baseline %s"
                  % (h_straight[:16], want_straight[:16]))
            check("BPT-3b single-click bridge untouched", h_bridge == want_bridge,
                  "single-click-bridge tape sha256 %s vs baseline %s"
                  % (h_bridge[:16], want_bridge[:16]))

    _check_pin_names_owner(world_path, real_ids)
    _check_slot_pin_track_scoped(world_path, real_ids)

    if not keep_world:
        try:
            os.remove(world_path)
            os.rmdir(tmpdir)
        except OSError:
            pass

    bad = [nm for (nm, ok, _d) in _RESULTS if not ok]
    print("\n%s  (%d checks, %d failed)"
          % ("ALL PASS" if not bad else "FAILED: " + ", ".join(bad),
             len(_RESULTS), len(bad)), flush=True)
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-pcm")
    ap.add_argument("--check-pcm")
    ap.add_argument("--keep-world", action="store_true")
    a = ap.parse_args(argv)
    return run(a.baseline_pcm, a.check_pcm, a.keep_world)


if __name__ == "__main__":
    raise SystemExit(main())
