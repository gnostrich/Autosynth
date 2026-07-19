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

import os
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
    from ets.render import bank_cache as bc
    world = wf.world
    by_id = {t.track_id: t for t in world.tracks}
    wanted = set(by_id) if track_ids is None else set(track_ids)
    # Storage precision: float32 default. ETS_BANK_DTYPE=float16 halves memory
    # (~1e-3 rel precision) so the full bank fits a smaller machine — a DECLARED
    # capacity option (LAUNCH.md), never a per-input fork; render math stays f64.
    dtype = np.dtype(os.environ.get("ETS_BANK_DTYPE", "float32"))
    use_cache = os.environ.get("ETS_BANK_NOCACHE") != "1"
    cache_dir = bc.default_cache_dir()
    bank = SourceUnitBank(sr=int(world.sr))
    log.info("bank: storage %s, disk-cache %s", dtype.name,
             "on" if use_cache else "off")
    librosa = None
    for tid in sorted(wanted):
        track = by_id[tid]
        path = src["paths"][tid] if isinstance(src["paths"], dict) else \
            src["paths"][int(tid)]
        try:
            src_size = os.path.getsize(path)
        except OSError:
            src_size = -1
        key = bc.track_key(track, dtype, src_size)
        units = bc.load_track_units(cache_dir, tid, dtype, key) if use_cache else None
        if units is not None:
            log.info("bank: track %d from cache (%d units)", tid, len(units))
            for u in units:
                bank.add(u)
            continue
        if librosa is None:
            import librosa as _lb           # corpus worlds only; import once
            librosa = _lb
        log.info("bank: materializing track %d from %s", tid, path)
        y, _ = librosa.load(path, sr=track.sr, mono=True)
        tb = load_source_units(track, y, storage_dtype=dtype)
        us = [tb._units[k] for k in tb._units]
        for u in us:
            bank.add(u)
        if use_cache:
            try:
                bc.save_track_units(us, cache_dir, tid, dtype, key, int(track.sr))
            except Exception as e:           # cache is best-effort, never fatal
                log.warning("bank: cache write failed track %d: %s", tid, e)
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


def track_anchor_profiles(world) -> Dict[int, np.ndarray]:
    """READ-ONLY static telemetry: each source track's ANCHOR-MASS PROFILE.

    A unit's anchor-mass profile is the band-indexed column of the frozen
    world's anchor band-profile matrix B (world.fstate.B, shape (M, n_bands),
    M = n_anchors): B[:, band] is the anchor masses of that band ("col @ B" from
    ingestion). A track's profile is the mass-weighted sum of its units' columns
    — sum_i mass_i * B[:, band_i] = B @ (per-band unit-mass totals) — then
    peak-normalized to 0..1 (the dominant anchor = 1.0). Pure reduction over the
    already-frozen world (track.masses + track.provenance_index['band'] + B);
    it calls NOTHING downstream (no settlement, writer, render, F, or
    provenance generation) and is computed ONCE at startup. Static.

    Returns {track_id: np.ndarray (M,)}."""
    B = np.asarray(world.fstate.B, dtype=np.float64)          # (M, n_bands)
    M, n_bands = B.shape
    profiles: Dict[int, np.ndarray] = {}
    for track in world.tracks:
        bands = np.asarray(track.provenance_index["band"], dtype=np.int64)
        masses = np.asarray(track.masses, dtype=np.float64)
        valid = (bands >= 0) & (bands < n_bands)
        band_mass = np.zeros(n_bands, dtype=np.float64)
        if valid.any():
            np.add.at(band_mass, bands[valid], masses[valid])
        v = B @ band_mass                                      # (M,)
        peak = float(v.max()) if v.size else 0.0
        profiles[int(track.track_id)] = (v / peak) if peak > 0.0 else v
    return profiles


def role_unit_counts(world) -> np.ndarray:
    """READ-ONLY static per-ROLE metadata: how many source units live under each
    role. A unit's role is the dominant anchor of its band's column of the frozen
    world's anchor band-profile matrix B (argmax over B[:, band]); the count is
    the number of units (across all tracks) whose band maps to that role. Pure
    reduction over the frozen world (world.fstate.B + track.provenance_index),
    computed ONCE at startup; nothing downstream is touched. Returns (M,) int."""
    B = np.asarray(world.fstate.B, dtype=np.float64)          # (M, n_bands)
    M, n_bands = B.shape
    dom = B.argmax(0)                                         # (n_bands,) role/band
    band_units = np.zeros(n_bands, dtype=np.int64)
    for track in world.tracks:
        bands = np.asarray(track.provenance_index["band"], dtype=np.int64)
        valid = (bands >= 0) & (bands < n_bands)
        if valid.any():
            band_units += np.bincount(bands[valid],
                                      minlength=n_bands).astype(np.int64)
    counts = np.zeros(M, dtype=np.int64)
    np.add.at(counts, dom, band_units)
    return counts


