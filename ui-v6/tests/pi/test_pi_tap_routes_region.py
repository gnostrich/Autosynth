"""PI bias-routing bite (ui-v6 FIELD edition; supersedes the pad-tap routing).

ROLE squares of the field are 1:1 with the region-tilt lane. Biasing role
square i must reach the engine ONLY as a region lean on anchor i, through the
panel's EXISTING emitter path:

    FieldView.wheelEvent -> FieldModel.add_bias(("role", i), ...)
        -> bias_changed -> panel.set_region_vector(model.region_vector())
        -> panel._push() -> emitter.emit(u)      (/ets/lanes, the one wire)

We install a recording emitter on the panel (the sanctioned wire), drive the
gesture, and assert (a) the region lean landed on anchor i and nowhere else,
and (b) NO other outbound channel fired — proving there is no second decision
channel parallel to the region lane.
"""
from __future__ import annotations

import numpy as np
import pytest

K = 4          # anchors / role squares
BIASED = 2     # the role we bias


@pytest.fixture
def wired(qapp, recording_emitter):
    """The real live wiring, headless: panel + field, bias -> region path."""
    widget = pytest.importorskip("ets.panel.widget")
    field_mod = pytest.importorskip("ets.instrument.field")

    panel = widget.Panel(emitter=recording_emitter, n_anchors=K)
    model = field_mod.FieldModel()
    model.telemetry_writer().apply_roleactivity([0.1] * K)
    view = field_mod.FieldView(model)
    view.resize(400, 200)
    view.bias_changed.connect(
        lambda: panel.set_region_vector(model.region_vector(panel.u.n_anchors)))
    return panel, model, view, recording_emitter


def _wheel(view, model, role, notches):
    """Drive the REAL wheel handler over role square `role`."""
    from tests.field.conftest import FakeWheelEvent
    sqs = view.current_squares()
    n = len(sqs)
    rows = max(1, int((n ** 0.5 + 0.999) // 1))
    idx = [s.key for s in sqs].index(("role", role))
    cols = max(1, int(n ** 0.5 + 0.999))
    r, c = divmod(idx, cols)
    w = view.width() / cols
    h = (view.height() - view._HEADER_PX) / max(1, (n + cols - 1) // cols)
    view.wheelEvent(FakeWheelEvent((c + 0.5) * w,
                                   view._HEADER_PX + (r + 0.5) * h,
                                   notches=notches))


def test_role_bias_leans_region_on_that_anchor_only(wired):
    panel, model, view, emitter = wired

    _wheel(view, model, BIASED, +4)               # scroll up over role square 2

    assert emitter.lanes, "bias did not reach the panel's region emitter"
    u_region = emitter.lanes[-1]
    assert u_region.shape[0] == K
    assert u_region[BIASED] > 0.0, "no region lean on the biased anchor"
    others = np.delete(u_region, BIASED)
    assert np.allclose(others, 0.0), \
        f"bias leaked lean onto non-biased anchors: {u_region}"
    assert emitter.tolerances == [], "a bias fired the tolerance channel"
    assert emitter.hellos == [], "a bias fired the hello channel"


def test_each_role_bias_leans_only_its_own_anchor(wired):
    """A role square addresses exactly its own region-lane component (asserted
    on the panel's region TARGET; the wire is its slewed follower)."""
    panel, model, view, emitter = wired
    for i in range(K):
        before = np.asarray(panel.u.u_region, dtype=float).copy()
        n_emits = len(emitter.lanes)
        _wheel(view, model, i, +1)
        after = np.asarray(panel.u.u_region, dtype=float)
        assert len(emitter.lanes) > n_emits, "bias did not reach the wire"
        assert after[i] > before[i], \
            f"bias on anchor {i} did not lean its own target"
        others = [j for j in range(K) if j != i]
        # other targets reflect only THEIR OWN accumulated bias (unchanged by
        # this gesture): the composite preserves locality of one-hot roles.
        assert np.allclose(after[others], before[others]), \
            f"bias on anchor {i} moved another anchor's target: {before} -> {after}"


def test_role_activity_lightup_sets_per_anchor_brightness(qapp):
    """Role light-up: the settled telemetry frame sets per-square brightness,
    clamped to 0..1 (the field-model store, via the capability writer)."""
    field_mod = pytest.importorskip("ets.instrument.field")
    m = field_mod.FieldModel()
    m.telemetry_writer().apply_roleactivity([0.0, 0.5, 5.0, -1.0])
    vals = [s.settled for s in m.role_squares_flat()]
    assert vals[0] == pytest.approx(0.0)
    assert vals[1] == pytest.approx(0.5)
    assert vals[2] == 1.0                        # clamped up
    assert vals[3] == 0.0                        # clamped down
    assert all(0.0 <= v <= 1.0 for v in vals)
