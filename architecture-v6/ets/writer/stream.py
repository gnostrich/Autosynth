"""The streaming (causal) writer — the MZ image of the equilibrium object
(spec §7), one bar at a time.

Committed past = clamped cells. The frontier window (the next bar) is settled by
the SAME I-projection as the batch reduced form (``settle_tape`` — one settlement
implementation, invoked on a one-bar tape node), the SAME fiber threading
mechanism (``realize.FiberThreader``), and never rewrites committed tape. User
demands enter as clamped future cells through the SAME ClampSet species (I-7):
there is no second placement-injection channel.

CONTROL (I-1): each bar binds the latest ``TiltTerms`` (the Layer-0 tilt,
ets.writer.tilt) AT THE WRITE FRONTIER. Nothing lane-shaped exists here; the
engine converts panel messages to TiltTerms via ``tilt.layer0`` and hands the
result over. Control latency is therefore exactly the engine's declared L bars
(connector: Real-time typing).

TEMPERATURE (spec §8 lane 6: "sampling looseness around the settled optimum").
The settlement measure is p(a) ∝ exp(−F/T_s + Σλφ). The writer first settles
the frontier's O-block to the tilted mode (certificate), then draws the emitted
O from the GAUSSIAN (Laplace) approximation of that measure around the mode:

    O = O* + ξ,   ξ ~ N(0, T_s · H⁻¹) per slot column,

with H the EXACT per-slot Hessian of the O-terms (solver._d2F_dO2_slot — the
same F the settlement descends; the tilt is linear in O and adds no curvature),
clipped to the positive orthant (the constraint set; same species as the mirror
floor). Directions of unreliable curvature (eigenvalues below the standard
numerical-rank tolerance M·eps·λ_max) receive ZERO variance — fluctuation is
sampled only along directions whose curvature the settled optimum certifies;
this is conservative (never explosive) and documented. Sampling is exact-to-
leading-order equilibrium fluctuation, which is what makes the σ_φ calibration
(FDT units) meaningful: the untilted writer at T_s=1 has genuine thermal motion
in every non-degenerate φ direction. All draws come from a seeded Generator —
same (world, tilt trajectory, seed) ⇒ bit-identical tape (H-8).

STABILITY / STATE (spec §7, I-8): the working state is (runs in flight,
last-committed-use recency, previous frame) — bounded by MATERIAL HEARD
(≤ corpus units + bands + constants), never by elapsed time. `write_bar`
asserts the per-bar frontier F-descent certificate and the state bound every
bar; violation raises ``StreamHalt`` (halt-and-report, no recovery mode).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..functional import solver as sv
from . import phi as PHI
from .realize import FiberThreader, RealizationIndex
from .clamp import ClampTerms
from .settle import settle_tape, _tape_state
from .tape import ClampSet, OutputGrid, TapeNode
from .tilt import TiltTerms, untilted


class StreamHalt(RuntimeError):
    """Streaming stability violation (I-8): per-bar certificate failed or the
    working state grew beyond the material bound. Halt and report — there is
    deliberately no recovery mode (a recovery mode is a patch signature)."""


@dataclass
class BarResult:
    """One committed bar: its settled+sampled occupancy, fiber placements, φ
    statistics, and the settlement certificate evidence."""
    bar: int
    O: np.ndarray                                   # (M, S) committed occupancy
    rows: List[Tuple[int, int, int, int, float]]    # (slot, tid, uid, sec, mass)
    continues: List[bool]
    phi: Dict[str, object]                          # the five φ of this bar
    converged: bool
    monotone: bool
    n_iter: int
    wall_time_s: float = 0.0                        # production time (latency math)
    starved: Tuple[Tuple[int, int, int], ...] = ()  # (bar, role, band) whose fence
                                                    # emptied the choice set and was
                                                    # widened for that slot — recorded,
                                                    # never a silent no-op (prereg §2.1)


class StreamWriter:
    """Bar-by-bar causal writer over a frozen world (ets.writer.World).

    ``seed`` drives ALL sampling (temperature + fiber draws); with the same
    (world, tilt trajectory, clamps, seed) the emitted tape is bit-identical.
    """

    def __init__(self, world, seed: int = 0):
        self.world = world
        self.fstate = world.fstate
        self.M = int(world.M)
        self.s_phase = int(getattr(world, "s_phase", 8))
        self.seed = int(seed)
        self._rng = np.random.default_rng(np.random.SeedSequence(self.seed))
        self.threader = FiberThreader(world.index, world.fstate, self.s_phase,
                                      tilt=None, rng=self._rng)
        self.bar = 0
        self.prev_frame = PHI.GaugeFrame()          # v0: frozen identity frame
        self.frame = PHI.GaugeFrame()
        # I-8 material bound: runs in flight (≤ bands) + recency (≤ real units
        # heard, ≤ corpus units) + pending (≤ placements of one bar).
        self._n_corpus_units = sum(len(t.units) for t in world.tracks)
        self._n_bands = int(world.fstate.B.shape[1])

    # -- I-8: the working-state size and its material bound -------------------
    def state_size(self) -> int:
        return self.threader.state_size() + 2       # + frame pair (constants)

    def state_bound(self) -> int:
        per_bar_placements = self._n_bands * self.s_phase
        return self._n_corpus_units + self._n_bands + per_bar_placements + 2

    def _bar_grid(self) -> OutputGrid:
        return OutputGrid(sr=int(self.world.sr),
                          tatum_len=int(self.world.out_tatum_len),
                          n_slots=self.s_phase, s_phase=self.s_phase)

    def _sample_temperature(self, O_star: np.ndarray, state, tilt: TiltTerms,
                            clamp_mask: np.ndarray) -> np.ndarray:
        """Laplace draw around the settled mode (module docstring). T_s scales
        the covariance; clamped columns are boundary conditions and do not
        fluctuate. Consumes rng even coherently across bars (one draw per free
        column) so the stream is reproducible."""
        T = float(tilt.T_s)
        O = O_star.copy()
        M, S = O.shape
        # SECOND-MOMENT SHAPE (PREREG-sampler-covariance-xy): an optional
        # per-eigendirection anisotropy rescales the draw's variance along each
        # Hessian eigendirection. `tilt.a` is ordered STIFFEST-FIRST (a[0] scales
        # the largest-curvature direction) — a deterministic, world-independent
        # convention so the pad axes are stable. eigh returns w ASCENDING, so the
        # stiffest column is w's LAST; `order = argsort(-w)` lists eigh columns
        # stiffest→softest and `a_col[order] = a` aligns the stiffest-first vector
        # to the eigh column order. a=None ⇒ the branch is skipped entirely: the
        # exact current draw (same z, same rng alignment, same clamp handling, same
        # max(·,1e-12)) — byte-identical.
        a = None if tilt.a is None else np.asarray(tilt.a, float).reshape(-1)
        for s in range(S):
            z = self._rng.standard_normal(M)         # drawn unconditionally: keeps
            if clamp_mask[s] or T <= 0.0:            # rng alignment independent of
                continue                             # clamp pattern
            H = sv._d2F_dO2_slot(O_star[:, s], state)
            H = 0.5 * (H + H.T)
            w, V = np.linalg.eigh(H)
            tol = M * np.finfo(float).eps * float(np.max(np.abs(w)))
            var = np.where(w > tol, T / np.maximum(w, tol), 0.0)
            if a is None:
                xi = V @ (np.sqrt(var) * z)
            else:
                a_col = np.empty(M)                  # align stiffest-first a to eigh cols
                a_col[np.argsort(-w)] = a
                xi = V @ (np.sqrt(var * a_col) * z)
            O[:, s] = np.maximum(O_star[:, s] + xi, 1e-12)
        return O

    def write_bar(self, tilt: Optional[TiltTerms] = None,
                  clamps: Optional[ClampSet] = None,
                  fence: Optional[ClampTerms] = None) -> BarResult:
        """Settle, sample, and commit the next bar. ``clamps`` address slots
        WITHIN this bar (0..S-1 local indices), the single intervention channel
        (I-7). Returns the committed BarResult; raises StreamHalt on a failed
        certificate or state-bound violation.

        ``fence`` is the FEASIBLE-SET RESTRICTION carrier (PREREG-live-mode.md
        PART A) — a DIFFERENT species from ``clamps``: it restricts which
        candidates the fiber choice may draw from, then the unchanged measure
        runs over the survivors (A-5), where an I-7 ``clamps`` cell instead
        forces its exact unit and bypasses the choice entirely. This is pure
        passthrough: the carrier is handed to the threader and nothing here
        interprets it. None ⇒ no restriction ⇒ byte-identical (A-2/LM-1), and
        it is re-set every bar so a fence can never outlive its caller."""
        import time
        t0 = time.perf_counter()
        if tilt is None:
            tilt = untilted(self.M)
        bar = self.bar

        grid = self._bar_grid()
        tape = TapeNode(grid=grid, M=self.M, clamps=clamps or ClampSet())

        # (1) frontier settlement to the tilted mode — SAME settlement as batch.
        res = settle_tape(self.fstate, tape, tilt=tilt)
        if not (res.converged and res.monotone):
            raise StreamHalt(
                f"bar {bar}: frontier settlement failed its F-descent "
                f"certificate (converged={res.converged}, monotone={res.monotone})"
                " — halt and report (I-8); no uncertified bar is emitted.")

        # (2) temperature: sampling looseness around the settled optimum.
        theta_out = np.ascontiguousarray(
            self.fstate.theta[:, grid.phase_row()], float)
        state = _tape_state(self.fstate, theta_out)
        clamp_mask, _ = tape.clamps.as_mask_values(self.M, grid.n_slots)
        O = self._sample_temperature(res.O, state, tilt, clamp_mask)

        # (3) fiber block: the SAME threading mechanism as batch, tilted+seeded.
        self.threader.tilt = tilt
        self.threader.clamp = fence          # per-bar; None ⇒ no restriction
        del self.threader.starved[:]         # this bar's starvation only
        rows: List[Tuple[int, int, int, int, float]] = []
        continues: List[bool] = []
        for s_local in range(grid.n_slots):
            s_global = bar * self.s_phase + s_local
            r, c = self.threader.place_slot(
                s_global, O[:, s_local],
                clamp_unit=(tape.clamps.unit_demands.get(s_local)))
            # re-express rows on the global grid (place_slot already gets the
            # global slot for phase/bar bookkeeping; rows carry it verbatim).
            rows.extend(r)
            continues.extend(c)

        # (4) the bar's φ statistics (Layer-0 observables; recency BEFORE commit
        #     — φ_novelty reads the committed tape, not this bar).
        keys = {(int(t), int(u)) for (_s, t, u, _sec, _m) in rows}
        arrangement = PHI.BarArrangement(
            O_bar=O, placements=tuple(
                (int(s) % self.s_phase, 0, int(t), int(u), float(m))
                for (s, t, u, _sec, m) in rows),
            continues=tuple(continues),
            frame=self.frame, prev_frame=self.prev_frame,
            recency=self.threader.recency_snapshot(keys, bar),
            s_phase=self.s_phase)
        phis = PHI.phi_all(arrangement)

        # (5) commit: recency state absorbs the bar; frame carries (v0: identity).
        self.threader.commit_bar(bar)
        self.prev_frame = self.frame
        self.bar += 1

        # (6) I-8 stability: bounded state growth by MATERIAL, not time.
        if self.state_size() > self.state_bound():
            raise StreamHalt(
                f"bar {bar}: working-state size {self.state_size()} exceeded the "
                f"material bound {self.state_bound()} — state growth on input "
                "that brought no new material is a broken instrument (I-8); "
                "halt and report.")

        return BarResult(bar=bar, O=O, rows=rows, continues=continues, phi=phis,
                         converged=res.converged, monotone=res.monotone,
                         n_iter=res.n_iter,
                         wall_time_s=time.perf_counter() - t0,
                         starved=tuple(self.threader.starved))

    @property
    def bar_samples(self) -> int:
        return self.s_phase * int(self.world.out_tatum_len)

    @property
    def bar_seconds(self) -> float:
        return self.bar_samples / float(self.world.sr)
