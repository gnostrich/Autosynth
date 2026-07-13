"""F — the SINGLE free-energy functional (spec §5).

There is exactly ONE functional in the whole system (invariant I-4). Every term
below is a real function of the shared decision variables; F(state, protos)
returns the scalar the solver minimises and the per-term decomposition (for
instrumentation only — the decomposition is not a second objective).

Decision variables (spec §5): couplings pi (unit/prototype -> role -> metrical
slot), channel gains B, anchor supports/masses (D, a), gauge sections g.

Terms (spec §5):
  T1 transport   — GW-typed intrinsic-geometry-to-anchors: sum_t GW(C_t, D; pi_t).
  T2 mass cons.  — unbalanced-OT marginal penalty on role x slot occupancy.
  T3 masking     — spectral-masking collision cost on co-scheduled units.
  T4 continuity  — tilted-Markov / Doob h-transform run-continuation reward.
  T5 gauge-fix   — per-SECTION global transposition/phase cost; never per-unit.

Holonomy / meters / drift / novelty appear NOWHERE in F (invariants I-5, I-14).
This is enforced by an AST scan of this module in tests/invariants (I-5 check).
The weights LAMBDA are frozen structural weights (calibrated at training time,
step d; I-9). No run-time control edits them.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
import numpy as np

from . import ot

# Term weights. T1 is the reference scale (weight 1). These are NOT run-time
# controls (I-9). *** F-1 UNDISCHARGED (WALL). *** These are the step-c PLACEHOLDER
# values, still HAND-SET. Step d's contrastive/NCE fit (ets.training.nce) is WALLED:
# F does not separate real tracks from the full fixed scramble family for any
# LAMBDA>=0 — grid-shuffle vs phase-rotate demand opposite-sign T2 gradients, and
# cross-track-swap does not raise F (see PREREG "Training — real-tracks-are-
# equilibria", registry train-nce-2026-07-13, and the step-d report). Per WALL
# PROTOCOL these are NOT hand-tuned to force separation; they await the proposed
# spec revision (R1/R2/R3) that re-types the occupancy terms. No settled-schedule
# gate (G4+) may stand on these values until F-1 is discharged.
LAMBDA = {"T2": 1.0, "T3": 0.5, "T4": 0.25, "T5": 0.1}


# --- I-15 term-input contract (rev-r1 §5, CI-enforced) -----------------------
# Every F term declares the decision-variable class it is POSED on. The
# authoritative partition is fixed by spec §5 (rev-r1) and checked by
# tests/invariants (_check_i15). A term is legal iff it either
#   (a) CONSUMES the full unit-resolved coupling pi  ("full-pi"), or
#   (b) is a MARGINAL of pi that provably factors through the occupancy O and
#       carries a WRITTEN factorization proof below ("marginal"), or
#   (c) is a per-SECTION gauge charge reading neither pi nor O ("gauge").
# "Premature aggregation / structure-deleting projection" — posing a term that
# the spec mandates on full pi (T1, T4) onto the marginal O instead — is the
# fidelity breach I-15 exists to forbid. There is no proof route for T1/T4.
TERM_INPUT_CONTRACT = {
    "T1": "full-pi",   # transport (GW) + circular metrical phase-displacement charge
    "T2": "marginal",  # mass conservation — a property of role x slot occupancy
    "T3": "marginal",  # spectral masking — a property of role x slot occupancy
    "T4": "full-pi",   # unit-successor continuity — needs which unit follows which
    "T5": "gauge",     # per-section transposition/phase cost; never per unit
}

# Written factorization proofs for every "marginal" term. Each states WHY the
# quantity is genuinely a function of the marginal O (and nothing finer), so no
# unit-resolved structure is silently deleted. _check_i15 additionally verifies
# each behaviorally: the term is invariant under any O-preserving pi rearrangement.
FACTORIZATION_PROOFS = {
    "T2": (
        "T2 = generalized-KL(O || a[k]*theta[k,:]). Mass conservation asks only "
        "how much role-k mass lands at slot s; that quantity IS O[k,s] by "
        "definition (O[k,s] = sum_units pi[u,k] q[u,s]). Two unit-couplings with "
        "equal O carry identical per-role-per-slot mass, hence identical T2. The "
        "term therefore factors through O with no loss of unit structure — mass "
        "is intrinsically a marginal observable."
    ),
    "T3": (
        "T3 = collision energy sum_{s,b} E[s,b]^2 - self, with E[s,b] = sum_k "
        "O[k,s] B[k,b]. Spectral masking is a property of how much band-b energy "
        "co-occurs at slot s; E is linear in O and reads no finer index than "
        "(role, slot). Equal O => equal E => equal T3. Masking is intrinsically a "
        "marginal (per-slot-per-band) observable; it does not see unit identity."
    ),
}


@dataclass
class FState:
    """Full corpus-time state F ranges over. Anchors carry ONLY support (D) and
    mass (a) — NO accumulator / pressure / momentum field (invariant I-3)."""
    D: np.ndarray                 # (M,M) anchor role-space cost (free support)
    a: np.ndarray                 # (M,) anchor masses
    B: np.ndarray                 # (M,n_bands) channel gains, rows on simplex
    theta: np.ndarray             # (M,S) anchor slot-profile target, rows on simplex
    pis: List[np.ndarray]         # per track: (K_t, M) coupling
    phase_off: np.ndarray         # (n_tracks,) integer gauge phase offset (slots)
    transpose: np.ndarray         # (n_tracks,) gauge transposition (pitch classes)

    @property
    def M(self) -> int:
        return self.a.shape[0]


def occupancy(state: FState, protos) -> np.ndarray:
    """O[k,s] = role k's mass at metrical slot s, summed over tracks, with each
    track's slot histogram rolled by its gauge phase offset (the phase section)."""
    M = state.M
    S = protos[0].slot_hist.shape[1]
    O = np.zeros((M, S))
    for t, P in enumerate(protos):
        q = P.slot_hist / (P.slot_hist.sum(1, keepdims=True) + 1e-12)  # (K,S) rows->1
        q = np.roll(q, int(state.phase_off[t]) % S, axis=1)
        O += state.pis[t].T @ q                                        # (M,S)
    return O


