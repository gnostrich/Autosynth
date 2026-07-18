"""Informative anchor band-profile B at world freeze (PREREG-informative-B.md §2/§5).

At freeze, ``anchors.build_world`` replaces the uniform band-blind fixed-point B with
the coupling-weighted band profile of the settled, pruned couplings (paper2 §2
fidelity: "same anchor-profile = same sound"). These tests pin the substance:

  * §5.1 a STRUCTURED corpus freezes an INFORMATIVE B (rows vary across bands; the
    per-band dominant anchor differentiates);
  * §5.2 a DEGENERATE corpus (every unit's band profile uniform) freezes an exactly
    FLAT B — no fabricated spread;
  * §5.6 F_final (recomputed on the FROZEN world) sits at or below F_init (the random
    start) — the receipt's descent bound, MEASURED here, not assumed;
  * the freeze form is VERBATIM the NCE reference world's coupling-weighted B form;
  * the NCE exam does not consume the frozen FState's B (it reads
    ``training.world.build_reference_world``'s own B), so it is structurally
    unaffected by this change (§3/§5.4).

Audio-free: prototypes are in-memory arrays; no beat model, no corpus, no bank.
"""
from __future__ import annotations

import numpy as np

from ets.geometry.roles import Prototypes
from ets.functional import f as ff, anchors as an
from ets.training import world as refworld, nce


def _proto(track_id, group, K=6, S=8, n_bands=8, seed=0, band_structured=True):
    """One prototype space. ``group`` places its role geometry near one of a few
    shared latents (so the traffic operator has rank > 1 and the fit self-sizes
    M >= 2). When ``band_structured``, each unit's band profile is PEAKED on a band
    region tied to ``group`` (so different roles carry genuinely different band
    content); otherwise every unit's band profile is UNIFORM across bands (the
    degenerate, no-band-information corpus)."""
    rng = np.random.default_rng(seed)
    centre = np.zeros(3); centre[group % 3] = 2.5
    pts = centre[None, :] + 0.4 * rng.standard_normal((K, 3))
    cost = np.sqrt(((pts[:, None] - pts[None]) ** 2).sum(-1))
    off = cost[~np.eye(K, dtype=bool)]
    cost = cost / (np.sqrt(np.mean(off ** 2)) + 1e-12)
    cost = 0.5 * (cost + cost.T); np.fill_diagonal(cost, 0.0)
    mass = rng.random(K) + 0.1; mass /= mass.sum()
    slot = rng.random((K, S)); slot /= slot.sum()
    if band_structured:
        band = np.full((K, n_bands), 0.02)
        peak = (group % n_bands)
        band[:, peak] += 1.0
        band[:, (peak + 1) % n_bands] += 0.5
        band = band / band.sum(1, keepdims=True) * mass[:, None]
    else:
        band = np.ones((K, n_bands)) / n_bands * mass[:, None]   # uniform: no info
    chroma = rng.random((K, 12)); chroma /= chroma.sum(1, keepdims=True)
    timbre = rng.standard_normal((K, 4))
    return Prototypes(track_id=track_id, cost=cost, mass=mass, slot_hist=slot,
                      band_profile=band, timbre=timbre, chroma=chroma)


def _structured(n_tracks=6, seed=0):
    return [_proto(t, group=t, seed=seed * 100 + t, band_structured=True)
            for t in range(n_tracks)]


def _degenerate(n_tracks=6, seed=0):
    return [_proto(t, group=t, seed=seed * 100 + t, band_structured=False)
            for t in range(n_tracks)]


def _row_ptp(B):
    B = np.asarray(B)
    return float((B.max(axis=1) - B.min(axis=1)).max())


# --- §5.1 informative B on a structured corpus -------------------------------

