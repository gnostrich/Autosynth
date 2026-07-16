"""The §8 exhaustiveness law: EXACTLY six CV lanes, no seventh.

Five direction-lanes (u = region, density, continuity, gauge, novelty) + one
sharpness-lane (T_s). Adding a seventh control is a spec violation. These tests
drive the law both on the pure lane model and on the built PySide6 panel, and
prove the guard BITES on a seventh.
"""
import os

import pytest

from ets.panel.lanes import (
    LANES, LANE_IDS, DIRECTION_IDS, SHARPNESS_ID, LaneKind,
    assert_lanes_exhaustive,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_exactly_six_lanes():
    assert len(LANES) == 6
    assert len(LANE_IDS) == 6
    assert set(LANE_IDS) == {
        "region", "density", "continuity", "gauge", "novelty", "temperature"}


def test_five_direction_one_sharpness():
    dirs = [s for s in LANES if s.kind is LaneKind.DIRECTION]
    sharp = [s for s in LANES if s.kind is LaneKind.SHARPNESS]
    assert len(dirs) == 5 and len(sharp) == 1
    assert set(DIRECTION_IDS) == {
        "region", "density", "continuity", "gauge", "novelty"}
    assert SHARPNESS_ID == "temperature"
    # only the sharpness lane (T_s) carries no φ; every direction lane scales one.
    assert sharp[0].phi is None
    assert all(d.phi is not None for d in dirs)
    # region is the only vector lane (a lean per discovered anchor).
    assert [s.id for s in LANES if s.is_vector] == ["region"]


def test_exhaustive_guard_accepts_the_six():
    assert_lanes_exhaustive(LANE_IDS)


def test_exhaustive_guard_bites_on_a_seventh():
    seventh = list(LANE_IDS) + ["swing"]   # a plausible-looking new control
    with pytest.raises(AssertionError):
        assert_lanes_exhaustive(seventh)


def test_exhaustive_guard_bites_on_a_missing_lane():
    with pytest.raises(AssertionError):
        assert_lanes_exhaustive(LANE_IDS[:-1])


def test_exhaustive_guard_bites_on_a_rename():
    renamed = list(LANE_IDS[:-1]) + ["temperatur"]   # typo'd id
    with pytest.raises(AssertionError):
        assert_lanes_exhaustive(renamed)


def test_panel_builds_exactly_six_lane_controls():
    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import Panel

    app = QApplication.instance() or QApplication([])
    panel = Panel(n_anchors=3)
    # the panel's own construction asserted exhaustiveness; confirm the built set.
    assert set(panel.lane_control_ids) == set(LANE_IDS)
    assert len(panel.lane_control_ids) == 6


def test_panel_routes_its_built_controls_through_the_biting_guard(monkeypatch):
    """Proves a seventh control WOULD fail construction: the panel feeds its
    actual built-control ids through `assert_lanes_exhaustive` (spied here), and
    that guard is independently shown to bite on a seventh (test above). So had
    the build produced seven ids, construction would have raised."""
    from PySide6.QtWidgets import QApplication
    import ets.panel.widget as W

    app = QApplication.instance() or QApplication([])

    seen = {}
    orig = W.assert_lanes_exhaustive          # capture BEFORE patching

    def spy(ids):
        seen["ids"] = list(ids)
        return orig(ids)                       # keep the real (biting) behaviour

    monkeypatch.setattr(W, "assert_lanes_exhaustive", spy)
    W.Panel(n_anchors=2)
    assert set(seen["ids"]) == set(LANE_IDS), \
        "panel did not validate its built control set against the six"
    assert len(seen["ids"]) == 6
