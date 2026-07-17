"""Table-6 declared-approximation measurement (litepaper Table 6; C.ii of the
architecture-v3 temperature-sampler prereg).

The litepaper / REGISTRY (stream-laplace-sampler) DECLARED the streaming
temperature sampler's approximation as "~0.11 std bias, ~13% clip at T_s=1"
without a committed measurement script. This constructs that measurement from
first principles and applies it IDENTICALLY to the OLD additive-Gaussian sampler
(O = max(O* + xi, floor)) and the NEW log-space sampler (O = O*·exp(xi)) so the
before/after is apples-to-apples. Both are second-order (Laplace) approximations
of the per-slot Gibbs measure

    p(O_col) ∝ exp( −F_col(O_col) / T ),   F_col = term_T2 + term_T3 (this slot),

around the settled mode O*. The two numbers, each defined once and computed the
same way for both samplers:

  CLIP RATE = fraction of sampled OCCUPANCY COMPONENTS that land at (or below)
    the positive-orthant floor 1e-12. For the OLD sampler this is exactly the
    max(·, floor) clip fraction; for the NEW sampler O=O*·exp(xi) is strictly
    positive, so it is ~0 by construction (nonzero only if a mode component is
    itself already at the floor). Same definition, both samplers.

  STD BIAS = mean over components k of |std_sampler_k − std_true_k|, expressed in
    units of a typical true std (mean_k std_true_k). std_true_k is the per-slot
    Gibbs standard deviation of component k, estimated by a REFERENCE sampler
    (log-space random-walk Metropolis on exp(−F_col/T), long well-mixed chain)
    that is INDEPENDENT of both approximations — the ground truth both are
    scored against. A sampler that matches the true local fluctuation has std
    bias 0; a clipped Gaussian that truncates the true positive-support measure
    is biased.

Run: python3 scripts/measure_table6.py            (synthetic CI world; fast)
     ETS_CACHE=/…/cache/ingest python3 scripts/measure_table6.py --corpus
"""
from __future__ import annotations
import os, sys, glob
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import replace
from ets.functional import f as ff
from ets.functional import solver as sv
from ets.writer.stream import (_normal_cdf, conditional_column_grids,
                               laplace_column_std)

FLOOR = 1e-12


def _slot_state(fstate, theta_col):
    return replace(fstate, theta=np.ascontiguousarray(theta_col.reshape(-1, 1), float))


def _F_col(o, state) -> float:
    O = np.asarray(o, float).reshape(-1, 1)
    return ff.term_T2(O, state) + ff.term_T3(O, state)


def _old_additive_draw(o, state, T, z):
    """OLD sampler (pre-fix): additive Gaussian in O-coordinates around the mode,
    clamped to the positive-orthant floor. Same eigenvalue-floor rule as shipped."""
    M = o.shape[0]
    H = 0.5 * (sv._d2F_dO2_slot(o, state) + sv._d2F_dO2_slot(o, state).T)
    w, V = np.linalg.eigh(H)
    tol = M * np.finfo(float).eps * float(np.max(np.abs(w)))
    var = np.where(w > tol, T / np.maximum(w, tol), 0.0)
    xi = V @ (np.sqrt(var) * z)
    raw = o + xi
    return np.maximum(raw, FLOOR), raw


def _new_reflect_draw(o, state, T, z):
    """NEW sampler (Fix C, architecture-v3): reflected O-space Laplace draw,
    O = |O* + xi|, xi ~ N(0, T·H_O⁻¹). Strictly > 0 a.s.; mode-preserving (no
    exp() mean blow-up); same rng draw as the old additive sampler."""
    M = o.shape[0]
    H = 0.5 * (sv._d2F_dO2_slot(o, state) + sv._d2F_dO2_slot(o, state).T)
    w, V = np.linalg.eigh(H)
    tol = M * np.finfo(float).eps * float(np.max(np.abs(w)))
    var = np.where(w > tol, T / np.maximum(w, tol), 0.0)
    xi = V @ (np.sqrt(var) * z)
    return np.abs(o + xi), None


def _new_log_draw(o, state, T, z):
    """The REJECTED log-space draw O=O*·exp(xi) — kept only to MEASURE its
    invalidity (mean blow-up) alongside the shipped reflected sampler."""
    M = o.shape[0]
    H = 0.5 * (sv._d2F_dO2_slot(o, state) + sv._d2F_dO2_slot(o, state).T)
    Hy = (o[:, None] * H) * o[None, :]
    Hy = 0.5 * (Hy + Hy.T)
    w, V = np.linalg.eigh(Hy)
    tol = M * np.finfo(float).eps * float(np.max(np.abs(w)))
    var = np.where(w > tol, T / np.maximum(w, tol), 0.0)
    xi = V @ (np.sqrt(var) * z)
    return o * np.exp(xi), None


