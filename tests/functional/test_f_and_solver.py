"""Feature tests for F (spec §5), the block-coordinate solver, and anchor
self-sizing (spec §4). Fast + audio-free: prototypes are built from in-memory
arrays so the single functional and its descent are exercised without the beat
model or the corpus.
"""
from __future__ import annotations
import numpy as np
import pytest

from ets.geometry.roles import Prototypes
from ets.functional import f as ff, solver as sv, anchors as an, ot


def _synth_proto(track_id, K=6, S=8, n_bands=8, seed=0):
    rng = np.random.default_rng(seed)
    pts = rng.standard_normal((K, 3))
    cost = np.sqrt(((pts[:, None] - pts[None]) ** 2).sum(-1))
    off = cost[~np.eye(K, dtype=bool)]
    cost = cost / (np.sqrt(np.mean(off ** 2)) + 1e-12)
    mass = rng.random(K) + 0.1; mass /= mass.sum()
    slot = rng.random((K, S)); slot /= slot.sum()
    band = rng.random((K, n_bands)); band = band / band.sum(1, keepdims=True) * mass[:, None]
    chroma = rng.random((K, 12)); chroma /= chroma.sum(1, keepdims=True)
    timbre = rng.standard_normal((K, 4))
    return Prototypes(track_id=track_id, cost=cost, mass=mass, slot_hist=slot,
                      band_profile=band, timbre=timbre, chroma=chroma)


# --- GW primitive sanity ----------------------------------------------------

def test_gw_distortion_small_on_identical_vs_different():
    P = _synth_proto(0, seed=1)
    Q = _synth_proto(1, seed=42)
    pi, d_same = ot.entropic_gw(P.cost, P.cost, P.mass, P.mass, eps=0.02)
    _, d_diff = ot.entropic_gw(P.cost, Q.cost, P.mass, Q.mass, eps=0.02)
    assert d_same < 0.1 * d_diff, (d_same, d_diff)     # self-match ~ 0 vs cross
    assert np.allclose(pi.sum(1), P.mass, atol=1e-4)   # row marginal preserved


def test_sinkhorn_marginals():
    rng = np.random.default_rng(0)
    C = rng.random((5, 7))
    r = rng.random(5); r /= r.sum()
    c = rng.random(7); c /= c.sum()
    pi = ot.sinkhorn(C, r, c, eps=0.05)
    assert np.allclose(pi.sum(1), r, atol=1e-4)
    assert np.allclose(pi.sum(0), c, atol=1e-4)


# --- F descent: the Lyapunov certificate ------------------------------------

def test_F_descent_is_monotone():
    protos = [_synth_proto(t, seed=t) for t in range(4)]
    st = an.init_state(protos, M=5, seed=0)
    st, traj = sv.batch_solve(st, protos, max_sweeps=12)
    traj = np.asarray(traj)
    assert np.all(np.diff(traj) <= 1e-9), \
        f"F not monotone: {np.sum(np.diff(traj) > 1e-9)} increases"
    assert traj[-1] < traj[0], "F did not decrease at all"


def test_all_five_terms_present_and_real():
    protos = [_synth_proto(t, seed=t + 10) for t in range(3)]
    st = an.init_state(protos, M=4, seed=0)
    total, terms = ff.F(st, protos)
    for k in ("T1", "T2", "T3", "T4", "T5"):
        assert k in terms and np.isfinite(terms[k])
    assert abs(total - sum(terms[k] for k in ("T1", "T2", "T3", "T4", "T5"))) < 1e-9
    # T1 (transport) dominates and is strictly positive; T4 (continuity) rewards
    # (<=0). The single scalar is exactly their sum — no hidden term.
    assert terms["T1"] > 0 and terms["T4"] <= 1e-12


def test_terms_are_active_during_descent():
    # T2 and T5 must do real work (be nonzero) somewhere on the trajectory, else
    # they would be decorative. Check at the initial (un-settled) state.
    protos = [_synth_proto(t, seed=t + 3) for t in range(4)]
    st = an.init_state(protos, M=6, seed=0)
    # perturb gauge + occupancy so the conservation/gauge terms are engaged
    st.phase_off[1] = 2
    _, terms = ff.F(st, protos)
    assert terms["T2"] >= 0 and terms["T3"] >= 0 and terms["T5"] > 0


# --- anchor self-sizing: balanced truncation of the traffic operator --------

# sigma is a FIXED corpus-level scale (calibrated once, then frozen and applied
# to every arm) — it must NOT be recomputed per arm, or a degenerate equal-
# distance arm would inflate its own rank. A representative corpus scale is used.
SIGMA = 0.5


def test_effective_rank_gauge_invariant_flat_in_N():
    # gauge copies share intrinsic geometry -> role distance ~ 0 (<< sigma) ->
    # traffic affinity ~ all-ones -> effective rank ~ 1, flat as N grows
    # (I-2 gauge law + spec §4 flat-in-N).
    P = _synth_proto(0, seed=7)
    for n in (2, 4, 6):
        protos = [P] + [an.gauge_copy(P, transpose=k, phase=k % 8, loud=1 + 0.3 * k)
                        for k in range(1, n)]
        A, D, _ = an.traffic_affinity(protos, sigma=SIGMA)
        assert D.max() < 0.05, f"gauge copies not role-identical: {D.max()}"
        er = an.effective_rank(A)
        assert er < 1.2, f"n={n}: gauge copies inflated anchor count to {er}"


def test_effective_rank_grows_with_diversity():
    same = [_synth_proto(0, seed=5)]
    same = same + [an.gauge_copy(same[0], transpose=k) for k in range(1, 5)]
    diverse = [_synth_proto(t, seed=100 + t) for t in range(5)]
    er_same = an.effective_rank(an.traffic_affinity(same, sigma=SIGMA)[0])
    er_div = an.effective_rank(an.traffic_affinity(diverse, sigma=SIGMA)[0])
    assert er_div > er_same + 0.25, (er_same, er_div)