def term_T1(state: FState, protos) -> float:
    return float(sum(ot.gw_distortion(P.cost, state.D, state.pis[t])
                     for t, P in enumerate(protos)))


def term_T2(O: np.ndarray, state: FState) -> float:
    """Unbalanced-OT generalised-KL between role x slot occupancy O and the
    target a[k]*theta[k,:]. Penalises mass NOT conserved per role per slot; the
    unbalanced form permits creation/destruction at a price (no hard marginal)."""
    tgt = state.a[:, None] * state.theta + 1e-12
    o = O + 1e-12
    gkl = np.sum(o * np.log(o / tgt) - o + tgt)
    return float(LAMBDA["T2"] * gkl)


def term_T3(O: np.ndarray, state: FState) -> float:
    """Spectral masking: energy routed to (slot s, band b) is E[s,b]=sum_k O[k,s]
    B[k,b]. Co-scheduled units in the same band collide; cost is the quadratic
    collision sum_s sum_b E[s,b]^2 minus the non-colliding self-energy, so a role
    spreading across bands is cheaper than several roles piling into one band."""
    E = O.T @ state.B                       # (S, n_bands)
    self_e = (O.T ** 2) @ (state.B ** 2)    # (S, n_bands) non-cross part
    collision = np.sum(E ** 2) - np.sum(self_e)
    return float(LAMBDA["T3"] * collision)


