"""The ENGINE (spec §12): frozen world + streaming writer + render, driven over
OSC, with live audio via a sounddevice callback and an offline render mode.

CONTROL PATH (I-1 / C-3, the whole of it):
    OSC /ets/lanes → Inbox.latest_lanes() → ets.writer.tilt.layer0(u, σ_φ)
        → TiltTerms → StreamWriter.write_bar(tilt=...)
Nothing else flows from the wire into the writer. Tolerances (/ets/tolerances)
are stored + logged and consumed by NOTHING (Stage-1 pending; CI-enforced).
Meters flow the other way only.

LANES BIND AT THE WRITE FRONTIER: the writer runs L bars ahead of the playhead
(L derived from buffer math at startup — ets.engine.latency; logged and sent to
the panel in /ets/welcome), so a knob change audibly lands L bars later.
Plugin-latency semantics, surfaced, never hidden.

TEMPERATURE SAMPLING & DETERMINISM (H-8): all stochasticity lives in the
writer's seeded Generator. Same (world hash, f.LAMBDA, knob trajectory, seed)
⇒ bit-identical offline render; the render receipt records the full tuple.

HEADLESS GRACE: live mode without an audio device (or without sounddevice
installed) runs the identical writer loop against a wall-clock playhead and
says so loudly — the OSC surface, meters, and logs behave exactly as with
audio. No silent fork: the audio path either exists or is reported absent.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from ets.engine.latency import PROFILES, LatencyProfile, derive_L
from ets.engine.osc_io import ControlServer, Inbox, MeterEmitter
from ets.engine.worldfile import WorldFile
from ets.panel.lanes import LaneVector, default_lane_vector
from ets.render import render as render_schedule
from ets.render.schedule import IDENTITY, PLACEMENT_DTYPE, Schedule, Section
from ets.render.sources import SourceUnitBank, load_source_units
from ets.writer import StreamWriter
from ets.writer.tilt import SigmaPhi, TiltTerms, layer0

log = logging.getLogger("ets.engine")


# --------------------------------------------------------------------------
# σ_φ resolution (the registered calibration instrument's numbers)
# --------------------------------------------------------------------------

def resolve_sigma(wf: WorldFile, cli_path: Optional[str] = None
                  ) -> Optional[SigmaPhi]:
    """Documented precedence: --sigma-phi PATH > world-file-embedded > the
    REGISTERED corpus artifact (ets.calibration.load_sigma_phi — the σ_φ
    calibration instrument, a concurrent feature). Returns None if none
    exists — the engine then runs UNTILTED ONLY and any nonzero lean raises
    WorldNotCalibrated (loud; λ is never invented)."""
    if cli_path:
        with open(cli_path) as fh:
            m = json.load(fh)
        log.info("sigma_phi: loaded from --sigma-phi %s", cli_path)
        return SigmaPhi.from_mapping(m)
    if wf.sigma_phi is not None:
        log.info("sigma_phi: embedded in world file")
        return SigmaPhi.from_mapping(wf.sigma_phi)
    try:
        from ets.calibration import load_sigma_phi, world_content_hash
    except ImportError:
        log.warning("sigma_phi: NO calibration found (ets.calibration absent) "
                    "— UNCALIBRATED world: direction lanes will refuse nonzero "
                    "leans (WorldNotCalibrated); T_s and u=0 remain available")
        return None
    cal = load_sigma_phi()
    if cal is None:
        log.warning("sigma_phi: ets.calibration present but returned no "
                    "artifact — running UNCALIBRATED (see above)")
        return None
    # STALENESS GUARD: the instrument is bound to ONE frozen world; a hash
    # mismatch means anchors changed since calibration (spawn/prune) and the
    # instrument must be re-run — refuse, never proceed on a stale scale.
    expected = world_content_hash(wf.world.fstate)
    if cal.world_hash != expected:
        raise RuntimeError(
            f"STALE CALIBRATION: registered σ_φ artifact was measured on world "
            f"{cal.world_hash[:12]} but this world file's content hash is "
            f"{expected[:12]}. Re-run the calibration instrument at "
            "world-freeze (σ_φ is re-run on any anchor spawn/prune); the "
            "engine will not lean on a stale scale.")
    # map the instrument's lane-keyed record onto the tilt map's SigmaPhi.
    # identifiable=False lanes (measured zero untilted fluctuation under the
    # registered MAP-settling writer: density, gauge) are DISARMED — λ is
    # undefined there and no tilt is applied (see ets.writer.tilt).
    sig = SigmaPhi(
        region=np.asarray(cal.sigma["region"], float),
        density=float(cal.sigma.get("density", 0.0) or 0.0),
        cont=float(cal.sigma["continuity"]),
        gauge=float(cal.sigma.get("gauge", 0.0) or 0.0),
        novelty=float(cal.sigma["novelty"]),
        identifiable={
            # region identifiability is PER-ANCHOR in the registered artifact
            # (an (M,) bool array — each anchor's sigma measured separately).
            # The lane arms iff EVERY component has a valid scale; a partially
            # identifiable region lane would need component-wise disarm in the
            # tilt map (declared: not implemented — all-or-nothing is the
            # conservative reading, and the registered corpus artifact is
            # all-True so the branch is currently inert).
            "region": bool(np.all(cal.identifiable.get("region", True))),
            "density": bool(cal.identifiable.get("density", False)),
            "cont": bool(cal.identifiable.get("continuity", True)),
            "gauge": bool(cal.identifiable.get("gauge", False)),
            "novelty": bool(cal.identifiable.get("novelty", True)),
        },
        meta={"source": "ets.calibration registered artifact",
              "world_hash": cal.world_hash,
              "lane_phi": dict(getattr(cal, "lane_phi", {}) or {})})
    dis = sorted(k for k, v in sig.identifiable.items() if not v)
    log.info("sigma_phi: registered artifact loaded (world %s); disarmed "
             "lanes (unidentifiable scale): %s", cal.world_hash[:12],
             ", ".join(dis) if dis else "none")
    return sig


def disarmed_lanes(sigma: Optional[SigmaPhi]) -> list:
    """Lane ids whose tilt scale the registered instrument could not identify
    (surfaced on /ets/welcome and in the log; the panel shows them)."""
    if sigma is None:
        return ["region", "density", "cont", "gauge", "novelty"]
    return sorted(k for k, v in dict(sigma.identifiable).items() if not v)


# --------------------------------------------------------------------------
# source materialization (I-12: every sample from a real unit)
# --------------------------------------------------------------------------

def build_bank(wf: WorldFile, track_ids: Optional[set] = None) -> SourceUnitBank:
    """Materialize source-unit audio. 'embedded' worlds carry their bank;
    'corpus' worlds re-derive units deterministically from the source files
    (the same G0-style band reconstruction as ingestion — no choices).

    Corpus banks are stored float32 (declared capacity decision, logged here
    and documented in LAUNCH.md): the full 20-track band decomposition at
    float64 (~17 GB) exceeds ordinary desktop memory; float32 (~8.5 GB) holds
    unit audio at ~1e-7 relative precision while ALL render arithmetic stays
    float64. Deterministic either way; never a per-input fork."""
    src = wf.sources
    if src["kind"] == "embedded":
        return src["bank"]
    import librosa                                  # corpus worlds only
    world = wf.world
    by_id = {t.track_id: t for t in world.tracks}
    wanted = set(by_id) if track_ids is None else set(track_ids)
    bank = SourceUnitBank(sr=int(world.sr))
    log.info("bank: corpus storage precision float32 (declared; see LAUNCH.md)")
    for tid in sorted(wanted):
        track = by_id[tid]
        path = src["paths"][tid] if isinstance(src["paths"], dict) else \
            src["paths"][int(tid)]
        log.info("bank: materializing track %d from %s", tid, path)
        y, _ = librosa.load(path, sr=track.sr, mono=True)
        tb = load_source_units(track, y, storage_dtype=np.float32)
        for key in list(tb._units.keys()):
            bank.add(tb._units[key])
    return bank


def bar_schedule(world, rows: List[Tuple[int, int, int, int, float]],
                 s_phase: int) -> Schedule:
    """One bar's rows (global slot indices) as a local one-bar Schedule for the
    render — pure re-indexing, identity gauge (the v0 frame)."""
    tatum = int(world.out_tatum_len)
    bounds = np.arange(s_phase + 1, dtype=np.int64) * tatum
    p = np.zeros(len(rows), dtype=PLACEMENT_DTYPE)
    for i, (s, tid, uid, sec, mass) in enumerate(rows):
        p[i]["out_slot"] = int(s) % s_phase
        p[i]["src_track"] = tid
        p[i]["src_unit"] = uid
        p[i]["section"] = 0
        p[i]["mass"] = mass
    return Schedule(sr=int(world.sr), slot_boundaries=bounds, placements=p,
                    sections=(Section(0, 0, s_phase, IDENTITY),))


# --------------------------------------------------------------------------
# knob trajectory (offline mode): the scripted lane schedule
# --------------------------------------------------------------------------

def load_knob_script(path: Optional[str]) -> List[dict]:
    """Knob script JSON: {"events": [{"bar": b, "lane": id, "value": v}, ...]}
    lane ∈ the six of spec §8; region takes a list (a lean per anchor)."""
    if path is None:
        return []
    with open(path) as fh:
        data = json.load(fh)
    events = sorted(data.get("events", []), key=lambda e: int(e["bar"]))
    return events


def apply_knob_events(u: LaneVector, events: List[dict], bar: int) -> LaneVector:
    """Apply the events scheduled AT this frontier bar to the lane vector."""
    for e in events:
        if int(e["bar"]) != bar:
            continue
        lane, v = e["lane"], e["value"]
        if lane == "region":
            vec = np.asarray(v, dtype=np.float32).reshape(-1)
            u.resize_region(vec.shape[0])
            u.u_region[:] = vec
        elif lane == "density":
            u.u_density = float(v)
        elif lane == "continuity":
            u.u_continuity = float(v)
        elif lane == "gauge":
            u.u_gauge = float(v)
        elif lane == "novelty":
            u.u_novelty = float(v)
        elif lane == "temperature":
            u.T_s = float(v)
        else:
            raise ValueError(f"knob script names a non-lane control {lane!r} "
                             "(the six lanes are exhaustive, spec §8)")
    return u


# --------------------------------------------------------------------------
# the engine
# --------------------------------------------------------------------------

@dataclass
class OfflineResult:
    audio: np.ndarray
    receipt: dict


class Engine:
    def __init__(self, wf: WorldFile, profile: str = "desktop", seed: int = 0,
                 sigma: Optional[SigmaPhi] = None):
        if profile not in PROFILES:
            raise ValueError(f"unknown latency profile {profile!r}; registered "
                             f"profiles: {sorted(PROFILES)}")
        self.wf = wf
        self.world = wf.world
        self.profile: LatencyProfile = PROFILES[profile]
        self.seed = int(seed)
        self.sigma = sigma
        self.writer = StreamWriter(self.world, seed=self.seed)
        from ets.functional import f as ff
        self._lambda = dict(ff.LAMBDA)          # logged into receipts (H-8 key)

    # -- the ONE lane→tilt conversion point (C-3) --------------------------
    def _tilt_for(self, u: Optional[LaneVector]) -> TiltTerms:
        if u is None:
            u = default_lane_vector(self.world.M)
        u.resize_region(self.world.M)
        tilt = layer0(u, self.sigma)
        if tilt.degenerate:
            log.warning("degenerate lanes (σ_φ=0 ⇒ identity tilt, exact): %s",
                        ", ".join(tilt.degenerate))
        if tilt.disarmed:
            log.warning("DISARMED lane leaned: %s — uncalibrated scale "
                        "(instrument measured zero untilted fluctuation under "
                        "the MAP writer); u transmitted, NO tilt applied. "
                        "Unblocking: registered σ_φ re-run under the T_s>0 "
                        "sampling writer.", ", ".join(tilt.disarmed))
        return tilt

    # ------------------------------------------------------------------
    # OFFLINE RENDER MODE
    # ------------------------------------------------------------------
    def render_offline(self, seconds: float, knob_script: Optional[str] = None,
                       out_path: Optional[str] = None,
                       bank: "Optional[SourceUnitBank]" = None) -> OfflineResult:
        world = self.world
        s_phase = self.writer.s_phase
        n_bars = max(1, int(round(seconds / self.writer.bar_seconds)))
        events = load_knob_script(knob_script)
        log.info("offline render: %d bars (%.1fs), %d knob events, seed=%d, "
                 "world %s", n_bars, n_bars * self.writer.bar_seconds,
                 len(events), self.seed, self.wf.world_hash[:12])

        u = default_lane_vector(world.M)
        bars = []
        for b in range(n_bars):
            u = apply_knob_events(u, events, b)      # binds AT the frontier
            tilt = self._tilt_for(u)
            bars.append(self.writer.write_bar(tilt=tilt))

        used = sorted({int(t) for r in bars for (_s, t, _u, _sec, _m) in r.rows})
        # A caller may inject a pre-built (warm) bank to avoid re-materializing
        # source units on every render (batch/streaming convenience). Byte-
        # identical: the bank holds the same deterministic units either way, so
        # determinism (H-8) is unaffected. Default None = build it here, as before.
        if bank is None:
            bank = build_bank(self.wf, track_ids=set(used))
        chunks = []
        prov_all = []
        for r in bars:
            sched = bar_schedule(world, r.rows, s_phase)
            audio, prov = render_schedule(sched, bank)
            chunks.append(audio)
            prov_all.append(prov.segments)
        audio = np.concatenate(chunks) if chunks else np.zeros(0)

        events_blob = json.dumps(events, sort_keys=True).encode()
        prov_cat = np.concatenate(prov_all) if prov_all else np.zeros(0)
        receipt = {
            "mode": "offline",
            "world_sha256": self.wf.world_hash,
            "lambda": self._lambda,
            "knob_trajectory_sha256": hashlib.sha256(events_blob).hexdigest(),
            "knob_events": events,
            "seed": self.seed,
            "n_bars": n_bars,
            "bar_seconds": self.writer.bar_seconds,
            "sr": int(world.sr),
            "tracks_used": used,
            "n_placements": int(sum(len(r.rows) for r in bars)),
            "audio_sha256": hashlib.sha256(audio.tobytes()).hexdigest(),
            "provenance_sha256": hashlib.sha256(prov_cat.tobytes()).hexdigest(),
            "phi_last_bar": {k: (v.tolist() if hasattr(v, "tolist") else v)
                             for k, v in bars[-1].phi.items()},
        }
        if out_path:
            import soundfile as sf
            peak = float(np.max(np.abs(audio))) + 1e-12
            sf.write(out_path, (0.97 * audio / peak).astype(np.float32),
                     int(world.sr), format="FLAC")
            with open(out_path.rsplit(".", 1)[0] + ".receipt.json", "w") as fh:
                json.dump(receipt, fh, indent=2)
            log.info("offline render written: %s (audio sha256 %s)", out_path,
                     receipt["audio_sha256"][:16])
        return OfflineResult(audio=audio, receipt=receipt)

    # ------------------------------------------------------------------
    # LIVE MODE (two-process; headless-graceful)
    # ------------------------------------------------------------------
    def run_live(self, control_port: int = 9000, meters_host: str = "127.0.0.1",
                 meters_port: int = 9001, max_bars: Optional[int] = None,
                 stop_event: Optional[threading.Event] = None) -> dict:
        world = self.world
        s_phase = self.writer.s_phase
        bar_seconds = self.writer.bar_seconds
        stop = stop_event or threading.Event()

        inbox = Inbox()
        server = ControlServer(inbox, port=control_port)
        server.start()
        meters = MeterEmitter(meters_host, meters_port)
        log.info("engine up: control udp:%d, meters -> %s:%d, profile=%s, "
                 "world %s (M=%d anchors), calibrated=%s", server.bound_port,
                 meters_host, meters_port, self.profile.name,
                 self.wf.world_hash[:12], world.M, self.sigma is not None)

        # live needs every track materialized before the clock starts (a run
        # may seed any unit; loading inside the deadline would starve the
        # writer). Memory cost is reported, not hidden.
        bank = build_bank(self.wf)
        log.info("bank: %d units in memory", len(bank))

        # --- audio sink: sounddevice if present+device, else wall clock ----
        sink = _open_audio_sink(int(world.sr), self.profile.blocksize)

        # --- warmup: measure production, derive L (buffer math; latency.py) --
        produced: deque = deque()      # (bar_index, float32 audio)
        prod_times: List[float] = []

        def produce_one() -> None:
            u = inbox.latest_lanes()
            tilt = self._tilt_for(u)
            t0 = time.perf_counter()
            r = self.writer.write_bar(tilt=tilt)
            sched = bar_schedule(world, r.rows, s_phase)
            audio, _prov = render_schedule(sched, bank)
            dt = time.perf_counter() - t0
            prod_times.append(dt)
            produced.append((r.bar, audio.astype(np.float32)))
            meters.clock(r.bar, r.bar * bar_seconds)
            meters.eoc(0)
            meters.novelty_sat(float(r.phi["novelty"]))
            log.info("bar %d committed: %d placements, settle %d iters, "
                     "%.3fs prod, phi_density=%.3f", r.bar, len(r.rows),
                     r.n_iter, dt, float(r.phi["density"]))

        for _ in range(self.profile.n_warmup):
            produce_one()
        deriv = derive_L(prod_times, bar_seconds)
        L = deriv["L_bars"]
        log.info("latency derivation (%s): %s", self.profile.name,
                 json.dumps(deriv))
        log.info("DECLARED CONTROL LATENCY: L=%d bars (%.2fs) + device %.1fms",
                 L, L * bar_seconds, 1000 * self.profile.device_latency_s)

        played_bars = 0
        start_t = None

        dis = ",".join(disarmed_lanes(self.sigma))

        def answer_hello():
            got = inbox.hello()
            if got is not None and inbox.hello_event.is_set():
                inbox.hello_event.clear()
                host, port = got
                meters.retarget(host, port)
                meters.welcome(world.M, self.wf.world_hash, L, bar_seconds,
                               int(world.sr), disarmed=dis)

        try:
            start_t = time.monotonic()
            if sink is not None:
                sink.start(produced)
            while not stop.is_set():
                answer_hello()
                if sink is not None:
                    if sink.underrun:
                        raise RuntimeError(
                            "WALL: audio underrun — the cold solve missed the "
                            "deadline within buffer L; halting (connector "
                            "Real-time typing; no silent quality fork).")
                    played_bars = sink.bars_consumed
                else:
                    played_bars = int((time.monotonic() - start_t) / bar_seconds)
                ahead = self.writer.bar - played_bars
                if ahead < L:
                    produce_one()
                else:
                    time.sleep(0.005)
                if max_bars is not None and self.writer.bar >= max_bars:
                    break
        finally:
            if sink is not None:
                sink.stop()
            server.stop()
        return {"bars_written": self.writer.bar, "L": L,
                "latency_derivation": deriv, "prod_times": prod_times}


def _open_audio_sink(sr: int, blocksize: int):
    """Lazily open the sounddevice output. Returns None (LOUDLY) when live
    audio is impossible here — the writer loop then runs against wall clock.
    This is the declared headless mode, not a fallback: the audio path either
    exists or its absence is reported at startup."""
    try:
        import sounddevice as sd
    except (ImportError, OSError) as e:
        log.warning("LIVE AUDIO UNAVAILABLE (%s: %s) — running HEADLESS live "
                    "loop (writer+OSC+meters real; no sound card output). "
                    "PART B exercises audio on the desktop.",
                    type(e).__name__, e)
        return None
    try:
        sd.check_output_settings(samplerate=sr)
    except Exception as e:
        log.warning("LIVE AUDIO UNAVAILABLE (no usable output device: %s) — "
                    "running HEADLESS live loop (writer+OSC+meters real).", e)
        return None
    return _SoundDeviceSink(sd, sr, blocksize)


class _SoundDeviceSink:
    """Pull-model audio sink: the callback drains the produced-bars queue.
    Underrun sets a flag the engine loop turns into a WALL halt (never a
    silent dropout loop)."""

    def __init__(self, sd, sr: int, blocksize: int):
        self._sd = sd
        self.sr = int(sr)
        self.blocksize = int(blocksize)
        self.underrun = False
        self.bars_consumed = 0
        self._queue: Optional[deque] = None
        self._current: Optional[np.ndarray] = None
        self._pos = 0
        self._stream = None
        self._started_once = False

    def _callback(self, outdata, frames, _time, _status):
        out = outdata[:, 0]
        out[:] = 0.0
        i = 0
        while i < frames:
            if self._current is None or self._pos >= len(self._current):
                if self._current is not None:
                    self.bars_consumed += 1
                if self._queue:
                    _bar, self._current = self._queue.popleft()
                    self._pos = 0
                else:
                    self._current = None
                    if self._started_once:
                        self.underrun = True
                    return
            n = min(frames - i, len(self._current) - self._pos)
            out[i:i + n] = self._current[self._pos:self._pos + n]
            self._pos += n
            i += n
        self._started_once = True

    def start(self, queue: deque) -> None:
        self._queue = queue
        self._stream = self._sd.OutputStream(
            samplerate=self.sr, blocksize=self.blocksize, channels=1,
            dtype="float32", callback=self._callback)
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
