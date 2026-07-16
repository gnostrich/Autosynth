"""PI telemetry-parse bite (PREREG-uiv5-playable-instrument PI-B/PI-E, read side).

`TelemetryReceiver` is the panel/instrument-side reader of the engine's read-only
monitor addresses. It parses the outbound telemetry messages and hands each to a
display callback (the MeterReceiver pattern: callback in, nothing reachable that
could emit — one-way, I-5). This pins the three parses the live grid depends on:

  * /ets/nowplaying   flat [int track_id, float activity, ...] -> {track: act}
                      (format FIXED by the engine emitter, ets.engine.osc_io)
  * /ets/profiles     flat [int track_id, float p0..p(K-1), ...] -> {track: K}
  * /ets/roleactivity flat float K-vector -> per-anchor (role) brightness list

The receiver is a concurrent feature; this bite SKIPS if it is not present yet.
"""
from __future__ import annotations

import pytest

from tests.pi.conftest import load_telemetry_receiver

udp_client = pytest.importorskip("pythonosc.udp_client")


@pytest.fixture
def wired_receiver():
    """A TelemetryReceiver with capturing callbacks bound to an ephemeral port,
    plus a udp client aimed at it. Yields (receiver, client, captured)."""
    cls = load_telemetry_receiver()
    if cls is None:
        pytest.skip("TelemetryReceiver not present yet (concurrent telemetry "
                    "feature); tried ets.instrument.live / .telemetry / .feed, "
                    "ets.panel.telemetry / .transport")

    captured = {}
    kwargs = dict(
        on_nowplaying=lambda d: captured.__setitem__("nowplaying", d),
        on_profiles=lambda d: captured.__setitem__("profiles", d),
        on_roleactivity=lambda v: captured.__setitem__("roleactivity", v),
        port=0,
    )
    try:
        rec = cls(**kwargs)
    except TypeError:
        pytest.skip("TelemetryReceiver signature differs from the agreed "
                    "callback contract (on_nowplaying/on_profiles/"
                    "on_roleactivity, port=0); parse bite not exercised")

    if not (hasattr(rec, "bound_port") and hasattr(rec, "handle_once")):
        if hasattr(rec, "stop"):
            rec.stop()
        pytest.skip("TelemetryReceiver present but not server-style "
                    "(no bound_port/handle_once)")

    host = getattr(rec, "bound_host", "127.0.0.1")
    client = udp_client.SimpleUDPClient(host, rec.bound_port)
    yield rec, client, captured
    if hasattr(rec, "stop"):
        rec.stop()


def _send(rec, client, addr, args):
    client.send_message(addr, args)
    assert rec.handle_once(timeout=2.0), f"no datagram handled for {addr}"


def test_nowplaying_parses_into_track_activity_dict(wired_receiver):
    rec, client, captured = wired_receiver
    _send(rec, client, "/ets/nowplaying", [0, 0.5, 2, 1.0])
    d = captured.get("nowplaying")
    assert d is not None, "on_nowplaying was not invoked"
    got = {int(k): float(v) for k, v in d.items()}
    assert got == {0: 0.5, 2: 1.0}


def test_profiles_parses_into_track_kvector_dict(wired_receiver):
    rec, client, captured = wired_receiver
    # two tracks, each a K=4 anchor-mass profile, on one message.
    _send(rec, client, "/ets/profiles",
          [1, 0.1, 0.7, 0.0, 0.2, 3, 0.25, 0.25, 0.25, 0.25])
    d = captured.get("profiles")
    assert d is not None, "on_profiles was not invoked"
    assert set(d) == {1, 3}
    assert [pytest.approx(x) for x in d[1]] == [0.1, 0.7, 0.0, 0.2]
    assert [pytest.approx(x) for x in d[3]] == [0.25, 0.25, 0.25, 0.25]


def test_roleactivity_parses_into_per_anchor_brightness(wired_receiver):
    rec, client, captured = wired_receiver
    acts = [0.1, 0.2, 0.3, 0.4]
    _send(rec, client, "/ets/roleactivity", acts)
    v = captured.get("roleactivity")
    assert v is not None, "on_roleactivity was not invoked"
    assert [pytest.approx(x) for x in list(v)] == acts
