"""G2 runner (spec §13). Pre-registered in PREREG.md (G2) and REGISTRY.jsonl
(g2-holonomy-2026-07-13) BEFORE this run (commit-before-run).

G2 tests the INTRINSIC HOLONOMY of real tracks' role-space traffic: the triangle
loop defect (spec §16, §10 "seams with drift prices") of the cross-track GW
couplings. Like G1 this is a property of the FROZEN WORLD's role geometry — it
uses ONLY entropic Gromov-Wasserstein couplings between prototype spaces
(internal costs; no coordinate crosses a boundary, I-2) and NO trained F/LAMBDA
(I-5). It is therefore runnable now, independent of the not-yet-built writer.

Instrument (meters.holonomy.loop_defect): compose the GW barycentric maps around
a loop of tracks; measure how far the composed map is from the identity in the
START track's own within-track-normalized role metric. A flat (globally
integrable) role geometry closes loops up to the solver/entropy/matching floor;
genuine curvature shows up as excess loop defect.

Scale-free per-triangle statistic (residual-conditioned by construction):
    r(triangle) = d3 / max(edge 2-loop defects) ;   curvature  κ = r - 1
A 2-loop (edge round-trip s→t→s) encloses no area, so its defect is pure floor;
normalising each triangle by its own worst edge round-trip conditions out the
per-edge residual, leaving the 3-way (curvature) excess.

Two references:
  • SOLVER FLOOR (measured FIRST): a gauge-copy flat world (identical geometry,
    homogeneous mass) — the pure entropic-GW composition floor, zero curvature
    and zero heterogeneity.
  • PARAMETRIC RESIDUAL-CONDITIONED NULL: a flat Euclidean world (n=20 tracks =
    independent noisy views of ONE latent K-point config, masses resampled from
    the pooled real prototype masses so heterogeneity matches). Globally
    integrable → true curvature 0; its edge (2-loop) residual is CALIBRATED to
    the real corpus's by a single noise knob η (bisection on 2-loops ONLY). Its
    loop inflation κ_null is the flat-world floor AT MATCHED EDGE RESIDUAL.

No metric here appears in F (I-5); the meter feeds nothing back (I-14)."""
from __future__ import annotations
import glob, itertools, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ets.functional import ot
from ets.functional import anchors as an
from ets.geometry import roles
from ets.ingestion.pipeline import load
from ets.meters.holonomy import loop_defect

EPS = 0.05                 # entropic-GW regulariser (same as G1 role couplings)
LATENT_DIM = 8             # null latent embedding dim (pre-registered)
TARGET_SEP = 20.0          # spec §13-G2 "order 20x" G4-class separation target
CACHE = "/home/user/Geodesic-Mixing/cache/ingest/track_*.npz"


# ---- survey primitives ----------------------------------------------------

def rms_normalize(C):
    """Within-track scalar normalization to off-diagonal RMS 1 (gauge-invariant,
    I-2): makes real and null defects directly comparable and the ratio scale-
    free."""
    K = len(C)
    off = C[~np.eye(K, dtype=bool)]
    s = float(np.sqrt(np.mean(off ** 2)))
    return C / (s if s > 0 else 1.0)


def directed_couplings(costs, masses):
    """All directed GW couplings, cached. coup[(i,j)] maps i→j (source marginal
    masses[i]); the round-trip orientation uses the transpose so 2-loops are
    exact."""
    n = len(costs)
    coup = {}
    for i, j in itertools.combinations(range(n), 2):
        pi, _ = ot.entropic_gw(costs[i], costs[j], masses[i], masses[j], EPS)
        coup[(i, j)] = pi
        coup[(j, i)] = pi.T
    return coup


def edge_2loops(costs, masses, coup):
    n = len(costs)
    d2 = {}
    for i, j in itertools.combinations(range(n), 2):
        d2[(i, j)] = 0.5 * (loop_defect(costs, masses, coup, [i, j, i]) +
                            loop_defect(costs, masses, coup, [j, i, j]))
    return d2


