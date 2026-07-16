"""Engine-side OSC endpoints (spec §12: IPC = OSC over localhost).

The engine binds EXACTLY the outbound half of the panel's closed message space
(osc_schema.OUTBOUND_ADDRESSES: lanes, tolerances, hello) and emits EXACTLY the
inbound half (welcome, clock, meters). Anything else on the wire is ignored by
construction (unmapped addresses are dropped by the dispatcher) — the message
space is closed at both ends (H-6/C-3).

CONTROL FLOW LAW (I-1 / C-3): the lane handler DECODES the wire into a
LaneVector and stores it in the inbox. It is the ENGINE LOOP that converts the
stored LaneVector to TiltTerms via ets.writer.tilt.layer0 — the single map —
immediately before the frontier bar binds it. No handler here touches the
writer; tolerances are stored + logged and reach NOTHING downstream (Stage-1
pending; CI-enforced).
"""
from __future__ import annotations
import logging
import math
import threading
from typing import Optional, Tuple

from pythonosc import dispatcher as _dispatcher
from pythonosc import osc_server, udp_client

from ets.panel import osc_schema as S
from ets.panel.lanes import LaneVector
from ets.panel.tolerances import Tolerances, display as tol_display

log = logging.getLogger("ets.engine")


class Inbox:
    """Thread-safe latest-value store for the three inbound control-plane
    messages. The writer loop reads; the OSC server thread writes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._u: Optional[LaneVector] = None
        self._tolerances = Tolerances()          # leash=inf, comma=inf
        self._hello: Optional[Tuple[str, int]] = None   # (panel host, meter port)
        self.hello_event = threading.Event()

    # writers (OSC thread)
    def put_lanes(self, u: LaneVector) -> None:
        with self._lock:
            self._u = u

    def put_tolerances(self, t: Tolerances) -> None:
        with self._lock:
            self._tolerances = t

    def put_hello(self, host: str, port: int) -> None:
        with self._lock:
            self._hello = (host, int(port))
        self.hello_event.set()

    # readers (engine loop)
    def latest_lanes(self) -> Optional[LaneVector]:
        with self._lock:
            return None if self._u is None else self._u.copy()

    def latest_tolerances(self) -> Tolerances:
        with self._lock:
            return Tolerances(self._tolerances.leash, self._tolerances.comma)

    def hello(self) -> Optional[Tuple[str, int]]:
        with self._lock:
            return self._hello


def _fmt_lanes(u: LaneVector) -> str:
    r = ", ".join(f"{x:+.2f}" for x in u.u_region.tolist())
    return (f"region=[{r}] density={u.u_density:+.2f} "
            f"continuity={u.u_continuity:+.2f} gauge={u.u_gauge:+.2f} "
            f"novelty={u.u_novelty:+.2f} T_s={u.T_s:.3f}")


def _on_lanes(_addr, fixed, *args) -> None:
    inbox: Inbox = fixed[0]
    u = S.decode_lanes(args)
    inbox.put_lanes(u)
    log.info("LANES  %s", _fmt_lanes(u))          # PART B: lanes echo in log


def _on_tolerances(_addr, fixed, *args) -> None:
    inbox: Inbox = fixed[0]
    t = S.decode_tolerances(args)
    inbox.put_tolerances(t)
    log.info("TOLERANCES  leash=%s comma=%s  (declared; consumed by nothing — "
             "Stage-1 authority pending)", tol_display(t.leash),
             tol_display(t.comma))


def _make_on_hello(inbox: Inbox):
    # python-osc's handler API does not expose the sender address through
    # dispatcher.map; we wrap the server's datagram entry instead (see
    # ControlServer). This plain handler receives (client_host) injected there.
    def _on_hello(_addr, fixed, *args) -> None:
        host = fixed[1]() if callable(fixed[1]) else "127.0.0.1"
        (meters_port,) = args
        inbox.put_hello(host, int(meters_port))
        log.info("HELLO from panel %s (meters_port=%d)", host, int(meters_port))
    return _on_hello


class ControlServer:
    """UDP OSC server on the engine control port; binds ONLY the closed
    outbound-from-panel space."""

    def __init__(self, inbox: Inbox, host: str = "127.0.0.1",
                 port: int = 9000) -> None:
        self.inbox = inbox
        self._last_sender = "127.0.0.1"
        disp = _dispatcher.Dispatcher()
        disp.map(S.ADDR_LANES, _on_lanes, inbox)
        disp.map(S.ADDR_TOLERANCES, _on_tolerances, inbox)
        disp.map(S.ADDR_HELLO, _make_on_hello(inbox), inbox,
                 lambda: self._last_sender)
        outer = self

        class _Server(osc_server.ThreadingOSCUDPServer):
            def verify_request(self, request, client_address):
                outer._last_sender = client_address[0]
                return True

        self._server = _Server((host, int(port)), disp)
        self._thread: Optional[threading.Thread] = None

    @property
    def bound_port(self) -> int:
        return self._server.server_address[1]

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        name="ets-engine-osc", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._server.shutdown()
            self._thread.join(timeout=2.0)
            self._thread = None
        self._server.server_close()


class MeterEmitter:
    """Engine → panel: welcome / clock / meter jacks. Values in, wire out —
    this object never reads the inbox (meters cannot loop back through the
    engine into control; the panel side enforces the same one-way law)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9001) -> None:
        self.retarget(host, port)

    def retarget(self, host: str, port: int) -> None:
        self.host, self.port = host, int(port)
        self._client = udp_client.SimpleUDPClient(host, int(port))

    def welcome(self, K: int, world_hash: str, L: int, bar_seconds: float,
                sr: int, disarmed: str = "") -> None:
        self._client.send_message(
            S.ADDR_WELCOME,
            S.encode_welcome(K, world_hash, L, bar_seconds, sr, disarmed))
        log.info("WELCOME -> %s:%d  (K=%d, L=%d bars, bar=%.3fs, world %s, "
                 "disarmed=%s)", self.host, self.port, K, L, bar_seconds,
                 world_hash[:8], disarmed or "none")

    def clock(self, bar: int, seconds: float) -> None:
        self._client.send_message(S.ADDR_CLOCK, S.encode_clock(bar, seconds))

    def eoc(self, gate: int) -> None:
        self._client.send_message(S.ADDR_METER_EOC, S.encode_eoc(gate))

    def novelty_sat(self, saturation: float) -> None:
        self._client.send_message(S.ADDR_METER_NOVELTY_SAT,
                                  S.encode_novelty_sat(saturation))

    def nowplaying(self, activity) -> None:
        """READ-ONLY telemetry (spec §12 meters direction): the source tracks
        sounding at the just-produced frontier bar, with a normalized 0..1
        activity. `activity` is an iterable of (track_id, activity) pairs; the
        wire is a FLAT alternating list [int track_id, float activity, ...].
        Sent to the SAME meters destination as the jacks. Values in, wire out —
        this reads the writer's already-produced provenance and NEVER loops back
        into control, settlement, the writer, render, F, or provenance
        generation (the audio path is byte-identical with this on or off)."""
        args: list = []
        for tid, act in activity:
            args.append(int(tid))
            args.append(float(act))
        self._client.send_message("/ets/nowplaying", args)

    def profiles(self, profiles) -> None:
        """READ-ONLY static telemetry: each source track's ANCHOR-MASS PROFILE,
        a K-vector (K = n_anchors, sent on /ets/welcome) in 0..1, so the panel
        can steer on a pad tap. `profiles` is an iterable of (track_id, sequence
        of K floats); the wire is a FLAT list [int track_id, float p0, ...,
        float p(K-1), int track_id, ...]. Sent ONCE to the SAME meters
        destination as the jacks, right after /ets/welcome. This is frozen-world
        structure out; it reads NOTHING downstream (settlement, writer, render,
        F, provenance generation and the audio path are all untouched)."""
        args: list = []
        for tid, vec in profiles:
            args.append(int(tid))
            for x in vec:
                args.append(float(x))
        self._client.send_message("/ets/profiles", args)

    def roleactivity(self, activity) -> None:
        """READ-ONLY per-ROLE telemetry: the activity of each anchor/role in the
        just-produced frontier bar. `activity` is a length-K sequence (K =
        n_anchors, sent on /ets/welcome) of floats in 0..1; the wire is a FLAT
        float list [a0, a1, ..., a(K-1)] (index == role id). Sent to the SAME
        meters destination as the jacks, once per bar. Reads the writer's
        already-produced bar rows only — no settlement/writer/render/F/
        provenance call (audio byte-identical)."""
        self._client.send_message("/ets/roleactivity",
                                  [float(x) for x in activity])

    def rolemeta(self, counts) -> None:
        """READ-ONLY static per-ROLE metadata: how many source units live under
        each role (for the pad drill-in). `counts` is an iterable of (role,
        unit_count); the wire is a FLAT list [int role, int unit_count, ...].
        Sent to the SAME meters destination once, right after /ets/welcome and
        /ets/profiles. Frozen-world structure out; nothing downstream is
        touched."""
        args: list = []
        for role, n in counts:
            args.append(int(role))
            args.append(int(n))
        self._client.send_message("/ets/rolemeta", args)
    # NOTE deliberately ABSENT: slide/loop emitters. Those jacks are fed by the
    # Stage-0 meters (a separate feature); this engine does not fabricate their
    # values, and the panel displays '—' until the real feed exists.
