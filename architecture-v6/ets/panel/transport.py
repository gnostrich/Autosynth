"""OSC transport (spec §12: IPC = OSC over localhost) — native UDP, no web tech.

Two one-directional flows, matching `osc_schema`:
  - `OscEmitter` sends the ONE outbound boundary-measure message (u + T_s).
  - `MeterReceiver` runs a UDP OSC server and routes the three inbound meter
    addresses to a `MeterState` — display only.

Structural separation (the meters-display-only guarantee): the meter handlers
below take a `MeterState` and NOTHING else. They cannot reach a `LaneVector`,
the emitter, or the outbound socket — so no emitted byte can be a function of a
received meter. `OscEmitter.emit` reads solely from the `LaneVector` handed to
it. The two halves never touch.

Uses python-osc (UDP/socketserver). No HTTP, no browser, no web framework — the
runtime stays native Qt + OSC (I-13).
"""
from __future__ import annotations

from typing import Optional

from pythonosc import dispatcher as _dispatcher
from pythonosc import osc_server, udp_client

from ets.panel.lanes import LaneVector
from ets.panel.meters import MeterState
from ets.panel.tolerances import Tolerances
from ets.panel import osc_schema as S


class OscEmitter:
    """Sends the panel's THREE outbound messages (the closed outbound space,
    osc_schema.OUTBOUND_ADDRESSES): the boundary-measure lanes, the declared
    tolerances, and the handshake hello. Nothing else can leave the panel."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9000) -> None:
        self.host = host
        self.port = int(port)
        self._client = udp_client.SimpleUDPClient(host, self.port)
        self.last_args: Optional[list] = None            # for tests/telemetry only
        self.last_tolerance_args: Optional[list] = None  # for tests/telemetry only

    def emit(self, u: LaneVector) -> None:
        """Serialise and send the lane vector — the boundary-measure channel.
        Reads nothing but `u`; no meter value can influence this message."""
        args = S.encode_lanes(u)
        self.last_args = args
        self._client.send_message(S.ADDR_LANES, args)

    def emit_tolerances(self, t: Tolerances) -> None:
        """Send the declared LEASH/COMMA tolerances. Reads nothing but `t`."""
        args = S.encode_tolerances(t)
        self.last_tolerance_args = args
        self._client.send_message(S.ADDR_TOLERANCES, args)

    def emit_hello(self, meters_port: int) -> None:
        """Announce the panel's meter-receiver port (handshake; no control)."""
        self._client.send_message(S.ADDR_HELLO, S.encode_hello(meters_port))


# --- inbound meter handlers: MeterState in, display out, nothing else ---------
# Kept at module scope so a structural test can confirm they never reference a
# lane / emitter / outbound socket. python-osc calls a mapped handler as
# handler(address, fixed_args_tuple, *osc_values); `fixed[0]` is the MeterState.

def _on_eoc(_addr: str, fixed, *args) -> None:
    meter_state = fixed[0]
    (gate,) = args
    meter_state.set_eoc(gate)


def _on_novelty_sat(_addr: str, fixed, *args) -> None:
    meter_state = fixed[0]
    (saturation,) = args
    meter_state.set_novelty_saturation(saturation)


def _on_slide(_addr: str, fixed, *args) -> None:
    meter_state = fixed[0]
    key, phase_feel, timbre = args
    meter_state.set_slide(key, phase_feel, timbre)


def _on_loop(_addr: str, fixed, *args) -> None:
    meter_state = fixed[0]
    key, phase_feel, timbre = args
    meter_state.set_loop(key, phase_feel, timbre)


def _on_clock(_addr: str, fixed, *args) -> None:
    meter_state = fixed[0]
    bar, seconds = args
    meter_state.set_clock(bar, seconds)


def _on_welcome(_addr: str, fixed, *args) -> None:
    meter_state = fixed[0]
    K, world_hash, L, bar_seconds, sr, disarmed = args
    meter_state.set_welcome(K, world_hash, L, bar_seconds, sr, disarmed)


def build_meter_dispatcher(meter_state: MeterState) -> _dispatcher.Dispatcher:
    """A dispatcher whose handlers write ONLY into `meter_state` — every
    inbound address of the closed message space, display-typed, no exceptions."""
    d = _dispatcher.Dispatcher()
    d.map(S.ADDR_METER_SLIDE, _on_slide, meter_state)
    d.map(S.ADDR_METER_LOOP, _on_loop, meter_state)
    d.map(S.ADDR_METER_EOC, _on_eoc, meter_state)
    d.map(S.ADDR_METER_NOVELTY_SAT, _on_novelty_sat, meter_state)
    d.map(S.ADDR_CLOCK, _on_clock, meter_state)
    d.map(S.ADDR_WELCOME, _on_welcome, meter_state)
    return d


class MeterReceiver:
    """UDP OSC server that updates a `MeterState` from inbound meter messages.

    Bind port 0 for an OS-assigned ephemeral port (`bound_port` reveals it) —
    used for loopback round-trip tests without a fixed port.
    """

    def __init__(self, meter_state: MeterState,
                 host: str = "127.0.0.1", port: int = 9001) -> None:
        self.meter_state = meter_state
        disp = build_meter_dispatcher(meter_state)
        self._server = osc_server.ThreadingOSCUDPServer((host, int(port)), disp)
        self._thread = None

    @property
    def bound_port(self) -> int:
        return self._server.server_address[1]

    @property
    def bound_host(self) -> str:
        return self._server.server_address[0]

    def start(self) -> None:
        import threading
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="ets-meter-osc", daemon=True)
        self._thread.start()

    def handle_once(self, timeout: float = 1.0) -> bool:
        """Process a single inbound datagram synchronously (deterministic for
        tests). Returns True if one was handled, False on timeout."""
        self._server.timeout = timeout
        import select
        r, _, _ = select.select([self._server.fileno()], [], [], timeout)
        if not r:
            return False
        self._server.handle_request()
        return True

    def stop(self) -> None:
        # shutdown() only makes sense (and only returns) if serve_forever() is
        # running on the thread; calling it otherwise blocks forever. The
        # synchronous handle_once() path never starts the thread, so we just
        # close the socket in that case.
        if self._thread is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass
            self._thread.join(timeout=2.0)
            self._thread = None
        self._server.server_close()
