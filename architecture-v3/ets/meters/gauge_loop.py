"""loop[g] — committed-region LOOP-HOLONOMY meter (directive-v1 feature 2,
STAGE 0 shadow). The other half of the drift-meter split (see ``gauge_slide``):
slide[g] reports the frame sliding along its gauge orbit; THIS jack reports
genuine holonomy — loops of settled coupling traffic that fail to close.

TIP-CHECK VERDICT (committed-region cycle structure, checked before building —
inspected ets/writer/settle.py, realize.py, ets/render/schedule.py at tip):

  * The architecture is a STAR by law (spec §4: all cross-track traffic
    factors through the anchors; no direct pairwise coupling exists anywhere),
    so no pairwise settled couplings live in committed state — and none are
    fabricated here.
  * The settled coupling that DOES exist is the tape node's own coupling to
    the anchor star: ``SettleResult.O : (M, S_out)`` (settle.py), returned by
    ``generate_batch`` alongside the Schedule — i.e. available at the exact
    point where meters/sidecars are computed, with NO new persistent state.
    (The Schedule itself carries placements + sections only; O is settlement
    output, and in the streaming writer spec §7 already mandates "anchor
    occupancies" as state, so per-bar committed O columns are spec-required
    state, not meter-added state.)
  * CYCLES therefore exist as paths THROUGH the star: each committed BAR is a
    node whose settled coupling block is its slot-phase x role occupancy;
    bar_i -> anchors -> bar_j is a genuine length-2 path in the real coupling
    graph, and closed bar cycles [b0, b1, ..., bt, b0] are genuine cycles.
    Verdict: cycle structure EXISTS in committed state without new state.

THE METER. Transplant of the G2 loop-defect integrator
(``holonomy.loop_defect`` + ``holonomy.barycentric_map`` — the same math, from
the same module), run per bar on the settled coupling restricted to the
committed region:

  * bar node i: pi_i = O[:, i*S:(i+1)*S]^T  (S x M; slot-phase -> role mass),
    slot masses m_i = pi_i 1, role masses r_i = pi_i^T 1. A bar node is one
    full metrical circle; a trailing partial bar is not yet a node.
  * star-factored edge (i -> j): the composed coupling through the anchors,
    pi_ij = diag(m_i) . barycentric(pi_i, m_i) . barycentric(pi_j^T, r_j) —
    forward hop bar_i -> anchors, then the Bayes reversal anchors -> bar_j.
    Settled quantities only; nothing pairwise is invented.
  * bar-internal metric: the circular metrical distance between slot phases,
    C[p,q] = min(|p-q|, S-|p-q|) / S — derived from the metrical-circle
    cardinality S alone (the only constant in this module).
  * per committed bar t: the defect of the committed cycle [0, 1, ..., t, 0]
    (the trajectory closed at home), ANTISYMMETRIZED over cycle orientation:

        loop_g[t] = defect(0 -> 1 -> ... -> t -> 0)
                  - defect(0 -> t -> ... -> 1 -> 0)

    Antisymmetrization keeps only the orientation-odd (curvature) part and
    annihilates the orientation-even residual exactly: a 2-bar cycle is its
    own reversal (identically 0 — the G2 "edge residual" floor is 0 here by
    construction, not by calibration), and detailed-balance traffic (identical
    bars, or bars sharing one role-mass profile) closes both orientations
    equally.

GLOBAL-GAUGE QUOTIENT (exact, by construction): a global metrical phase roll
cyclically permutes every bar's slot axis and conjugates C (circulant) — the
defect is invariant; a global loudness scale cancels in every barycentric
normalization and in the final mass-weighted average; a global anchor
relabeling is summed out by the star composition; transposition never appears
(no chroma coordinate exists in these objects, I-2).

Read-only instrumentation (spec §9, I-5, I-14): imports ONLY numpy and its
sibling ``holonomy`` module; takes no F-weights; feeds nothing back into any
objective, gradient, or settlement decision.
"""
from __future__ import annotations
from typing import Dict, List, Tuple
import numpy as np

from .holonomy import barycentric_map, loop_defect


def bar_blocks(O: np.ndarray, s_phase: int
               ) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Split the settled tape occupancy ``O : (M, n_slots)`` into committed bar
    nodes: per COMPLETE bar i, the coupling block pi_i : (S, M) (slot-phase ->
    role settled mass) and its slot-mass marginal m_i : (S,). A trailing
    partial bar is not a node (a bar node is one full metrical circle)."""
    O = np.asarray(O, float)
    if O.ndim != 2:
        raise ValueError("O must be (M, n_slots)")
    S = int(s_phase)
    n_bars = O.shape[1] // S
    pis, masses = [], []
    for i in range(n_bars):
        pi = O[:, i * S:(i + 1) * S].T          # (S, M)
        pis.append(pi)
        masses.append(pi.sum(axis=1))            # (S,)
    return pis, masses


def metrical_cost(s_phase: int) -> np.ndarray:
    """Bar-internal metric: circular distance between slot phases, in circle
    units — C[p,q] = min(|p-q|, S-|p-q|) / S. Derived from the metrical-circle
    cardinality S only (no free constant)."""
    S = int(s_phase)
    p = np.arange(S)
    d = np.abs(p[:, None] - p[None, :])
    return np.minimum(d, S - d) / float(S)


def star_edge(pis: List[np.ndarray], masses: List[np.ndarray],
              i: int, j: int) -> np.ndarray:
    """The composed settled coupling bar_i -> (anchors) -> bar_j: forward hop =
    barycentric map of bar i's coupling; return hop = the Bayes reversal of bar
    j's coupling (normalized by ITS OWN anchor-side marginal r_j). Source
    marginal of the result is m_i. Settled quantities only — this is a path in
    the real star coupling graph, not a fabricated pairwise coupling."""
    P_iA = barycentric_map(pis[i], masses[i])                 # (S, M)
    r_j = pis[j].sum(axis=0)                                   # (M,)
    P_Aj = barycentric_map(pis[j].T, r_j)                      # (M, S)
    return masses[i][:, None] * (P_iA @ P_Aj)                  # (S, S)


def loop_g(O: np.ndarray, s_phase: int) -> np.ndarray:
    """Per-bar committed-region loop holonomy CV (see module docstring).

    ``O`` is the settled tape occupancy restricted to the committed region
    (settlement-side; never a tape-audio quantity). Returns (n_bars,) with
    loop_g[t] = the antisymmetrized defect of the committed cycle
    [0, ..., t, 0]; loop_g[0] = 0 (no cycle), loop_g[1] = 0 exactly (a 2-cycle
    is its own reversal)."""
    pis, masses = bar_blocks(O, s_phase)
    n_bars = len(pis)
    out = np.zeros(n_bars)
    if n_bars < 3:
        return out
    C = metrical_cost(s_phase)
    costs = [C] * n_bars
    edges: Dict[Tuple[int, int], np.ndarray] = {}

    def edge(a: int, b: int) -> np.ndarray:
        if (a, b) not in edges:
            edges[(a, b)] = star_edge(pis, masses, a, b)
        return edges[(a, b)]

    for t in range(2, n_bars):
        fwd = list(range(t + 1)) + [0]
        rev = [0] + list(range(t, 0, -1)) + [0]
        coup = {(a, b): edge(a, b)
                for cyc in (fwd, rev) for a, b in zip(cyc[:-1], cyc[1:])}
        d_f = loop_defect(costs, masses, coup, fwd)
        d_r = loop_defect(costs, masses, coup, rev)
        out[t] = d_f - d_r
    return out
