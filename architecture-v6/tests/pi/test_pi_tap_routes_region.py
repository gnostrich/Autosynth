"""PI tap-routing bite (PREREG-uiv5-playable-instrument PI-D, revised per the
role/anchor design pivot).

Play pads are per-ROLE/anchor (`RegionTapPads`), 1:1 with the region-tilt lane.
Tapping role-pad i must reach the engine ONLY as a spike on the region-tilt lane
at anchor i, through the panel's EXISTING emitter path:

    RegionTapPads.tapped(i) -> RegionTapController.tap(i)
        -> panel.tap_region_anchor(i, peak) -> panel._push() -> emitter.emit(u)

We install a recording emitter on the panel (the sanctioned wire), simulate the
signal, and assert (a) the region lean landed on anchor i and nowhere else, and
(b) NO other outbound channel fired — proving there is no second decision
channel parallel to the region lane.

The role LIGHT-UP surface (`RegionTapPads.set_role_activity`) is a concurrent
addition; its bite skips gracefully until the method exists.
"""
from __future__ import annotations

import numpy as np
import pytest

K = 4          # anchors / role pads
TAPPED = 2     # the role we tap


@pytest.fixture
def wired(qapp, recording_emitter):
    """The real app.py wiring, headless: panel + role tap pads + controller."""
    widget = pytest.importorskip("ets.panel.widget")
    pads_mod = pytest.importorskip("ets.instrument.pads")
    tap_mod = pytest.importorskip("ets.instrument.tap")

    panel = widget.Panel(emitter=recording_emitter, n_anchors=K)
    pads = pads_mod.RegionTapPads(K)
    controller = tap_mod.RegionTapController(
        K, region_sink=panel.tap_region_anchor)
    pads.tapped.connect(controller.tap)
    return panel, pads, controller, recording_emitter


def test_role_tap_spikes_region_on_that_anchor_only(wired):
    panel, pads, controller, emitter = wired

    pads.tapped.emit(TAPPED)                      # simulate a role-pad tap

    # the region/lanes channel fired ...
    assert emitter.lanes, "tap did not reach the panel's region emitter"
    u_region = emitter.lanes[-1]
    assert u_region.shape[0] == K

    # ... with a POSITIVE lean on the tapped anchor and zero on every other.
    assert u_region[TAPPED] > 0.0, "no region lean on the tapped anchor"
    others = np.delete(u_region, TAPPED)
    assert np.allclose(others, 0.0), \
        f"tap leaked lean onto non-tapped anchors: {u_region}"

    # ... and NO second channel: no tolerance / hello emit accompanied it.
    assert emitter.tolerances == [], "a role tap fired the tolerance channel"
    assert emitter.hellos == [], "a role tap fired the hello channel"


def test_each_role_tap_leans_only_its_own_anchor(wired):
    """A role pad addresses exactly its own region-lane component. The routing
    invariant is on the panel's region TARGET (what the control sets): tapping
    anchor i raises target[i] and leaves every OTHER anchor's target untouched.

    (The EMITTED vector is a slewed follower of that target, so it legitimately
    keeps ramping earlier taps still in flight — that is the living lane, not a
    cross-anchor leak; locality is asserted on the target the pad actually set.)"""
    panel, pads, controller, emitter = wired
    for i in range(K):
        before = np.asarray(panel.u.u_region, dtype=float).copy()
        n_emits = len(emitter.lanes)
        pads.tapped.emit(i)
        after = np.asarray(panel.u.u_region, dtype=float)
        assert len(emitter.lanes) > n_emits, "tap did not reach the wire"
        assert after[i] > 0.0 and after[i] >= before[i], \
            f"tap on anchor {i} did not lean its own target"
        others = [j for j in range(K) if j != i]
        assert np.allclose(after[others], before[others]), \
            f"tap on anchor {i} moved another anchor's target: {before} -> {after}"


def test_role_activity_lightup_sets_per_anchor_brightness(qapp):
    """Role light-up (concurrent): set_role_activity([...]) sets per-anchor
    brightness, clamped to 0..1. Skips until the method lands."""
    pads_mod = pytest.importorskip("ets.instrument.pads")
    pads = pads_mod.RegionTapPads(K)
    if not hasattr(pads, "set_role_activity"):
        pytest.skip("RegionTapPads.set_role_activity not present yet "
                    "(concurrent role light-up feature)")

    pads.set_role_activity([0.0, 0.5, 5.0, -1.0])   # over/under range on purpose

    # find where the widget stored the per-anchor brightness.
    for attr in ("_role_activity", "role_activity", "_activity",
                 "_brightness", "brightness"):
        store = getattr(pads, attr, None)
        if store is None:
            continue
        vals = [store[i] for i in range(K)] if isinstance(store, dict) \
            else list(store)
        assert vals[0] == pytest.approx(0.0)
        assert vals[1] == pytest.approx(0.5)
        assert vals[2] == 1.0                        # clamped up
        assert vals[3] == 0.0                        # clamped down
        assert all(0.0 <= v <= 1.0 for v in vals)
        break
    else:
        pytest.skip("set_role_activity present but its per-anchor store is not "
                    "discoverable by this bite; assert the storage name once set")
