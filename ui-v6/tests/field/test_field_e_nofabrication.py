"""FIELD-E — no fabrication: every glowing square is backed by a real
unit/role/track present in the engine's telemetry, with real settled weight.
Real-or-absent; no synthetic squares, no decorative glow.
"""
from __future__ import annotations

from tests.field.conftest import fed_model


def test_empty_telemetry_means_empty_field():
    from ets.instrument.field import FieldModel
    m = FieldModel()
    assert m.track_squares() == []
    assert m.role_squares_flat() == []
    assert m.unit_squares(0) == []


def test_every_square_traces_to_an_ingested_telemetry_record():
    m = fed_model()
    # tracks: exactly the ids the engine named (profiles/nowplaying), no more.
    assert [s.key for s in m.track_squares()] == [("track", 0), ("track", 7)]
    # roles: exactly the K the roleactivity frame carried.
    assert [s.key for s in m.role_squares_flat()] == [
        ("role", 0), ("role", 1), ("role", 2)]
    # units: exactly the pool the engine emitted for role 0, and none for a
    # role the engine sent no pool for.
    assert [s.key for s in m.unit_squares(0)] == [
        ("unit", 0, 0, 0), ("unit", 0, 5, 7)]
    assert m.unit_squares(1) == []
    assert m.unit_squares(99) == []


def test_brightness_is_the_ingested_settled_value_never_decorative():
    m = fed_model()
    assert [s.settled for s in m.role_squares_flat()] == [0.9, 0.2, 0.5]
    by_key = {s.key: s.settled for s in m.track_squares()}
    assert by_key[("track", 0)] == 0.8
    assert by_key[("track", 7)] == 0.3
    # unit fill = its SOURCE TRACK's settled activity (the disclosed
    # track-grain wall) — a real telemetry value, not an invented per-unit one.
    assert [s.settled for s in m.unit_squares(0)] == [0.8, 0.3]


def test_no_glow_without_a_positive_settled_value():
    from ets.instrument.field import FieldModel
    m = FieldModel()
    w = m.telemetry_writer()
    w.apply_profiles({3: [0.5, 0.5]})       # named, but no activity yet
    (sq,) = m.track_squares()
    assert sq.key == ("track", 3) and sq.settled == 0.0   # present, dark


def test_ids_are_never_invented_for_unknown_children():
    """A drill on a square whose children the engine never emitted yields
    NOTHING (absent), not placeholders."""
    m = fed_model()
    # track 7's profile clears the floor, but its role children are the GLOBAL
    # role squares (engine-backed); a role with no emitted pool has no units.
    for sq in m.roles_of_track(7):
        assert sq.key in {("role", r) for r in range(3)}
    assert m.children(("role", 2)) == []
    assert m.children(("unit", 0, 0, 0)) == []      # units are leaves
