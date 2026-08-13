"""LIVE mode against a REAL engine + world (Train B2) — the out-of-process
fixture from test_wavemap_fixture.py (arch-v6 pinned, a genuine trained
world with real provenance/role storage), proving the plumbing
``StreamPlayer.live_start`` / ``live_stop`` / ``live_state`` actually runs
against ``track_unit_slices`` and the real ``StreamWriter.write_bar`` — not
just mocks.

As of THIS build, Part A (``ets.writer.clamp``) has not landed in
architecture-v6 either, so the happy path (successful straight play) is not
yet exercisable end-to-end. What IS real and tested here: idle state before
any click, a proper ``ValueError`` on an unknown track, and — the important
one — that ``live_start`` on a REAL track/time gets all the way through slice
resolution against the real engine and fails HONESTLY and SPECIFICALLY at
the carrier-construction step (never silently proceeding unfenced).
"""
from __future__ import annotations

from cloud.tests.test_wavemap_fixture import probe

_LIVE_PROBE = r'''
from cloud.companion.engine_bridge import StreamPlayer
from cloud.companion.live import LiveCarrierUnavailable, clamp_kwarg_name

p = StreamPlayer(WORLD, seed=0, is_trained=True, eigen_n_seed=2, eigen_n_bar=2)

idle_state = p.live_state()

# §2 introspection against the REAL write_bar (arch-v6, pinned in THIS
# subprocess): as of this build it carries no ClampTerms-typed parameter yet.
no_clamp_kwarg_yet = clamp_kwarg_name(p.engine.writer.write_bar) is None

try:
    p.live_start(999, 0.0)
    unknown_track_error = None
except ValueError as e:
    unknown_track_error = str(e)
except Exception as e:
    unknown_track_error = "WRONG_TYPE:" + type(e).__name__ + ":" + str(e)

try:
    p.live_start(0, 0.05)
    start_ok, start_error = True, None
except LiveCarrierUnavailable as e:
    start_ok, start_error = False, str(e)
except Exception as e:
    start_ok, start_error = False, "WRONG_TYPE:" + type(e).__name__ + ":" + str(e)

p.live_stop()
post_stop_state = p.live_state()

# BYTE-IDENTITY REGRESSION (my own plumbing's neutral law, distinct from
# Part A's own LM-1): a player that went through the whole live_start
# (refused) / live_stop dance must produce EXACTLY the same first bar as a
# twin player that never touched a /api/live/* route at all -- proving
# _compose_bar's new clamp_call_kwargs(...) step is a true no-op when
# self._live["clamp"] is None (the byte-identical write_bar(tilt=tilt) call
# it always was).
touched_pcm, touched_roles = p.produce_one_bar()
twin = StreamPlayer(WORLD, seed=0, is_trained=True, eigen_n_seed=2, eigen_n_bar=2)
twin_pcm, twin_roles = twin.produce_one_bar()

emit({"idle_state": idle_state, "unknown_track_error": unknown_track_error,
      "start_ok": start_ok, "start_error": start_error,
      "post_stop_state": post_stop_state,
      "pcm_identical": touched_pcm == twin_pcm,
      "roles_identical": touched_roles == twin_roles,
      "no_clamp_kwarg_yet": no_clamp_kwarg_yet})
'''


def _d():
    if not hasattr(_d, "_v"):
        _d._v = probe(_LIVE_PROBE)
    return _d._v


def test_idle_state_before_any_click_is_honest_idle():
    d = _d()
    assert d["idle_state"] == {"mode": "idle", "track": None, "unit": None,
                               "slice_index": None, "starved": False}


def test_unknown_track_raises_value_error_not_something_else():
    d = _d()
    err = d["unknown_track_error"]
    assert err is not None and not err.startswith("WRONG_TYPE:"), err
    assert "999" in err


def test_a_real_click_reaches_the_carrier_boundary_and_refuses_honestly():
    """The load-bearing assertion: live_start(0, 0.05) must run track lookup
    + track_unit_slices + resolve_start_index + pin_unit_ids against the REAL
    engine/world (no exception from any of that), and THEN — because Part A
    hasn't landed in architecture-v6 either — refuse specifically at the
    clamp0 construction step. If this ever fails with a DIFFERENT exception
    type, that's a real bug in the slice-resolution plumbing, not the
    expected-and-disclosed carrier-availability wall."""
    d = _d()
    assert d["start_ok"] is False, d
    assert d["start_error"] is not None and not d["start_error"].startswith("WRONG_TYPE:"), d
    assert "clamp0" in d["start_error"] or "ets.writer.clamp" in d["start_error"], d


def test_stop_after_a_refused_start_is_still_clean_idle():
    """A refused live_start must not leave a half-set fence behind."""
    d = _d()
    assert d["post_stop_state"] == {"mode": "idle", "track": None, "unit": None,
                                    "slice_index": None, "starved": False}


def test_unfenced_production_stays_byte_identical_to_an_untouched_player():
    """LM-0/LM-1-adjacent regression on MY OWN plumbing: _compose_bar's new
    clamp-kwarg step must be a true no-op whenever no fence is set — proven
    against the REAL engine/world, not just by code review."""
    d = _d()
    assert d["pcm_identical"] is True, "produce_one_bar diverged with no fence set"
    assert d["roles_identical"] is True


def test_real_write_bar_carries_no_clampterms_parameter_yet():
    """§2 of the prereg, checked against the REAL (arch-v6) StreamWriter.
    write_bar, in an isolated subprocess (see test_live_carrier.py's module
    docstring for why this must never run in the shared pytest process)."""
    d = _d()
    assert d["no_clamp_kwarg_yet"] is True, d


# --- build_full_fence's own wiring, with a FAKE clamp0 injected -----------
# A separate, LIGHTWEIGHT subprocess (no fixture world needed — build_full_
# fence is a pure function of (track, unit_ids)) that injects a fake
# ets.writer.clamp module BEFORE anything else touches `ets`, so this proves
# the exact call shape (track_mask/openness/unit_pin) without ever importing
# the real ets.writer tree in-process (same isolation reason as above).

_FAKE_CLAMP0_PROBE = r'''
import sys, types, json
calls = {}

def fake_clamp0(track_mask=None, openness=None, unit_pin=None):
    calls["track_mask"] = track_mask
    calls["openness"] = openness
    calls["unit_pin"] = list(unit_pin)
    return ["FAKE_CLAMP_TERMS"]

fake_mod = types.ModuleType("ets.writer.clamp")
fake_mod.clamp0 = fake_clamp0
sys.modules.setdefault("ets", types.ModuleType("ets"))
sys.modules.setdefault("ets.writer", types.ModuleType("ets.writer"))
sys.modules["ets.writer.clamp"] = fake_mod

from cloud.companion.live import build_full_fence
out = build_full_fence(3, (10, 11, 12))
print("PROBE " + json.dumps({"out": out, "calls": calls}))
'''


def test_build_full_fence_calls_clamp0_with_the_exact_b1_shape():
    import json
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    r = subprocess.run([sys.executable, "-c", _FAKE_CLAMP0_PROBE], cwd=str(root),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("PROBE ")]
    assert lines, f"{r.stdout}\n{r.stderr}"
    d = json.loads(lines[-1][len("PROBE "):])
    assert d["out"] == ["FAKE_CLAMP_TERMS"]
    assert d["calls"] == {"track_mask": {"3": 1.0}, "openness": 1.0,
                          "unit_pin": [3, [10, 11, 12]]}
