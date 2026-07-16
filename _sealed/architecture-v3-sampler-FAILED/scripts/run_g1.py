"""G1 runner (spec §13). Pre-registered in PREREG.md (G1) and REGISTRY.jsonl
(g1-anchors-2026-07-13) BEFORE this run. Reads the 20 cached ingested tracks,
builds the pre-committed arms ALGORITHMICALLY, and evaluates the self-sized
anchor count (balanced-truncation effective rank of the cross-track role-traffic
operator). Writes g1_results.json. No metric here appears in F (I-5)."""
from __future__ import annotations
import glob, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ets.ingestion.pipeline import load
from ets.geometry import roles
from ets.functional import anchors as an


def greedy_tightest_cluster(D, k):
    n = len(D)
    iu = np.triu_indices(n, 1)
    p = np.argmin(D[iu])
    cluster = [int(iu[0][p]), int(iu[1][p])]
    while len(cluster) < k:
        rest = [i for i in range(n) if i not in cluster]
        mean_d = [np.mean([D[i, c] for c in cluster]) for i in rest]
        cluster.append(int(rest[int(np.argmin(mean_d))]))
    return cluster


def greedy_farthest_point(D, k):
    n = len(D)
    iu = np.triu_indices(n, 1)
    p = np.argmax(D[iu])
    chosen = [int(iu[0][p]), int(iu[1][p])]
    while len(chosen) < k:
        rest = [i for i in range(n) if i not in chosen]
        min_d = [min(D[i, c] for c in chosen) for i in rest]
        chosen.append(int(rest[int(np.argmax(min_d))]))
    return chosen


def main():
    paths = sorted(glob.glob("cache/ingest/track_*.npz"))
    protos = [roles.extract_prototypes(load(p), seed=0) for p in paths]

    # (1) role-distance matrix + FROZEN corpus sigma (calibrated once, all arms).
    D = roles.role_distance_matrix(protos)
    sigma = float(np.median(D[~np.eye(len(D), dtype=bool)]))

    def er(idx):
        A, _, _ = an.traffic_affinity([protos[i] for i in idx], sigma=sigma)
        return an.effective_rank(A)

    # (2) algorithmic arms
    same_order = greedy_tightest_cluster(D, 6)
    div_order = greedy_farthest_point(D, 6)

    Ns = [2, 3, 4, 6]
    same_curve = {n: er(same_order[:n]) for n in Ns}
    div_curve = {n: er(div_order[:n]) for n in Ns}

    # gauge-copy arm (strict flat-in-N + gauge-invariance control) on track_00
    ref = protos[0]
    def gauge_stack(n):
        stack = [ref] + [an.gauge_copy(ref, transpose=k, phase=k % 8, loud=1 + 0.3 * k)
                         for k in range(1, n)]
        A, dd, _ = an.traffic_affinity(stack, sigma=sigma)
        return an.effective_rank(A), float(dd.max())
    gauge = {n: gauge_stack(n) for n in [2, 4, 6, 8]}

    # (3) role-scrambled null (noise floor) on both arms' 6-sets
    null_same = an.scramble_null([protos[i] for i in same_order], seed=0)
    null_div = an.scramble_null([protos[i] for i in div_order], seed=0)
    er_null_same = an.effective_rank(an.traffic_affinity(null_same, sigma=sigma)[0])
    er_null_div = an.effective_rank(an.traffic_affinity(null_div, sigma=sigma)[0])

    # (4) settle the barycenter supports at M* for both 6-arms (F-descent health)
    st_same, info_same = an.build_world([protos[i] for i in same_order], sigma=sigma)
    st_div, info_div = an.build_world([protos[i] for i in div_order], sigma=sigma)

    # (5) verdict vs pre-registered pass criterion
    slope = lambda c: (c[6] - c[2]) / (6 - 2)
    er_same6, er_div6 = same_curve[6], div_curve[6]
    H1 = (er_div6 - er_same6) >= 1.0
    gauge_max = max(v[0] for v in gauge.values())
    H2_strict = gauge_max < 1.2
    H2_real = slope(div_curve) > slope(same_curve)
    ordering = er_same6 < er_null_same and er_div6 > er_null_div
    G1_pass = bool(H1 and H2_strict and H2_real and ordering)

    out = {
        "sigma_frozen": sigma,
        "role_dist_stats": {"min": float(D[~np.eye(len(D), dtype=bool)].min()),
                            "median": sigma,
                            "max": float(D.max())},
        "arms": {"SAME_order": same_order, "DIVERSE_order": div_order,
                 "reference_track_gauge_copy": 0},
        "eff_rank": {
            "SAME": {str(n): float(same_curve[n]) for n in Ns},
            "DIVERSE": {str(n): float(div_curve[n]) for n in Ns},
            "GAUGE_COPY": {str(n): {"eff_rank": float(gauge[n][0]),
                                    "role_dist_max": gauge[n][1]} for n in gauge},
            "NULL_same6": float(er_null_same),
            "NULL_diverse6": float(er_null_div),
        },
        "slopes": {"SAME": float(slope(same_curve)), "DIVERSE": float(slope(div_curve))},
        "barycenter_settle": {
            "SAME": {"M_star": info_same["n_anchors"], "F_final": info_same["F_final"],
                     "F_monotone": info_same["F_monotone"]},
            "DIVERSE": {"M_star": info_div["n_anchors"], "F_final": info_div["F_final"],
                        "F_monotone": info_div["F_monotone"]},
        },
        "hypothesis": {"H1_diversity": bool(H1), "H2_flat_strict_gauge": bool(H2_strict),
                       "H2_real_slower_growth": bool(H2_real),
                       "ordering_SAME_lt_NULL_lt_DIVERSE": bool(ordering)},
        "G1_pass": G1_pass,
        "prereg": "PREREG.md G1; registry g1-anchors-2026-07-13",
    }
    with open("g1_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
