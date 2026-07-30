"""WS-1 (backend half) — MAPPING HONESTY of /api/wavemap's q, spans and masses.

The directive (PREREG-waveform-scrub, W-2 + check WS-1): the weights the scrub emits
must be the trained world's STORED assignment for the pointed units — "invented/
smoothed weights FAIL". The backend half of that gate is that the served ``slices``
are an EXACT copy of stored objects:

  q      == the indicator of ``world.index.unit_role[(track_id, unit_id)]``
            (the finest STORED per-unit role assignment; see the q WALL note in
            cloud/companion/engine_bridge.py for the full survey of what the frozen
            world does and does not store, and why ``fstate.pis`` cannot be used
            without inventing an unstored unit->prototype link)
  t0, t1 == ``provenance_index["src_start"/"src_end"] / track.sr`` exactly
  m      == ``track.masses[row]`` exactly
  uid    == ``provenance_index["unit_id"]`` exactly

TEETH: the comparison lives in ONE function, ``_assert_slices_are_stored``, and the
gate runs it three times — once on the SERVED payload (must pass) and twice on
DELIBERATELY VIOLATED payloads (must FAIL):

  * SMOOTHED   q <- (1-eps)*q + eps/M  (the "make it look soft" temptation);
  * BAND-PROFILE q <- normalized ``fstate.B[:, band]`` (the plausible-but-wrong
    source: a real stored matrix, but not the world's per-unit role ASSIGNMENT —
    it cannot distinguish two units of the same band that the world assigned to
    different roles).

If either violated payload passed, the gate would be decoration.
"""
from __future__ import annotations

import copy

import pytest

from cloud.tests.test_wavemap_fixture import probe

_PROBE = r'''
import numpy as np
from ets.engine.worldfile import load_world
from cloud.companion.engine_bridge import StreamPlayer

wf = load_world(WORLD)
w = wf.world
M = int(w.M)

# The STORED objects, read straight off the frozen world (the gate's ground truth).
stored = {}
for tr in w.tracks:
    tid = int(tr.track_id)
    prov = tr.provenance_index
    B = np.asarray(w.fstate.B, float)
    rows = {}
    for j in range(len(prov)):
        uid = int(prov["unit_id"][j])
        k = w.index.unit_role[(tid, uid)]
        q = [0.0] * M
        q[int(k)] = 1.0
        band = int(prov["band"][j])
        col = B[:, band]
        s = float(col.sum())
        rows[str(uid)] = {
            "q": q,
            "t0": float(prov["src_start"][j]) / float(tr.sr),
            "t1": float(prov["src_end"][j]) / float(tr.sr),
            "m": float(tr.masses[j]),
            "band_q": [float(x) / s for x in col] if s > 0 else [0.0] * M,
        }
    stored[str(tid)] = rows

p = StreamPlayer(WORLD, seed=0, is_trained=True)
wm = p.wavemap()
emit({"wavemap": wm, "stored": stored, "M": M})
'''


def _payload():
    if not hasattr(_payload, "_d"):
        _payload._d = probe(_PROBE)
    return _payload._d


def _assert_slices_are_stored(tracks, stored, M):
    """THE gate assertion. Run on the served payload (must pass) and on deliberately
    violated payloads (must fail) — same code, no special cases."""
    assert tracks, "no tracks served"
    for tid, tr in tracks.items():
        rows = stored[tid]
        assert len(tr["slices"]) == len(rows), (
            f"track {tid}: served {len(tr['slices'])} slices for {len(rows)} stored units")
        for (t0, t1, uid, m, q) in tr["slices"]:
            exp = rows[str(uid)]
            assert q == exp["q"], (
                f"track {tid} unit {uid}: served q {q} != STORED assignment "
                f"{exp['q']} (invented/smoothed weights are forbidden)")
            assert t0 == exp["t0"] and t1 == exp["t1"], (
                f"track {tid} unit {uid}: served span ({t0}, {t1}) != stored span "
                f"({exp['t0']}, {exp['t1']})")
            assert m == exp["m"], (
                f"track {tid} unit {uid}: served mass {m} != stored mass {exp['m']}")
            assert len(q) == M and abs(sum(q) - 1.0) < 1e-12, \
                f"track {tid} unit {uid}: q must be an M-vector normalized to 1: {q}"


def _smoothed(tracks, M, eps=0.05):
    out = copy.deepcopy(tracks)
    for tr in out.values():
        for s in tr["slices"]:
            s[4] = [(1.0 - eps) * v + eps / M for v in s[4]]
    return out


def _band_profiled(tracks, stored):
    out = copy.deepcopy(tracks)
    for tid, tr in out.items():
        for s in tr["slices"]:
            s[4] = list(stored[tid][str(s[2])]["band_q"])
    return out


def test_served_q_spans_and_masses_are_the_stored_values_exactly():
    d = _payload()
    assert d["wavemap"]["ok"] is True, d["wavemap"]
    _assert_slices_are_stored(d["wavemap"]["tracks"], d["stored"], d["M"])


def test_smoothed_q_fails_the_same_assertion():
    """The deliberate-violation arm: a payload whose q has been smoothed toward
    uniform must FAIL the gate. If this passed, WS-1 would be decoration."""
    d = _payload()
    bad = _smoothed(d["wavemap"]["tracks"], d["M"])
    with pytest.raises(AssertionError):
        _assert_slices_are_stored(bad, d["stored"], d["M"])


def test_band_profile_q_fails_the_same_assertion():
    """The other deliberate violation: q taken from the anchor band-profile column
    ``B[:, band]`` — a real stored matrix, but NOT the per-unit role assignment. It
    gives every unit of a band the same weights, so it cannot reproduce the world's
    own per-unit assignment and must FAIL."""
    d = _payload()
    bad = _band_profiled(d["wavemap"]["tracks"], d["stored"])
    with pytest.raises(AssertionError):
        _assert_slices_are_stored(bad, d["stored"], d["M"])


def test_slices_are_in_time_order_and_inside_the_track():
    """The spans are the world's OWN segmentation: ordered, non-empty, and inside
    the stored duration (the axis the envelope is drawn on)."""
    d = _payload()
    for tid, tr in d["wavemap"]["tracks"].items():
        last = -1.0
        for (t0, t1, uid, m, q) in tr["slices"]:
            assert t1 > t0, f"track {tid} unit {uid}: empty/negative span"
            assert t0 >= last - 1e-12, f"track {tid}: slices out of time order"
            assert t1 <= tr["duration_s"] + 1e-9, \
                f"track {tid} unit {uid}: span past the stored duration"
            last = t0


def test_envelope_is_a_real_nonconstant_peak_envelope():
    """The lane is the GIVEN material, decoded: ~800 buckets in [0,1] that actually
    vary (a fabricated/blank envelope would be constant)."""
    d = _payload()
    for tid, tr in d["wavemap"]["tracks"].items():
        pk = tr["peaks"]
        assert len(pk) == 800, f"track {tid}: {len(pk)} peak buckets (expected 800)"
        assert all(0.0 <= v <= 1.0 for v in pk), f"track {tid}: peak outside [0,1]"
        assert max(pk) > 0.0, f"track {tid}: silent envelope — no material decoded"
        assert len(set(round(v, 6) for v in pk)) > 8, \
            f"track {tid}: envelope is (near-)constant — not a real waveform"