def role_unit_pool(world, top_n: int = 24) -> Dict[int, list]:
    """READ-ONLY static per-ROLE unit POOL for the pad drill-in (spec §8 region
    lane; the classical-sampler drill).

    SOFT, NON-EXCLUSIVE by construction: this world cannot hard-partition units to
    roles (one anchor tends to win every band's argmax), so role i's pool is
    simply the units RANKED by their anchor-profile weight on anchor i — the value
    B[i, band] — with OVERLAP ALLOWED and a manageable `top_n` kept. Forcing a
    unit onto exactly one role would be a fabricated partition; it is deliberately
    not done.

    A unit's ANCHOR-PROFILE is B[:, band] — the length-M column of the frozen
    anchor band-profile matrix world.fstate.B (M = n_anchors), where the unit's
    band comes from its track's provenance_index. Each pool entry is
    (unit_id, track_id, band, profile=B[:, band]).

    Pure reduction over the frozen world (world.fstate.B + track.provenance_index);
    it calls NOTHING downstream (no settlement, writer, render, F, or provenance
    generation) and is computed ONCE at startup. Static. Returns
    {role: [(unit_id, track_id, band, np.ndarray (M,)), ...]}."""
    B = np.asarray(world.fstate.B, dtype=np.float64)          # (M, n_bands)
    M, n_bands = B.shape
    units: List[Tuple[int, int, int]] = []
    for track in world.tracks:
        tid = int(track.track_id)
        prov = track.provenance_index
        uids = np.asarray(prov["unit_id"], dtype=np.int64).tolist()
        bands = np.asarray(prov["band"], dtype=np.int64).tolist()
        for uid, band in zip(uids, bands):
            if 0 <= band < n_bands:
                units.append((int(uid), tid, int(band)))
    pools: Dict[int, list] = {}
    for i in range(M):
        ranked = sorted(units, key=lambda u: -float(B[i, u[2]]))[:int(top_n)]
        pools[i] = [(uid, tid, band, B[:, band].copy())
                    for (uid, tid, band) in ranked]
    return pools


def bar_role_activity(rows, bank, B) -> np.ndarray:
    """READ-ONLY per-ROLE activity for a produced bar.

    Projects the just-produced bar's PLACED units through the frozen anchor
    band-profile B (col @ B — the same map /ets/profiles uses): each placed row
    is (slot, track, unit, section, mass); the unit's band comes from the
    already-materialized bank (bank.get(...).band), and B[:, band] is that band's
    per-anchor mass. Sum mass per band, then B @ band_mass gives the (M,) per-
    anchor activity, peak-normalized to 0..1. Pure reduction over already-
    produced rows + the frozen world/bank; it calls NOTHING downstream (no
    settlement, writer, render, F, or provenance generation), so audio is
    byte-identical whether or not this runs. Returns np.ndarray (M,)."""
    B = np.asarray(B, dtype=np.float64)                       # (M, n_bands)
    M, n_bands = B.shape
    band_mass = np.zeros(n_bands, dtype=np.float64)
    for (_slot, tid, uid, _sec, mass) in rows:
        try:
            band = int(bank.get(int(tid), int(uid)).band)
        except KeyError:
            continue
        if 0 <= band < n_bands:
            band_mass[band] += float(mass)
    v = B @ band_mass                                         # (M,)
    peak = float(v.max()) if v.size else 0.0
    return (v / peak) if peak > 0.0 else v


def _playback_soft_limit(y: np.ndarray, thr: float = 0.40, ceil: float = 0.60,
                         target_rms: float = 0.10) -> np.ndarray:
    """LIVE-only playback SAFETY (I-11 playback stage, OUTSIDE the trained object —
    never applied to render_offline, so offline renders stay byte-identical). Guards
    against the sudden-loud EARDRUM risk in three stages: (1) kill non-finite garbage
    (a divergence blow-up is NaN/inf, which a plain '>thr' test silently passes);
    (2) a LOUDNESS CAP that attenuates — never boosts — each bar toward a safe target
    RMS, so a dense/decisive steer cannot swell the volume; (3) a soft-knee tanh + hard
    ceiling well below full scale. Conservative by design: it can only make things
    quieter/safer, never louder."""
    y = np.asarray(y, dtype=np.float32)
    # 1) non-finite garbage -> tamed.
    if not np.all(np.isfinite(y)):
        y = np.nan_to_num(y, nan=0.0, posinf=ceil, neginf=-ceil).astype(np.float32)
    # 2) LOUDNESS CAP — the real 'sudden loud' guard: turn DOWN any bar louder than the
    #    target RMS; never boost a quiet bar (no noise-floor blast). Constant safe level.
    if y.size:
        rms = float(np.sqrt(np.mean(y.astype(np.float64) ** 2)))
        if rms > target_rms:
            y = (y * (target_rms / rms)).astype(np.float32)
    # 3) soft-knee tanh above the (low) threshold.
    a = np.abs(y)
    over = a > thr
    if np.any(over):
        out = y.copy()
        s = np.sign(y[over])
        out[over] = (s * (thr + (ceil - thr) * np.tanh((a[over] - thr) / (ceil - thr)))).astype(np.float32)
        y = out
    # 3) hard safety ceiling — nothing leaves above `ceil`, ever.
    return np.clip(y, -ceil, ceil).astype(np.float32)


