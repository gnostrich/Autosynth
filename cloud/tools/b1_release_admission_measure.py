"""B-1 RELEASE — does openness actually change ADMISSION during a bridge?
MEASUREMENT ONLY (adversarial-finding follow-up, 2026-08-14). No rule is
proposed or changed here.

Instruments ``live.release_clamp`` (the ONE call that builds the bridge's
per-bar ClampTerms) directly, on the REAL produce loop, on TWO worlds:

  * ``demo.etsworld`` — the committed self-contained demo, via StreamPlayer,
    exactly as a browser session would drive it.
  * a SYNTHETIC world built with a much longer per-track tatum count (so the
    straight-phase window has NOT exhausted a track's material by the time a
    second click starts a bridge) — built the same way
    ``cloud/tests/test_wavemap_fixture.py`` builds its real-engine fixture
    (``roles.extract_prototypes`` -> ``anchors.build_world`` -> real
    ``StreamWriter``), just with more tatums per track.

For every bridge bar this records: ``openness_cur`` (the state passed in),
the resulting carrier's ``track_mask``/``openness``, the ADMITTED track set
computed with the carrier's own rule (mirrors ``bridge_admission_measure.
py``'s ``_admitted``), and whether ``pin_units``/``slot_pin`` were present
(non-empty) or empty on that call — the direct answer to "does the source's
forward-walking unit pin ever actually release something, or was it already
empty before release started".

Usage:
  python3 cloud/tools/b1_release_admission_measure.py [--bars 10]
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


def _admitted(fence, ntracks):
    """The tracks THIS bar's fence actually admits — evaluated with the
    carrier's OWN admission rule, on the object handed to the writer. Same
    reduction ``bridge_admission_measure.py`` uses."""
    if fence is None:
        return tuple(range(ntracks))          # no fence: the whole corpus
    return tuple(t for t in range(ntracks)
                 if float(fence.track_mask.get(t, 0.0)) >= float(fence.openness))


def _build_synthetic_world(out_dir, n_slots=200, n_bands=8, n_tracks=4):
    """A world with the SAME real-engine construction
    ``test_wavemap_fixture.ensure_world`` uses, but with ``n_slots`` tatums
    per track instead of 24 — enough tatum groups (``n_slots // s_phase``
    bars of straight-window room, s_phase defaulting to 8) that a click made
    early in the track does NOT exhaust the forward window within the bars a
    bridge needs to fully release (5 bars at SLEW_MAX_STEP=0.20). This
    isolates "release does nothing" from "there was nothing left to release
    on this world" — the whole point of this measurement, per the operator's
    STEP 1."""
    import numpy as np
    from pathlib import Path
    from cloud.tests.test_wavemap_fixture import _write_wav
    from ets.ingestion import beatclock as bc
    from ets.ingestion.pipeline import build_track
    from ets.writer import build_world_from_tracks
    from ets.engine.worldfile import save_world
    from cloud.companion.train_local import _calibrate_sigma_phi

    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    out = d / "synthetic_unexhausted.etsworld"
    if out.exists():
        return str(out)

    def make_track(tid, sr=22050):
        rng = np.random.default_rng(tid)
        n = n_slots * n_bands
        hop = sr // 8
        bounds = np.arange(n_slots + 1, dtype=np.int64) * hop
        slot_ix = np.repeat(np.arange(n_slots), n_bands)
        band_ix = np.tile(np.arange(n_bands), n_slots)
        uid = np.arange(n)
        phase = (slot_ix % 8) / 8.0
        fam = (band_ix >= n_bands // 2).astype(int)
        centers = np.array([[-4.0, -4.0, 0.0, 0.0], [4.0, 4.0, 0.0, 0.0]])
        timbre = centers[fam] + 0.15 * rng.standard_normal((n, 4))
        timbre[:, 2] += 2.0 * (tid % 2)
        chroma = np.full((n, 12), 1.0 / 12) + 0.01 * rng.random((n, 12))
        chroma[fam == 1, 0] += 0.5
        chroma /= chroma.sum(1, keepdims=True)
        masses = 0.2 + 0.8 * rng.random(n)
        units_cols = {"unit_id": uid, "slot": slot_ix, "band": band_ix,
                      "phase": phase, "bar": slot_ix // 8,
                      "level": np.zeros(n, np.int64)}
        prov_cols = {"unit_id": uid, "track_id": np.full(n, tid, np.int64),
                     "src_start": bounds[slot_ix], "src_end": bounds[slot_ix + 1],
                     "band": band_ix}
        grid = bc.BeatGrid(sr=sr, beats=bounds, downbeats=bounds[::8],
                           tatum_boundaries=bounds,
                           tempo_curve=np.full(max(n_slots - 1, 1), 120.0),
                           beats_per_bar=8, tatums_per_beat=1)
        return build_track(tid, units_cols, masses, timbre, chroma, phase, grid,
                           prov_cols, int(bounds[-1]), sr, rng)

    tracks = [make_track(i) for i in range(n_tracks)]
    paths = {}
    for tr in tracks:
        p = d / ("t%d.wav" % tr.track_id)
        _write_wav(str(p), tr.n_samples, tr.sr, int(tr.track_id))
        paths[int(tr.track_id)] = str(p)
    world = build_world_from_tracks(tracks, seed=0)
    sigma_phi = _calibrate_sigma_phi(world, tracks)
    tmp = str(out) + ".tmp"
    save_world(tmp, world, {"kind": "corpus", "paths": paths}, sigma_phi=sigma_phi)
    os.replace(tmp, str(out))
    return str(out)


def run_journey(world_path, src_track, src_frac, dst_track, dst_frac, bars, label):
    from cloud.companion.engine_bridge import StreamPlayer
    from cloud.companion import live as live_mod
    import functools

    p = StreamPlayer(world_path, seed=0, is_trained=True,
                     eigen_n_seed=2, eigen_n_bar=2)
    ntracks = len(p.world.tracks)
    calls = []

    orig_release_clamp = live_mod.release_clamp
    orig_bar_window = live_mod.bar_window
    win_calls = []
    click_marker = {"clicked": False}

    def spy_release_clamp(openness_cur, source_track, pin_units=None,
                          slot_pin=None, dest_track=None,
                          scope=live_mod.BRIDGE_SCOPE_DIRECT, carry_tracks=None):
        ct = orig_release_clamp(openness_cur, source_track, pin_units=pin_units,
                                slot_pin=slot_pin, dest_track=dest_track,
                                scope=scope, carry_tracks=carry_tracks)
        calls.append({
            "openness_cur_in": float(openness_cur),
            "pin_units_n": len(pin_units) if pin_units else 0,
            "slot_pin_n": len(slot_pin) if slot_pin else 0,
            "carrier_track_mask": dict(ct.track_mask) if ct is not None else None,
            "carrier_openness": float(ct.openness) if ct is not None else None,
            "admitted": list(_admitted(ct, ntracks)),
        })
        return ct

    def spy_bar_window(slices, bars_elapsed, s_phase, start_group=0, plan=None):
        w = orig_bar_window(slices, bars_elapsed, s_phase,
                            start_group=start_group, plan=plan)
        win_calls.append({
            "phase": "bridge" if click_marker["clicked"] else "straight",
            "bars_elapsed": int(bars_elapsed),
            "exhausted": bool(w["exhausted"]),
            "core_n": len(w.get("core") or ()),
        })
        return w

    # patch the NAMEs engine_bridge.py actually calls through (`live_mod.X` via
    # the `live` module object it imports), so the instrumentation sees every
    # real call the produce loop makes — not a copy.
    from cloud.companion import engine_bridge as EB
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
        time.sleep(0.5)             # let a couple straight bars land first
        click_marker["clicked"] = True
        p.live_click(int(dst_track), t_of(int(dst_track), dst_frac))
        hold(bars)
    finally:
        try:
            p.live_stop()
            p.stop()
        except Exception:
            pass
        stop.set()
        live_mod.release_clamp = orig_release_clamp
        live_mod.bar_window = orig_bar_window

    return {"label": label, "ntracks": ntracks, "calls": calls,
            "bridge_bar_window_calls": [w for w in win_calls if w["phase"] == "bridge"]}


def summarize(journey):
    calls = journey["calls"]
    admitted_sets = sorted(set(tuple(c["admitted"]) for c in calls))
    opennesses = [c["openness_cur_in"] for c in calls]
    pin_ns = [c["pin_units_n"] for c in calls]
    exh = [w["exhausted"] for w in journey.get("bridge_bar_window_calls", [])]
    return {
        "label": journey["label"],
        "n_bars": len(calls),
        "openness_trajectory": opennesses,
        "distinct_admitted_sets": [list(s) for s in admitted_sets],
        "admission_ever_changed": len(admitted_sets) > 1,
        "pin_units_n_trajectory": pin_ns,
        "pin_ever_nonzero": any(n > 0 for n in pin_ns),
        "pin_ever_zero": any(n == 0 for n in pin_ns),
        "pin_transitioned_nonzero_to_zero": any(
            pin_ns[i] > 0 and pin_ns[i + 1] == 0 for i in range(len(pin_ns) - 1)),
        # CAUSATION: was pin_units==0 caused by the window running off the end
        "exhausted_trajectory": exh,
        # of the track (bar_window's own "exhausted" flag) at a bar where
        # openness was STILL > 0 -- i.e. the pin vanished for a reason OTHER
        # than openness reaching its release floor?
        "exhausted_while_openness_still_positive": any(
            exh[i] and opennesses[i] > 1e-6 for i in range(min(len(exh), len(opennesses)))),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo-world", default=os.environ.get("ETS_VERIFY_WORLD",
                                                           os.path.join(ROOT, "demo.etsworld")))
    ap.add_argument("--bars", type=int, default=10)
    ap.add_argument("--out", default="/tmp/b1_release_admission")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)

    results = {}

    print("=== demo.etsworld: A(track0,0.05) -> bridge -> B(track2,0.35) ===", flush=True)
    j_demo = run_journey(a.demo_world, 0, 0.05, 2, 0.35, a.bars, "demo.etsworld A->B")
    results["demo"] = j_demo
    print(json.dumps(summarize(j_demo), indent=1), flush=True)

    print(flush=True)
    print("=== building synthetic UNEXHAUSTED world (n_slots=200/track) ===", flush=True)
    synth_path = _build_synthetic_world(os.path.join(a.out, "world"))
    print("synthetic world:", synth_path, flush=True)

    print("=== synthetic world: A(track0,0.02) -> bridge -> B(track2,0.5) ===", flush=True)
    j_synth = run_journey(synth_path, 0, 0.02, 2, 0.5, a.bars, "synthetic A->B")
    results["synthetic"] = j_synth
    print(json.dumps(summarize(j_synth), indent=1), flush=True)

    path = os.path.join(a.out, "release_admission.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=1)
    print(flush=True)
    print("WROTE %s" % path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
