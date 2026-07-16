"""Live telemetry receiver for the CONNECTED instrument (ets.instrument.live).

The engine emits its read-only telemetry to the meters destination the panel
announced in /ets/hello:

  * /ets/meter/*     — the read-only meter jacks (display; forwarded untouched);
  * /ets/roleactivity— flat float K-vector: per-ROLE (anchor) light-up level
                       0..1 for the primary role grid (the play surface);
  * /ets/rolemeta    — flat int K-vector: per-role unit_count (drill-in sizing);
  * /ets/nowplaying  — flat [int track_id, float activity, ...]: which source
                       tracks are sounding now (secondary per-track pad lights);
  * /ets/profiles    — flat [int track_id, float p0..p(K-1), ...]: each track's
                       normalized K-vector anchor-mass profile.

Parsing note (why there is no K field, and why that is not a hidden channel):
the flat nowplaying/profiles arrays carry no explicit vector length. We do NOT
invent a length flag or a second framing channel — we read the OSC TYPE TAGS
python-osc already decodes: an int opens a new track block, and the floats that
follow are that track's values. This is unambiguous for both messages (one float
per track for nowplaying, K floats for profiles) and needs no side-channel.

Structural separation mirrors ets.panel.transport.MeterReceiver: every handler
takes only its callback and NOTHING that can reach an emitter or the outbound
socket, so no received telemetry can become an emitted byte (the meters/telemetry
path stays one-way; I-5).

Uses python-osc (UDP/socketserver). No HTTP, no browser, no web framework — the
runtime stays native Qt + OSC (I-13).
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from pythonosc import dispatcher as _dispatcher
from pythonosc import osc_server


def group_by_track(args) -> Dict[int, List[float]]:
    """Group a flat OSC arg list into {track_id: [float, ...]} using the decoded
    types: each int opens a new track block; the floats after it are that track's
    values. Order of first appearance is preserved. Tolerant of any per-track
    vector length (1 for nowplaying, K for profiles) with no explicit length
    field, so the wire format needs no second framing channel."""
    out: Dict[int, List[float]] = {}
    cur: Optional[int] = None
    for a in args:
        if isinstance(a, bool):                    # bool is an int subclass; skip
            continue
        if isinstance(a, int):
            cur = int(a)
            out.setdefault(cur, [])
        elif cur is not None:
            out[cur].append(float(a))
    return out


class TelemetryReceiver:
    """UDP OSC server that routes the engine's live telemetry to callbacks.

    Bind port 0 for an OS-assigned ephemeral port (`bound_port` reveals it) so
    the panel can announce it in /ets/hello and the engine sends telemetry back.

    Every callback is optional; a missing one makes its address a no-op.
      * on_roleactivity(list[float])           per-role (anchor) light-up 0..1
      * on_rolemeta(list[int])                  per-role unit_count
      * on_nowplaying(dict[int,float])          track_id -> activity (0..1)
      * on_profiles(dict[int, list[float]])     track_id -> normalized K-vector
      * on_meter(address, *args)                forwarded /ets/meter/* payload
    """

    def __init__(self,
                 on_roleactivity: Optional[Callable[[List[float]], None]] = None,
                 on_rolemeta: Optional[Callable[[List[int]], None]] = None,
                 on_nowplaying: Optional[Callable[[Dict[int, float]], None]] = None,
                 on_profiles: Optional[Callable[[Dict[int, List[float]]], None]] = None,
                 on_meter: Optional[Callable[..., None]] = None,
                 host: str = "127.0.0.1", port: int = 0) -> None:
        self._on_roleactivity = on_roleactivity
        self._on_rolemeta = on_rolemeta
        self._on_nowplaying = on_nowplaying
        self._on_profiles = on_profiles
        self._on_meter = on_meter
        disp = _dispatcher.Dispatcher()
        disp.map("/ets/meter/*", self._handle_meter)
        disp.map("/ets/roleactivity", self._handle_roleactivity)
        disp.map("/ets/rolemeta", self._handle_rolemeta)
        disp.map("/ets/nowplaying", self._handle_nowplaying)
        disp.map("/ets/profiles", self._handle_profiles)
        self._server = osc_server.ThreadingOSCUDPServer((host, int(port)), disp)
        self._thread = None

    # --- handlers: callback in, nothing reachable that could emit -------------
    def _handle_meter(self, address: str, *args) -> None:
        if self._on_meter is not None:
            self._on_meter(address, *args)

    def _handle_roleactivity(self, _address: str, *args) -> None:
        if self._on_roleactivity is not None:
            self._on_roleactivity([float(a) for a in args])

    def _handle_rolemeta(self, _address: str, *args) -> None:
        if self._on_rolemeta is not None:
            self._on_rolemeta([int(a) for a in args])

    def _handle_nowplaying(self, _address: str, *args) -> None:
        if self._on_nowplaying is not None:
            grouped = group_by_track(args)
            self._on_nowplaying(
                {t: (v[0] if v else 0.0) for t, v in grouped.items()})

    def _handle_profiles(self, _address: str, *args) -> None:
        if self._on_profiles is not None:
            self._on_profiles(group_by_track(args))

    # --- server lifecycle (mirrors panel.transport.MeterReceiver) -------------
    @property
    def bound_port(self) -> int:
        return self._server.server_address[1]

    @property
    def bound_host(self) -> str:
        return self._server.server_address[0]

    def start(self) -> None:
        import threading
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="ets-telemetry-osc",
            daemon=True)
        self._thread.start()

    def handle_once(self, timeout: float = 1.0) -> bool:
        """Process a single inbound datagram synchronously (deterministic for
        tests). Returns True if one was handled, False on timeout."""
        import select
        self._server.timeout = timeout
        r, _, _ = select.select([self._server.fileno()], [], [], timeout)
        if not r:
            return False
        self._server.handle_request()
        return True

    def stop(self) -> None:
        if self._thread is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass
            self._thread.join(timeout=2.0)
            self._thread = None
        self._server.server_close()
