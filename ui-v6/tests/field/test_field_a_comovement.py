"""FIELD-A — proof-of-realness, both halves, against the REAL writer:

  (a) CO-MOVEMENT: biasing one square makes RELATED squares move that you did
      not touch (the engine re-settles the whole landscape, the display shows
      its answer everywhere);
  (b) DYNAMIC SENSITIVITY: the SAME push yields a DIFFERENT response depending
      on the current settled state (you feel the local stiffness).

Settled quantity: the per-bar UNNORMALIZED role-mass projection (B @ band_mass
— what /ets/roleactivity displays before its cosmetic per-bar peak norm).
The fixture asserts the region lane is ARMED; a disarmed fixture FAILS loudly.
"""
from __future__ import annotations

import numpy as np

from tests.field.conftest import settled_run

_BARS = 6


def test_co_movement_untouched_role_responds():
    base, M = settled_run([0.0] * 2, n_bars=_BARS)
    push = [1.0] + [0.0] * (M - 1)                 # bias ONLY role 0
    up, _ = settled_run(push, n_bars=_BARS)
    d = up - base                                  # per-bar response, all roles
    assert np.any(np.abs(d[:, 0]) > 1e-9), "the pushed role did not respond"
    untouched = np.abs(d[:, 1:])
    assert np.any(untouched > 1e-9), \
        "NO untouched role moved — the surface is echoing input, not " \
        "re-settling (FIELD-A co-movement violated)"


def test_dynamic_sensitivity_same_push_different_state():
    """Apply the SAME +1 push on role 0 from two different settled states
    (neutral vs leaning on role 1). The engine's response profile must differ:
    the landscape's local stiffness is real, not a constant input->output map."""
    n0, M = settled_run([0.0, 0.0], n_bars=_BARS)
    n1, _ = settled_run([1.0, 0.0], n_bars=_BARS)
    resp_neutral = n1 - n0

    s0, _ = settled_run([0.0, 0.8], n_bars=_BARS)
    s1, _ = settled_run([1.0, 0.8], n_bars=_BARS)
    resp_leaning = s1 - s0

    assert not np.allclose(resp_neutral, resp_leaning, atol=1e-9), \
        "identical response from different settled states — the field would " \
        "be a static input map, not a live landscape (FIELD-A dynamic " \
        "sensitivity violated)"


def test_displayed_value_is_the_settled_answer_not_the_input():
    """The settled response to a +1 push is NOT the pushed vector itself: what
    the display shows (settled mass) differs in shape from what was pushed —
    the machine answered, it did not echo."""
    base, M = settled_run([0.0, 0.0], n_bars=_BARS)
    up, _ = settled_run([1.0, 0.0], n_bars=_BARS)
    d = (up - base).mean(axis=0)
    pushed = np.array([1.0, 0.0])
    dn = np.linalg.norm(d)
    assert dn > 0
    cos = float(np.dot(d / dn, pushed))
    assert abs(abs(cos) - 1.0) > 1e-6, \
        "response exactly parallel to the input — indistinguishable from echo"
