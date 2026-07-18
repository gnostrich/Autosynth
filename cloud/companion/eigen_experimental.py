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
    _eigen_lane_vector, _eigen_node_means, _eigen_obs_names,
    _EIGEN_H, _EIGEN_N_BOOT, _EIGEN_N_NULL, _EIGEN_FLOOR_PCT,
)


def _build_kernel(world, sigma, M, n_seed, n_bar, h, rng_seed):
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

    R = np.zeros((D, D)); node_data = []
    for j, (up, um) in enumerate(builders):
        mp = _eigen_node_means(world, sigma, up, M, 70000 + j * 1000, n_seed, n_bar)
        mm = _eigen_node_means(world, sigma, um, M, 70000 + j * 1000 + 500, n_seed, n_bar)
        node_data.append((mp, mm)); R[:, j] = (mp.mean(0) - mm.mean(0)) / (2.0 * h)

    def _ksym(Rmat):
        K = Rmat / sig_safe[:, None]; K[sig <= 0.0, :] = 0.0
        return 0.5 * (K + K.T)

    w_eig, _ = np.linalg.eigh(_ksym(R))
    order = np.argsort(-np.abs(w_eig)); w_eig = w_eig[order]

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
    return names, w_eig, se, floor, sig_safe, thermal


def diagnose(world, sigma, M, n_seed=24, n_bar=32, h=_EIGEN_H, rng_seed=20260718):
    """Full-spectrum diagnostic + baseline and alternative mode counts. Pure report."""
    if sigma is None or int(M) <= 0:
        return {"error": "no sigma / M<=0", "k_baseline": 0}
    names, w, se, floor, sig_safe, thermal = _build_kernel(world, sigma, int(M), n_seed, n_bar, h, rng_seed)
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
