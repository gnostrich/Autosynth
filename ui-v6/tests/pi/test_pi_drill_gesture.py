"""PI drill/fine-bias bite (ui-v6 FIELD edition; supersedes the drill overlay).

Zoom INTO a role square -> the field shows that role's UNIT POOL (from the
read-only /ets/unitpool telemetry). Biasing a unit square is the FINE steer: it
leans the region toward THAT unit's anchor-profile (its B[:, band] vector,
peak-normalized and scaled by the bias toward the safe magnitude) through the
panel's EXISTING whole-vector region path (`Panel.set_region_vector`) — the
SAME region-tilt lane, and NOTHING else. A CUE toggle routes a unit CLICK to a
private audition (never main-out). These bites pin:

  * a unit bias reaches the engine ONLY as a region-tilt lean (no 2nd channel);
  * at full bias the lean EQUALS the unit's normalized profile scaled to cap;
  * CUE on auditions (cue bus) and does NOT steer;
  * zoom opens a role's units and zoom-out returns (the drill, no overlay).
"""
from __future__ import annotations

import numpy as np
import pytest

from tests.pi.conftest import RecordingEmitter

K = 3          # anchors / roles
ROLE = 1       # the role we drill into

# a role-1 pool: two units on two different source tracks, profiles length K.
# (two comparable loadings at role 1 -> the pool clears the noise floor.)
POOL1 = [
    {"unit_id": 0, "track_id": 0, "band": 2, "profile": [0.6, 0.3, 0.1]},
    {"unit_id": 5, "track_id": 7, "band": 4, "profile": [0.2, 0.2, 0.6]},
]


@pytest.fixture
def live(qapp):
    """A real LiveInstrument, headless, with its outbound emitter swapped for a
    recording one so a test can prove single-channel routing. The role-1 pool is
    fed through the real telemetry inbox + GUI tick (the capability path)."""
    live_mod = pytest.importorskip("ets.instrument.live")
    inst = live_mod.LiveInstrument(engine_host="127.0.0.1", engine_port=9000,
                                   meters_port=0, n_anchors=K)
    inst.panel.emitter = RecordingEmitter()          # capture the one wire
    inst.panel.set_anchor_count(K)                   # size the region lane to K
    inst._feed_roleactivity([0.5, 0.9, 0.1])         # real inboxes, plain data
    inst._feed_unitpool(ROLE, list(POOL1))
    inst._on_tick()                                  # drain -> field model
    yield inst
    inst.receiver.stop()


def _expected_lean(profile, bias=1.0):
    """The unit's normalized profile scaled by bias to the safe cap."""
    from ets.panel.envelope import SAFE_REGION_MAGNITUDE
    p = np.asarray(profile, float)
    return p / np.max(np.abs(p)) * SAFE_REGION_MAGNITUDE * float(bias)


def test_unit_full_bias_sets_region_target_only(live):
    inst = live
    emitter = inst.panel.emitter
    ukey = ("unit", ROLE, 0, 0)                       # unit 0 of role 1

    inst.field_model.add_bias(ukey, 1.0)              # scroll to the up-stop
    inst.push_field_bias()                            # the one wiring

    assert emitter.lanes, "unit bias did not reach the panel's region emitter"
    want = _expected_lean(POOL1[0]["profile"])
    assert np.allclose(np.asarray(inst.panel.u.u_region, float), want), \
        f"region target != normalized profile*cap: {inst.panel.u.u_region} vs {want}"
    assert emitter.tolerances == [], "unit bias fired the tolerance channel"
    assert emitter.hellos == [], "unit bias fired the hello channel"


def test_emitted_lean_converges_to_normalized_profile_scaled_to_cap(live):
    """The wire value is the panel's usual slewed region; ticking the slew to
    convergence, the EMITTED lean equals the biased unit's normalized profile
    scaled to the cap (peak component == SAFE_REGION_MAGNITUDE)."""
    inst = live
    emitter = inst.panel.emitter
    inst.field_model.add_bias(("unit", ROLE, 5, 7), 1.0)   # unit 5 (index 1)
    inst.push_field_bias()

    for _ in range(64):                               # drive the bounded slew home
        inst.panel.tick_slew()
    want = _expected_lean(POOL1[1]["profile"])
    assert np.allclose(np.asarray(emitter.lanes[-1], float), want, atol=1e-4), \
        f"emitted lean did not converge: {emitter.lanes[-1]} vs {want}"
    assert float(np.max(np.abs(emitter.lanes[-1]))) == pytest.approx(1.0, abs=1e-4)


def test_cue_on_click_auditions_and_does_not_steer(live):
    inst = live
    emitter = inst.panel.emitter
    inst.on_cue_toggled(True)                         # CUE on
    n_before = len(emitter.lanes)

    inst.on_unit_clicked(("unit", ROLE, 0, 0))        # click unit 0 under CUE

    assert len(emitter.lanes) == n_before, "CUE-on unit click leaked an emit"
    assert emitter.tolerances == [] and emitter.hellos == []
    assert inst.cue.active is True
    assert POOL1[0]["track_id"] in inst.cue.auditioned, \
        "CUE-on unit click did not route to the cue audition bus"


def test_zoom_drill_opens_units_and_zooms_back(live):
    """The drill is the ZOOM: role 1 (pool clears the floor) opens into its
    unit squares; zoom-out returns to the parent level. Roles with no emitted
    pool are atomic and refuse (no drill into noise)."""
    inst = live
    view = inst.field
    assert view.zoom_path == []
    assert view.zoom_into(("role", ROLE)) is True
    assert view.zoom_path == [("role", ROLE)]
    keys = [s.key for s in view.current_squares()]
    assert keys == [("unit", ROLE, 0, 0), ("unit", ROLE, 5, 7)], \
        "the drilled role's squares are not its emitted unit pool"
    assert view.zoom_out() is True and view.zoom_path == []
    # a role with no pool refuses to open:
    assert view.zoom_into(("role", 0)) is False
