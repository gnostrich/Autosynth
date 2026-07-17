"""UV5-C — ROAM (ui-v5 BUG-2). The soft (Gaussian) kernel over anchor distance
lets the operator roam the whole pad instead of being pinned to the nearest
region:

  * a dot BETWEEN two anchors weights BOTH meaningfully (a genuine blend), not
    ~all-mass-on-the-nearest as the old inverse-distance kernel did;
  * sweeping the pad around the ring changes the dominant anchor SMOOTHLY — only
    to an adjacent anchor, balanced at the midpoints — and every region is
    reachable.

The tests operate on the kernel directly (`_vector` at set dot positions); the
event plumbing is covered by v5c / UV5-B.
"""
from __future__ import annotations

import math

import numpy as np

from PySide6.QtCore import QPointF


def _pad(K=6, size=240):
    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import _RegionXYPad
    QApplication.instance() or QApplication([])
    pad = _RegionXYPad()
    pad.resize(size, size)
    pad.set_anchor_count(K)
    return pad


def _vec_at(pad, ang, frac=1.0):
    """Region vector for a dot at polar (frac*R, ang) about the pad centre."""
    cx, cy = pad._center()
    R = pad._ring_radius()
    pad._dot = pad._clamp_to_ring(
        QPointF(cx + frac * R * math.cos(ang), cy + frac * R * math.sin(ang)))
    return pad._vector()


def test_between_two_anchors_blends_both():
    K = 6
    pad = _pad(K)
    # midpoint angle between anchor 0 (angle 0) and anchor 1 (angle 2π/K).
    v = _vec_at(pad, math.pi / K, frac=1.0)
    order = [int(i) for i in np.argsort(-np.abs(v))]
    assert set(order[:2]) == {0, 1}, f"midpoint 0–1 not dominated by 0,1: {v}"
    # BOTH neighbours meaningfully weighted and roughly balanced (a real blend,
    # not a pin): by symmetry the ratio is ~1.
    ratio = abs(v[0]) / abs(v[1])
    assert 0.7 < ratio < 1.4, f"midpoint blend not balanced (pin?): {ratio}, {v}"
    # the runner-up neighbour is not negligible vs the winner.
    assert abs(v[1]) > 0.4 * abs(v[0]), f"neighbour swamped: {v}"


def test_soft_kernel_does_not_pin_at_an_anchor():
    K = 6
    pad = _pad(K)
    v = _vec_at(pad, 0.0, frac=1.0)             # dot ON anchor 0
    share = np.abs(v) / (np.abs(v).sum() + 1e-12)
    nearest = float(share[0])
    # SOFT: the nearest anchor holds a blended share, NOT ~all the mass.
    assert nearest < 0.75, f"the kernel still pins at the anchor: share={nearest}"
    # the immediate ring neighbours still carry real weight (you can lean away).
    assert float(share[1]) > 0.05 and float(share[K - 1]) > 0.05, f"no blend: {share}"

    # BITE: the OLD inverse-distance kernel, at the SAME geometry, pins ~all mass
    # on anchor 0 — this is exactly the pin ui-v5 removed.
    a0 = np.array(pad._anchor_xy(0))
    d = np.array([math.hypot(*(np.array(pad._anchor_xy(i)) - a0)) for i in range(K)])
    old = 1.0 / (d + 1e-6)
    old = old / old.sum()
    assert old[0] > 0.95, "sanity: 1/dist pins at the anchor (the removed behaviour)"
    assert nearest < old[0] - 0.2, "soft kernel is not meaningfully softer than 1/dist"


def test_sweep_changes_dominant_anchor_smoothly():
    K = 6
    pad = _pad(K)
    doms = []
    M = 360
    for j in range(M):
        v = _vec_at(pad, 2 * math.pi * j / M, frac=1.0)
        doms.append(int(np.argmax(np.abs(v))))
    doms = np.array(doms)

    # every anchor is reachable (you can roam the whole pad).
    assert set(doms.tolist()) == set(range(K)), f"unreachable regions: {set(doms)}"
    # the dominant index only ever steps to an ADJACENT anchor (circularly) — a
    # smooth progression, never a hard jump across regions.
    circ = np.concatenate([doms, doms[:1]])
    dd = np.abs(np.diff(circ))
    step = np.minimum(dd, K - dd)               # circular distance
    assert np.all(step <= 1), f"dominant anchor jumped non-adjacently: max={step.max()}"
    # it genuinely sweeps through all K regions (>= K transitions round the ring).
    assert int(np.count_nonzero(step)) >= K, "sweep did not traverse all regions"


def test_center_is_even_neutral_and_zero_magnitude():
    K = 5
    pad = _pad(K)
    v = _vec_at(pad, 0.0, frac=0.0)             # dot at dead centre
    assert np.allclose(v, 0.0, atol=1e-6), f"centre must be zero lean: {v}"
    # just off-centre toward no particular anchor stays even: all anchors are
    # equidistant on a tiny circle, so weights are ~uniform.
    from PySide6.QtCore import QPointF
    cx, cy = pad._center()
    pad._dot = QPointF(cx + 1.0, cy)            # 1px off-centre
    v = pad._vector()
    w = np.abs(v)
    if w.sum() > 0:
        w = w / w.sum()
        assert float(w.max() - w.min()) < 0.2, f"near-centre not ~even: {w}"
