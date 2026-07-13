"""OSC schema — the panel↔engine binding contract.

Covers: (1) pure encode/decode round-trip of u + T_s over the ONE outbound
channel, for K=0 and K>0 anchors; (2) a live UDP loopback emit→receive of the
lane message decoded back to the same LaneVector (the engine's Layer-0 map is
exactly this decode); (3) schema stability — the addresses and the arity
contract are pinned so a drift is caught.
"""
import numpy as np
import pytest

from ets.panel.lanes import LaneVector
from ets.panel import osc_schema as S


def _sample_u(K):
    return LaneVector(
        u_region=np.linspace(-2.0, 2.0, K).astype(np.float32) if K else np.zeros(0),
        u_density=0.5, u_continuity=-1.25, u_gauge=2.0, u_novelty=-0.75, T_s=0.3)


@pytest.mark.parametrize("K", [0, 1, 3, 7])
def test_encode_decode_roundtrip(K):
    u = _sample_u(K)
    args = S.encode_lanes(u)
    assert len(args) == 1 + K + 5           # arity contract
    assert args[0] == K                      # self-describing anchor count
    back = S.decode_lanes(args)
    assert back.n_anchors == K
    np.testing.assert_allclose(back.u_region, u.u_region, atol=1e-6)
    assert back.u_density == pytest.approx(u.u_density, abs=1e-6)
    assert back.u_continuity == pytest.approx(u.u_continuity, abs=1e-6)
    assert back.u_gauge == pytest.approx(u.u_gauge, abs=1e-6)
    assert back.u_novelty == pytest.approx(u.u_novelty, abs=1e-6)
    assert back.T_s == pytest.approx(u.T_s, abs=1e-6)


def test_decode_rejects_bad_arity():
    with pytest.raises(ValueError):
        S.decode_lanes([2, 0.0, 0.0])        # claims K=2 but too few args
    with pytest.raises(ValueError):
        S.decode_lanes([])                    # empty


def test_single_outbound_channel():
    # The boundary-measure typing: exactly ONE outbound address, nothing else.
    assert S.OUTBOUND_ADDRESSES == ("/ets/lanes",)


def test_inbound_addresses_are_the_meter_jacks_only():
    assert set(S.INBOUND_ADDRESSES) == {
        "/ets/meter/drift", "/ets/meter/eoc", "/ets/meter/novelty_sat"}


def test_schema_addresses_are_pinned():
    # Golden values — the engine binds to these strings; a rename is a breaking
    # contract change and must fail loudly here.
    assert S.ADDR_LANES == "/ets/lanes"
    assert S.ADDR_METER_DRIFT == "/ets/meter/drift"
    assert S.ADDR_METER_EOC == "/ets/meter/eoc"
    assert S.ADDR_METER_NOVELTY_SAT == "/ets/meter/novelty_sat"
    assert S.DRIFT_COMPONENTS == ("key", "phase_feel", "timbre")


def test_live_udp_loopback_roundtrip():
    """Emit the lane message over real UDP localhost; the receiver decodes it
    back to the same LaneVector. This is the actual wire the engine binds to."""
    from pythonosc import dispatcher as D
    from pythonosc import osc_server, udp_client
    import select

    got = {}

    def _capture(_addr, *args):
        got["u"] = S.decode_lanes(list(args))

    disp = D.Dispatcher()
    disp.map(S.ADDR_LANES, _capture)
    server = osc_server.ThreadingOSCUDPServer(("127.0.0.1", 0), disp)
    try:
        port = server.server_address[1]
        client = udp_client.SimpleUDPClient("127.0.0.1", port)
        u = _sample_u(4)
        client.send_message(S.ADDR_LANES, S.encode_lanes(u))
        # deterministic single-datagram handling
        r, _, _ = select.select([server.fileno()], [], [], 2.0)
        assert r, "no OSC datagram received on loopback"
        server.handle_request()
    finally:
        server.server_close()

    assert "u" in got, "lane message did not arrive"
    np.testing.assert_allclose(got["u"].u_region, u.u_region, atol=1e-6)
    assert got["u"].T_s == pytest.approx(u.T_s, abs=1e-6)
    assert got["u"].u_gauge == pytest.approx(u.u_gauge, abs=1e-6)
