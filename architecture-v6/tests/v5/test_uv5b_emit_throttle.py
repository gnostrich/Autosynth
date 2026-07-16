"""UV5-B — EMIT THROTTLE (ui-v5 BUG-1). A burst of armed mouseMove events must
NOT flood the wire. The armed move updates only the region TARGET; the wire
advances solely on the panel's single timer tick, as a MONOTONE, per-step-bounded
slew ramp — no raw (un-slewed) target is pushed directly on a move, and a drop
settles exactly on the final target.

These bite the old behaviour (one `emitter.emit` per mouseMove): a fast drag of N
moves would have produced ~N wire messages and jumped the wire straight to the
raw target.
"""
from __future__ import annotations

import numpy as np
import pytest

from ets.panel.envelope import SLEW_MAX_STEP
from tests.v5._fakeqt import FakeMouseEvent


class _RecEmitter:
    def __init__(self) -> None:
        self.calls = []

    def emit(self, u) -> None:
        self.calls.append(u.copy())


def _panel(K=4, size=200):
    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import Panel
    QApplication.instance() or QApplication([])
    em = _RecEmitter()
    p = Panel(emitter=em, n_anchors=K)
    p._xy.resize(size, size)
    return p, em


def test_move_burst_does_not_flood_the_wire():
    p, em = _panel(K=4)
    pad = p._xy
    # ARM on anchor 0, then fire a fast burst of armed moves sweeping across the
    # pad toward anchor 2 — WITHOUT any timer tick in between (all "in one tick").
    ax, ay = pad._anchor_xy(0)
    pad.mousePressEvent(FakeMouseEvent(ax, ay))          # arm
    n_after_arm = len(em.calls)
    cx, cy = pad._center()
    bx, by = pad._anchor_xy(2)
    N = 60
    for k in range(1, N + 1):
        t = k / N
        pad.mouseMoveEvent(FakeMouseEvent(cx + (bx - cx) * t, cy + (by - cy) * t))

    # THE THROTTLE: N armed moves produced at most ONE wire update (here zero —
    # gestures only set the target; the timer owns the wire). Old code: one
    # emitter.emit per arm/move => ~N+1 messages.
    assert len(em.calls) - n_after_arm <= 1, (
        f"the move burst flooded the wire: {len(em.calls) - n_after_arm} "
        f"messages for {N} moves")

    # NO raw target pushed directly on a move: the slew has not advanced toward
    # the (now far) target — its current is still the pre-burst value.
    target = p._region_target()
    assert float(np.max(np.abs(target))) > 0.2, "test target too small to bite"
    assert not np.allclose(p._region_slew.current, target, atol=SLEW_MAX_STEP), (
        "the wire jumped straight to the raw target on a move (no slew)")


def test_timer_glides_a_monotone_bounded_ramp_to_the_target():
    p, em = _panel(K=4)
    pad = p._xy
    # arm+park on anchor 1 (a far target from the zeroed slew start).
    ax, ay = pad._anchor_xy(1)
    pad.mousePressEvent(FakeMouseEvent(ax, ay))          # arm
    pad.mousePressEvent(FakeMouseEvent(ax, ay))          # drop (park)
    base = len(em.calls)

    # drive the single timer; collect the emitted region per pushing tick.
    seq = []
    for _ in range(400):
        p.tick_slew()
        if len(em.calls) > base + len(seq):
            seq.append(em.calls[-1].u_region.copy())
        if p._region_slew.at_target(p._region_target()):
            break
    seq = np.array(seq)

    assert len(seq) > 1, "the wire advanced in a single step (no ramp)"
    # per-tick, EVERY component moved at most one slew step (no per-tick pop).
    step = np.abs(np.diff(seq, axis=0))
    assert np.all(step <= SLEW_MAX_STEP + 1e-6), "a per-tick step exceeded the cap"
    # monotone toward the target on every component (a true ramp).
    target = p._region_target()
    approach = np.abs(seq - target)
    assert np.all(np.diff(approach, axis=0) <= 1e-6), "ramp not monotone toward target"
    # DROP settles exactly on the final target.
    np.testing.assert_allclose(seq[-1], target, atol=1e-3)


def test_wire_rate_is_bounded_by_ticks_not_by_move_count():
    """A pathological drag (hundreds of moves) between two ticks still yields one
    wire message per tick — the emit rate is the timer's, not the mouse's."""
    p, em = _panel(K=5)
    pad = p._xy
    pad.mousePressEvent(FakeMouseEvent(*pad._anchor_xy(0)))   # arm
    ticks = 0
    for k in range(5):
        # a flood of moves, then exactly one tick.
        for j in range(200):
            ang = 2 * np.pi * ((k * 200 + j) % 360) / 360.0
            cx, cy = pad._center()
            R = pad._ring_radius()
            pad.mouseMoveEvent(FakeMouseEvent(cx + 0.8 * R * np.cos(ang),
                                              cy + 0.8 * R * np.sin(ang)))
        n_before = len(em.calls)
        p.tick_slew()
        ticks += 1
        assert len(em.calls) - n_before <= 1, "a single tick emitted more than once"
    assert ticks == 5