def nowplaying_activity(rows) -> List[Tuple[int, float]]:
    """READ-ONLY reduction over a produced bar's provenance rows.

    `rows` is the writer's already-produced schedule for the frontier bar
    (r.rows = tuples (out_slot, src_track, src_unit, section, mass)); the SAME
    object that bar_schedule() re-indexes into audio. This function only READS
    it: it sums per-source-track mass (the energy the writer placed at the
    frontier) and normalizes by the bar's peak track mass to a 0..1 activity.
    It calls NOTHING downstream — no settlement, no writer, no render, no F, no
    provenance generation — so audio is byte-identical whether or not this runs.

    Returns (track_id, activity) pairs sorted by track_id."""
    energy: Dict[int, float] = {}
    for (_slot, tid, _unit, _sec, mass) in rows:
        energy[int(tid)] = energy.get(int(tid), 0.0) + float(mass)
    if not energy:
        return []
    peak = max(energy.values())
    if peak <= 0.0:
        return [(tid, 0.0) for tid in sorted(energy)]
    return [(tid, energy[tid] / peak) for tid in sorted(energy)]


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
    def _tilt_for(self, u: Optional[LaneVector], a=None) -> TiltTerms:
        # `a` (default None) is the optional second-moment anisotropy
        # (PREREG-sampler-covariance-xy): NOT a lane, no σ scale, no effect on the
        # settled mode — it rides the ONE TiltTerms the writer consumes so the
        # covariance-shape pad adds no new control channel. None ⇒ byte-identical.
        if u is None:
            u = default_lane_vector(self.world.M)
        u.resize_region(self.world.M)
        tilt = layer0(u, self.sigma, a=a)
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
            audio = _playback_soft_limit(audio)   # LIVE-only playback safety (I-11)
            dt = time.perf_counter() - t0
            prod_times.append(dt)
            produced.append((r.bar, audio.astype(np.float32)))
            meters.clock(r.bar, r.bar * bar_seconds)
            meters.eoc(0)
            meters.novelty_sat(float(r.phi["novelty"]))
            # READ-ONLY now-playing telemetry: reduce the just-produced bar's
            # provenance rows (r.rows, already used to build `audio` above) to
            # per-source-track 0..1 activity and emit to the meters destination.
            # Reads produced state only; adds no call into settlement/writer/
            # render/F/provenance-generation (audio byte-identical on/off).
            meters.nowplaying(nowplaying_activity(r.rows))
            # READ-ONLY per-ROLE activity: project the same produced rows through
            # the frozen anchor band-profile B (col @ B) to per-anchor 0..1 and
            # emit. Adds no downstream call (audio byte-identical on/off).
            meters.roleactivity(bar_role_activity(r.rows, bank, world.fstate.B))
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

        # READ-ONLY static telemetry, computed ONCE from the frozen world: each
        # source track's anchor-mass profile (K=world.M vector, 0..1). Emitted
        # right after /ets/welcome so the panel can steer on a pad tap. Reads
        # nothing downstream; audio path untouched.
        track_profiles = track_anchor_profiles(world)
        role_counts = role_unit_counts(world)      # static per-role unit count
        role_pools = role_unit_pool(world)         # static per-role drill-in pool

        def answer_hello():
            got = inbox.hello()
            if got is not None and inbox.hello_event.is_set():
                inbox.hello_event.clear()
                host, port = got
                meters.retarget(host, port)
                meters.welcome(world.M, self.wf.world_hash, L, bar_seconds,
                               int(world.sr), disarmed=dis)
                meters.profiles(sorted(track_profiles.items()))
                meters.rolemeta(enumerate(role_counts.tolist()))
                # per-ROLE drill-in unit pool (one small datagram per role).
                for role in sorted(role_pools):
                    meters.unitpool(role, world.M, role_pools[role])

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
