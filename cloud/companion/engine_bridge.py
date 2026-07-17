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

Realtime note: bar production runs at the host's speed. On real hardware this is
~realtime (the native instrument streams live); on a slow box it under-runs — the
browser simply buffers. Nothing here changes the arrangement (H-8): u=0 bars are
byte-identical to ``render_offline``.
"""
from __future__ import annotations

import struct
import sys
import threading
from pathlib import Path
from typing import Optional

import numpy as np

_ARCH_V6 = str(Path(__file__).resolve().parents[2] / "architecture-v6")


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
        # latest read-only telemetry (roles 0..1, elapsed seconds) — for /api/telemetry
        self.telemetry = {"roles": [0.0] * self.M, "t": 0.0, "bar": 0}
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
                "bar_seconds": float(self.engine.writer.bar_seconds)}

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
                                        bar_role_activity)
        from ets.render import render as render_schedule
        self._ensure_bank()
        u = self._current_lane()
        tilt = self.engine._tilt_for(u)                      # ONE lane->tilt point
        r = self.engine.writer.write_bar(tilt=tilt)
        sched = bar_schedule(self.world, r.rows, self.s_phase)
        audio, _prov = render_schedule(sched, self._bank)
        audio = _playback_soft_limit(audio)                  # LIVE-only eardrum cap
        roles = bar_role_activity(r.rows, self._bank, self.world.fstate.B)
        roles = [float(x) for x in np.asarray(roles).reshape(-1)[:self.M]]
        self._bar_index = int(r.bar)
        self.telemetry = {"roles": roles, "bar": int(r.bar),
                          "t": float(r.bar * self.engine.writer.bar_seconds)}
        pcm = _to_int16(audio)
        return pcm, roles

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

    def _loop(self):
        while self._playing.is_set():
            try:
                pcm, _ = self.produce_one_bar()
            except Exception:
                break
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
