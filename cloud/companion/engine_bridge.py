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

    def __init__(self, world_path: str, seed: int = 0, sigma_path: Optional[str] = None):
        if _ARCH_V6 not in sys.path:
            sys.path.insert(0, _ARCH_V6)
        from ets.engine.engine import Engine, resolve_sigma
        from ets.engine.worldfile import load_world

        self.world_path = world_path
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
        # produced PCM waiting to be streamed (bytes of int16 mono @ sr)
        import queue
        self._pcm_q: "queue.Queue[bytes]" = queue.Queue(maxsize=64)

    # --- world info ---------------------------------------------------------
    def world_info(self) -> dict:
        return {"ready": True, "M": self.M, "sr": self.sr,
                "world": Path(self.world_path).name,
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
        try:
            from ets.panel.envelope import SAFE_REGION_MAGNITUDE as _CAP
        except Exception:
            _CAP = 1.0
        peak = float(np.max(np.abs(vec))) if vec.size else 0.0
        if peak > _CAP:
            vec = vec * (_CAP / peak)
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
    def _loop(self):
        while self._playing.is_set():
            try:
                pcm, _ = self.produce_one_bar()
            except Exception:
                break
            try:
                self._pcm_q.put(pcm, timeout=2.0)
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
        # drain
        try:
            while True:
                self._pcm_q.get_nowait()
        except Exception:
            pass

    def wav_header(self, data_len: int = 0xFFFFFFFF - 44) -> bytes:
        """A streaming WAV header (mono int16 @ sr) with an open-ended size."""
        return _wav_header(self.sr, 1, data_len)

    def stream_chunks(self):
        """Yield the WAV header then PCM chunks as bars are produced, until stop."""
        yield self.wav_header()
        import queue
        while self._playing.is_set():
            try:
                yield self._pcm_q.get(timeout=1.0)
            except queue.Empty:
                continue


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
