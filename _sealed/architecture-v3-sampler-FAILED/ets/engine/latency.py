"""Declared latency (connector: Real-time typing) — L from BUFFER MATH.

The writer runs L bars ahead of the playhead; knob changes bind at the write
frontier, so control latency = L bars (plugin-latency semantics, surfaced on
the panel via /ets/welcome, never hidden).

DERIVATION (producer–consumer buffer law; no taste anywhere):
  Let T_bar   = bar duration (seconds)      [world: S_phase·tatum_len/sr]
      T_prod  = wall time to PRODUCE one bar (settle + temperature sample +
                fiber threading + render + OSC emit), measured on the running
                host over N_WARMUP bars (max, so the first-bar transient and
                jitter are inside the bound).
  The playhead consumes one bar per T_bar. The queue of committed bars must
  never empty; producing bar n+L must complete before the playhead exhausts
  bars n..n+L−1. A buffer of L bars survives a worst-case production burst iff
      L · T_bar > max(T_prod)  ⇒  L = ceil(max(T_prod) / T_bar) + 1
  (the +1 is the classic double-buffer term: one bar is being consumed while
  the next is produced). If mean(T_prod) ≥ T_bar no finite L works — the COLD
  solve cannot meet the deadline: that is a WALL, the engine halts and reports
  (connector: shipping unverified guesses / reducing frontier resolution under
  load are named patch signatures; neither exists here).

  The audio device adds its own fixed blocksize/sr output latency AFTER the
  tape; it does not enter L (it delays playback uniformly, it cannot starve
  the writer).

PROFILES are pre-registered (PREREG.md "Latency profile table"): each names
the device parameters and the derivation procedure; the engine re-measures
T_prod on ITS host at startup with the registered procedure and logs the
derived L (buffer math from local measurement — the registered reference
numbers for this repo's build box live in REGISTRY.jsonl).
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, Sequence

# Number of measured warmup bars, registered with the profile table: max over
# 8 bars covers the first-bar transient (index/run seeding, allocator warmup)
# plus steady-state jitter; registered in PREREG, not tuned at runtime.
N_WARMUP_BARS = 8


@dataclass(frozen=True)
class LatencyProfile:
    """Declared per-hardware-profile constants (CONTROL typing, connector)."""
    name: str
    sr: int                 # engine sample rate
    blocksize: int          # audio callback frames per block (device buffer)
    n_warmup: int = N_WARMUP_BARS

    @property
    def device_latency_s(self) -> float:
        return self.blocksize / float(self.sr)


PROFILES: Dict[str, LatencyProfile] = {
    # desktop: 44.1k engine rate (spec §2 internal rate); 2048-frame device
    # buffer = 46.4 ms callback deadline — the stock desktop-audio block size
    # (a device parameter, not a writer decision; the writer's own deadline
    # math is in bars, above).
    "desktop": LatencyProfile(name="desktop", sr=44100, blocksize=2048),
    # headless-ci: the audio-device-less build/CI host (this repo's build box;
    # PART B's desktop uses "desktop"). Same engine rate; blocksize is the
    # would-be device parameter (unused without a device); a shorter warmup
    # because CI demos run few bars and the derivation is logged, not load-
    # bearing for a sound card that does not exist.
    "headless-ci": LatencyProfile(name="headless-ci", sr=44100, blocksize=2048,
                                  n_warmup=4),
}


def derive_L(t_prod_s: Sequence[float], bar_seconds: float) -> dict:
    """The buffer law. Returns the derivation record the engine logs and the
    render receipt embeds; raises on the no-finite-L WALL."""
    t = [float(x) for x in t_prod_s]
    if not t:
        raise ValueError("no production-time measurements")
    t_max = max(t)
    t_mean = sum(t) / len(t)
    if t_mean >= float(bar_seconds):
        raise RuntimeError(
            f"WALL: mean per-bar production time {t_mean:.3f}s >= bar duration "
            f"{bar_seconds:.3f}s — the cold solve cannot meet the real-time "
            "deadline for ANY finite L. Halt and report (connector Real-time "
            "typing); no silent quality fork exists.")
    L = int(math.ceil(t_max / float(bar_seconds))) + 1
    return {"L_bars": L, "bar_seconds": float(bar_seconds),
            "t_prod_max_s": t_max, "t_prod_mean_s": t_mean,
            "n_measured": len(t),
            "formula": "L = ceil(max(T_prod)/T_bar) + 1"}
