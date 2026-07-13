"""Batch (non-causal) settlement of the output tape (spec §5 batch mode, §7
reduced to the batch first sample; connector: "for the FIRST sample, settle the
WHOLE tape in BATCH (non-causal) to F-equilibrium").

This is the REDUCED FORM of the streaming writer for the "lanes constant" case
with u=0 (no tilt). The tape node's free cells are its per-slot role occupancy
``O_tape : (M, S_out)``; the anchors (D, a, B, theta) are FROZEN (built at step c,
input-only). We run a block-coordinate I-PROJECTION on ``O_tape`` — the tape's
one free block — to a LYAPUNOV F-DESCENT CERTIFICATE, in the field of the frozen
anchors.

Single-authority discipline, concretely:
  * The descent quantity is the single functional F itself: its O-dependent terms
    ``f.term_T2 + f.term_T3 + f.term_T4`` (T1 is the input-tracks' GW transport to
    the frozen anchors — constant w.r.t. the tape's cells; T5 is the tape gauge,
    identity at u=0). We call f.py's OWN term functions; nothing is re-derived.
  * The gradient is ``solver._dF_dO`` — the SAME dF/dO the corpus solver uses for
    its pi block. The tape-O update is a new BLOCK (the tape is a new node), not a
    new objective.
  * ``f.LAMBDA`` is read LIVE inside those term functions and inside the gradient,
    so the weights that land from step d auto-apply here with no edit.
  * The accept guard is a comparison of F values only (mirror-descent step with an
    adaptive rate, halved on any non-decrease) — a genuine Lyapunov certificate,
    identical in spirit to ``solver.batch_solve``'s guard.

Each I-projection step is entropic-mirror (multiplicative), i.e. a KL projection
of the current occupancy against the F-gradient — the same I-projection family as
Sinkhorn/exponentiated-gradient in the corpus solver. T2 is UNBALANCED (no hard
marginal), so free mirror descent under the Lyapunov guard is the faithful reduced
update; the guard, not a fixed step, is the whole termination theory.

CONTROL ENTRY (I-1). The ONLY control parameter is ``u`` — the h-transform tilt
(spec §1, §8). This batch reduced form is defined at u=0. The Layer-0 tilt map
(connector) is a PARALLEL build; a non-zero ``u`` here raises rather than fake a
second control path. The single jack exists; its map is deferred, not bypassed.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import List, Optional
import numpy as np

from ..functional import f as ff
from ..functional import solver as sv
from .tape import TapeNode


@dataclass
class SettleResult:
    O: np.ndarray                 # (M, S_out) settled tape occupancy
    trace: List[float]            # F(O) after every accepted/attempted step (monotone)
    terms_final: dict             # per-term F decomposition at the settled O
    n_iter: int
    converged: bool
    clamped_slots: List[int]
    monotone: bool


def _tape_state(fstate, theta_out: np.ndarray):
    """A frozen-anchor state whose theta is tiled onto the output grid. Only
    (a, B, D, theta) are read by f.term_T2/T3/T4 and solver._dF_dO; the tape has
    no pis/gauge of its own in this reduced (identity-gauge, u=0) form."""
    return replace(fstate, theta=theta_out)


def _F_O(O: np.ndarray, state) -> tuple:
    """The O-dependent part of the SINGLE functional F, via f.py's own terms.
    Returns (scalar, decomposition). LAMBDA read live inside each term."""
    t2 = ff.term_T2(O, state)
    t3 = ff.term_T3(O, state)
    t4 = ff.term_T4(O, state)
    return t2 + t3 + t4, {"T2": t2, "T3": t3, "T4": t4, "F_O": t2 + t3 + t4}


def settle_tape(fstate, tape: TapeNode, u: Optional[np.ndarray] = None,
                max_iter: int = 600, eta0: float = 0.25,
                tol: float = 1e-10, floor: float = 1e-12) -> SettleResult:
    """Settle the whole tape in batch to an F-descent certificate (u=0).

    ``fstate``: frozen world FState (anchors D, a, B, theta from step c).
    ``tape``  : the (N+1)-th track-typed node (grid + clamp interface).
    ``u``     : tilt (single control jack). None / all-zero => the untilted
                reduced form. A non-zero tilt raises (Layer-0 map is parallel).
    """
    if u is not None and np.any(np.asarray(u, float) != 0.0):
        raise NotImplementedError(
            "non-zero tilt u requires the Layer-0 tilt map (connector), a parallel "
            "build; this batch reduced form is defined at u=0. The single control "
            "jack exists here; its map is deferred, not bypassed (I-1).")

    M = int(tape.M)
    S_out = int(tape.grid.n_slots)
    if fstate.a.shape[0] != M:
        raise ValueError(f"tape M={M} != world anchor count {fstate.a.shape[0]}")

    # tiled anchor field on the output grid (theta WITHOUT a; term_T2 applies a).
    theta_out = np.ascontiguousarray(fstate.theta[:, tape.grid.phase_row()], float)
    state = _tape_state(fstate, theta_out)

    # boundary conditions (clamped cells) — same TYPE as settled cells (I-7).
    mask, vals = tape.clamps.as_mask_values(M, S_out)
    clamped = np.where(mask)[0].tolist()

    # init at the frozen anchor equilibrium (= the T2 target); a defensible,
    # decision-free starting point. Clamped columns pinned to their demand.
    O = np.maximum(fstate.a[:, None] * theta_out, floor)
    if mask.any():
        O[:, mask] = np.maximum(vals[:, mask], 0.0)

    F_cur, _ = _F_O(O, state)
    trace = [float(F_cur)]
    eta = float(eta0)
    n_iter = 0
    converged = False

    for n_iter in range(1, max_iter + 1):
        g = sv._dF_dO(O, state)                       # dF/dO of T2+T3+T4 (LAMBDA live)
        step = np.clip(-eta * g, -50.0, 50.0)         # mirror step, exp-safe
        O_cand = np.maximum(O * np.exp(step), floor)
        if mask.any():                                # re-impose clamped cells
            O_cand[:, mask] = np.maximum(vals[:, mask], 0.0)

        F_cand, _ = _F_O(O_cand, state)
        if F_cand <= F_cur + 1e-12:                   # Lyapunov accept guard
            rel = abs(F_cur - F_cand) / (abs(F_cur) + 1e-12)
            O, F_cur = O_cand, F_cand
            trace.append(float(F_cur))
            if rel < tol:
                converged = True
                break
        else:                                         # reject: shrink the rate
            eta *= 0.5
            trace.append(float(F_cur))
            if eta < 1e-6:
                converged = True
                break

    _, terms = _F_O(O, state)
    tr = np.asarray(trace)
    monotone = bool(np.all(np.diff(tr) <= 1e-9))
    return SettleResult(O=O, trace=[float(x) for x in trace], terms_final=terms,
                        n_iter=n_iter, converged=converged,
                        clamped_slots=clamped, monotone=monotone)