def _reference_true_std(o, state, T, n=60000, burn=5000, seed=0):
    """Ground-truth per-component std of the per-slot Gibbs measure
    exp(−F_col/T), by log-space random-walk Metropolis (independent of both
    approximations). Step size auto-scaled to the Laplace log-covariance so the
    chain mixes; acceptance reported by the caller if wanted."""
    rng = np.random.default_rng(seed)
    M = o.shape[0]
    H = 0.5 * (sv._d2F_dO2_slot(o, state) + sv._d2F_dO2_slot(o, state).T)
    Hy = (o[:, None] * H) * o[None, :]
    w, V = np.linalg.eigh(Hy)
    tol = M * np.finfo(float).eps * float(np.max(np.abs(w)))
    std_dir = np.sqrt(np.where(w > tol, T / np.maximum(w, tol), 0.0))
    step = 0.5                                   # in units of the log-std ellipsoid
    y = np.log(np.maximum(o, FLOOR))
    Fy = _F_col(np.exp(y), state)
    samples = np.empty((n, M))
    acc = 0
    for i in range(n + burn):
        prop = y + V @ (step * std_dir * rng.standard_normal(M))
        Fp = _F_col(np.exp(prop), state)
        # target in y: p(y) ∝ exp(−F(e^y)/T) · Π e^{y_k} (log-Jacobian) — the
        # measure on O pushed to y; the Jacobian keeps the reference honest.
        logratio = -(Fp - Fy) / T + float(np.sum(prop - y))
        if np.log(rng.uniform() + 1e-300) < logratio:
            y, Fy = prop, Fp
            acc += 1
        if i >= burn:
            samples[i - burn] = np.exp(y)
    return samples.std(axis=0, ddof=1), acc / (n + burn), samples.mean(axis=0)


def _settled_columns(world, n_bars=3):
    from ets.writer import OutputGrid, TapeNode, settle_tape
    from ets.writer.tape import S_PHASE
    grid = OutputGrid(sr=world.sr, tatum_len=world.out_tatum_len,
                      n_slots=n_bars * S_PHASE)
    tape = TapeNode(grid=grid, M=world.M)
    res = settle_tape(world.fstate, tape)
    theta_out = np.ascontiguousarray(
        world.fstate.theta[:, grid.phase_row()], float)
    return res.O, theta_out


def _run_reach(world, s_phase=8):
    """The plausible-reach scale z_run = sqrt(2 ln N_draws) the streaming writer
    (StreamWriter) uses on THIS world, replicated identically so the shipped
    conditional sampler is measured on its true operating reach (apples-to-apples
    with the writer). N_draws = M·s_phase·(corpus bars)."""
    M = int(world.M)
    sp = int(getattr(world, "s_phase", s_phase))
    n_bars = sum(int(t.units["bar"].max()) + 1 for t in world.tracks)
    n_draws = max(2, M * sp * int(n_bars))
    return float(np.sqrt(2.0 * np.log(n_draws)))


