"""WS-7 / WS-8 (backend halves) — NOT-A-PLAYHEAD and NO-INJECTION
(PREREG-waveform-scrub, "NOT-A-PLAYHEAD LAW").

The directive: pointing at a moment must affect audio ONLY through the bias payload,
and "unit IDs must NOT travel from pointer to writer". The backend halves:

  WS-7  A recorded /api/steer sequence replayed TWICE — once plain, once interleaved
        with /api/wavemap GETs — must produce a BYTE-IDENTICAL tape. The wavemap
        route is the only new surface the pointer touches on the server; if reading
        it perturbed the tape by one byte, the "read-only view" claim would be false.

  WS-8  The writer entry is INSTRUMENTED (the single tilt-construction point,
        ``StreamPlayer._compose_bar`` -> ``engine._tilt_for(u, a=…,
        channel_logbias=…)``) and asserted to receive NO unit-id-typed argument for a
        TRACKS-view payload sequence, plus: a crafted payload attempting unit
        injection (uid / transport keys the pointer might smuggle) is INERT — it
        changes neither the writer's carrier nor the tape.

DISCLOSED SCOPE (a real wall, reported not papered over): ``/api/steer`` DOES have
one unit-id-typed field — ``unit_bias``, the pre-existing GRID field UNIT-drill grain
(PREREG-field-bias-REV3), which rides the ``"unit"`` sub-map of the writer's ONE
``channel_logbias`` carrier. It is sanctioned for the GRID surface and is NOT part of
the TRACKS view's jack set (annex: row lean -> ``channel_bias``, cell leans ->
``track_role_bias``). So WS-8's honest backend statement is: for a TRACKS-view
payload the writer's carrier contains NO ``"unit"`` grain and the player's
``_unit_bias`` stays None. That the detector has TEETH is proven by the deliberate-
violation arm: a payload that DOES carry ``unit_bias`` makes the very same assertion
FAIL (unit ids demonstrably reach the carrier when something sends them) — so a
TRACKS view that ever smuggled a uid could not pass this gate.
"""
from __future__ import annotations

import pytest

from cloud.tests.test_wavemap_fixture import probe

_PROBE = r'''
import hashlib, json, os, threading, urllib.request
from cloud.companion.app import serve
from cloud.companion.engine_bridge import StreamPlayer

# A RECORDED TRACKS-view steer sequence: row lean -> channel_bias, cell leans ->
# track_role_bias, region neutral (the TRACKS view emits no region force). This is
# exactly the sanctioned jack set of the annex — nothing else.
SEQ = [
    {"region": [], "channel_bias": [0.55, 0.0, 0.0, 0.0],
     "track_role_bias": [[0, 1, 0.62], [0, 2, 0.31]]},
    {"region": [], "channel_bias": [0.55, -0.30, 0.0, 0.0],
     "track_role_bias": [[1, 0, 0.48], [0, 1, 0.20]]},
    {"region": [], "channel_bias": [], "track_role_bias": []},      # release
]
# The CRAFTED injection attempt: the same TRACKS payloads plus every unit-id /
# transport key a pointer could try to smuggle. None is a /api/steer field, so all
# must be inert.
INJECT = {"unit": 5, "unit_id": 5, "uid": 5, "unit_ids": [5, 6],
          "inject_unit": [0, 5], "pin_unit": 5, "play_unit": 5, "queue_unit": 5,
          "seek": 1.25, "seek_s": 1.25, "t": 1.25, "slice": [1.0, 1.25],
          "audition": True, "preview": True}
# The DELIBERATE VIOLATION: the GRID unit-drill grain. If the TRACKS view ever sent
# this, unit ids WOULD reach the writer's carrier — which is exactly what the WS-8
# assertion must catch.
VIOLATION = dict(SEQ[0], unit_bias={"7": 0.9, "11": -0.4})

httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
              session_dir=os.path.join(WDIR, "sess"), public=True)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % httpd.server_address[1]

def post(payload):
    req = urllib.request.Request(BASE + "/api/steer",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        assert r.status == 200, r.status
        return json.load(r)

def get_wavemap():
    with urllib.request.urlopen(BASE + "/api/wavemap", timeout=120) as r:
        return r.status, json.load(r)

def instrument(p):
    """Record the ARGUMENTS that reach the single tilt-construction point."""
    seen = []
    orig = p.engine._tilt_for
    def spy(u, *a, **kw):
        clog = kw.get("channel_logbias")
        seen.append(sorted(clog.keys()) if isinstance(clog, dict) else None)
        return orig(u, *a, **kw)
    p.engine._tilt_for = spy
    return seen

def run(seq, with_wavemap=False, extra=None):
    """Replay a steer sequence on a FRESH player, one bar per payload; return
    (tape sha256, grains seen at the writer entry, unit_bias state)."""
    p = StreamPlayer(WORLD, seed=0, is_trained=True)
    httpd.hub.playable_for = lambda session, _p=p: _p
    seen = instrument(p)
    h = hashlib.sha256()
    wm_status = []
    for payload in seq:
        body = dict(payload)
        if extra:
            body.update(extra)
        if with_wavemap:
            wm_status.append(get_wavemap()[0])
        post(body)
        if with_wavemap:
            wm_status.append(get_wavemap()[0])
        pcm, _roles = p.produce_one_bar()
        h.update(pcm)
    return {"tape": h.hexdigest(), "grains": seen,
            "unit_bias": p._unit_bias, "wm_status": wm_status}

plain = run(SEQ)
interleaved = run(SEQ, with_wavemap=True)
crafted = run(SEQ, extra=INJECT)
violation = run([VIOLATION] + SEQ[1:])
# CONTROL: a DIFFERENT lean sequence must give a DIFFERENT tape, or every
# byte-identity claim above would be vacuous (a tape nothing can move).
control = run([{"region": [], "channel_bias": [-0.95, 0.95, -0.95, 0.95],
                "track_role_bias": [[1, 0, -0.9], [2, 1, 0.9]]}] * len(SEQ))

emit({"plain": plain, "interleaved": interleaved, "crafted": crafted,
      "violation": violation, "control": control})
'''


