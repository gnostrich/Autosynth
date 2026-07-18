"""P6 — no UI-side inter-frame brightness decay (FieldModel).

papers/paper1 §3 C': "any UI easing/damping is a falsification of the
display." `FieldModel`'s settled stores (roleactivity, nowplaying) must equal
the LATEST ingested telemetry frame exactly — never a blend, never a fade
toward some other value between frames. Three teeth:

  1. the `decay` method is GONE (not merely unused — the load-bearing fade
     path cannot be reintroduced/rewired by mistake);
  2. two frames fed in sequence: the displayed value is the SECOND frame's
     value exactly, not a blend with the first;
  3. hold-last-real: a square not refreshed by a given telemetry batch keeps
     its previous REAL value unchanged (no implicit fade of the stale field)
     until the next real write.
"""
from __future__ import annotations

import inspect

import pytest

from ets.instrument.field import FieldModel


def test_field_model_has_no_decay_method():
    """The fade path is REMOVED, not just unused, so it cannot be silently
    reintroduced/rewired into the live tick."""
    m = FieldModel()
    assert not hasattr(m, "decay"), \
        "FieldModel.decay still exists — the P6 fade path was not removed"


def test_second_frame_replaces_first_exactly_no_blend():
    m = FieldModel()
    w = m.telemetry_writer()

    w.apply_roleactivity([0.2, 0.8])
    w.apply_nowplaying({0: 0.1, 1: 0.9})
    first_roles = [s.settled for s in m.role_squares_flat()]
    assert first_roles == pytest.approx([0.2, 0.8])

    # a second, unrelated frame — NOT a small increment (a blend would land
    # strictly between 0.2->0.9 and 0.8->0.05; an exact-replace lands exactly
    # on the new values).
    w.apply_roleactivity([0.9, 0.05])
    w.apply_nowplaying({0: 0.95, 1: 0.02})
    second_roles = [s.settled for s in m.role_squares_flat()]
    assert second_roles == pytest.approx([0.9, 0.05]), \
        "role brightness is not the latest telemetry frame exactly (blend?)"

    tracks = {sq.track: sq.settled for sq in m.track_squares()}
    assert tracks[0] == pytest.approx(0.95)
    assert tracks[1] == pytest.approx(0.02)


def test_untouched_square_holds_last_real_value_not_faded():
    """Feeding roleactivity again must not perturb nowplaying (and vice
    versa): each settled store holds its own last REAL write, full stop —
    no cross-kind fade, no implicit decay of the untouched half of state."""
    m = FieldModel()
    w = m.telemetry_writer()
    w.apply_nowplaying({3: 0.77})

    # unrelated telemetry arrives; nowplaying for track 3 must be UNCHANGED —
    # exactly the last real value, not decayed toward 0.
    w.apply_roleactivity([0.1, 0.2, 0.3])
    tracks = {sq.track: sq.settled for sq in m.track_squares()}
    assert tracks[3] == pytest.approx(0.77), \
        "nowplaying value drifted from its last real write with no new data"

    # repeat several more unrelated ingests: still exactly the same, forever
    # (no decay constant is being silently applied per call).
    for _ in range(20):
        w.apply_unitpool(0, [])
    tracks = {sq.track: sq.settled for sq in m.track_squares()}
    assert tracks[3] == pytest.approx(0.77)


def test_no_decay_lerp_ease_constant_in_field_module_source():
    """Static sweep of the module text: no residual fade constant/method name
    in the brightness path."""
    import ets.instrument.field as field_mod
    src = inspect.getsource(field_mod)
    for token in ("decay(", "def decay", "lerp(", "ease("):
        assert token not in src, \
            f"field.py still contains a fade/decay token: {token!r}"