def test_structured_corpus_freezes_informative_B():
    protos = _structured()
    state, info = an.build_world(protos, seed=0, sweeps=8)
    assert state.M >= 2, "structured corpus must self-size >= 2 anchors for this test"
    # rows sum to 1 (band simplex) and DISTINGUISH bands.
    assert np.allclose(state.B.sum(axis=1), 1.0, atol=1e-9)
    assert _row_ptp(state.B) > 1e-3, "structured B must vary across bands (informative)"
    # the per-band dominant anchor is not the same anchor for every band.
    assert len(set(state.B.argmax(0).tolist())) >= 2, \
        "informative B must spread the per-band argmax across >= 2 anchors"


def test_informative_B_uses_settled_pruned_couplings_form():
    """The frozen B is EXACTLY coupling_weighted_B(state.pis, protos) — the verbatim
    training/world.py freeze form applied to the world's OWN settled, pruned pi's."""
    protos = _structured()
    state, _ = an.build_world(protos, seed=0, sweeps=8)
    B_form = an.coupling_weighted_B(state.pis, protos)
    assert np.array_equal(state.B, B_form), \
        "frozen B must be the coupling-weighted band profile of the settled couplings"


# --- §5.2 flat corpus stays honestly flat (no fabricated spread) -------------

def test_degenerate_corpus_freezes_flat_B():
    protos = _degenerate()
    state, _ = an.build_world(protos, seed=0, sweeps=8)
    # every unit's band profile is uniform -> the coupling-weighted mean is uniform.
    assert _row_ptp(state.B) < 1e-9, \
        "a corpus with no band structure must freeze a FLAT B (no invented spread)"


# --- §5.6 F descended: F_final (frozen world) <= F_init (random start) --------

def test_F_final_at_most_F_init_on_freeze():
    """MEASURED, per §5.6/§7.2: the informative-B swap must not push F above its
    random-start value. If this ever fails on an honest corpus it is a FINDING, not
    a threshold to loosen. Checked on structured AND degenerate fixtures + seeds."""
    for build in (_structured, _degenerate):
        for seed in range(4):
            protos = build(seed=seed)
            state, info = an.build_world(protos, seed=0, sweeps=8)
            assert info["F_final"] <= info["F_init"] + 1e-9, (
                f"F did not descend on {build.__name__} seed={seed}: "
                f"F_final={info['F_final']} > F_init={info['F_init']}")
            # F_final is F of the FROZEN (informative-B) state, not the solve terminal.
            assert abs(info["F_final"] - float(ff.F(state, protos)[0])) <= 1e-9
            assert info["F_monotone"] is True


def test_receipt_info_carries_F_init_and_seed():
    protos = _structured()
    _, info = an.build_world(protos, seed=3, sweeps=8)
    for key in ("F_init", "F_final", "F_monotone", "seed"):
        assert key in info, f"build_world info must carry {key!r} for the receipt"
    assert int(info["seed"]) == 3


# --- §3/§5.4 the NCE exam is structurally unaffected by the freeze B ----------

def test_reference_world_B_is_independent_of_frozen_fstate_B():
    """The exam scores against training.world.build_reference_world's OWN
    coupling-weighted B (from pure entropic-GW couplings), which does not call
    anchors.build_world and never reads the frozen FState.B. This pins that the
    exam contrast is unchanged by the freeze-B change (no re-bless). If the exam
    ever started reading the frozen FState's B, this and nce.feature's signature
    would have to change together -- STOP-and-re-bless, per §5.4."""
    protos = _structured()
    ref = refworld.build_reference_world(protos)
    # build_reference_world produces its own B (its docstring: "coupling-weighted
    # mean prototype band profile") without touching anchors.build_world's freeze.
    assert isinstance(ref, refworld.WorldFreeze)
    assert ref.B.shape[1] == protos[0].band_profile.shape[1]
    # nce.feature consumes world.B (the reference world's B) — asserted by source:
    src = nce.feature.__doc__ or ""
    # structural pin: nce reads raw_terms_O(O, world.D, world.a, world.B, world.theta)
    import inspect
    body = inspect.getsource(nce.feature)
    assert "world.B" in body and "raw_terms_O" in body, \
        "nce.feature must score against the reference world's B (world.B), not a re-frozen FState"
    assert "build_world" not in inspect.getsource(nce), \
        "the exam module must not call anchors.build_world"
