# legacy/v0-validated — FROZEN. DO NOT EDIT. (H-1 enforced by CI)

This folder is a byte-exact snapshot of the **validated v0 build**: git commit
`6eabf6d` ("I-15 merge-readiness"), the racer-C rev-r1 state — the exact code
that passed the registered training exam and rendered the delivered clip
`samples/revr1C_u0_calibrated_60s.flac`. Local tag: `v0-validated-revr1`
(remote tag push rejected 403 by the app's permissions; the tag exists in the
local clone and this folder is the visible, CI-guarded backup).

## Exam receipts (registered gate train-nce-revr1-2026-07-13)

- Held-out per-member separation (seeds {4,5}, disjoint from fit seeds {1,2,3}):
  grid-shuffle 1.00 (median margin 18.79), role-permute 0.95 (1.07),
  phase-rotate 1.00 (6.03), cross-track-swap 0.975 (7.33).
  overall_min_sep 0.95 >= SEP_MIN 0.90 (pre-registered, untouched). KILL=false.
- LAMBDA (derived by convex logistic NCE, frozen in ets/functional/f.py):
  T2=4.9923137910018385, T3=0.8023184886520748, T4=10.457681912759295,
  T1p=8.758101446990384 (T1_gw reference = 1; T5=0.1 declared R3 baseline).
- Independent audit (pre-merge): exam re-run from an isolated scratchpad
  reproduced LAMBDA bit-exactly (16 digits) and identical margins. VERDICT PASS.
  Declared divergence at merge: greedy uncertified fiber realization
  (REGISTRY id realize-greedy-fiber).
- Prereg committed 15:43 (f15cc7a), result 16:04 — commit-before-run held.

## Contents

- Full source tree at 6eabf6d (ets/, tests/, scripts/, spec + authorities,
  PREREG.md / REGISTRY.jsonl as of that commit).
- `cache-ingest-frozen/`: byte copy of cache/ingest (the 20 ingested track
  .npz files) — the frozen world inputs. The corpus mp3s (source audio for
  rendering) live in the main checkout `corpus/` and are referenced by
  absolute path, as the scripts always did.

## Replay (H-2)

`python3 scripts/generate_batch.py --seconds 60 --out <path>` run from this
folder must reproduce the delivered 60s FLAC bit-identically. Executed once at
snapshot time; result logged in the main REGISTRY.jsonl (id legacy-h2-replay).

## Law

Nothing under legacy/ is ever edited (directive v1 A1; CI check H-1). New work
lives outside. This includes "harmless" fixes: a divergence here is a breach.