def triangle_ratios(costs, masses, coup, d2):
    n = len(costs)
    r = []
    for s, t, u in itertools.combinations(range(n), 3):
        d3 = loop_defect(costs, masses, coup, [s, t, u, s])
        floor = max(d2[(min(s, t), max(s, t))], d2[(min(t, u), max(t, u))],
                    d2[(min(s, u), max(s, u))])
        r.append(d3 / (floor + 1e-12))
    return np.array(r)


def survey(costs, masses):
    """Full loop-defect survey → (edge-2loop values, triangle ratios r)."""
    coup = directed_couplings(costs, masses)
    d2 = edge_2loops(costs, masses, coup)
    r = triangle_ratios(costs, masses, coup, d2)
    return np.array(list(d2.values())), r


# ---- flat null world ------------------------------------------------------

def flat_null_world(n, K, eta, mass_pool, seed, latent_dim=LATENT_DIM):
    """n tracks = independent noisy views of ONE latent K-point config → globally
    integrable (flat), true curvature 0. Masses resampled from the pooled real
    prototype masses so heterogeneity matches. η = per-point noise (sets the edge
    residual)."""
    rng = np.random.default_rng(seed)
    X0 = rng.standard_normal((K, latent_dim))
    costs, masses = [], []
    for _ in range(n):
        Xk = X0 + eta * rng.standard_normal((K, latent_dim))
        C = np.sqrt(((Xk[:, None, :] - Xk[None, :, :]) ** 2).sum(-1))
        costs.append(rms_normalize(C))
        m = rng.choice(mass_pool, size=K, replace=True) + 1e-6
        masses.append(m / m.sum())
    return costs, masses


def calibrate_eta(n, K, mass_pool, target_2loop, seed):
    """Bisect the null noise η so its median edge 2-loop matches the real median
    (2-loops ONLY — solver-floor calibration, no curvature information used)."""
    lo, hi = 1e-3, 6.0

    def med2(eta):
        costs, masses = flat_null_world(n, K, eta, mass_pool, seed)
        coup = directed_couplings(costs, masses)
        return float(np.median(list(edge_2loops(costs, masses, coup).values())))

    m_lo, m_hi = med2(lo), med2(hi)
    trace = [("lo", lo, m_lo), ("hi", hi, m_hi)]
    # if the attainable range does not bracket the target, clamp to the nearest
    # attainable end and report it honestly (a conservative null: looser edges
    # than real only INFLATE its loops, so κ_null is an upper bound on the flat
    # floor → the separation is a lower bound).
    if target_2loop <= m_lo:
        return lo, m_lo, "clamped_low", trace
    if target_2loop >= m_hi:
        return hi, m_hi, "clamped_high", trace
    for _ in range(24):
        mid = 0.5 * (lo + hi)
        mm = med2(mid)
        trace.append(("mid", mid, mm))
        if mm < target_2loop:
            lo = mid
        else:
            hi = mid
        if abs(mm - target_2loop) < 0.005:
            return mid, mm, "matched", trace
    mid = 0.5 * (lo + hi)
    return mid, med2(mid), "matched_tol", trace


# ---- main -----------------------------------------------------------------

