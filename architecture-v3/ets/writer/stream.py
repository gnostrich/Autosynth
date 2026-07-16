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
O from the Laplace approximation of that measure around the mode, in O
coordinates, REFLECTED into the positive orthant (the constraint set):

    O = |O* + ξ|,   ξ ~ N(0, T_s · H_O⁻¹) per slot column,

with H_O = solver._d2F_dO2_slot(O*) — the EXACT per-slot Hessian of the O-terms
(the same F the settlement descends; the tilt is linear in O and adds no
curvature). Directions of unreliable curvature (eigenvalues below the
numerical-rank tolerance M·eps·λ_max) receive ZERO variance — conservative,
never explosive. Reflection at 0 keeps O STRICTLY POSITIVE for every draw (|·| >
0 a.s.): no slot is ever zeroed, no positive-orthant CLIP (max(·,floor)) exists,
so the seed-dependent dead-slot failure (a negative additive draw floored to
1e-12) is impossible by construction. z is drawn once per column BEFORE the
clamp/cold skip, so rng alignment is independent of the clamp pattern and
temperature; same (world, tilt trajectory, seed) ⇒ bit-identical tape (H-8).

WHY REFLECTION, NOT A LOG/MIRROR DRAW (measured, architecture-v3 finding). The
Laplace covariance in O-coordinates is the true measure's second-order model on
the constraint set; the near-boundary mode (per-cell occupancy O*≈0.025 with
O-space std ≈0.07, i.e. σ/O*≈2.8 on the psytech corpus) makes ~1/3 of a raw
Gaussian draw negative, which the old max(·,floor) clip turned into dead slots.
A LOG-space draw O=O*·exp(ξ) is positivity-clean but INVALID at this scale: its
mean is O*·exp(diag(Σ)/2), and with σ_log≈2.8 that is a ~50× occupancy inflation
(measured: per-bar density mean 58 vs mode 1.0, region σ up to 413) — it does not
sample AROUND the mode, it blows the mode up. Reflection is the positive-orthant
folding of the O-space Gaussian: it preserves the mode scale (density mean ≈2.4×
mode — the intrinsic near-boundary adjustment, not a blow-up), reproduces the
calibrated fluctuation the σ_φ instrument expects (region σ≈0.13), and zeroes no
slot. Bug-1's runaway is driven by the TILTED MODE size (mis-calibrated λ), not
by the draw — it is handled by the recalibrated σ_φ (bounded λ) and the halt
below, which is the correct division of labor. See the session report /
proposed prereg revision (Fix C: reflected O-space Laplace, not log-space).