def measure(world, T=1.0, n_draws=20000, seed=7, ref_n=40000):
    O_star, theta_out = _settled_columns(world)
    M, S = O_star.shape
    reach = _run_reach(world)
    rng = np.random.default_rng(seed)
    # aggregate over slot columns (the ensemble the sampler faces per bar)
    old_clip = 0; old_total = 0; new_clip = 0; new_total = 0
    log_clip = 0; cond_clip = 0
    old_bias = []; new_bias = []; log_bias = []; cond_bias = []; ref_bias = []
    old_mr = []; new_mr = []; log_mr = []; cond_mr = []; ref_mr = []  # mean/mode
    for s in range(S):
        o = O_star[:, s]
        state = _slot_state(world.fstate, theta_out[:, s])
        if _F_col(o, state) == 0.0 and float(o.sum()) == 0.0:
            continue
        Z = rng.standard_normal((n_draws, M))
        old = np.empty((n_draws, M)); new = np.empty((n_draws, M))
        log = np.empty((n_draws, M)); cond = np.empty((n_draws, M))
        for i in range(n_draws):
            oi, raw = _old_additive_draw(o, state, T, Z[i])
            ni, _ = _new_reflect_draw(o, state, T, Z[i])
            li, _ = _new_log_draw(o, state, T, Z[i])
            old[i] = oi; new[i] = ni; log[i] = li
            old_clip += int(np.sum(raw <= FLOOR)); old_total += M
            new_clip += int(np.sum(ni <= FLOOR)); new_total += M
            log_clip += int(np.sum(li <= FLOOR))
        # NEW conditional sampler: build the per-role inverse-CDF tables ONCE for
        # this slot (draw-independent), then map every draw's Φ(z) through them —
        # the SAME grids + np.interp the shipped sample_conditional_column uses.
        s_lap = laplace_column_std(o, state, T)
        grids = conditional_column_grids(o, state, T, s_lap, reach)
        U = _normal_cdf(Z)                       # (n_draws, M) uniforms
        for k in range(M):
            if grids[k] is None:
                cond[:, k] = o[k]
            else:
                x, cdf = grids[k]
                cond[:, k] = np.interp(np.clip(U[:, k], 1e-12, 1 - 1e-12), cdf, x)
        cond_clip += int(np.sum(cond <= FLOOR))
        std_true, acc, mean_true = _reference_true_std(o, state, T, n=ref_n,
                                                       seed=seed + s)
        # true-Gibbs-ref column: an INDEPENDENT reference chain scored against the
        # first — the Monte-Carlo noise floor of the std_bias instrument itself.
        std_ref2, _, _ = _reference_true_std(o, state, T, n=ref_n,
                                             seed=seed + s + 991)
        typ = float(np.mean(std_true)) + 1e-30
        mode = float(o.sum()) + 1e-30
        old_bias.append(np.mean(np.abs(old.std(0, ddof=1) - std_true)) / typ)
        new_bias.append(np.mean(np.abs(new.std(0, ddof=1) - std_true)) / typ)
        log_bias.append(np.mean(np.abs(log.std(0, ddof=1) - std_true)) / typ)
        cond_bias.append(np.mean(np.abs(cond.std(0, ddof=1) - std_true)) / typ)
        ref_bias.append(np.mean(np.abs(std_ref2 - std_true)) / typ)
        old_mr.append(old.sum(1).mean() / mode)
        new_mr.append(new.sum(1).mean() / mode)
        log_mr.append(log.sum(1).mean() / mode)
        cond_mr.append(cond.sum(1).mean() / mode)
        ref_mr.append(float(mean_true.sum()) / mode)
    return {
        "T_s": T, "n_slots_measured": len(old_bias), "n_draws_per_slot": n_draws,
        "reach_z_run": reach,
        "OLD_additive": {"clip_rate": old_clip / max(1, old_total),
                         "std_bias": float(np.mean(old_bias)),
                         "mean_mode_ratio": float(np.mean(old_mr))},
        "NEW_reflect": {"clip_rate": new_clip / max(1, new_total),
                        "std_bias": float(np.mean(new_bias)),
                        "mean_mode_ratio": float(np.mean(new_mr))},
        "REJECTED_logspace": {"clip_rate": log_clip / max(1, new_total),
                              "std_bias": float(np.mean(log_bias)),
                              "mean_mode_ratio": float(np.mean(log_mr))},
        "TRUE_gibbs_ref": {"clip_rate": 0.0,
                           "std_bias": float(np.mean(ref_bias)),
                           "mean_mode_ratio": float(np.mean(ref_mr))},
        "NEW_conditional": {"clip_rate": cond_clip / max(1, new_total),
                            "std_bias": float(np.mean(cond_bias)),
                            "mean_mode_ratio": float(np.mean(cond_mr))},
    }


def main():
    corpus = "--corpus" in sys.argv
    if corpus:
        from ets.ingestion.pipeline import load
        from ets.writer import build_world_from_tracks
        CACHE = os.environ.get("ETS_CACHE", "cache/ingest")
        paths = sorted(glob.glob(os.path.join(CACHE, "track_*.npz")))
        world = build_world_from_tracks([load(p) for p in paths])
        label = "CORPUS (psytech, M=%d)" % world.M
    else:
        from tests.harness.worldtools import build_synthetic_world
        world = build_synthetic_world()
        label = "SYNTHETIC CI world (M=%d)" % world.M
    res = measure(world)
    print(f"Table-6 measurement — {label}, T_s={res['T_s']}, "
          f"{res['n_slots_measured']} slots x {res['n_draws_per_slot']} draws, "
          f"reach z_run={res['reach_z_run']:.3f}")
    for k in ("OLD_additive", "NEW_reflect", "REJECTED_logspace",
              "TRUE_gibbs_ref", "NEW_conditional"):
        print(f"  {k:18s} clip_rate={res[k]['clip_rate']*100:6.2f}%   "
              f"std_bias={res[k]['std_bias']:.4f}   "
              f"mean/mode={res[k]['mean_mode_ratio']:.2f}")
    o, n = res["OLD_additive"], res["NEW_conditional"]
    print(f"  => clip {o['clip_rate']*100:.2f}% -> {n['clip_rate']*100:.2f}% "
          f"(shipped conditional); std_bias {o['std_bias']:.3f} -> {n['std_bias']:.3f} "
          f"(true-Gibbs-ref noise floor {res['TRUE_gibbs_ref']['std_bias']:.3f}; "
          f"reflect {res['NEW_reflect']['std_bias']:.3f}); "
          f"mean/mode {o['mean_mode_ratio']:.2f} -> {n['mean_mode_ratio']:.2f}")


if __name__ == "__main__":
    main()
