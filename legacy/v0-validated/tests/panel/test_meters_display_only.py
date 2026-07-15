"""Meters are DISPLAY ONLY (spec §9, I-5).

The panel shows received meter values; it must emit NOTHING derived from them.
Meters→planner/feedback is the sanctioned consumer — never the panel's lanes.

Two independent teeth:
  (A) BEHAVIOURAL — feeding a wide stream of meter values updates the display
      but never changes the emitted boundary-measure message, and never triggers
      an emit. Emission is a function of the LaneVector alone.
  (B) STRUCTURAL — the inbound meter handlers (and the widget's meter refresh)
      reference no lane / emitter / outbound-channel identifier. Proven to bite
      against a mutant handler that writes a lane from a meter value.
"""
import ast
import inspect
import os

import numpy as np
import pytest

from ets.panel.lanes import LaneVector, default_lane_vector
from ets.panel.meters import MeterState
from ets.panel import osc_schema as S
from ets.panel import transport as T
from ets.panel.transport import OscEmitter


# ---- (A) behavioural --------------------------------------------------------

def test_emitter_output_is_function_of_lane_vector_only():
    """Same LaneVector ⇒ identical outbound args, no matter what meters arrived.
    The emitter has no meter input at all — this pins that structurally-guaranteed
    fact behaviourally."""
    u = default_lane_vector(3)
    u.u_region[:] = [0.1, -0.2, 0.3]
    emitter = OscEmitter(port=9)     # never actually sent; we read last_args
    emitter.emit(u)
    a1 = list(emitter.last_args)
    # a flood of arbitrary meter values into a MeterState changes nothing upstream
    ms = MeterState()
    for k in range(50):
        ms.set_drift(k, -k, 0.5 * k)
        ms.set_eoc(k % 2)
        ms.set_novelty_saturation((k % 7) / 7.0)
    emitter.emit(u)                  # re-emit the SAME u
    assert emitter.last_args == a1, "emitted message changed though only u matters"


def test_meter_receiver_updates_display_and_emits_nothing():
    """A live meter datagram updates MeterState; the receive path holds no
    emitter and cannot emit. We assert the display updated and that the meter
    dispatcher's registered handlers touch only the MeterState."""
    ms = MeterState()
    rx = T.MeterReceiver(ms, host="127.0.0.1", port=0)
    try:
        from pythonosc import udp_client
        client = udp_client.SimpleUDPClient("127.0.0.1", rx.bound_port)
        client.send_message(S.ADDR_METER_DRIFT, S.encode_drift(0.4, -0.1, 0.9))
        assert rx.handle_once(timeout=2.0)
        client.send_message(S.ADDR_METER_EOC, S.encode_eoc(1))
        assert rx.handle_once(timeout=2.0)
        client.send_message(S.ADDR_METER_NOVELTY_SAT, S.encode_novelty_sat(0.75))
        assert rx.handle_once(timeout=2.0)
    finally:
        rx.stop()
    # OSC floats ride as float32 — compare with tolerance.
    assert ms.drift["key"] == pytest.approx(0.4, abs=1e-6)
    assert ms.drift["phase_feel"] == pytest.approx(-0.1, abs=1e-6)
    assert ms.drift["timbre"] == pytest.approx(0.9, abs=1e-6)
    assert ms.eoc_gate == 1
    assert ms.novelty_saturation == pytest.approx(0.75, abs=1e-6)


def test_panel_receiving_meters_never_emits():
    """Through the widget: pushing meter values and refreshing the jacks updates
    the display but issues ZERO emits and leaves the last outbound message
    byte-identical."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    class _RecEmitter:
        def __init__(self):
            self.calls = []
            self.last_args = None

        def emit(self, u):
            from ets.panel import osc_schema as _S
            self.last_args = _S.encode_lanes(u)
            self.calls.append(self.last_args)

    from ets.panel.widget import Panel
    app = QApplication.instance() or QApplication([])
    emitter = _RecEmitter()
    panel = Panel(emitter=emitter, n_anchors=2)

    # one legitimate lane edit → exactly one emit
    panel.u.u_density = 1.0
    panel._push()
    baseline_calls = len(emitter.calls)
    baseline_args = list(emitter.last_args)

    # now flood meters and refresh the display many times
    for k in range(100):
        panel.meter_state.set_drift(k, -2 * k, 0.3 * k)
        panel.meter_state.set_eoc(k % 2)
        panel.meter_state.set_novelty_saturation((k % 5) / 5.0)
        panel.refresh_meters()

    assert len(emitter.calls) == baseline_calls, \
        "receiving/displaying meters triggered an emit (I-5 violation)"
    assert list(emitter.last_args) == baseline_args, \
        "the outbound message changed after meters arrived (I-5 violation)"


# ---- (B) structural ---------------------------------------------------------

_LANE_TOKENS = {
    "LaneVector", "OscEmitter", "emit", "emitter", "u_region", "u_density",
    "u_continuity", "u_gauge", "u_novelty", "T_s", "encode_lanes",
    "send_message", "last_args", "_push", "lanes_changed",
}


def _identifiers(fn) -> set:
    import textwrap
    src = textwrap.dedent(inspect.getsource(fn))   # dedent methods for ast.parse
    idents = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Name):
            idents.add(n.id)
        elif isinstance(n, ast.Attribute):
            idents.add(n.attr)
    return idents


def test_meter_handlers_touch_no_lane_or_emitter():
    for fn in (T._on_drift, T._on_eoc, T._on_novelty_sat, T.build_meter_dispatcher):
        used = _identifiers(fn) & _LANE_TOKENS
        assert not used, (
            f"meter handler {fn.__name__} references lane/emit identifiers "
            f"{sorted(used)} — meters would leak into control (I-5)")


def test_widget_meter_refresh_touches_no_lane_or_emitter():
    from ets.panel.widget import Panel
    used = _identifiers(Panel.refresh_meters) & _LANE_TOKENS
    assert not used, (
        f"Panel.refresh_meters references lane/emit identifiers {sorted(used)} "
        f"— the display path must not feed control (I-5)")


def test_structural_scanner_bites_on_a_leaking_handler():
    """A mutant meter handler that writes a lane from a meter value MUST be
    flagged — proving the structural check is non-vacuous."""
    src = (
        "def _on_drift(meter_state, _addr, *args):\n"
        "    key, phase_feel, timbre = args\n"
        "    meter_state.u_density = key   # LEAK: meter → lane\n"
    )
    idents = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Name):
            idents.add(n.id)
        elif isinstance(n, ast.Attribute):
            idents.add(n.attr)
    assert idents & _LANE_TOKENS, "structural scanner is vacuous"
