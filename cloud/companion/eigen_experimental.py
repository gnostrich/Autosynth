"""EXPERIMENTAL — Gibbs-EBM-natural mode cutoff (prereg: papers/PREREG-natural-eigen-cutoff.md).

ADDITIVE / OPT-IN. Does NOT modify the protected baseline
(engine_bridge.compute_eigenmodes) or any engine/settlement/render path. It reuses the
baseline's EXACT response kernel Ksym and shuffle-null / bootstrap machinery, and only
adds: (1) exposure of the FULL signed eigenvalue spectrum + floor + per-mode SE, and
(2) two ALTERNATIVE cutoffs (spectral-gap, thermal-scale) reported ALONGSIDE the
baseline cutoff — never replacing it. Read-only w.r.t. the world.

The object is unchanged on purpose: the response kernel already realizes Theorem A's
projected conjugate fluctuation and dodges the P5 covariance trap. Only the *cutoff*
(statistical shuffle-null vs physical thermal/gap) is under test here.
"""
from __future__ import annotations
import numpy as np

from cloud.companion.engine_bridge import (
    _eigen_lane_vector, _eigen_node_means, _eigen_obs_names, _eigen_phi_vec,
    _EIGEN_H, _EIGEN_N_BOOT, _EIGEN_N_NULL, _EIGEN_FLOOR_PCT,
)


def _sigma_vec(sigma, M):
    sig = np.concatenate([np.asarray(sigma.region, float).reshape(-1)[:M],
                          [float(sigma.density), float(sigma.cont), float(sigma.novelty)]])
    return sig, np.where(sig > 0.0, sig, 1.0)


def _ensemble_bars_at_zero(world, sigma, M, n_seed, n_bar, seed0=90000):
    """Collect the JOINT sampling ensemble of settled Phi at the u=0 operating point —
    every (seed, bar) settled observable vector, the object's own wobble with NO lean
    applied. This is the 'covariance on the sampling ensemble' E1 originally specified."""
    from ets.writer.tilt import layer0
    from ets.writer.stream import StreamWriter
    u0 = _eigen_lane_vector(M)                 # all-zero lean
    tilt = layer0(u0, sigma)
    rows = []
    for i in range(n_seed):
        w = StreamWriter(world, seed=int(seed0 + i))
        for _ in range(n_bar):
            rows.append(_eigen_phi_vec(w.write_bar(tilt=tilt).phi, M))
    return np.asarray(rows, float)             # (n_seed*n_bar, D)


