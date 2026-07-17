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
        # Canonical unit->role map (spec §8 region lane): a unit's role is the
        # DOMINANT anchor of its band's column of the frozen anchor band-profile
        # matrix B (argmax over B[:, band]) — the SAME map role_unit_counts() uses.
        # Precomputed ONCE over the frozen world; read-only. On a degenerate world
        # whose B is uniform this genuinely collapses every band onto anchor 0 (a
        # real property of that world, surfaced honestly, not a fabricated split).
        _B0 = np.asarray(self.world.fstate.B, dtype=np.float64)   # (M, n_bands)
        self._role_of_band = (_B0.argmax(0).astype(np.int64)
                              if _B0.size else np.zeros(0, np.int64))
        # latest read-only telemetry — for /api/telemetry. `rms`/`peak` are the level
        # of the ALREADY-PRODUCED, eardrum-capped bar audio (a pure reduction of the
        # produced buffer; nothing downstream), so the UI output meters reflect real
        # playback level, not decoration.
        self.telemetry = {"roles": [0.0] * self.M, "t": 0.0, "bar": 0,
                          "rms": 0.0, "peak": 0.0}
        # LAST produced bar's REAL render provenance, grouped by role. Each entry is
        # a placed unit's real source (track_id, unit_id) + settled mass, taken from
        # render()'s ProvenanceStream (I-12: every unit that reached the tape). Read-
        # only; surfaced to the drill-in via /api/units. Empty until the first bar.
        self._last_bar = {"bar": -1, "roles": {i: [] for i in range(self.M)}}
        # produced PCM waiting to be streamed (bytes of int16 mono @ sr)
        import queue
        self._pcm_q: "queue.Queue[bytes]" = queue.Queue(maxsize=64)

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
        audio, prov = render_schedule(sched, self._bank)
        audio = _playback_soft_limit(audio)                  # LIVE-only eardrum cap
        roles = bar_role_activity(r.rows, self._bank, self.world.fstate.B)
        roles = [float(x) for x in np.asarray(roles).reshape(-1)[:self.M]]
        # REAL per-bar provenance for the drill-in: group render()'s ProvenanceStream
        # segments (each an on-tape placed unit) by their canonical role. Pure READ of
        # already-produced state (prov + the frozen bank/B); calls nothing downstream,
        # so the audio is byte-identical whether or not this runs.
        by_role = self._group_units_by_role(prov)
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))) if audio.size else 0.0
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        self._bar_index = int(r.bar)
        with self._lock:
            self._last_bar = {"bar": int(r.bar), "roles": by_role}
        self.telemetry = {"roles": roles, "bar": int(r.bar),
                          "t": float(r.bar * self.engine.writer.bar_seconds),
                          "rms": rms, "peak": peak}
        pcm = _to_int16(audio)
        return pcm, roles

    def _group_units_by_role(self, prov) -> dict:
        """Group a rendered bar's provenance segments by canonical role. Each placed
        unit's role is the dominant anchor of its band (self._role_of_band, argmax over
        the frozen B). Returns {role: [{track_id, unit_id, mass}, ...]}. READ-ONLY over
        already-produced provenance + the frozen bank; nothing downstream is touched."""
        by_role: dict = {i: [] for i in range(self.M)}
        n_bands = int(self._role_of_band.shape[0])
        for seg in prov.segments:
            tid = int(seg["src_track"]); uid = int(seg["src_unit"])
            try:
                band = int(self._bank.get(tid, uid).band)
            except KeyError:
                continue
            if not (0 <= band < n_bands):
                continue
            role = int(self._role_of_band[band])
            if 0 <= role < self.M:
                by_role[role].append({"track_id": tid, "unit_id": uid,
                                      "mass": float(seg["mass"])})
        return by_role

    def last_bar_units(self) -> dict:
        """READ-ONLY snapshot of the LAST produced bar's real placed units, grouped by
        role, plus the world's source-track set (for stable per-track colouring). Empty
        (`bar == -1`, all roles []) until the first bar is produced. Pure read of the
        state produce_one_bar() already captured; issues no engine-control."""
        with self._lock:
            lb = self._last_bar
            roles = {int(k): [dict(v) for v in vs] for k, vs in lb["roles"].items()}
            bar = int(lb["bar"])
        return {"bar": bar, "M": self.M, "roles": roles,
                "tracks": [int(t.track_id) for t in self.world.tracks]}

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

    def is_playing(self) -> bool:
        """True while the produce loop is armed. Read-only; the session registry
        uses it to avoid evicting a session whose audio is actively streaming."""
        return self._playing.is_set()

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
