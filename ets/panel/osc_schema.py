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

INBOUND (engine → panel), read-only meter jacks (spec §9). These feed the
panel's DISPLAY only; nothing derived from them is ever emitted (I-5):

  /ets/meter/drift        key:float32, phase_feel:float32, timbre:float32
                          (accumulated holonomy per gauge component — §9)
  /ets/meter/eoc          gate:int32          (phrase end-of-chain gate; 0/1)
  /ets/meter/novelty_sat  saturation:float32  (novelty saturation CV; ~[0,1])

There is deliberately NO inbound control address: the engine never writes the
panel's lanes. The panel is the sole author of u/T_s; the engine is the sole
author of meters. One direction each.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np

from ets.panel.lanes import LaneVector

# --- addresses (stable identifiers; the engine binds to these strings) --------
ADDR_LANES = "/ets/lanes"                 # OUTBOUND, the one boundary-measure channel
ADDR_METER_DRIFT = "/ets/meter/drift"     # INBOUND
ADDR_METER_EOC = "/ets/meter/eoc"         # INBOUND
ADDR_METER_NOVELTY_SAT = "/ets/meter/novelty_sat"  # INBOUND

OUTBOUND_ADDRESSES: Tuple[str, ...] = (ADDR_LANES,)
INBOUND_ADDRESSES: Tuple[str, ...] = (
    ADDR_METER_DRIFT, ADDR_METER_EOC, ADDR_METER_NOVELTY_SAT)

# Drift gauge components, in wire order (spec §9).
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


def encode_drift(key: float, phase_feel: float, timbre: float) -> List[float]:
    return [float(key), float(phase_feel), float(timbre)]


def encode_eoc(gate: int) -> List[int]:
    return [int(bool(gate))]


def encode_novelty_sat(saturation: float) -> List[float]:
    return [float(saturation)]
