"""PI drill-in gesture bite (the classical-sampler drill, panel/gesture side).

Hold a role-pad -> the drill overlay shows that role's UNIT POOL (from the
read-only /ets/unitpool telemetry). Tapping a unit cell is a FINE STEER: it leans
the region toward THAT unit's anchor-profile (its B[:, band] vector, peak-
normalized and scaled to the safe magnitude) through the panel's EXISTING
whole-vector region path (`Panel.set_region_vector`) — the SAME region-tilt lane
the role pads and XY pad use, and NOTHING else. A CUE toggle reroutes the tap to a
private audition (never main-out). These bites pin:

  * a unit tap reaches the engine ONLY as a region-tilt lean (no second channel);
  * that lean EQUALS the tapped unit's normalized profile scaled to the cap;
  * CUE on auditions (cue bus) and does NOT steer;
  * the overlay opens on drill and closes on the close button AND on click-away.

The design law: the ONLY gesture->engine door is the region lane. No unit is
force-isolated (that would be clamping); the tap sets a soft lean over all roles
in the unit's true proportions.
"""
from __future__ import annotations

import numpy as np
import pytest

from tests.pi.conftest import RecordingEmitter

K = 3          # anchors / roles
ROLE = 1       # the role we drill into

# a role-1 pool: two units on two different source tracks, profiles length K.
POOL1 = [
    {"unit_id": 0, "track_id": 0, "band": 2, "profile": [0.6, 0.3, 0.1]},
    {"unit_id": 5, "track_id": 7, "band": 4, "profile": [0.2, 0.2, 0.6]},
]


@pytest.fixture
def live(qapp):
    """A real LiveInstrument, headless, with its outbound emitter swapped for a
    recording one so a test can prove single-channel routing. The role-1 pool is
    fed through the real telemetry inbox."""
    live_mod = pytest.importorskip("ets.instrument.live")
    inst = live_mod.LiveInstrument(engine_host="127.0.0.1", engine_port=9000,
                                   meters_port=0, n_anchors=K)
    inst.panel.emitter = RecordingEmitter()          # capture the one wire
    inst.panel.set_anchor_count(K)                   # size the region lane to K
    inst._feed_unitpool(ROLE, list(POOL1))           # real inbox, plain data
    yield inst
    inst.receiver.stop()


def _expected_lean(profile):
    """The unit's normalized profile scaled to the safe cap (peak = cap)."""
    from ets.panel.envelope import SAFE_REGION_MAGNITUDE
    p = np.asarray(profile, float)
    return p / np.max(np.abs(p)) * SAFE_REGION_MAGNITUDE


def test_unit_tap_cue_off_sets_region_target_only(live):
    inst = live
    emitter = inst.panel.emitter
    inst.open_unit_layer(ROLE)
    assert inst.unit_layer.cue_on is False

    inst.on_unit_tapped(0)                            # tap unit 0, CUE off

    # the region/lanes channel fired ...
    assert emitter.lanes, "unit tap did not reach the panel's region emitter"
    # ... the region TARGET equals the tapped unit's normalized profile * cap ...
    want = _expected_lean(POOL1[0]["profile"])
    assert np.allclose(np.asarray(inst.panel.u.u_region, float), want), \
        f"region target != normalized profile scaled to cap: {inst.panel.u.u_region} vs {want}"
    # ... and NO second channel fired.
    assert emitter.tolerances == [], "unit tap fired the tolerance channel"
    assert emitter.hellos == [], "unit tap fired the hello channel"


def test_emitted_lean_converges_to_normalized_profile_scaled_to_cap(live):
    """The wire value is the panel's usual slewed region; ticking the slew to
    convergence, the EMITTED lean equals the tapped unit's normalized profile
    scaled to the cap (peak component == SAFE_REGION_MAGNITUDE)."""
    inst = live
    emitter = inst.panel.emitter
    inst.open_unit_layer(ROLE)
    inst.on_unit_tapped(1)                            # tap unit 5 (index 1)

    for _ in range(64):                               # drive the bounded slew home
        inst.panel.tick_slew()
    want = _expected_lean(POOL1[1]["profile"])
    assert np.allclose(np.asarray(emitter.lanes[-1], float), want, atol=1e-4), \
        f"emitted lean did not converge to normalized profile*cap: {emitter.lanes[-1]} vs {want}"
    assert float(np.max(np.abs(emitter.lanes[-1]))) == pytest.approx(1.0, abs=1e-4)


def test_cue_on_auditions_and_does_not_steer(live):
    inst = live
    emitter = inst.panel.emitter
    inst.open_unit_layer(ROLE)
    inst.on_cue_toggled(True)                         # CUE on
    n_before = len(emitter.lanes)

    inst.on_unit_tapped(0)                            # tap unit 0 under CUE

    assert len(emitter.lanes) == n_before, "CUE-on unit tap leaked a region emit"
    assert emitter.tolerances == [] and emitter.hellos == []
    assert inst.cue.active is True
    assert POOL1[0]["track_id"] in inst.cue.auditioned, \
        "CUE-on unit tap did not route to the cue audition bus"


def test_drill_overlay_opens_on_drill_and_closes_back(live):
    # isHidden() reflects the explicit show/hide state regardless of whether a
    # top-level window is shown (this instrument is built headless, unshown).
    inst = live
    assert inst.unit_layer.isHidden() is True

    inst.open_unit_layer(ROLE)                        # drill fired
    assert inst.unit_layer.isHidden() is False
    assert inst.unit_layer.role == ROLE
    assert inst.unit_layer.grid._units == POOL1       # cells came from the pool

    # close button path.
    inst.close_unit_layer()
    assert inst.unit_layer.isHidden() is True

    # click-away path: interacting with the coarse role pads dismisses the drill.
    inst.open_unit_layer(ROLE)
    assert inst.unit_layer.isHidden() is False
    inst.role_pads.tapped.emit(0)
    assert inst.unit_layer.isHidden() is True