def main():
    paths = sorted(glob.glob(CACHE))
    protos = [roles.extract_prototypes(load(p), seed=0) for p in paths]
    n = len(protos)
    K = 12
    real_costs = [rms_normalize(p.cost) for p in protos]
    real_masses = [p.mass for p in protos]
    mass_pool = np.concatenate([p.mass for p in protos])

    # (1) SOLVER FLOOR MEASURED FIRST: gauge-copy flat world (identical geometry,
    #     homogeneous mass) — pure entropic-GW composition floor, zero curvature.
    ref = protos[0]
    gstack = [ref] + [an.gauge_copy(ref, transpose=k, phase=k % 8, loud=1.0 + 0.3 * k)
                      for k in range(1, n)]
    floor_costs = [rms_normalize(P.cost) for P in gstack]
    floor_masses = [P.mass for P in gstack]
    floor_d2, floor_r = survey(floor_costs, floor_masses)
    kappa_floor = float(np.median(floor_r) - 1.0)

    # (2) REAL survey.
    real_d2, real_r = survey(real_costs, real_masses)
    kappa_real = float(np.median(real_r) - 1.0)
    real_med2 = float(np.median(real_d2))

    # (3) RESIDUAL-CONDITIONED NULL: calibrate η on 2-loops to match real edge
    #     residual, then measure its 3-loop inflation.
    eta, null_med2, calib_status, calib_trace = calibrate_eta(
        n, K, mass_pool, real_med2, seed=20260713)
    null_costs, null_masses = flat_null_world(n, K, eta, mass_pool, seed=20260713)
    null_d2, null_r = survey(null_costs, null_masses)
    kappa_null = float(np.median(null_r) - 1.0)

    # (4) separations + dominance.
    mad = lambda x: float(np.median(np.abs(x - np.median(x))) + 1e-12)
    sep_vs_null = kappa_real / (kappa_null + 1e-12)
    sep_vs_floor = kappa_real / (kappa_floor + 1e-12)
    z_vs_null = (np.median(real_r) - np.median(null_r)) / mad(null_r)
    dominance_p95 = float(np.median(real_r) > np.percentile(null_r, 95))
    dominance_p99 = float(np.median(real_r) > np.percentile(null_r, 99))

    # (5) pre-registered verdict: PASS(strong) = dominance(p99) AND sep_vs_null
    #     >= 20x (spec target against the residual-conditioned null).
    pass_strong = bool(dominance_p99 and sep_vs_null >= TARGET_SEP)
    signal_present = bool(dominance_p95 and sep_vs_null > 1.0)

    out = {
        "gate": "G2",
        "instrument": "triangle loop-defect holonomy of role-space GW traffic "
                      "(meters.holonomy.loop_defect); ratio r=d3/max_edge_2loop, "
                      "curvature kappa=r-1; eps=%.3f; costs RMS-normalized" % EPS,
        "n_tracks": n, "n_triangles": int(len(real_r)),
        "solver_floor_first": {
            "world": "gauge-copy of track_00 (identical geometry, homogeneous mass)",
            "median_2loop": float(np.median(floor_d2)),
            "median_ratio": float(np.median(floor_r)),
            "kappa_floor": kappa_floor,
        },
        "real": {
            "median_2loop_edge_floor": real_med2,
            "median_ratio": float(np.median(real_r)),
            "kappa_real": kappa_real,
            "ratio_p50_p90_max": [float(np.median(real_r)),
                                  float(np.percentile(real_r, 90)),
                                  float(real_r.max())],
        },
        "residual_conditioned_null": {
            "world": "flat Euclidean (noisy views of one latent config), "
                     "masses resampled from pooled real proto masses, latent_dim=%d" % LATENT_DIM,
            "calibrated_eta": float(eta),
            "calib_status": calib_status,
            "target_2loop": real_med2,
            "achieved_2loop": float(null_med2),
            "median_ratio": float(np.median(null_r)),
            "kappa_null": kappa_null,
            "ratio_p95_p99": [float(np.percentile(null_r, 95)),
                              float(np.percentile(null_r, 99))],
        },
        "separation": {
            "kappa_real_over_kappa_null": float(sep_vs_null),
            "kappa_real_over_kappa_floor": float(sep_vs_floor),
            "robust_z_vs_null": float(z_vs_null),
            "dominance_median_real_gt_null_p95": bool(dominance_p95),
            "dominance_median_real_gt_null_p99": bool(dominance_p99),
        },
        "target_separation": TARGET_SEP,
        "G2_pass_strong_20x": pass_strong,
        "signal_present_above_null": signal_present,
        "prereg": "PREREG.md G2; registry g2-holonomy-2026-07-13",
    }
    with open("g2_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
