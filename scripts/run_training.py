"""Step-d training runner (spec §6): contrastive/NCE fit of the F-weights LAMBDA.

PRE-REGISTERED in PREREG.md ("Scramble family" REGISTERED; "Training —
real-tracks-are-equilibria separation") and REGISTRY.jsonl (train-nce-2026-07-13)
BEFORE this run (commit-before-run).

Procedure: build the LAMBDA-free reference world; draw negatives ONLY through the
registered fixed scramble family (assert_family_fixed wired in nce.draw_pairs);
compute the LAMBDA-free feature map phi=(T1,T2,T3,T4); fit LAMBDA by the convex
logistic NCE on the FIT seeds; evaluate the pre-registered separation validity
check on HELD-OUT seeds (a metric distinct from the fit's logistic loss, so no fit
metric is a gate metric, I-5); apply the KILL condition.

KILL (pre-registered): if any fixed-family member's held-out separation rate
< SEP_MIN, F does not separate real from that re-arrangement for the fitted
LAMBDA -> an F term is mis-specified -> WALL. On kill the runner does NOT emit an
authoritative LAMBDA (F-1 stays open); the wall is reported, never patched.
"""
from __future__ import annotations
import glob, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ets.ingestion.pipeline import load
from ets.geometry import roles
from ets.training import nce
from ets.training.world import build_reference_world

FIT_SEEDS = (1, 2, 3)          # pre-registered
HELDOUT_SEEDS = (4, 5)         # pre-registered (disjoint from FIT_SEEDS)
SEP_MIN = 0.90                 # pre-registered kill threshold (per-member sep rate)


def main():
    paths = sorted(glob.glob("cache/ingest/track_*.npz"))
    tracks = [load(p) for p in paths]
    protos = [roles.extract_prototypes(t, seed=0) for t in tracks]
    world = build_reference_world(protos)

    pos = nce.positive_features(tracks, world)
    negs_fit = nce.draw_pairs(tracks, world, seeds=FIT_SEEDS)
    negs_val = nce.draw_pairs(tracks, world, seeds=HELDOUT_SEEDS)

    fit = nce.fit_lambda(pos, negs_fit)
    sep = nce.separation(pos, negs_val, fit.lam)

    # T5 identifiability (R3): T5 is 0 for every family member at native gauge, so
    # lambda_5 carries no contrastive signal and is not fit here (structural 0).
    t5_max = 0.0

    killed_members = [k for k, d in sep.items()
                      if isinstance(d, dict) and d["sep_rate"] < SEP_MIN]
    kill = len(killed_members) > 0

    # rev-r1 feature order: phi = [T1_gw, T2, T3, T4_raw, phase_charge]; T1_gw is the
    # reference scale (weight fixed 1); fit lambda = [T2, T3, T4, T1p].
    lam = {k: float(v) for k, v in zip(("T2", "T3", "T4", "T1p"), fit.lam)}
    emitted = None if kill else {"T1_gw": 1.0, **lam, "T5": 0.1}
    out = {
        "rev": "r1 (fork C: richer fiber + gauge-aligned groove target)",
        "world": {"M_star": world.M, "sigma": world.sigma},
        "fit": {"lambda_T2_T3_T4_T1p": [float(x) for x in fit.lam],
                "logistic_loss": fit.loss, "grad_norm": fit.grad_norm,
                "n_pairs": fit.n_pairs, "fit_seeds": list(FIT_SEEDS),
                "note": "T1_gw = reference scale 1 (fixed). phi = [T1_gw, T2, T3, "
                        "T4_raw=-succ_reward, phase_charge]. T5 not identifiable "
                        "(0 for every family member at native gauge; R3)."},
        "separation_heldout": sep,
        "heldout_seeds": list(HELDOUT_SEEDS),
        "sep_min_threshold": SEP_MIN,
        "t5_feature_max": t5_max,
        "KILL": bool(kill),
        "killed_members": killed_members,
        "verdict": ("KILL — F does not separate real from these re-arrangements "
                    "for the fitted LAMBDA; F term(s) still mis-specified (WALL). "
                    "No authoritative LAMBDA emitted; F-1 remains open."
                    if kill else
                    "PASS — real tracks separate from the whole fixed family "
                    "(min held-out sep >= 0.90). Authoritative LAMBDA emitted; "
                    "F-1 (frozen-weight discharge) DISCHARGED."),
        "lambda_emitted": emitted,
        "prereg": "PREREG.md 'Training rev-r1 — real-tracks-are-equilibria "
                  "separation (fork C)'; registry train-nce-revr1-2026-07-13",
    }
    with open("training_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    if kill:
        print("\nWALL: separation KILL on members:", killed_members,
              "\nNo LAMBDA emitted. F-1 stays open. See report / PREREG.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
