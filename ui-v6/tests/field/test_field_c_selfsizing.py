"""FIELD-C — drill depth is SELF-SIZING by the SAME noise-floor criterion that
set the anchor count M: the participation-ratio effective mode count
(sum w)^2 / sum w^2, expandable iff round(PR) >= 2. Atomic squares render
non-expandable (no affordance); no drill resolves into noise.

The field's local restatement is PINNED BY VALUE to the engine's
`ets.functional.anchors.effective_rank` (the test may import the trained
object; the instrument module may not — that separation is exactly the point).
"""
from __future__ import annotations

import numpy as np
import pytest

from tests.field.conftest import fed_model


def test_criterion_pinned_to_anchors_effective_rank():
    from ets.functional.anchors import effective_rank
    from ets.instrument.field import participation_ratio
    rng = np.random.default_rng(0)
    for _ in range(20):
        w = rng.random(rng.integers(1, 9)) * rng.integers(1, 5)
        # effective_rank of a diagonal operator IS the participation ratio of
        # its (non-negative) spectrum — the identical formula.
        assert participation_ratio(w) == pytest.approx(
            effective_rank(np.diag(w)), rel=1e-9)


def test_floor_semantics():
    from ets.instrument.field import clears_noise_floor, participation_ratio
    assert participation_ratio([]) == 0.0
    assert participation_ratio([0.0, 0.0]) == 0.0
    assert not clears_noise_floor([])                  # nothing inside
    assert not clears_noise_floor([1.0])               # one mode: atomic
    assert not clears_noise_floor([1.0, 0.01, 0.01])   # one DOMINANT mode:
    #   sub-structure below the floor is truncated -> atomic (drilling would
    #   resolve into noise)
    assert clears_noise_floor([1.0, 1.0])              # two real modes
    assert clears_noise_floor([0.5, 0.4, 0.3])


def test_squares_expandability_follows_the_floor():
    m = fed_model()
    tracks = {s.key: s for s in m.track_squares()}
    # track 0 profile [0.7,0.2,0.1]: PR≈1.85 -> round 2 -> expandable, 2 kids
    assert tracks[("track", 0)].expandable
    assert tracks[("track", 0)].n_children == 2
    # role 0 pool loads [0.6, 0.5] at role 0 -> two effective units -> expands
    assert m.role_square(0).expandable
    # role 1 has NO emitted pool -> atomic (absence is honest)
    assert not m.role_square(1).expandable
    assert m.role_square(1).n_children == 0
    # units are leaves: no sub-unit telemetry exists -> always atomic
    for sq in m.unit_squares(0):
        assert not sq.expandable and sq.n_children == 0


def test_dominated_substructure_is_atomic():
    """A role whose pool is one dominant unit (PR < 1.5) refuses to expand —
    'nothing distinct inside' renders no fake affordance."""
    from ets.instrument.field import FieldModel
    m = FieldModel()
    w = m.telemetry_writer()
    w.apply_roleactivity([0.5])
    w.apply_unitpool(0, [
        {"unit_id": 1, "track_id": 0, "band": 0, "profile": [1.0]},
        {"unit_id": 2, "track_id": 0, "band": 1, "profile": [0.02]},
    ])
    assert not m.role_square(0).expandable


def test_view_refuses_to_drill_into_atomic_squares(qapp):
    from ets.instrument.field import FieldView
    m = fed_model()
    v = FieldView(m)
    v.resize(400, 300)
    # a track square that is atomic: give track 9 a concentrated profile.
    m.telemetry_writer().apply_profiles({9: [1.0, 0.0, 0.0]})
    assert v.zoom_into(("track", 9)) is False          # refused: atomic
    assert v.zoom_path == []
    assert v.zoom_into(("track", 0)) is True           # real sub-structure
    assert v.zoom_path == [("track", 0)]
    # drill on into role 0 (expandable), then a unit (leaf: refused).
    assert v.zoom_into(("role", 0)) is True
    assert v.zoom_into(("unit", 0, 0, 0)) is False
    assert v.zoom_out() and v.zoom_out() and not v.zoom_out()


def test_depth_varies_per_square_and_is_honest_information():
    """Two sibling squares, different depths: that variation is the honest
    display of where real structure ends."""
    m = fed_model()
    sq = {s.key: s for s in m.role_squares_flat()}
    assert sq[("role", 0)].expandable          # has a distinct pool
    assert not sq[("role", 2)].expandable      # no pool emitted -> leaf
