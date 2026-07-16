"""The sigma_phi calibration artifact + loader (registered instrument
sigma-phi-untilted-2026-07-15 / -fix1): schema, honesty flags, world binding.

These tests pin the CONTRACT the engine consumes (ets.calibration), not the
measured values themselves — those belong to the registered run and its
artifact. What is asserted about values is only what the instrument's
pre-registered derivations require: the two structural exact zeros (gauge,
density) and strictly positive fiber fluctuations (region, continuity,
novelty), plus flag/sigma consistency with NO floors anywhere.
"""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from ets.calibration import (SIGMA_PHI_PATH, load_sigma_phi,
                             world_content_hash)
from ets.connector.phi import LANE_PHI, PHI_NAMES


def test_artifact_loads_and_schema_is_complete():
    cal = load_sigma_phi()
    assert set(cal.sigma) == set(PHI_NAMES)
    assert cal.lane_phi == LANE_PHI
    assert len(cal.world_hash) == 64 and int(cal.world_hash, 16) >= 0
    assert cal.n_bars > 0
    assert cal.meta["regenerate"] == "python3 scripts/run_sigma_phi.py"
    assert cal.meta["world"]["cache"]["hash"]          # corpus binding present


def test_region_is_a_per_anchor_vector():
    cal = load_sigma_phi()
    sig = cal.sigma["region"]
    assert isinstance(sig, np.ndarray) and sig.ndim == 1
    assert sig.shape[0] == cal.M == int(cal.meta["world"]["M"])
    # region fluctuates through the fiber at u=0 (run threading redistributes
    # role mass at pinned total) — every component carries a real scale.
    assert np.all(sig > 0.0)
    assert np.all(np.asarray(cal.identifiable["region"]))


def test_fiber_observables_are_identifiable():
    cal = load_sigma_phi()
    for name in ("continuity", "novelty"):
        assert cal.identifiable[name] is True
        assert cal.sigma[name] > 0.0
        assert name not in cal.notes


def test_density_arms_under_the_sampling_ensemble():
    """architecture-v3 Fix A: the ensemble is the untilted T_s>0 SAMPLING writer,
    under which the O-marginal (density) fluctuates (temperature draws around the
    bar-periodic mode) — so DENSITY ARMS with its measured, derived scale. Under
    the prior MAP instrument it was pinned (bar-periodic MAP) and disarmed; that
    missing-ensemble artifact is what the re-derivation removed. No floor: this is
    a genuine measured sigma > 0, not a substituted constant."""
    cal = load_sigma_phi()
    assert cal.identifiable["density"] is True
    assert cal.sigma["density"] > 0.0
    assert "density" not in cal.notes                  # armed => no honest-zero note


def test_gauge_is_the_only_honest_zero_with_note_no_floor():
    """GAUGE stays a structural exact zero even under the sampling writer: the v0
    frame is frozen at the identity, so no frame move exists to fluctuate
    (temperature samples the O-block, not the gauge frame). Honest zero, R3 note,
    no floor invented."""
    cal = load_sigma_phi()
    assert cal.identifiable["gauge"] is False
    assert cal.sigma["gauge"] == 0.0                   # exactly; no floor
    assert "NOT IDENTIFIABLE" in cal.notes["gauge"]    # R3-style honesty note
    assert "identity-gauge" in cal.notes["gauge"]


def test_identifiable_is_exactly_sigma_positive():
    cal = load_sigma_phi()
    for name in PHI_NAMES:
        ident = np.asarray(cal.identifiable[name])
        sig = np.asarray(cal.sigma[name])
        assert np.array_equal(ident, sig > 0.0)


# ---- the loader BITES (no silent acceptance of a broken artifact) ----------

def _tampered(tmp_path, mutate):
    with open(SIGMA_PHI_PATH, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    mutate(doc)
    p = tmp_path / "sigma_phi.json"
    p.write_text(json.dumps(doc))
    return str(p)


def test_loader_rejects_floored_sigma(tmp_path):
    # someone "helpfully" floors the non-identifiable GAUGE sigma (the sole
    # structural exact-zero under the v3 sampling instrument): the flag (still
    # false) now disagrees with sigma > 0 -> hard error, not acceptance.
    def mutate(doc):
        doc["phi"]["gauge"]["sigma"] = 1e-6
    with pytest.raises(ValueError, match="identifiable flag inconsistent"):
        load_sigma_phi(_tampered(tmp_path, mutate))


def test_loader_rejects_flag_override(tmp_path):
    # ...or flips the flag to true while sigma stays 0 -> same law, same error.
    def mutate(doc):
        doc["phi"]["gauge"]["identifiable"] = True
    with pytest.raises(ValueError, match="identifiable flag inconsistent"):
        load_sigma_phi(_tampered(tmp_path, mutate))


def test_loader_rejects_missing_observable(tmp_path):
    def mutate(doc):
        del doc["phi"]["novelty"]
    with pytest.raises(ValueError, match="lacks observables"):
        load_sigma_phi(_tampered(tmp_path, mutate))


def test_loader_rejects_noteless_non_identifiable(tmp_path):
    def mutate(doc):
        doc["phi"]["gauge"].pop("note", None)   # gauge is the disarmed lane (v3)
    with pytest.raises(ValueError, match="honesty note"):
        load_sigma_phi(_tampered(tmp_path, mutate))


def test_loader_rejects_broken_lane_map(tmp_path):
    def mutate(doc):
        doc["lanes"]["6"] = "region"        # TEMPERATURE must map to no phi
    with pytest.raises(ValueError, match="lane map"):
        load_sigma_phi(_tampered(tmp_path, mutate))


# ---- world binding ----------------------------------------------------------

def _fstate(seed=0):
    rng = np.random.default_rng(seed)
    return SimpleNamespace(D=rng.random((3, 3)), a=rng.random(3),
                           B=rng.random((3, 8)), theta=rng.random((3, 8)))


def test_world_hash_binds_anchor_content_and_lambda():
    lam = {"T2": 1.0, "T3": 0.5}
    st = _fstate()
    h0 = world_content_hash(st, lam)
    assert h0 == world_content_hash(_fstate(), lam)    # deterministic

    st2 = _fstate()
    st2.D = st2.D.copy()
    st2.D[0, 1] += 1e-9                                # an anchor moved
    assert world_content_hash(st2, lam) != h0

    assert world_content_hash(st, {"T2": 1.0, "T3": 0.6}) != h0  # weights moved

    st3 = _fstate()
    st3.a = st3.a.reshape(3, 1)                        # reshape cannot collide
    assert world_content_hash(st3, lam) != h0
