"""OSC message schema — the panel↔engine wire contract (spec §12; connector C-3).

This is the ONE place the wire format lives. The engine's Layer-0 map (build
order step f) binds to exactly these addresses and types; keep it stable.

OUTBOUND (panel → engine), the boundary-measure typing — ONE channel, nothing
else (connector: "emit u + T_s over the ONE OSC channel and nothing else"):

  address:  /ets/lanes
  args:     K:int32,                      # anchor count (self-sizing region dim)
            r_0 … r_{K-1}:float32,        # u_region, a lean per discovered anchor
            u_density:float32,
            u_continuity:float32,
            u_gauge:float32,
            u_novelty:float32,
            T_s:float32
  arg count = 1 + K + 5.  The leading K makes the message self-describing, so
  the variable-length region vector and the four scalar leans + temperature
  ride ONE message unambiguously. This single message IS the clamped role-space
  measure the panel sets; there is no second outbound address.

OUTBOUND also carries exactly two non-lane messages, both control-plane:

  /ets/tolerances  leash:float32, comma:float32
      The two declared TOLERANCE knobs (directive v1): LEASH (slide tolerance)
      and COMMA (loop tolerance; default = +inf, displayed 'inf'). They are
      NOT lanes (the six lanes stay exhaustive, spec §8) and NOT tilt inputs:
      the engine receives, logs, and stores them as declared tolerances;
      NOTHING consumes them yet (Stage-1 authority wiring is a separate,
      pre-registered feature). A tolerance reaching the writer/render is a
      CI failure (tests/harness/test_h6_panel_exhaustive.py).
  /ets/hello       meters_port:int32
      The handshake: the panel announces where its meter receiver listens;
      the engine replies on /ets/welcome. Carries no control value.

INBOUND (engine → panel), read-only meter jacks (spec §9) + control-plane
replies. These feed the panel's DISPLAY only; nothing derived from them is
ever emitted (I-5):

  /ets/welcome            K:int32, world_hash:str, L:int32,
                          bar_seconds:float32, sr:int32
                          (handshake reply: anchor count sizes the REGION
                          strips; L is the DECLARED control latency in bars —
                          plugin-latency semantics, surfaced, never hidden)
  /ets/clock              bar:int32, seconds:float32   (master-clock display)
  /ets/meter/drift        key:float32, phase_feel:float32, timbre:float32
                          (accumulated holonomy per gauge component — §9.
                          DEPRECATED as a pair-conflating readout: it sums the
                          slide and loop parts of drift; retained for
                          compatibility, displayed as deprecated.)
  /ets/meter/slide        key:float32, phase_feel:float32, timbre:float32
  /ets/meter/loop         key:float32, phase_feel:float32, timbre:float32
                          (the slide/loop jack PAIRS that split the conflated
                          drift readout — values produced by the Stage-0
                          meters; until that feed exists the panel displays
                          '—'. NaN on the wire = no reading.)
  /ets/meter/eoc          gate:int32          (phrase end-of-chain gate; 0/1)
  /ets/meter/novelty_sat  saturation:float32  (novelty saturation CV; ~[0,1])

There is deliberately NO inbound control address: the engine never writes the
panel's lanes. The panel is the sole author of u/T_s/tolerances; the engine is
the sole author of meters/clock/welcome. One direction each. THIS LIST IS THE
CLOSED MESSAGE SPACE: the engine binds exactly these addresses and the panel
sends/receives exactly these (H-6/C-3 CI checks both directions).
"""
from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np

from ets.panel.lanes import LaneVector
from ets.panel.tolerances import Tolerances

# --- addresses (stable identifiers; the engine binds to these strings) --------
ADDR_LANES = "/ets/lanes"                 # OUTBOUND, the one boundary-measure channel
ADDR_TOLERANCES = "/ets/tolerances"       # OUTBOUND, declared tolerances (no consumer)
ADDR_HELLO = "/ets/hello"                 # OUTBOUND, handshake
ADDR_WELCOME = "/ets/welcome"             # INBOUND, handshake reply
ADDR_CLOCK = "/ets/clock"                 # INBOUND, master-clock display
ADDR_METER_DRIFT = "/ets/meter/drift"     # INBOUND (deprecated: conflates slide+loop)
ADDR_METER_SLIDE = "/ets/meter/slide"     # INBOUND (Stage-0 shadow feed)
ADDR_METER_LOOP = "/ets/meter/loop"       # INBOUND (Stage-0 shadow feed)
ADDR_METER_EOC = "/ets/meter/eoc"         # INBOUND
ADDR_METER_NOVELTY_SAT = "/ets/meter/novelty_sat"  # INBOUND

