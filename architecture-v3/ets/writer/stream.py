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
The settlement measure is p(O) ∝ exp(−F_col/T_s) per slot column, F_col = the
O-marginal terms (T2 mass-conservation + T3 masking) that provably factor
through the occupancy (spec §5 rev-r1). The writer first settles the frontier's
O-block to the tilted mode O* (certificate), then draws the emitted O by
sampling THAT SAME measure directly — not a Gaussian model of it — via the exact
1D conditional slices through the settled mode:

    for each role k:  g_k(x) = F_col(O* with O*_k := x) / T_s ,   x > 0
                      O_k ~  p_k(x) ∝ exp(−g_k(x))  by inverse-CDF on a grid,

with the grid spanning the plausible reach [~0, O*_k + z_run·s_k] and s_k =
sqrt(T_s·[H_O⁻¹]_kk) the per-role O-space Laplace std (H_O =
solver._d2F_dO2_slot(O*), the EXACT per-slot Hessian — the same F the settlement
descends). Directions of unreliable curvature (eigenvalues below the
numerical-rank tolerance M·eps·λ_max) get ZERO variance (s_k=0) and pin to the
mode. The grid support is STRICTLY POSITIVE (x_0>0), so every draw is strictly
positive: no slot is ever zeroed, no positive-orthant CLIP (max(·,floor)) and no
floor-fill exists — the seed-dependent dead-slot failure is impossible by
construction. z ~ N(0,1)^M is drawn once per column BEFORE the clamp/cold skip
and mapped u=Φ(z) → inverse-CDF, so rng alignment is independent of the clamp
pattern and temperature; same (world, tilt trajectory, seed) ⇒ bit-identical
tape (H-8). T_s divides F_col in the exponent, so it scales the looseness around
the mode exactly (T_s→0 concentrates the measure onto the mode — cold = the
settled optimum).

WHY THE EXACT CONDITIONAL SLICE, NOT A GAUSSIAN MODEL (measured, architecture-v3
finding; Table-6 harness on the psytech corpus, T_s=1). The measure is
near-boundary (per-role O*≈0.025, s_k≈0.07) and NON-Gaussian there: its true
per-role Gibbs std (≈0.090, reference log-space Metropolis) is ~1.27× WIDER than
the Laplace marginal s_k (≈0.071) — the boundary + gKL curvature give a heavier
positive tail than the quadratic model. So any Gaussian-model draw mis-matches
the true fluctuation the σ_φ instrument is calibrated to: the additive Gaussian
CLIPPED to the floor (std_bias 0.45, 36% clip → dead slots), its REFLECTION
O=|O*+ξ| (std_bias 0.50, folds the fold-mass so it is too WIDE), and the log
draw O=O*·exp(ξ) (std_bias 344, a ~50× mean blow-up) all fail. The O-terms
Hessian has ZERO T3 diagonal (H_kk = L2/O*_k, pure T2; T3 restricted to one axis
is affine), so the 1D conditional slice through the mode along role k IS the
exact per-role Gibbs marginal up to a linear tilt — sampling it by inverse-CDF
reproduces the true std (std_bias 0.09, at the reference sampler's own noise
floor) while staying strictly positive and mode-centred. The plausible reach is
tied to the SAME z_run the runaway halt uses (below): the sampler draws the true
measure RESTRICTED to the set the halt certifies as non-runaway, so a draw can
never exceed the runaway bound — one scale governs both, no second channel. See
the session report / proposed prereg revision (Fix C: exact 1D-conditional
inverse-CDF draw, superseding the reflected O-space Laplace).

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
import math
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..functional import f as ff
from ..functional import solver as sv
from . import phi as PHI
from .realize import FiberThreader, RealizationIndex
from .settle import settle_tape, _tape_state
from .tape import ClampSet, OutputGrid, TapeNode
from .tilt import TiltTerms, untilted


_SQRT2 = math.sqrt(2.0)
_GRID_N = 129            # inverse-CDF grid resolution for the 1D conditional slice