STREAMHALT ON NON-FINITE / RUNAWAY (spec §7 halt-and-report; never emit garbage
to the speakers). After the sample, `write_bar` raises ``StreamHalt`` if the
occupancy is (i) non-finite (any NaN/inf — a free, always-valid check), or
(ii) a RUNAWAY beyond a FINITE bound DERIVED from the machine's own scales:
the reflected draw's plausible-max total occupancy Σ_{s,k}(O*_k + z_run·s_k) —
where O* is the certified settled mode (its mass O*.sum() equals the world total
anchor mass a.sum() untilted), s_k = sqrt(T_s·[H_O⁻¹]_kk) is role k's O-space
std, and z_run = sqrt(2 ln N_draws) is the asymptotic expected maximum of
N_draws = M·S·(corpus bars) standard normals (so per-bar draws sit well under the
run-scale bound — natural headroom, no hand-set constant). Since |O*+ξ| ≤
O* + |ξ| ≤ O* + z_run·s componentwise, an occupancy beyond this bound is a draw
the sampler could not plausibly have produced from the certified mode — a
runaway; halt and report.

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
        # Runaway-halt scale (Fix B): the log-space sampler draws M·s_phase
        # standard normals per bar; over the corpus horizon the number of draws
        # is N_draws = M·s_phase·(corpus bars). z_run = sqrt(2 ln N_draws) is the
        # asymptotic expected maximum of that many standard normals — the
        # plausible-max draw magnitude for the whole run. Checking each bar
        # against this run-scale magnitude leaves natural headroom (a per-bar max
        # is ~sqrt(2 ln(M·s_phase)) ≪ z_run) with no hand-set constant.
        n_corpus_bars = sum(int(t.units["bar"].max()) + 1 for t in world.tracks)
        n_draws = max(2, self.M * self.s_phase * int(n_corpus_bars))
        self._z_run = float(np.sqrt(2.0 * np.log(n_draws)))

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
                            clamp_mask: np.ndarray) -> Tuple[np.ndarray, float]:
        """Reflected O-space Laplace draw around the settled mode (module
        docstring). Returns (O, occ_bound): the sampled occupancy and the
        DERIVED plausible-max total occupancy Σ_{s,k}(O*_k + z_run·s_k) the draw
        could produce this bar (Fix B runaway reference).

        T_s scales the covariance; clamped columns and cold (T_s≤0) columns are
        boundary conditions and do not fluctuate. z is drawn unconditionally (one
        M-vector per column, BEFORE the skip) so rng alignment is independent of
        the clamp pattern and temperature (H-8)."""
        T = float(tilt.T_s)
        O = O_star.copy()
        M, S = O.shape
        z_run = self._z_run
        occ_bound = 0.0
        for s in range(S):
            z = self._rng.standard_normal(M)         # drawn unconditionally: keeps
            o = O_star[:, s]                         # rng alignment independent of
            if clamp_mask[s] or T <= 0.0:            # clamp pattern / temperature
                occ_bound += float(o.sum())          # pinned column: no fluctuation
                continue
            H = sv._d2F_dO2_slot(o, state)           # H_O = d²F_O/dO² (this slot)
            H = 0.5 * (H + H.T)
            w, V = np.linalg.eigh(H)
            tol = M * np.finfo(float).eps * float(np.max(np.abs(w)))
            var = np.where(w > tol, T / np.maximum(w, tol), 0.0)
            xi = V @ (np.sqrt(var) * z)              # O-space perturbation
            O[:, s] = np.abs(o + xi)                 # reflect at 0: strictly > 0 a.s.
            # per-role O-space std s_k = sqrt(diag of the covariance T·H_O⁻¹);
            # plausible-max column mass Σ_k(O*_k + z_run·s_k) (Fix B bound):
            # |o+xi| ≤ o + |xi| ≤ o + z_run·s_k component-wise.
            s_k = np.sqrt((V * V) @ var)
            occ_bound += float(np.sum(o + z_run * s_k))
        return O, occ_bound

    def write_bar(self, tilt: Optional[TiltTerms] = None,
                  clamps: Optional[ClampSet] = None) -> BarResult:
        """Settle, sample, and commit the next bar. ``clamps`` address slots
        WITHIN this bar (0..S-1 local indices), the single intervention channel
        (I-7). Returns the committed BarResult; raises StreamHalt on a failed
        certificate or state-bound violation."""
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
        O, occ_bound = self._sample_temperature(res.O, state, tilt, clamp_mask)

        # (2b) HALT-AND-REPORT on non-finite or runaway occupancy (Fix B) —
        #      BEFORE the fiber block or any commit, so garbage never reaches the
        #      render/speakers. (i) non-finite is free and always valid; (ii) the
        #      runaway bound is DERIVED (never hand-set): the certified settled
        #      mode mass M* = res.O.sum() (untilted == world total mass a.sum())
        #      times the log-space sampler's plausible-max inflation occ_bound.
        if not np.all(np.isfinite(O)):
            raise StreamHalt(
                f"bar {bar}: non-finite occupancy after temperature sampling "
                f"(NaN/inf) — halt and report; no non-finite bar is emitted.")
        occ = float(O.sum())
        if occ > occ_bound:
            mode_mass = float(res.O.sum())
            raise StreamHalt(
                f"bar {bar}: runaway occupancy O.sum={occ:.3e} exceeds the "
                f"derived plausible-max {occ_bound:.3e} "
                f"(= Σ_k(M*_k + z_run·s_k), z_run={self._z_run:.3f}) around the "
                f"certified settled mode mass M*={mode_mass:.3e} "
                f"(untilted M*==world total mass a.sum()={float(self.fstate.a.sum()):.3e})"
                f" — the sampler could not have produced this from the mode; "
                f"halt and report (spec §7). No runaway bar is emitted.")

        # (3) fiber block: the SAME threading mechanism as batch, tilted+seeded.
        self.threader.tilt = tilt
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
                         wall_time_s=time.perf_counter() - t0)

    @property
    def bar_samples(self) -> int:
        return self.s_phase * int(self.world.out_tatum_len)

    @property
    def bar_seconds(self) -> float:
        return self.bar_samples / float(self.world.sr)
