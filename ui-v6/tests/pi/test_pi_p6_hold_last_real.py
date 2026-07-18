"""P6 — the connected instrument's GUI tick shows the LATEST engine read, held
(sample-and-hold), never faded (ui-v6, `ets.instrument.live.LiveInstrument`).

papers/paper1 §3 C': "any UI easing/damping is a falsification of the
display." Before this fix, `_on_tick` multiplied `FieldModel`/`PadModel`
settled state by a 0.90 factor every GUI tick — including the same tick a
fresh frame was just written — so displayed brightness was never quite the
engine's actual answer. This pins the honest replacement:

  1. two telemetry frames fed across two ticks: the displayed value after
     tick 2 is frame 2's value EXACTLY, not a blend with frame 1;
  2. a tick with NO new telemetry (simulating telemetry arriving slower than
     the GUI's 33ms cadence) leaves the display EXACTLY at the last real
     frame — sample-and-hold, not a fade toward zero;
  3. this holds for both the field (`field_model`, role/track squares) and
     the library dots (`pad_model`, the sibling that was the same violation);
  4. no decay/lerp/ease token remains in `_on_tick`'s source.
"""
from __future__ import annotations

import inspect

import pytest

from tests.pi.conftest import RecordingEmitter

K = 2


@pytest.fixture
def live(qapp):
    live_mod = pytest.importorskip("ets.instrument.live")
    inst = live_mod.LiveInstrument(engine_host="127.0.0.1", engine_port=9000,
                                   meters_port=0, n_anchors=K)
    inst.panel.emitter = RecordingEmitter()
    inst.panel.set_anchor_count(K)
    yield inst
    inst.receiver.stop()


def _role_settled(inst):
    return [s.settled for s in inst.field_model.role_squares_flat()]


def test_tick_shows_latest_frame_exactly_no_blend(live):
    inst = live

    inst._feed_roleactivity([0.2, 0.8])
    inst._feed_nowplaying({0: 0.1, 1: 0.9})
    inst._on_tick()
    assert _role_settled(inst) == pytest.approx([0.2, 0.8])
    assert inst.pad_model.activity[0] == pytest.approx(0.1)
    assert inst.pad_model.activity[1] == pytest.approx(0.9)

    # a second frame, far from the first: an exact-replace lands exactly on
    # the new values; a blend/decay would land strictly between old and new.
    inst._feed_roleactivity([0.95, 0.03])
    inst._feed_nowplaying({0: 0.97, 1: 0.01})
    inst._on_tick()
    assert _role_settled(inst) == pytest.approx([0.95, 0.03]), \
        "field brightness is not the latest telemetry frame exactly"
    assert inst.pad_model.activity[0] == pytest.approx(0.97)
    assert inst.pad_model.activity[1] == pytest.approx(0.01)


def test_tick_with_no_new_telemetry_holds_last_real_value(live):
    """Telemetry arriving slower than the GUI tick must not stale/fade the
    display: a tick that drains nothing leaves every settled value EXACTLY
    where the last real frame put it."""
    inst = live
    inst._feed_roleactivity([0.4, 0.6])
    inst._feed_nowplaying({0: 0.5, 1: 0.5})
    inst._on_tick()
    before_roles = _role_settled(inst)
    before_pads = dict(inst.pad_model.activity)

    # several ticks with NO fresh telemetry queued (the slow-frame case).
    for _ in range(10):
        inst._on_tick()
        assert _role_settled(inst) == pytest.approx(before_roles), \
            "field brightness drifted with no new telemetry (a fade, not a hold)"
        assert dict(inst.pad_model.activity) == pytest.approx(before_pads), \
            "library dot brightness drifted with no new telemetry (a fade, not a hold)"


def test_on_tick_source_has_no_decay_lerp_ease_token(live):
    src = inspect.getsource(type(live)._on_tick)
    for token in ("decay(", "lerp(", "ease("):
        assert token not in src, \
            f"_on_tick still contains a fade/decay token: {token!r}"
