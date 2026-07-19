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
