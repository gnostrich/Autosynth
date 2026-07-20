"""PREREG-field-bias-REV3 Phase B — the PER-UNIT nowplaying glow (CI teeth).

Operator principle: every square (track AND unit) glows by its OWN live settled
telemetry. Track squares already diverge (per-track ``nowplaying_activity``); unit
squares must too. ``engine_bridge.nowplaying_unit_activity`` is the per-UNIT counterpart
of the engine's per-track ``nowplaying_activity``: a READ-ONLY reduction of a produced
bar's provenance rows by ``src_unit`` (sum mass per uid, normalize by the bar's peak unit
mass to 0..1). It reads placed rows only — no settlement / writer / render — so audio is
byte-identical whether or not it runs.

Teeth:
  POPULATED  the per-unit map is built from rows by uid.
  DISTINCT   units with different placed mass get DIFFERENT glow values (they diverge —
             the whole point; a unit no longer borrows its track's glow).
  ABSENT     a unit not placed this bar is ABSENT (⇒ the field reads it as 0 = dark).
  NORMALIZED the peak-mass unit reads 1.0; all values are in [0, 1] (same scale as the
             per-track glow).
"""
from __future__ import annotations

from cloud.companion.engine_bridge import nowplaying_unit_activity


# rows: (out_slot, src_track, src_unit, section, mass). Two tracks; within track 0 the
# two units carry DIFFERENT mass (they must not collapse to one shared value).
_ROWS = [
    (0, 0, 10, 0, 4.0),      # track 0, unit 10  (peak)
    (1, 0, 11, 0, 1.0),      # track 0, unit 11  (same track, smaller mass -> diverges)
    (2, 0, 10, 0, 0.0),      # unit 10 again, another slot (mass accumulates)
    (3, 1, 20, 0, 2.0),      # track 1, unit 20
]


def test_per_unit_nowplaying_is_populated_distinct_and_normalized():
    m = nowplaying_unit_activity(_ROWS)
    # POPULATED: keyed by unit_id, one entry per placed unit
    assert set(m) == {10, 11, 20}, f"per-unit map must key by placed uid, got {set(m)}"
    # NORMALIZED: peak-mass unit (10, mass 4.0) reads 1.0; all in [0,1]
    assert m[10] == 1.0, f"peak-mass unit must normalize to 1.0, got {m[10]}"
    assert all(0.0 <= v <= 1.0 for v in m.values()), "all glow values must be in [0,1]"
    # DISTINCT: units within the SAME track diverge (10 != 11), so a unit square does NOT
    # borrow its track's shared glow.
    assert m[11] == 0.25 and m[10] != m[11], \
        "units in one track must get DISTINCT own-glow values (10=1.0 vs 11=0.25)"
    assert m[20] == 0.5


def test_absent_unit_reads_dark():
    m = nowplaying_unit_activity(_ROWS)
    # a unit that was never placed this bar is ABSENT -> the field falls back to 0 (dark)
    assert 99 not in m, "an unplaced unit must be absent from the per-unit map"
    assert m.get(99, 0.0) == 0.0


def test_empty_bar_is_empty_map():
    assert nowplaying_unit_activity([]) == {}


# --- per-(track, role) glow (track_role_activity) --------------------------------
import numpy as _np
from cloud.companion.engine_bridge import track_role_activity


def test_track_role_activity_reconstructs_slot_role_and_conserves_mass():
    """The role-cell glow reduces a bar by (track_id, slot-role k). For slot s, band b:
    k = argmax(O[:,s]*B[:,b]) and the placed row carries mass sqrt((O[:,s]@B)[b]) — the
    SAME k the (track,role) bias keys on. One slot, two bands, two tracks."""
    B = _np.array([[1.0, 0.2], [0.1, 1.0]])          # M=2 anchors, n_bands=2
    O = _np.array([[1.0], [1.0]])                    # one slot, col=[1,1]
    e = O[:, 0] @ B                                  # [1.1, 1.2]
    m0, m1 = float(_np.sqrt(e[0])), float(_np.sqrt(e[1]))
    # band 0: k=argmax([1.0,0.1])=0 (track 3);  band 1: k=argmax([0.2,1.0])=1 (track 7)
    rows = [(0, 3, 100, 0, m0), (0, 7, 200, 0, m1)]
    act = track_role_activity(rows, O, B, s_phase=1)
    assert act == {(3, 0): m0, (7, 1): m1}, f"slot-role reconstruction wrong: {act}"
    # MASS CONSERVED: every placed row's mass is credited to exactly one (track, role)
    assert abs(sum(act.values()) - (m0 + m1)) < 1e-9


def test_track_role_activity_empty_and_distinct():
    assert track_role_activity([], _np.zeros((2, 2)), _np.ones((2, 2)), 1) == {}
    # two rows, same track, DIFFERENT slot-role -> two distinct cells (the point:
    # a track's roles diverge, they don't share one glow)
    B = _np.array([[1.0, 0.1], [0.1, 1.0]])
    O = _np.array([[1.0], [1.0]])
    e = O[:, 0] @ B
    m0, m1 = float(_np.sqrt(e[0])), float(_np.sqrt(e[1]))
    rows = [(0, 5, 1, 0, m0), (0, 5, 2, 0, m1)]      # same track 5, bands 0 and 1
    act = track_role_activity(rows, O, B, s_phase=1)
    assert set(act) == {(5, 0), (5, 1)}, f"one track's roles must be distinct cells: {act}"
