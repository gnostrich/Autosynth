# futuregarage — a second instantiation of the v1 architecture

`futuregarage` is a **trained model**: the v1 ETS architecture (rev-r1 F, unit-resolved
fiber) run on a **new corpus** — 25 tracks of deep / atmospheric halftime (bass).
Per the user's isolation choice it is a **full fork**: a self-contained copy of the
v1 implementation lives here under `instantiations/futuregarage/`, so the v1 tree that
produced the first instantiation ("psytech") is **never edited**.

It re-earned every gate on its own corpus (nothing assumed to transfer):

| stage | result |
|---|---|
| NCE separation exam | **PASS** — held-out min sep **0.98** ≥ 0.90; all four scramble families separate (grid-shuffle 1.00, role-permute 0.98, phase-rotate 1.00, cross-track-swap 0.98). Authoritative LAMBDA emitted; F-1 discharged. |
| world | frozen, **M=5** anchors, bound to the futuregarage LAMBDA |
| σ_φ calibration | armed lanes **region / continuity / novelty**; density + gauge non-identifiable at u=0 (structural — no floor invented), disarmed |

The fitted weights differ from v1 by design (same F structure, genre-specific fit —
e.g. spectral-masking weight T3 = 1.02 vs v1's 0.80). See `MANIFEST.json`,
`training_results.json`, `lambda.json`, `ets/calibration/sigma_phi.json`.

## Render from this instantiation

Everything resolves to this fork automatically (its `scripts/` sit one level under
the fork root, so `MAIN` → this folder):

```bash
cd instantiations/futuregarage
PYTHONPATH=$PWD python3 scripts/render_journeys.py \
    --out /path/to/out --journeys journeys.json   # or omit for a u=0 probe
```

`render_journeys.py` loads `corpus.etsworld`, materializes the source bank once
(disk-cached under `cache/units/`), renders each seeded/steered journey through the
engine's offline path, and applies the external mastering layer per clip. Knob
scripts steer only the armed lanes; `temperature` must be finite and > 0 once set.

## What is NOT committed

`cache/` (ingest + bank) is git-ignored — both are deterministic functions of the
committed `corpus/` + code, rebuilt on demand. The corpus mp3s and `corpus.etsworld`
ARE committed so the instantiation is self-contained and reproducible.