def _d():
    if not hasattr(_d, "_v"):
        _d._v = probe(_PROBE)
    return _d._v


def _assert_no_unit_id_reaches_the_writer(run):
    """THE WS-8 assertion, as a function — run on the TRACKS-view arms (must pass)
    and on the deliberate-violation arm (must fail)."""
    for grains in run["grains"]:
        assert grains is None or "unit" not in grains, (
            "a unit-id-typed grain reached the writer's tilt carrier from a TRACKS "
            f"payload: {grains}")
    assert run["unit_bias"] is None, (
        "the player holds a per-UNIT bias map after a TRACKS-view payload sequence — "
        "unit ids travelled from the pointer path into engine state")


def test_wavemap_reads_do_not_change_one_byte_of_the_tape():
    """WS-7: same steer sequence, once plain and once interleaved with /api/wavemap
    GETs -> byte-identical tape."""
    d = _d()
    assert d["interleaved"]["wm_status"], "the interleaved arm never called /api/wavemap"
    assert set(d["interleaved"]["wm_status"]) == {200}, \
        f"/api/wavemap did not serve during the interleaved replay: {d['interleaved']['wm_status']}"
    assert d["plain"]["tape"] == d["interleaved"]["tape"], (
        "interleaving /api/wavemap GETs changed the produced tape — the pointer's "
        "view is NOT read-only")


def test_the_byte_identity_claims_are_not_vacuous():
    """CONTROL: the sanctioned TRACKS leans DO move the tape, so 'byte-identical
    under wavemap reads' is a real invariance and not a tape nothing can move."""
    d = _d()
    assert d["plain"]["tape"] != d["control"]["tape"], (
        "a very different TRACKS lean sequence produced the SAME tape — the "
        "byte-identity gates above would be vacuous")


def test_crafted_unit_injection_payload_is_inert():
    """WS-8: a payload carrying every uid/transport key a pointer might smuggle
    changes neither the writer's carrier nor the tape (no route reads them)."""
    d = _d()
    assert d["plain"]["tape"] == d["crafted"]["tape"], (
        "a crafted unit-injection / transport payload changed the tape — some field "
        "of it reached the writer")
    assert d["plain"]["grains"] == d["crafted"]["grains"], (
        "a crafted unit-injection payload changed the writer's tilt carrier: "
        f"{d['plain']['grains']} vs {d['crafted']['grains']}")
    _assert_no_unit_id_reaches_the_writer(d["crafted"])


def test_tracks_payloads_send_no_unit_id_to_the_writer():
    """WS-8: the sanctioned TRACKS jack set (channel_bias + track_role_bias) reaches
    the writer as track / track_role grains only."""
    d = _d()
    _assert_no_unit_id_reaches_the_writer(d["plain"])
    _assert_no_unit_id_reaches_the_writer(d["interleaved"])
    # the TRACKS leans DO arrive (the gate must not pass by the payload being inert)
    grains = [g for g in d["plain"]["grains"] if g]
    assert any("track" in g for g in grains), \
        "no track grain reached the writer — the TRACKS payload did nothing at all"
    assert any("track_role" in g for g in grains), \
        "no track_role grain reached the writer — the cell leans did nothing at all"


def test_the_no_injection_assertion_bites_on_a_unit_bearing_payload():
    """The deliberate-violation arm: a payload that DOES carry the GRID unit grain
    (``unit_bias``) makes unit ids reach the writer's carrier, and the SAME assertion
    FAILS. Without this, WS-8 could be passing vacuously."""
    d = _d()
    with pytest.raises(AssertionError):
        _assert_no_unit_id_reaches_the_writer(d["violation"])
    assert any(g and "unit" in g for g in d["violation"]["grains"]), (
        "the violation arm did not actually deliver a unit grain to the writer — the "
        "WS-8 detector would have no teeth")
