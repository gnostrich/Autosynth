"""LOCAL render bridge — the on-device decoder (CS-4: LOCAL only, never cloud).

All engine/render imports live HERE, isolated from the companion's cloud path
(app.run_train -> cloud.client), so that path stays provably decoder-free. This
module reuses the engine's ``produce_one`` building blocks VERBATIM — the same
``write_bar`` / ``bar_schedule`` / ``render`` / ``_playback_soft_limit`` /
``bar_role_activity`` the native live instrument uses — driven by the SINGLE
region-tilt control. It makes NO engine edits and authors no learned object.

The engine that carries the live playback loudness cap + read-only telemetry is
the ui-v5 engine tree (``architecture-v6/ets``); we put it first on sys.path so
``import ets`` resolves to it. (Root engine-v1 is byte-identical minus the
live-only cap; the native instrument runs on this same tree.)

Realtime note: bar EMISSION is paced to realtime (``_loop``; small fixed lead),
because an unpaced fast host renders far ahead and makes steering audible
minutes late for a realtime listener. Render itself still runs at the host's
speed; a slow box still under-runs and the browser simply buffers. Nothing here
changes the arrangement (H-8): u=0 bars are byte-identical to ``render_offline``.
"""
from __future__ import annotations

import logging
import struct
import sys
import threading
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("ets.companion.bridge")

_ARCH_V6 = str(Path(__file__).resolve().parents[2] / "architecture-v6")

# Anchor-profile arming (Theorem A arming corollary — papers/paper1-typed-control-
# calculus.md §3, papers/paper2-ets-instrument.md §2-3). The frozen anchor
# band-profile matrix ``world.fstate.B`` (M anchors x n_bands) is the coupling's
# band-grouping observable: a unit's anchor profile is its band's column B[:, band],
# and the per-track profile / per-role unit pool are reductions of it. If B carries
# NO information — every anchor row is flat across bands (the band-blind fixed point:
# F is band-blind, so uniform B is its fixed point, and every world trained to date
# sits exactly there) — that observable's constrained fluctuation is identically
# zero. By the fluctuation-dissipation identity two field controls that route
# THROUGH B then degenerate and DISARM (Phase-1A typing table):
#   * the ROLE->UNIT drill — the per-role pools are B-column-ranked, and under
#     uniform B they collapse (tie + top_n insertion order) to a single monopolizing
#     track: a FALSE attribution, so no honest unit pool exists;
#   * the TRACK-square LEAN — a track-bias direction built from the (all-ones) flat
#     profiles collapses onto the global density marginal (phi_density = sum
#     phi_region): a degenerate T1 whose "lean this track" label would lie.
# What STAYS ARMED under uniform B (these do NOT route through B's columns): the
# TRACK->ROLE drill (roles shown by index, no false ranking) and ROLE-square bias
# (a well-typed T1 tilt through the role indicator e_r). This is Theorem A's
# degenerate case, MEASURED off B here, never a policy flag: a world whose B has
# real band spread ARMS all of it automatically, so the pre-registered engine change
# that makes B informative re-arms with no edit here.
_PROFILE_ARMING_EPS = 1e-6   # numerical-noise floor on B's RELATIVE row spread


def anchor_profile_armed(B) -> bool:
    """MEASURED arming test for the anchor band-profile observable: ``True`` iff the
    matrix ``B`` (M x n_bands) DISTINGUISHES bands — i.e. some anchor row varies
    across bands above the numerical-noise floor. A uniform/degenerate B (the
    band-blind fixed point, every row flat) returns ``False`` (disarm the unit drill
    + track lean). The spread is measured RELATIVE to B's own magnitude, so it is
    scale-invariant and cannot be gamed by rescaling; it reads only the frozen B and
    nothing downstream."""
    Bm = np.asarray(B, dtype=np.float64)
    if Bm.size == 0:
        return False
    scale = float(np.max(np.abs(Bm)))
    if scale <= 0.0:                                   # all-zero B: no information
        return False
    row_ptp = float((Bm.max(axis=1) - Bm.min(axis=1)).max())
    return (row_ptp / scale) > _PROFILE_ARMING_EPS