def term_T4(O: np.ndarray, state: FState) -> float:
    """Continuity / run-continuation (tilted-Markov, Doob h-transform). Base
    continuation kernel W = exp(-D) tilts toward anchor-to-anchor transitions
    that are close in role space; the term REWARDS (negative cost) runs that
    continue smoothly across adjacent metrical slots."""
    W = np.exp(-state.D)
    S = O.shape[1]
    reward = 0.0
    for s in range(S):
        reward += float(O[:, s] @ W @ O[:, (s + 1) % S])
    return float(-LAMBDA["T4"] * reward)


def term_T5(state: FState) -> float:
    """Gauge-fixing cost, per SECTION (per track here), never per unit. Charges
    the magnitude of the applied gauge action: phase offset (slots) + a
    transposition penalty. Because the cross-track costs are transposition-
    quotiented (spec §3), transposition is inert on T1 and its optimum is the
    identity; the phase section is the live gauge at corpus time."""
    S = 8.0
    phase_cost = np.sum((np.asarray(state.phase_off, float) / S) ** 2)
    trans_cost = np.sum((np.asarray(state.transpose, float) / 12.0) ** 2)
    return float(LAMBDA["T5"] * (phase_cost + trans_cost))


def raw_terms(state: FState, protos) -> dict:
    """The five UNWEIGHTED term quantities (phi_i), before LAMBDA is applied.

    F = T1 + sum_i LAMBDA[Ti] * raw[Ti]  for i in {T2,T3,T4,T5}, with T1 the
    reference scale (implicit weight 1). This is the feature map the corpus-time
    NCE estimator (step d, spec §6) scores: it depends ONLY on the arrangement +
    frozen world, NOT on LAMBDA, so the weights can be fit contrastively without
    circularity. The sign convention matches F exactly: raw T4 = -(continuation
    reward) (<=0), so F's contribution is +LAMBDA[T4]*rawT4 = -LAMBDA[T4]*reward.
    Nothing here reads LAMBDA (verified: this function is LAMBDA-free)."""
    O = occupancy(state, protos)
    t1 = float(sum(ot.gw_distortion(P.cost, state.D, state.pis[t])
                   for t, P in enumerate(protos)))
    core = raw_terms_O(O, state.D, state.a, state.B, state.theta)
    t5 = float(np.sum((np.asarray(state.phase_off, float) / 8.0) ** 2)
               + np.sum((np.asarray(state.transpose, float) / 12.0) ** 2))
    return {"T1": t1, "T2": core["T2"], "T3": core["T3"], "T4": core["T4"], "T5": t5}


def raw_terms_O(O: np.ndarray, D: np.ndarray, a: np.ndarray, B: np.ndarray,
                theta: np.ndarray) -> dict:
    """The occupancy-dependent unweighted terms {T2,T3,T4} from a bare occupancy O
    (anchor×slot) and the frozen world. This is the SINGLE implementation of the
    T2/T3/T4 formulas; both f.raw_terms (from an FState) and the corpus-time
    estimator (from a role-space Arrangement's occupancy) delegate here, so a
    role-space negative is scored by exactly the same F terms as a real track."""
    tgt = a[:, None] * theta + 1e-12
    o = O + 1e-12
    t2 = float(np.sum(o * np.log(o / tgt) - o + tgt))
    E = O.T @ B
    self_e = (O.T ** 2) @ (B ** 2)
    t3 = float(np.sum(E ** 2) - np.sum(self_e))
    W = np.exp(-D)
    S = O.shape[1]
    rew = 0.0
    for s in range(S):
        rew += float(O[:, s] @ W @ O[:, (s + 1) % S])
    return {"T2": t2, "T3": t3, "T4": float(-rew)}


def F(state: FState, protos):
    """The single scalar F and its per-term decomposition (decomposition is
    instrumentation, not a second objective)."""
    O = occupancy(state, protos)
    t1 = term_T1(state, protos)
    t2 = term_T2(O, state)
    t3 = term_T3(O, state)
    t4 = term_T4(O, state)
    t5 = term_T5(state)
    total = t1 + t2 + t3 + t4 + t5
    return total, {"T1": t1, "T2": t2, "T3": t3, "T4": t4, "T5": t5, "F": total}
