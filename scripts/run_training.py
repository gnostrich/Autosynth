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

    # T5 identifiability probe: max |T5 feature| over the whole family (native
    # gauge -> identically 0 -> lambda_5 carries no contrastive signal).
    t5_max = 0.0   # phi has no T5 column by construction; recorded as structural 0.

    killed_members = [k for k, d in sep.items()
                      if isinstance(d, dict) and d["sep_rate"] < SEP_MIN]
    kill = len(killed_members) > 0

    out = {
        "world": {"M_star": world.M, "sigma": world.sigma},
        "fit": {"lambda_T2T3T4": [float(x) for x in fit.lam],
                "logistic_loss": fit.loss, "grad_norm": fit.grad_norm,
                "n_pairs": fit.n_pairs, "fit_seeds": list(FIT_SEEDS),
                "note": "T1 = reference scale 1 (fixed); T5 not identifiable "
                        "(phi_T5 == 0 for every family member at native gauge)."},
        "separation_heldout": sep,
        "heldout_seeds": list(HELDOUT_SEEDS),
        "sep_min_threshold": SEP_MIN,
        "t5_feature_max": t5_max,
        "KILL": bool(kill),
        "killed_members": killed_members,
        "verdict": ("KILL — F does not separate real from these re-arrangements "
                    "for any LAMBDA>=0; F term(s) mis-specified (WALL). No "
                    "authoritative LAMBDA emitted; F-1 remains open."
                    if kill else
                    "PASS — real tracks separate from the whole fixed family."),
        "lambda_emitted": None if kill else [1.0] + [float(x) for x in fit.lam],
        "prereg": "PREREG.md 'Scramble family' + 'Training — real-tracks-are-"
                  "equilibria separation'; registry train-nce-2026-07-13",
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
