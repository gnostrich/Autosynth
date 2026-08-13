"""LIVE mode — carrier math + honest-refusal contract (Train B2).

Pure-Python tests of ``cloud.companion.live`` (no world, no engine): the
slice-resolution math B-1/B-1-amended describe, the writer-capability
introspection (§2 of the prereg — the ONE thing that's locked is the
carrier's constructor + TYPE NAME, not the keyword ``write_bar`` binds it
to), and the "measured, not asserted" reduction.

IMPORTANT (test-isolation wall, found and resolved here): ``build_full_fence``
does ``from ets.writer.clamp import clamp0``, and — even when that specific
submodule doesn't exist — Python's import machinery still has to import the
PARENT packages first (``ets``, ``ets.writer``), and root ``ets.writer``'s own
``__init__.py`` eagerly imports its whole submodule tree (stream/tape/settle/
tilt/phi/realize) plus ``ets.render`` plus ``librosa``. Doing that ONCE in
THIS shared pytest process would permanently pollute ``sys.modules`` for every
test that runs afterward in the same session — including
``test_mvp_d_no_decoder.py`` / ``test_role_grain_arming.py``, which assert
that importing the CLOUD SERVICE surface never drags in a decoder (a real,
load-bearing MVP-D invariant, unrelated to LIVE). So any test that actually
calls ``build_full_fence`` — or imports ``ets.writer.stream`` directly to
introspect the real ``write_bar`` — belongs in the OUT-OF-PROCESS harness
(``test_live_engine_integration.py``, one subprocess per probe, thrown away
when it exits) and NOT here. This file stays to the PURE functions that never
touch ``ets`` at all, plus the writer-introspection functions exercised only
against FAKE ``write_bar`` stubs.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "companion"))

from live import (  # noqa: E402
    LiveCarrierUnavailable, clamp_call_kwargs, clamp_kwarg_name,
    current_placement, pin_unit_ids, resolve_start_index, uid_index_map,
)

# a track's own time-ordered slice rows: [t0_s, t1_s, unit_id, mass, q]
_SLICES = [
    [0.0, 0.5, 10, 1.0, [1.0, 0.0]],
    [0.5, 1.0, 11, 1.0, [1.0, 0.0]],
    [1.0, 1.5, 12, 1.0, [0.0, 1.0]],
    [1.5, 2.0, 13, 1.0, [0.0, 1.0]],
]


# --- resolve_start_index -----------------------------------------------

def test_resolve_start_index_lands_inside_a_span():
    assert resolve_start_index(_SLICES, 0.2) == 0
    assert resolve_start_index(_SLICES, 0.5) == 1     # half-open: [0.5,1.0) -> idx 1
    assert resolve_start_index(_SLICES, 1.9) == 3


def test_resolve_start_index_clamps_before_and_after():
    assert resolve_start_index(_SLICES, -5.0) == 0     # before the track: first slice
    assert resolve_start_index(_SLICES, 999.0) == 3    # past the end: last slice


def test_resolve_start_index_refuses_an_empty_track():
    try:
        resolve_start_index([], 0.0)
        assert False, "must raise on an empty slice list"
    except LiveCarrierUnavailable:
        pass


# --- pin_unit_ids / uid_index_map ---------------------------------------

def test_pin_unit_ids_is_consecutive_from_the_click_onward():
    assert pin_unit_ids(_SLICES, 0) == (10, 11, 12, 13)
    assert pin_unit_ids(_SLICES, 2) == (12, 13)
    assert pin_unit_ids(_SLICES, 3) == (13,)


def test_uid_index_map_round_trips_the_time_order():
    m = uid_index_map(_SLICES)
    assert m == {10: 0, 11: 1, 12: 2, 13: 3}


# --- current_placement (the "measured, not asserted" reduction) ---------

def test_current_placement_picks_the_highest_mass_row_for_the_fenced_track():
    rows = [(0, 5, 99, 0, 0.1), (1, 0, 11, 0, 0.9), (2, 0, 10, 0, 0.2)]
    uid_index = {10: 0, 11: 1}
    assert current_placement(rows, 0, uid_index) == (11, 1)


def test_current_placement_none_when_the_fenced_track_placed_nothing():
    rows = [(0, 5, 99, 0, 0.1)]
    assert current_placement(rows, 0, {}) is None


def test_current_placement_unit_index_absent_reports_none_not_a_fabrication():
    rows = [(0, 0, 77, 0, 0.5)]                   # 77 is not in uid_index
    uid, idx = current_placement(rows, 0, {})
    assert uid == 77 and idx is None


# --- write_bar keyword introspection (§2: the locked TYPE NAME, not a guess)
# NOTE: ``build_full_fence`` itself (the real ``from ets.writer.clamp import
# clamp0`` path, honest-refusal-today included) and any check against the
# REAL ``StreamWriter.write_bar`` are exercised in
# ``test_live_engine_integration.py`` (out-of-process — see this file's
# module docstring for why that isolation is load-bearing here).

def test_clamp_kwarg_name_finds_a_clampterms_annotated_parameter():
    def fake_write_bar(tilt=None, clamps=None, clamp: "Optional[ClampTerms]" = None):
        pass
    assert clamp_kwarg_name(fake_write_bar) == "clamp"


def test_clamp_kwarg_name_ignores_the_pre_existing_i7_clamps_parameter():
    def fake_write_bar(tilt=None, clamps: "Optional[ClampSet]" = None):
        pass
    assert clamp_kwarg_name(fake_write_bar) is None


def test_clamp_call_kwargs_empty_when_no_fence_never_introspects():
    """None (GRID/TRACKS, or LIVE untouched) must short-circuit to {} WITHOUT
    ever calling clamp_kwarg_name — so an unfenced call stays exactly
    write_bar(tilt=tilt), byte-identical, even if write_bar's signature can't
    be introspected at all (e.g. a C-extension stub)."""
    def unintrospectable(*a, **k):
        pass
    unintrospectable.__signature__ = None  # would blow up inspect.signature
    # Passing a plain object (not callable/introspectable) proves clamp_terms
    # being None short-circuits before any signature work is attempted.
    assert clamp_call_kwargs(object(), None) == {}


def test_clamp_call_kwargs_refuses_honestly_when_unwired():
    def fake_write_bar(tilt=None, clamps=None):
        pass
    try:
        clamp_call_kwargs(fake_write_bar, ("FAKE_CLAMP",))
        assert False, "must refuse when write_bar has no ClampTerms parameter"
    except LiveCarrierUnavailable:
        pass


def test_clamp_call_kwargs_routes_to_the_discovered_kwarg():
    def fake_write_bar(tilt=None, clamps=None, clamp: "Optional[ClampTerms]" = None):
        pass
    assert clamp_call_kwargs(fake_write_bar, ("FAKE_CLAMP",)) == {"clamp": ("FAKE_CLAMP",)}