class StreamPlayer:
    """Owns a loaded world + engine and a produce loop. The ONLY method that
    mutates the settlement input is :meth:`set_region` (the region-tilt lane).
    Everything else reads produced state."""

    def __init__(self, world_path: str, seed: int = 0, sigma_path: Optional[str] = None,
                 is_trained: bool = False):
        # Force the ui-v5 engine tree to the FRONT of sys.path (membership isn't
        # enough — root engine-v1 must not shadow it), THEN assert we actually
        # resolved the capped engine. If root ets was imported first, fail LOUD
        # rather than silently render without the eardrum cap / telemetry.
        while _ARCH_V6 in sys.path:
            sys.path.remove(_ARCH_V6)
        sys.path.insert(0, _ARCH_V6)
        import ets.engine.engine as _eng
        if not (hasattr(_eng, "_playback_soft_limit") and hasattr(_eng, "bar_role_activity")):
            raise RuntimeError(
                "companion resolved the ROOT engine-v1 (missing the live playback "
                "cap + telemetry). architecture-v6 must own `import ets`; run via "
                "`python -m cloud.companion` and ensure no root-ets import precedes "
                f"the bridge. resolved: {getattr(_eng, '__file__', '?')}")
        from ets.engine.engine import Engine, resolve_sigma
        from ets.engine.worldfile import load_world

        self.world_path = world_path
        # is_trained reports (truthfully) whether this world is the user's freshly
        # cloud-trained corpus (True) or the founding/demo world (False). The
        # Companion passes True only when it built the player from the trained
        # .etsworld produced by the train->play seam (cloud.companion.train_local).
        self.is_trained = bool(is_trained)
        self.wf = load_world(world_path)                 # ~0.5s (fast); no bank yet
        self.world = self.wf.world
        self.M = int(self.world.M)
        self.sr = int(self.world.sr)
        self.seed = int(seed)
        sigma = resolve_sigma(self.wf, sigma_path)
        self.engine = Engine(self.wf, profile="desktop", seed=self.seed, sigma=sigma)
        self.s_phase = self.engine.writer.s_phase

        self._bank = None                                # lazy: built on first bar (slow)
        self._region = np.zeros(self.M, dtype=np.float32)  # the SINGLE control input
        self._lock = threading.Lock()
        self._playing = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._bar_index = 0
        # WARMED (OPEN_ENDS #21d): has the produce loop rendered its FIRST bar yet?
        # False until the loop emits (the bank build + first render is the multi-
        # minute cold window a listener would otherwise sit through in silence).
        # Read-only state for /api/world; set once by _loop, never by any input.
        self._warmed = False
        # LOOP HONESTY (OPEN_ENDS #21c): the last produce-loop failure, as a
        # timestamped "<ISO-time> <ExcType>: <msg>" string, or None. Exposed via
        # world_info()/telemetry so a dead engine reports "engine failed: <type>"
        # instead of an infinite silent stream.
        self.last_error: Optional[str] = None
        # latest read-only telemetry (roles 0..1, per-track nowplaying, elapsed
        # seconds) — for /api/telemetry. `nowplaying` starts empty (no bar yet).
        # `lanes` are per-bar Layer-0 φ statistics reduced to intrinsic [0,1]
        # readouts; `loop`/`slide` are the gauge-drift jack pair (read-only meters,
        # spec §9). All start absent (None → "—" on the web) until the first bar.
        self.telemetry = {"roles": [0.0] * self.M, "t": 0.0, "bar": 0,
                          "nowplaying": {},
                          "lanes": {"region": None, "continuity": None,
                                    "novelty": None, "density": None},
                          "loop": None, "slide": None}
        # I-8 bounded windows (deque, maxlen) for the two whole-trajectory gauge
        # meters: committed occupancy O per bar (loop[g]) and the gauge-frame
        # trajectory (slide[g]). Bounded by material window, never by elapsed time.
        from collections import deque
        self._METER_WINDOW = 16
        self._O_window: "deque" = deque(maxlen=self._METER_WINDOW)
        self._frame_hist: "deque" = deque(maxlen=self._METER_WINDOW)
        # STATIC per-world field telemetry (computed ONCE, here at load): the SAME
        # read-only reductions the desktop engine emits over /ets/profiles +
        # /ets/unitpool (ets.engine.engine.track_anchor_profiles / role_unit_pool).
        # They read only the frozen world (fstate.B + track provenance) — no bank,
        # no settlement, no writer, no F. Mirrors Engine.run_live's startup exactly.
        from ets.engine.engine import track_anchor_profiles, role_unit_pool
        self._track_profiles = track_anchor_profiles(self.world)   # {tid: (M,)}
        self._role_pools = role_unit_pool(self.world)              # {role: [...]}
        # ANCHOR-PROFILE ARMING (Theorem A arming corollary; module docstring above).
        # MEASURED once off the frozen world's anchor band-profile B: True iff B
        # distinguishes bands (some anchor row varies), False on the band-blind fixed
        # point (uniform B). It gates the two field controls that route through B's
        # columns — the ROLE->UNIT drill (pools) and the TRACK-square LEAN — while the
        # TRACK->ROLE drill and ROLE bias (which do not route through B) stay armed.
        self._profile_armed = anchor_profile_armed(self.world.fstate.B)
        self._static_field_cache: Optional[dict] = None
        # Per-listener PCM fan-out. ONE produce loop broadcasts each bar to every
        # subscriber's own queue, so a SHARED engine (the demo singleton, or a shared
        # set several visitors opened) can serve concurrent listeners without any
        # listener stealing another's audio. Steer + telemetry AND TRANSPORT
        # (play/stop) are shared state on a shared engine — a disclosed
        # consequence of one engine per world: concurrent listeners co-play one
        # live mix. An LRU-evicted engine stops mid-stream for any current
        # listener (the memory bound is real; the world file reloads on demand).
        self._subscribers: set = set()
        self._sub_lock = threading.Lock()

    # --- world info ---------------------------------------------------------
    def world_info(self) -> dict:
        # `is_trained` reports truthfully which world is loaded: True for the
        # user's freshly cloud-trained corpus (built by the train->play seam,
        # cloud.companion.train_local: local ingest -> cloud anchor-fit -> local
        # build_index -> playable .etsworld), False for the founding/demo world.
        # The UI reads this to label what is actually playing. (The seam is WIRED;
        # see PREREG-cloud-mvp2 "Phase-2 seam WIRED" amendment.)
        # Which steering lanes are ARMED (their σ_φ scale was identified) vs
        # DISARMED (measured σ=0 at u=0 → no tilt applied). Reported so the UI can
        # be honest: a DISARMED region means region-tilt taps settle no differently,
        # so the steer surface must say so rather than pretend it steers.
        sig = getattr(self.engine, "sigma", None)
        lanes = ["region", "cont", "novelty", "density", "gauge"]
        if sig is None:
            armed, disarmed = [], list(lanes)
        else:
            armed = [ln for ln in lanes if sig.is_identifiable(ln)]
            disarmed = [ln for ln in lanes if not sig.is_identifiable(ln)]
        return {"ready": True, "M": self.M, "sr": self.sr,
                "world": Path(self.world_path).name,
                "is_trained": self.is_trained,
                "armed": armed, "disarmed": disarmed,
                "region_armed": ("region" in armed),
                # ANCHOR-PROFILE ARMING (Theorem A corollary): whether the anchor
                # band-profile observable carries information on THIS world (measured
                # off B). False on the band-blind fixed point (uniform B) → the FE
                # disarms the role->unit drill and the track-square lean, keeping the
                # track->role drill and role bias live.
                "profile_armed": bool(self._profile_armed),
                # honest engine-state readouts (OPEN_ENDS #21c/d): warmed = has the
                # produce loop rendered its first bar; last_error = the loop's
                # recorded failure (None while healthy). Real flags, never inferred.
                "warmed": bool(self._warmed),
                "last_error": self.last_error,
                "bar_seconds": float(self.engine.writer.bar_seconds)}

    # --- STATIC per-world field telemetry (read-only, once-per-world) -------
    def static_field(self) -> dict:
        """The world's STATIC field telemetry as JSON-ready dicts — the web analog
        of the desktop's /ets/profiles + /ets/unitpool feeds, from the SAME
        reductions (computed at load in __init__):

          * ``profiles``   {track_id: [float]*M}  — each source track's peak-
            normalized anchor-mass profile (track_anchor_profiles). The TRACK
            grain of the field ladder: fill/expandability come from these.
          * ``unit_pools`` {role: [{unit_id, track_id, band, profile:[float]*M}]}
            — each role's drill-in unit pool (role_unit_pool). The UNIT grain.
          * ``track_names`` {track_id: str} — an HONEST display label per track.
            The frozen world carries NO source filenames (embedded/synthetic
            tracks have none), so the bridge labels tracks by WHAT THEY ARE: a
            demo/founding world's tracks are ``"demo track N"``; a trained world's
            tracks are ``"track N"`` here. Real ingested filenames are known only
            to the SESSION (not the world), so the companion overrides these with
            the true names for a session's OWN trained world (see app.py). No
            invented names, ever.

        Pure serialization of already-frozen reductions; it touches NOTHING
        downstream (no bank, settlement, writer, render, F) and is cached, so a
        world's static section is built once. Static."""
        if self._static_field_cache is None:
            profiles = {int(t): [float(x) for x in np.asarray(v).reshape(-1)]
                        for t, v in self._track_profiles.items()}
            # UNIT-DRILL DISARM (Theorem A arming corollary). The per-role unit POOLS
            # are the role->unit reduction of the band-profile grouping observable. On
            # the band-blind fixed point (uniform B) that observable carries no
            # information: the pools collapse (tie + top_n insertion order) to a single
            # monopolizing track, a FALSE attribution. We refuse to serve them as
            # informative — the pools are EMPTY when disarmed, and profile_armed says
            # so honestly, so the FE's floor gate makes role squares non-expandable
            # (no unit drill). The per-TRACK profiles STAY (tracks are real provenance;
            # a flat profile is the honest truth of uniform B), keeping the track->role
            # drill open (roles shown by index, no false ranking) and role bias live;
            # only the TRACK-square lean is gated off on the FE (profile_armed). A
            # world whose B is informative arms automatically → pools served.
            pools: dict = {}
            if self._profile_armed:
                for role, entries in self._role_pools.items():
                    pools[int(role)] = [
                        {"unit_id": int(uid), "track_id": int(tid), "band": int(band),
                         "profile": [float(x) for x in np.asarray(prof).reshape(-1)]}
                        for (uid, tid, band, prof) in entries]
            kind = "track" if self.is_trained else "demo track"
            names = {int(t): "%s %d" % (kind, int(t)) for t in profiles}
            self._static_field_cache = {"profiles": profiles, "unit_pools": pools,
                                        "track_names": names,
                                        "profile_armed": bool(self._profile_armed)}
        return self._static_field_cache

    # --- THE SINGLE ENGINE-CONTROL PATH ------------------------------------
    def set_region(self, region) -> None:
        """Set the region-tilt lane — the ONLY input that reaches settlement.
        `region` is a length-M vector; it is clamped to the panel's safe envelope
        so a decisive multi-lane steer can't drive the writer to divergence."""
        vec = np.asarray(region, dtype=np.float32).reshape(-1)
        if vec.size < self.M:
            vec = np.concatenate([vec, np.zeros(self.M - vec.size, np.float32)])
        vec = vec[:self.M]
        from ets.panel.envelope import clamp_region     # reuse the engine's own wall
        vec = np.asarray(clamp_region(vec), dtype=np.float32)
        with self._lock:
            self._region = vec

    def _current_lane(self):
        from ets.panel.lanes import default_lane_vector
        u = default_lane_vector(self.M)
        with self._lock:
            u.u_region = np.asarray(self._region, dtype=np.float32).copy()
        return u

    # --- bar production (mirrors Engine.produce_one) -----------------------
    def _ensure_bank(self):
        if self._bank is None:
            from ets.engine.engine import build_bank
            self._bank = build_bank(self.wf)      # slow warmup (materialize units)

    def produce_one_bar(self):
        """Produce ONE bar of capped PCM + role telemetry, exactly as the engine's
        live loop does. Returns (pcm_int16_bytes, roles_list)."""
        from ets.engine.engine import (bar_schedule, _playback_soft_limit,
                                        bar_role_activity, nowplaying_activity)
        from ets.render import render as render_schedule
        self._ensure_bank()
        u = self._current_lane()
        tilt = self.engine._tilt_for(u)                      # ONE lane->tilt point
        r = self.engine.writer.write_bar(tilt=tilt)
        sched = bar_schedule(self.world, r.rows, self.s_phase)
        audio, _prov = render_schedule(sched, self._bank)
        audio = _playback_soft_limit(audio)                  # LIVE-only eardrum cap
        # STREAM MONO CONTRACT (live-only, like the soft limit): `wav_header` declares
        # ONE channel, and the FE frames the byte stream as mono int16. If a render
        # ever returns a 2-D (multi-channel) buffer, `_to_int16` would emit INTERLEAVED
        # samples that the mono header mislabels — the exact "sample alignment / dtype
        # mismatch" failure mode that decodes as white-noise garbage. Collapse to mono
        # here so the emitted PCM can never disagree with the header. For the demo world
        # (mono render) this is a no-op — the streamed bytes stay byte-identical to
        # `produce_one`, verified in tests/test_stream_decode.py.
        audio = np.asarray(audio)
        if audio.ndim > 1:
            audio = audio.mean(axis=tuple(range(1, audio.ndim)))
        roles = bar_role_activity(r.rows, self._bank, self.world.fstate.B)
        roles = [float(x) for x in np.asarray(roles).reshape(-1)[:self.M]]
        # READ-ONLY per-track nowplaying: reduce the just-produced bar's rows by
        # source track (the SAME reduction the desktop emits on /ets/nowplaying —
        # engine.nowplaying_activity). Reads produced rows only; adds no downstream
        # call (audio byte-identical on/off). Keyed by track_id for the field's
        # TRACK/UNIT square fills.
        nowplaying = {int(tid): float(act)
                      for tid, act in nowplaying_activity(r.rows)}
        self._bar_index = int(r.bar)
        lanes = self._lane_readouts(r)
        loop_val, slide_val = self._gauge_meters(r)
        self.telemetry = {"roles": roles, "bar": int(r.bar),
                          "t": float(r.bar * self.engine.writer.bar_seconds),
                          "nowplaying": nowplaying,
                          "lanes": lanes, "loop": loop_val, "slide": slide_val}
        pcm = _to_int16(audio)
        return pcm, roles

    # --- read-only display reductions of the produced bar (spec §9) ---------
    def _lane_readouts(self, r) -> dict:
        """The four Lane-Console lanes as INTRINSIC [0,1] reductions of this bar's
        Layer-0 φ statistics (ets.writer.phi; carried on r.phi) — the SAME read-only
        pattern as roles/nowplaying. No invented constant: every bound comes from the
        bar itself (anchor count M, placement count, slot count s_phase). Feeds the
        web display only; touches no settlement/writer/F (I-5/I-14)."""
        phi = r.phi
        # region: occupancy concentration of φ_region, 0=uniform .. 1=one anchor.
        region_vec = np.asarray(phi["region"], float).reshape(-1)
        tot = float(region_vec.sum())
        if tot > 0.0 and self.M > 1:
            peak = float(region_vec.max()) / tot
            region = (peak - 1.0 / self.M) / (1.0 - 1.0 / self.M)
        else:
            region = 0.0
        # continuity: share of this bar's placements that continue a real source run.
        n_place = len(r.rows)
        continuity = (float(phi["cont"]) / n_place) if n_place else 0.0
        # density: fraction of the bar's metrical slots carrying any placement.
        filled = len({int(row[0]) % self.s_phase for row in r.rows})
        density = filled / float(self.s_phase) if self.s_phase else 0.0
        # novelty: recency-weighted unit reuse vs the committed tape (already [0,1]).
        novelty = float(phi["novelty"])
        clamp = lambda v: float(max(0.0, min(1.0, v)))
        return {"region": clamp(region), "continuity": clamp(continuity),
                "novelty": clamp(novelty), "density": clamp(density)}

    def _gauge_meters(self, r):
        """The gauge-drift jack pair (spec §9), read-only, over BOUNDED windows:
          loop[g] — ets.meters.gauge_loop.loop_g over the committed occupancy O of
                    the last W bars (the incorruptible holonomy quantity). Real and
                    live; None until a 3-bar cycle exists.
          slide[g] — ets.meters.gauge_slide over the gauge-frame trajectory. On a v0
                    world the writer holds the frame at the identity every bar, so
                    slide is structurally zero and DISARMS (None); it auto-arms only
                    if the frame ever actually moves. Never fabricated.
        Imports the existing meter modules (no engine edit); consumes produced state
        only; feeds nothing back into any objective/gradient/settlement (I-5/I-14)."""
        from ets.meters.gauge_loop import loop_g
        from ets.meters.gauge_slide import gauge_slide
        self._O_window.append(np.asarray(r.O, float))
        fr = self.engine.writer.frame
        self._frame_hist.append((float(fr.transpose), float(fr.phase)))
        # loop[g]: committed-region holonomy over the window (needs >= 3 bar nodes).
        loop_val = None
        if len(self._O_window) >= 3:
            Ocat = np.concatenate(list(self._O_window), axis=1)
            loop_val = float(loop_g(Ocat, self.s_phase)[-1])
        # slide[g]: armed only if the gauge frame actually moved across the window.
        ts = {t for (t, _p) in self._frame_hist}
        ps = {p for (_t, p) in self._frame_hist}
        slide_val = None
        if len(ts) > 1 or len(ps) > 1:
            ft = [t for (t, _p) in self._frame_hist]
            fp = [p for (_t, p) in self._frame_hist]
            slide_val = float(gauge_slide(ft, fp, float(self.s_phase)).phase.per_bar[-1])
        return loop_val, slide_val

    # --- transport / streaming ---------------------------------------------
    def subscribe(self):
        """Register a NEW listener queue and ensure the produce loop is running.
        Each /api/stream connection gets its own queue (fan-out) so concurrent
        listeners on a shared engine never steal each other's PCM."""
        import queue
        q: "queue.Queue[bytes]" = queue.Queue(maxsize=64)
        with self._sub_lock:
            self._subscribers.add(q)
        self.start()
        return q

    def unsubscribe(self, q) -> None:
        with self._sub_lock:
            self._subscribers.discard(q)

    # Steady-state lead the producer keeps over realtime, so a network hiccup
    # never starves the client. With the emission re-anchor below, steering
    # latency is bounded by roughly this lead + the re-anchor threshold +
    # client-side buffering — a producer stall shifts the stream's timeline
    # instead of silently inflating the client's buffer forever.
    PACE_LEAD_SECONDS = 1.0
    # If the schedule falls this far behind wall clock (first-bar warmup such
    # as _ensure_bank, or a mid-stream render stall), re-anchor to NOW rather
    # than bursting at host speed to catch up — a catch-up burst would land in
    # the client's buffer and become permanent extra steering latency
    # (auditor note 1, 2026-07-18).
    PACE_REANCHOR_SECONDS = 2.0

    def _loop(self):
        # REALTIME PACING. Unpaced, a fast host renders far ahead of realtime
        # (measured 10.8x on the hosted deploy, 2026-07-18), so a realtime
        # listener buffers ever further behind "live" and steering becomes
        # audible minutes late. Pacing changes WHEN a bar is emitted, never
        # WHAT is rendered (H-8 untouched: u=0 bars stay byte-identical to
        # render_offline). A slow host is never slept — under-run behavior is
        # unchanged (the browser buffers).
        import time as _time
        t0 = None                                  # anchored on FIRST EMISSION
        sent = 0                                   # samples emitted so far
        while self._playing.is_set():
            try:
                pcm, _ = self.produce_one_bar()
            except Exception as exc:
                # LOOP HONESTY (OPEN_ENDS #21c): a failing engine must be LOUD.
                # The old bare `except: break` died silently and every listener's
                # stream then hung forever with no trace. Log the FULL traceback
                # and record a timestamped last_error for world_info()/telemetry,
                # then still break — no retry loop: a failing engine must not spin.
                logger.exception("produce_one_bar failed — the produce loop halts")
                self.last_error = "%s %s: %s" % (
                    _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                    type(exc).__name__, exc)
                tel = dict(self.telemetry)
                tel["last_error"] = self.last_error
                self.telemetry = tel
                break
            # WARMED (OPEN_ENDS #21d): the first successfully produced bar ends
            # the cold window — the honest flag /api/world reports.
            self._warmed = True
            now = _time.monotonic()
            if t0 is None or now - (t0 + sent / self.sr) > self.PACE_REANCHOR_SECONDS:
                t0 = now - sent / self.sr          # anchor/re-anchor at emission
            with self._sub_lock:
                subs = list(self._subscribers)
            for q in subs:
                try:
                    q.put_nowait(pcm)
                except Exception:
                    # subscriber fell behind: drop its oldest bar, keep it current.
                    try:
                        q.get_nowait()
                        q.put_nowait(pcm)
                    except Exception:
                        pass
            sent += len(pcm) // 2                  # mono int16 -> samples
            # Interruptible pacing wait: stop() must not have to out-wait a
            # bar-slot sleep (auditor note 2) — poll the playing flag.
            end = t0 + sent / self.sr - self.PACE_LEAD_SECONDS
            while self._playing.is_set():
                remaining = end - _time.monotonic()
                if remaining <= 0:
                    break
                _time.sleep(min(remaining, 0.05))

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._playing.set()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._playing.clear()
        # drain every subscriber queue
        with self._sub_lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                while True:
                    q.get_nowait()
            except Exception:
                pass

    def wav_header(self, data_len: int = 0xFFFFFFFF - 44) -> bytes:
        """A streaming WAV header (mono int16 @ sr) with an open-ended size."""
        return _wav_header(self.sr, 1, data_len)

    def stream_chunks(self):
        """Yield the WAV header then this listener's PCM chunks as bars are produced,
        until stop. Each caller gets its OWN fan-out queue (see :meth:`subscribe`)."""
        import queue
        yield self.wav_header()
        q = self.subscribe()
        try:
            while self._playing.is_set():
                try:
                    yield q.get(timeout=1.0)
                except queue.Empty:
                    continue
        finally:
            self.unsubscribe(q)


def _to_int16(audio: np.ndarray) -> bytes:
    a = np.nan_to_num(np.asarray(audio, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    a = np.clip(a, -1.0, 1.0)
    return (a * 32767.0).astype("<i2").tobytes()


def _wav_header(sr: int, channels: int, data_len: int) -> bytes:
    byte_rate = sr * channels * 2
    block_align = channels * 2
    return b"".join([
        b"RIFF", struct.pack("<I", 36 + data_len), b"WAVE",
        b"fmt ", struct.pack("<IHHIIHH", 16, 1, channels, sr, byte_rate, block_align, 16),
        b"data", struct.pack("<I", data_len),
    ])
