"""FIELD-B — soft bias: scroll-down saturates at "strongly disfavored" and
NEVER hard-mutes. bias != membership (the crate/library checkbox is the
separate hard on/off system).

UI side: the bias accumulator saturates at ±1 and the emitted lean never leaves
the panel's safe envelope. Authority side: the region lane is an exponential
(h-transform) tilt with finite λ — a full down-stop DISFAVORS the role's
settled mass but the writer keeps placing real material (weight stays > 0).
"""
from __future__ import annotations

import numpy as np
import pytest

from tests.field.conftest import settled_run


def test_bias_accumulator_saturates_soft():
    from ets.instrument.field import FieldModel
    m = FieldModel()
    m.telemetry_writer().apply_roleactivity([0.1, 0.1])
    for _ in range(100):                       # scroll far past the stop
        m.add_bias(("role", 0), -0.125)
    assert m.bias_of(("role", 0)) == -1.0      # saturated, not unbounded
    for _ in range(100):
        m.add_bias(("role", 1), +0.125)
    assert m.bias_of(("role", 1)) == +1.0


def test_composite_lean_never_leaves_the_safe_envelope():
    from ets.instrument.field import FieldModel
    from ets.panel.envelope import SAFE_REGION_MAGNITUDE, clamp_region
    m = FieldModel()
    w = m.telemetry_writer()
    w.apply_roleactivity([0.2, 0.2, 0.2])
    w.apply_profiles({0: [1.0, 0.9, 0.8]})
    # pile maximal biases on overlapping directions:
    m.add_bias(("role", 0), 5.0)
    m.add_bias(("role", 1), -5.0)
    m.add_bias(("track", 0), 5.0)
    vec = m.region_vector(3)
    emitted = clamp_region(vec)                # the panel's wall on this path
    assert float(np.max(np.abs(emitted))) <= SAFE_REGION_MAGNITUDE + 1e-6


def test_full_down_bias_disfavors_but_never_mutes():
    """ENGINE answer at the down-stop: the down-biased role's settled mass
    DROPS vs baseline (disfavor is real) yet stays > 0 on every bar (mute is
    impossible through the bias lane — that power belongs to membership only).
    Runs the REAL writer on the fixture world (region lane verified armed)."""
    base, M = settled_run([0.0, 0.0], n_bars=6)
    down, _ = settled_run([-1.0, 0.0], n_bars=6)     # role 0 at the down-stop
    assert down[:, 0].sum() < base[:, 0].sum(), \
        "full down-bias failed to disfavor the role (bias lane inert?)"
    assert np.all(down.sum(axis=1) > 0.0), "a bar settled to silence"
    assert np.all(down[:, 0] >= 0.0) and down[:, 0].sum() > 0.0, \
        "down-bias HARD-MUTED the role — bias must never reach zero weight"


def test_tilt_lambda_stays_finite_at_the_stops():
    """The authority-level no-mute fact: at the UI stops (|u| = safe cap) the
    Layer-0 λ is finite, so the exponential tilt factor is strictly positive —
    zero weight is unreachable through this lane."""
    from ets.panel.envelope import SAFE_REGION_MAGNITUDE
    from ets.writer.tilt import SigmaPhi, layer0
    from ets.panel.lanes import default_lane_vector
    sigma = SigmaPhi(region=np.array([0.5, 0.7]), density=0.0, cont=1.0,
                     gauge=0.0, novelty=1.0,
                     identifiable={"region": True, "density": False,
                                   "cont": True, "gauge": False,
                                   "novelty": True})
    u = default_lane_vector(2)
    u.u_region[:] = [-SAFE_REGION_MAGNITUDE, SAFE_REGION_MAGNITUDE]
    t = layer0(u, sigma)
    assert np.all(np.isfinite(t.lam_region))
    assert np.all(np.exp(t.lam_region) > 0.0)


def test_bias_is_not_membership():
    """The field exposes NO membership/mute affordance: no API of the model or
    view can remove a square from play. (The crate/library display filter is a
    separate widget, unchanged in ui-v6.)"""
    import ets.instrument.field as f
    api = {n for n in dir(f.FieldModel) if not n.startswith("__")}
    api |= {n for n in dir(f.FieldView) if not n.startswith("__")}
    forbidden = {"mute", "exclude", "remove", "set_membership", "kill"}
    assert not (api & forbidden)
    with pytest.raises(Exception):
        f.FieldModel().add_bias(("role", 0), "mute")   # only numeric deltas
