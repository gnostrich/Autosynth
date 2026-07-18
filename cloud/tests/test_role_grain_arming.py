"""ROLE/UNIT-GRAIN ARMING — the MEASURED disarm of the anchor band-profile observable
(OPEN_ENDS #22; Theorem A arming corollary, papers/paper1-typed-control-calculus.md
§3, papers/paper2-ets-instrument.md §2-3).

The field's role->unit drill and its track-square lean both route through the frozen
anchor band-profile matrix B (world.fstate.B). On the band-blind fixed point B is
uniform, the grouping observable carries no information, and by the fluctuation-
dissipation identity those two controls degenerate and must DISARM. The decision is
MEASURED off B — never a hardcoded flag — so a world whose B carries real band spread
ARMS automatically (the pre-registered engine change that makes B informative re-arms
with no code edit here).

These are pure-predicate tests: they import ONLY the module-level ``anchor_profile_armed``
(numpy only), never a StreamPlayer, so no arch-v6 engine/render/writer module enters
the cloud test interpreter (the test_mvp_d import-graph guard stays clean). The
end-to-end static_field gating on a real world is exercised out-of-process in
test_web_field_payload.py.
"""
from __future__ import annotations

import sys

import numpy as np

# Module import only (no StreamPlayer instance -> no ets.* import). Guard the invariant.
from cloud.companion.engine_bridge import anchor_profile_armed, _PROFILE_ARMING_EPS


def test_module_import_pulls_no_engine():
    """Importing the arming predicate must NOT drag the arch-v6 engine/render/writer
    into the cloud interpreter (ets.* imports live inside StreamPlayer.__init__)."""
    leaked = [m for m in sys.modules
              if any(b in m for b in ("ets.writer", "ets.render", "ets.engine",
                                      "ets.panel", "ets.meters"))]
    assert not leaked, f"the arming predicate import leaked engine modules: {leaked}"


def test_uniform_B_disarms():
    """The band-blind fixed point: every anchor row flat across bands -> DISARM.
    This is the exact shape every world trained to date carries (uniform 1/n_bands)."""
    for shape in [(2, 8), (1, 4), (5, 16), (3, 3)]:
        B = np.full(shape, 1.0 / shape[1], dtype=float)
        assert anchor_profile_armed(B) is False, f"uniform B{shape} must disarm"


def test_informative_B_arms():
    """Some anchor row varies across bands above the noise floor -> ARM."""
    B = np.array([[0.9, 0.1, 0.5, 0.2],
                  [0.1, 0.9, 0.5, 0.8]], dtype=float)
    assert anchor_profile_armed(B) is True


def test_all_zero_B_disarms():
    """A degenerate all-zero B carries no information (no scale) -> DISARM,
    without a divide-by-zero."""
    assert anchor_profile_armed(np.zeros((4, 6))) is False


def test_empty_B_disarms():
    assert anchor_profile_armed(np.zeros((0, 0))) is False


def test_arming_is_scale_invariant():
    """The measure is RELATIVE row spread, so it cannot be gamed by rescaling:
    a tiny-magnitude but relatively-structured B ARMS; a large-magnitude but
    perfectly uniform B DISARMS. (Guards against an absolute-epsilon mistake.)"""
    tiny_informative = np.array([[9e-9, 1e-9], [1e-9, 9e-9]], dtype=float)
    assert anchor_profile_armed(tiny_informative) is True, \
        "relative spread ~0.89 must arm regardless of absolute magnitude"
    big_uniform = np.full((3, 5), 1e6, dtype=float)
    assert anchor_profile_armed(big_uniform) is False, \
        "a perfectly uniform B disarms at any magnitude"


def test_epsilon_is_a_noise_floor_not_a_tuned_threshold():
    """The threshold is a numerical-noise floor: an exactly-flat B sits at 0 spread
    (disarm), and any real structure clears the floor by orders of magnitude (arm).
    A relative spread just under the floor disarms; just over it arms — the honest
    boundary, not a knob tuned to a corpus."""
    # relative spread exactly at ~half the floor -> disarm; ~10x the floor -> arm.
    lo = np.array([[1.0, 1.0 + 0.5 * _PROFILE_ARMING_EPS]], dtype=float)
    hi = np.array([[1.0, 1.0 + 10.0 * _PROFILE_ARMING_EPS]], dtype=float)
    assert anchor_profile_armed(lo) is False
    assert anchor_profile_armed(hi) is True
