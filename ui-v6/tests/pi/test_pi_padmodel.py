"""PI pad-activity model bite.

`PadModel` is the pure (Qt-free) light-up state: a now-playing feed sets per-key
brightness, and a decay makes lights fade instead of snapping. This pins the two
behaviors the live grid depends on:

  * set_activity stores the feed and CLAMPS every level into 0..1;
  * decay multiplies every level toward 0 (monotone, never negative).

Pure model — no Qt, no engine, no emit.
"""
from __future__ import annotations

import pytest

model = pytest.importorskip("ets.instrument.model")


def test_set_activity_stores_and_clamps():
    pm = model.PadModel()
    pm.set_activity({0: 0.4, 1: 5.0, 2: -3.0})   # over/under range on purpose
    assert pm.activity[0] == pytest.approx(0.4)
    assert pm.activity[1] == 1.0                  # clamped up
    assert pm.activity[2] == 0.0                  # clamped down
    # new keys register into the stable pad order.
    assert set(pm.tracks) == {0, 1, 2}
    assert all(0.0 <= v <= 1.0 for v in pm.activity.values())


def test_decay_moves_every_level_toward_zero():
    pm = model.PadModel()
    pm.set_activity({0: 1.0, 1: 0.5})
    before = dict(pm.activity)
    pm.decay(0.5)
    for k, v0 in before.items():
        assert pm.activity[k] == pytest.approx(v0 * 0.5)
        assert 0.0 <= pm.activity[k] < v0 or v0 == 0.0
    # repeated decay converges toward 0, never below it.
    for _ in range(50):
        pm.decay(0.5)
    assert all(v >= 0.0 for v in pm.activity.values())
    assert max(pm.activity.values()) < 1e-6