def _normal_cdf(z: np.ndarray) -> np.ndarray:
    """Standard-normal CDF Φ, dependency-free (stdlib erf; the engine core has no
    scipy). Maps the per-column N(0,1) draw to uniforms for inverse-CDF sampling
    without perturbing the rng-draw discipline (H-8)."""
    z = np.asarray(z, float)
    return 0.5 * (1.0 + np.array([math.erf(float(v) / _SQRT2) for v in z.ravel()])
                  ).reshape(z.shape)


def sample_conditional_column(o: np.ndarray, slot_state, T: float,
                              s_lap: np.ndarray, reach: float,
                              z: np.ndarray, n: int = _GRID_N) -> np.ndarray:
    """ONE deterministic, strictly-positive draw from the exact per-role 1D
    conditional slices of the per-slot Gibbs measure exp(−F_col/T) through the
    settled mode ``o`` (module docstring). This is the SINGLE sampler both the
    streaming writer and the Table-6 measurement invoke (apples-to-apples).

    For role k with per-role Laplace std s_lap[k]>0, build the potential
    g_k(x) = F_col(o with o_k:=x)/T on a positive grid [x0, o_k + reach·s_lap_k]
    — F_col via f.py's OWN terms (single source of truth, no re-derivation) — and
    inverse-CDF map u_k=Φ(z_k) → O_k. The grid starts strictly above 0 so the
    draw is strictly positive (no clamp, no floor-fill). Roles on a zero-variance
    direction (s_lap[k]=0) pin to the mode. z is the per-column N(0,1) vector."""
    M = o.shape[0]
    out = np.array(o, float)
    u = _normal_cdf(z)
    Ocol = np.array(o, float)
    for k in range(M):
        sk = float(s_lap[k])
        if sk <= 0.0:                      # unreliable-curvature axis: pin to mode
            continue
        xmax = float(o[k]) + reach * sk
        x = np.linspace(0.0, xmax, n)
        x[0] = xmax / (n * 50.0)           # strictly-positive support ⇒ draw > 0
        g = np.empty(n)
        col = Ocol.reshape(-1, 1)
        for i in range(n):
            col[k, 0] = x[i]
            g[i] = (ff.term_T2(col, slot_state) + ff.term_T3(col, slot_state)) / T
        col[k, 0] = o[k]
        g -= g.min()                       # stabilise exp; max exponent = 0
        p = np.exp(-g) * np.gradient(x)    # trapezoidal measure weights
        cdf = np.cumsum(p)
        cdf /= cdf[-1]
        uk = min(max(float(u[k]), 1e-12), 1.0 - 1e-12)
        out[k] = float(np.interp(uk, cdf, x))
    return out


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
        """Exact 1D-conditional inverse-CDF draw around the settled mode (module
        docstring). Returns (O, occ_bound): the sampled occupancy and the DERIVED
        plausible-max total occupancy Σ_{s,k}(O*_k + z_run·s_k) — the SAME z_run
        reach the sampler grid uses, so occ ≤ occ_bound by construction and the
        Fix-B runaway arm fires only on a genuine mis-produced occupancy.

        T_s scales the looseness (F_col/T_s in the exponent); clamped columns and
        cold (T_s≤0) columns are boundary conditions and do not fluctuate. z is
        drawn unconditionally (one M-vector per column, BEFORE the skip) so rng
        alignment is independent of the clamp pattern and temperature (H-8)."""
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
            # per-role O-space Laplace std s_k = sqrt(diag of the covariance
            # T·H_O⁻¹): sets BOTH the sampler grid reach (o_k + z_run·s_k) and the
            # Fix-B plausible-max bound Σ_k(o_k + z_run·s_k). One scale, no second
            # channel; the draw lives on [~0, o_k + z_run·s_k] ⇒ occ ≤ occ_bound.
            s_k = np.sqrt((V * V) @ var)
            slot_state = replace(state, theta=state.theta[:, s:s + 1])
            O[:, s] = sample_conditional_column(o, slot_state, T, s_k, z_run, z)
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