OUTBOUND_ADDRESSES: Tuple[str, ...] = (ADDR_LANES, ADDR_TOLERANCES, ADDR_HELLO)
INBOUND_ADDRESSES: Tuple[str, ...] = (
    ADDR_WELCOME, ADDR_CLOCK,
    ADDR_METER_DRIFT, ADDR_METER_SLIDE, ADDR_METER_LOOP,
    ADDR_METER_EOC, ADDR_METER_NOVELTY_SAT)

# Drift gauge components, in wire order (spec §9); the slide/loop pairs split
# the SAME components.
DRIFT_COMPONENTS: Tuple[str, ...] = ("key", "phase_feel", "timbre")


def encode_lanes(u: LaneVector) -> List:
    """Serialise the lane vector + T_s to the ONE outbound message's args.

    Returns a flat list [K:int, r_0..r_{K-1}:float, density, continuity, gauge,
    novelty, T_s:float]. python-osc infers OSC types from Python types, so ints
    stay int32 and floats stay float32-on-the-wire; we cast explicitly to make
    the typing unambiguous and independent of numpy scalar quirks.
    """
    region = np.asarray(u.u_region, dtype=np.float32).reshape(-1)
    K = int(region.shape[0])
    args: List = [K]
    args.extend(float(x) for x in region.tolist())
    args.append(float(u.u_density))
    args.append(float(u.u_continuity))
    args.append(float(u.u_gauge))
    args.append(float(u.u_novelty))
    args.append(float(u.T_s))
    assert len(args) == 1 + K + 5, "lane message arity contract violated"
    return args


def decode_lanes(args) -> LaneVector:
    """Inverse of `encode_lanes`. Reconstructs the LaneVector from wire args.

    This is exactly what the engine's Layer-0 map will run to recover u/T_s.
    """
    args = list(args)
    if not args:
        raise ValueError("empty /ets/lanes message")
    K = int(args[0])
    if K < 0:
        raise ValueError(f"negative anchor count K={K}")
    expected = 1 + K + 5
    if len(args) != expected:
        raise ValueError(
            f"/ets/lanes arity {len(args)} != 1+K+5 = {expected} (K={K})")
    region = np.asarray(args[1:1 + K], dtype=np.float32)
    density, continuity, gauge, novelty, T_s = (float(x) for x in args[1 + K:])
    return LaneVector(region, density, continuity, gauge, novelty, T_s)


def encode_tolerances(t: Tolerances) -> List[float]:
    """The two declared tolerance knobs. +inf rides the wire as IEEE-754 inf
    (float32 has an exact inf), so 'comma untouched' is representable exactly."""
    return [float(t.leash), float(t.comma)]


def decode_tolerances(args) -> Tolerances:
    args = list(args)
    if len(args) != 2:
        raise ValueError(f"/ets/tolerances arity {len(args)} != 2")
    return Tolerances(leash=float(args[0]), comma=float(args[1]))


def encode_hello(meters_port: int) -> List[int]:
    return [int(meters_port)]


def encode_welcome(K: int, world_hash: str, L: int, bar_seconds: float,
                   sr: int) -> List:
    return [int(K), str(world_hash), int(L), float(bar_seconds), int(sr)]


def encode_clock(bar: int, seconds: float) -> List:
    return [int(bar), float(seconds)]


def encode_drift(key: float, phase_feel: float, timbre: float) -> List[float]:
    return [float(key), float(phase_feel), float(timbre)]


# slide/loop pairs use the same 3-component wire shape as drift; NaN = "no
# reading yet" (the Stage-0 shadow feed may be absent; the panel shows '—').
encode_slide = encode_drift
encode_loop = encode_drift


def encode_eoc(gate: int) -> List[int]:
    return [int(bool(gate))]


def encode_novelty_sat(saturation: float) -> List[float]:
    return [float(saturation)]