def covariance_read(world, sigma, M, n_seed=24, n_bar=32, rng_seed=20260718):
    """(2) SPEC-COMPLIANCE — the E1-original 'covariance on the sampling ensemble' read,
    as an ALTERNATIVE to the per-lever finite-difference response kernel. At u=0 collect
    the joint wobble, form the sigma-whitened covariance kernel, eigendecompose, and cut
    with a marginal-shuffle null (destroy cross-correlation, keep each observable's own
    variance). Reports k/modes AND which observable dominates the top mode — the P5 tell.
    Read-only; no engine/settlement change."""
    if sigma is None or int(M) <= 0:
        return {"error": "no sigma / M<=0", "k_cov": 0}
    M = int(M); names = _eigen_obs_names(M)
    sig, sig_safe = _sigma_vec(sigma, M)
    ens = _ensemble_bars_at_zero(world, sigma, M, n_seed, n_bar)   # (N, D)
    D = ens.shape[1]

    def _whiten_cov(A):
        C = np.cov(A, rowvar=False)
        K = C / np.outer(sig_safe, sig_safe)      # symmetric, scale-consistent with R/sigma
        K[sig <= 0.0, :] = 0.0; K[:, sig <= 0.0] = 0.0
        return K

    w_eig, V = np.linalg.eigh(_whiten_cov(ens))
    order = np.argsort(-np.abs(w_eig)); w_eig, V = w_eig[order], V[:, order]

    rng = np.random.default_rng(rng_seed)
    # MARGINAL-SHUFFLE NULL: permute each observable column independently -> destroys the
    # cross-correlations (the real joint structure) but keeps each marginal variance, so a
    # mode driven purely by one big-variance observable (the P5 continuity trap) does NOT
    # clear this floor, while a genuine JOINT mode does.
    null_max = []
    for _ in range(_EIGEN_N_NULL // 2 or 1):
        A = ens.copy()
        for j in range(D):
            A[:, j] = A[rng.permutation(A.shape[0]), j]
        wn, _ = np.linalg.eigh(_whiten_cov(A)); null_max.append(float(np.max(np.abs(wn))))
    floor = float(np.percentile(null_max, _EIGEN_FLOOR_PCT)) if null_max else 0.0
    boot = []
    N = ens.shape[0]
    for _ in range(_EIGEN_N_BOOT):
        idx = rng.integers(0, N, N)
        wb, _ = np.linalg.eigh(_whiten_cov(ens[idx])); boot.append(wb[np.argsort(-np.abs(wb))])
    se = np.std(np.stack(boot), axis=0) if boot else np.zeros(D)

    absw = np.abs(w_eig)
    k_cov = int(np.sum([(absw[r] > floor) and (absw[r] - 2.0*se[r] > floor) for r in range(D)]))
    # dominant observable of the top mode (the P5 tell: is it continuity's variance?)
    top_dom = names[int(np.argmax(np.abs(V[:, 0])))] if D else None
    return {
        "M": M, "cov_floor": floor,
        "cov_spectrum_abs": [round(float(x), 4) for x in absw],
        "cov_se": [round(float(x), 4) for x in se],
        "k_cov": k_cov, "top_mode_dominant_observable": top_dom,
        "observable_names": names,
        # raw marginal variances (whitened) — shows continuity's variance directly.
        "whitened_marginal_var": {names[j]: round(float(np.var(ens[:, j]) / (sig_safe[j]**2)), 4) for j in range(D)},
    }


def _run_mean_at_T(world, sigma, u, seed, n_bar, M, T_s):
    """Per-seed mean Phi at a SET temperature T_s (frozen tilt -> dataclasses.replace)."""
    import dataclasses
    from ets.writer.tilt import layer0
    from ets.writer.stream import StreamWriter
    tilt = dataclasses.replace(layer0(u, sigma), T_s=float(T_s))
    w = StreamWriter(world, seed=int(seed))
    acc = np.zeros(M + 3, dtype=np.float64)
    for _ in range(n_bar):
        acc += _eigen_phi_vec(w.write_bar(tilt=tilt).phi, M)
    return acc / n_bar


def _node_means_at_T(world, sigma, builder, M, seed0, n_seed, n_bar, T_s):
    return np.stack([_run_mean_at_T(world, sigma, builder(), seed0 + i, n_bar, M, T_s)
                     for i in range(n_seed)])


def _build_kernel(world, sigma, M, n_seed, n_bar, h, rng_seed, T_s=None):
    """Reproduce the baseline Ksym + null draws + bootstrap SE, but keep every
    intermediate (full spectrum, floor, se). Mirrors compute_eigenmodes exactly."""
    D = M + 3
    names = _eigen_obs_names(M)
    sig = np.concatenate([np.asarray(sigma.region, float).reshape(-1)[:M],
                          [float(sigma.density), float(sigma.cont), float(sigma.novelty)]])
    sig_safe = np.where(sig > 0.0, sig, 1.0)
    builders = []
    for i in range(M):
        builders.append(((lambda ii=i: _eigen_lane_vector(M, region_idx=ii, region_val=+h)),
                         (lambda ii=i: _eigen_lane_vector(M, region_idx=ii, region_val=-h))))
    builders.append(((lambda: _eigen_lane_vector(M, density=+h)), (lambda: _eigen_lane_vector(M, density=-h))))
    builders.append(((lambda: _eigen_lane_vector(M, cont=+h)),    (lambda: _eigen_lane_vector(M, cont=-h))))
    builders.append(((lambda: _eigen_lane_vector(M, novelty=+h)), (lambda: _eigen_lane_vector(M, novelty=-h))))

    def _nm(builder, seed0):
        if T_s is None:
            return _eigen_node_means(world, sigma, builder, M, seed0, n_seed, n_bar)
        return _node_means_at_T(world, sigma, builder, M, seed0, n_seed, n_bar, T_s)
    R = np.zeros((D, D)); node_data = []
    for j, (up, um) in enumerate(builders):
        mp = _nm(up, 70000 + j * 1000)
        mm = _nm(um, 70000 + j * 1000 + 500)
        node_data.append((mp, mm)); R[:, j] = (mp.mean(0) - mm.mean(0)) / (2.0 * h)

    def _ksym(Rmat):
        K = Rmat / sig_safe[:, None]; K[sig <= 0.0, :] = 0.0
        return 0.5 * (K + K.T)

    w_eig, V = np.linalg.eigh(_ksym(R))
    order = np.argsort(-np.abs(w_eig)); w_eig = w_eig[order]; V = V[:, order]

    rng = np.random.default_rng(rng_seed)
    null_max = []
    for _ in range(_EIGEN_N_NULL):
        Rn = np.zeros((D, D))
        for j, (mp, mm) in enumerate(node_data):
            both = np.concatenate([mp, mm], axis=0); idx = rng.permutation(both.shape[0])
            half = both.shape[0] // 2
            Rn[:, j] = (both[idx[:half]].mean(0) - both[idx[half:2*half]].mean(0)) / (2.0 * h)
        wn, _ = np.linalg.eigh(_ksym(Rn)); null_max.append(float(np.max(np.abs(wn))))
    floor = float(np.percentile(null_max, _EIGEN_FLOOR_PCT)) if null_max else 0.0

    boot = []
    for _ in range(_EIGEN_N_BOOT):
        Rb = np.zeros((D, D))
        for j, (mp, mm) in enumerate(node_data):
            idx = rng.integers(0, n_seed, n_seed)
            Rb[:, j] = (mp[idx].mean(0) - mm[idx].mean(0)) / (2.0 * h)
        wb, _ = np.linalg.eigh(_ksym(Rb)); boot.append(wb[np.argsort(-np.abs(wb))])
    se = np.std(np.stack(boot), axis=0) if boot else np.zeros(D)
    # thermal scale: the median observable sigma_phi (the physical fluctuation unit the
    # kernel is already whitened by -> a mode of |lambda|~1 is "one sigma of response").
    thermal = float(np.median(sig_safe))
    return names, w_eig, se, floor, sig_safe, thermal, V


def temperature_sweep(world, sigma, M, T_grid, n_seed=24, n_bar=32, rng_seed=20260718):
    """(1) PREREG-temperature-sweep. Measure k and the mode spectrum at each T_s in the
    grid, re-deriving the floor at that temperature (floors-first). The response kernel
    (protected baseline estimator) is unchanged; only the writer temperature is set.
    A mode crossing the floor as T_s moves is the H1 signal (a mode freezing in/out)."""
    if sigma is None or int(M) <= 0:
        return {"error": "no sigma / M<=0"}
    M = int(M); names = _eigen_obs_names(M); rows = []
    for T in T_grid:
        _n, w, se, floor, sig_safe, thermal, V = _build_kernel(
            world, sigma, M, n_seed, n_bar, _EIGEN_H, rng_seed, T_s=float(T))
        D = len(w); absw = np.abs(w)
        surviving = [r for r in range(D)
                     if (absw[r] > floor) and (absw[r] - 2.0 * se[r] > floor)]
        # FULL modes (compute_eigenmodes format) for the k surviving modes, so the pad
        # can render the pre-measured modes at this temperature (petals appearing as T_s
        # rises). Composition/gain/sign are the real measured eigenvector/eigenvalue.
        modes = []
        for out_idx, r in enumerate(surviving):
            vec = V[:, r]
            comp = {names[a]: float(vec[a]) for a in range(D)}
            comp["fill"] = float(sum(vec[a] for a in range(M)))
            modes.append({"index": out_idx, "gain": float(w[r]),
                          "sign": (1 if w[r] >= 0.0 else -1), "composition": comp,
                          "earned_word": None})
        rows.append({"T_s": round(float(T), 4), "k": len(surviving),
                     "floor": round(float(floor), 4), "eigen_floor": round(float(floor), 4),
                     "modes": modes,
                     "spectrum_abs": [round(float(x), 4) for x in absw],
                     "lambda2_over_floor": (round(float(absw[1] / floor), 3)
                                            if D > 1 and floor > 0 else None)})
    return {"M": M, "n_seed": n_seed, "n_bar": n_bar,
            "observable_names": names, "sweep": rows}


def diagnose(world, sigma, M, n_seed=24, n_bar=32, h=_EIGEN_H, rng_seed=20260718):
    """Full-spectrum diagnostic + baseline and alternative mode counts. Pure report."""
    if sigma is None or int(M) <= 0:
        return {"error": "no sigma / M<=0", "k_baseline": 0}
    names, w, se, floor, sig_safe, thermal, _V = _build_kernel(world, sigma, int(M), n_seed, n_bar, h, rng_seed)
    absw = np.abs(w)
    # BASELINE cutoff (exactly compute_eigenmodes' rule).
    k_base = int(np.sum([(absw[r] > floor) and (absw[r] - 2.0*se[r] > floor) for r in range(len(w))]))
    # SPECTRAL-GAP cutoff: dominant ratio gap in the sorted magnitudes (only among
    # eigenvalues that clear the bare floor at all — below the floor is noise bulk).
    above = [r for r in range(len(w)) if absw[r] > floor]
    if len(above) <= 1:
        k_gap = len(above)
    else:
        ratios = [absw[above[i]] / max(absw[above[i+1]], 1e-12) for i in range(len(above)-1)]
        k_gap = int(np.argmax(ratios) + 1)
    # THERMAL-scale cutoff sweep: |lambda| above c * (floor) for a few c (c=1 is bare
    # floor, i.e. drop the 2SE margin; c<1 is looser). Reported, not chosen.
    thermal_sweep = {f"c={c}": int(np.sum(absw > c*floor)) for c in (0.5, 0.75, 1.0)}
    return {
        "M": int(M), "floor_p97.5": floor, "thermal_sigma_med": thermal,
        "spectrum_abs": [round(float(x), 4) for x in absw],
        "spectrum_signed": [round(float(x), 4) for x in w],
        "se": [round(float(x), 4) for x in se],
        "lambda2_vs_floor": (round(float(absw[1]/floor), 3) if len(w) > 1 and floor > 0 else None),
        "k_baseline": k_base, "k_spectral_gap": k_gap, "k_thermal_sweep": thermal_sweep,
        "observable_names": names,
    }
