# ASYM RESULTS — genuine-vs-artifact diagnostic for the 45x tilt cross-talk asymmetry
Run: Sat Jul 18 2026 UTC. Repo /home/user/Geodesic-Mixing, READ-ONLY.
PREREG.md (same dir, timestamped 09:31:04 UTC) written BEFORE any estimand run.
Harness: scratchpad/asym/harness.py (offline monkeypatch of the slot-processing
order; NO repo file edited). Data: results.json. Engine: architecture-v6/ets
(ownership asserted). Faithfulness certificate: the patched writer at IDENTITY
order reproduces the stock write_bar bit-for-bit on all phi (asserted in code
before measurement) — the harness changes ONLY the fiber slot-processing order.

## VERDICT: **ARTIFACT**
The 45x asymmetry (novelty suppresses continuity ~45x harder than the reverse)
is MANUFACTURED by the greedy sequential fiber sampler's default left-to-right
slot-processing ORDER. It is NOT an order-invariant property of the trained
object. Theorem B / Maxwell reciprocity is RESCUED: with the ordering bias
removed (random slot permutation), both tilt-tilt cross-derivatives sit within
the noise floor — i.e. the deployed object's tilt response is approximately
Maxwell-symmetric, and the default ordering is what breaks it.

Located lane-iteration site: architecture-v6/ets/writer/stream.py
`StreamWriter.write_bar` step (3), `for s_local in range(grid.n_slots)` →
`FiberThreader.place_slot`; sequential coupling is `FiberThreader.run_head[b]`.

## T-ORD (PRIMARY — lane-ordering invariance) — decides ARTIFACT
Paired seeds (identical seed block across all orders; step-(2) O identical, only
fiber slot order differs — disclosed deviation from prereg, strictly stronger).
N=16 seeds/node, 24 bars/run, h=0.75. Asymmetry statistic dK = K_AB−K_BA
(lambda-normalized; the Phase-1B "45x" statistic; floor ~0.01). Baseline
continuity shown as phi_cont at the ±novelty nodes (ceiling ≈ 64).

| order | D_AB=dcont/dnov | D_BA=dnov/dcont | dK=K_AB−K_BA | cont(nov+/nov−) |
|---|---|---|---|---|
| **O1 identity (default)** | **−5.134 ± 0.150** | +0.0048 ± 0.0045 | **−0.417 ± 0.018** | 50.7 / 58.4 (near ceiling) |
| O2 reversed | +1.287 ± 0.394 | −0.0011 ± 0.0020 | **+0.104 ± 0.032** | 40.6 / 38.6 |
| O3 random | +0.111 ± 0.336 | +0.0002 ± 0.0033 | **+0.008 ± 0.028** | 43.4 / 43.2 |
| O4 random | +0.734 ± 0.519 | −0.0042 ± 0.0023 | **+0.070 ± 0.041** | 39.8 / 38.7 |
| O5 random | +0.526 ± 0.356 | −0.0016 ± 0.0024 | **+0.046 ± 0.029** | 39.5 / 38.7 |

across-order dK: mean −0.038, std 0.215, range [−0.417, +0.104], SIGN FLIPS
(1 negative at the default order, 4 positive otherwise). Across-order std (0.215)
is ~6–10× the per-order SE (0.018–0.041).

PRE-REGISTERED READ: H-ARTIFACT ("dK flips sign / collapses toward floor / varies
wildly across orders") is REALIZED on every clause:
- SIGN FLIP: the default order alone is large negative (−0.417); reversal and all
  three random permutations are positive.
- COLLAPSE: random permutations — which leave the corpus, successor graph, world,
  and F ENTIRELY intact and change only slot order — collapse dK from −0.417 to
  +0.008…+0.070 (near the ~0.01 floor). Under H-GENUINE (asymmetry = order-invariant
  object property) this is impossible; the object is untouched by a slot permutation.
- Mechanism confirmed by the continuity column: the default left-to-right order
  builds the LONGEST runs (phi_cont ≈ 58, near the 64 ceiling); novelty tilt then
  breaks runs for a large −D_AB. Random/reversed orders yield phi_cont ≈ 40 (well
  below ceiling), so novelty has little to knock down and the asymmetry vanishes.
  The 45x asymmetry is DOWNSTREAM of an order-created continuity ceiling.
=> T-ORD says ARTIFACT (order manufactures it).

## T-COR (SECONDARY — corpus dependence) — corroborates ARTIFACT
dK at the fixed DEFAULT order O1, across 4 structurally different corpora
(C0 demo M=2; C1 synth M=2/4tracks; C2 synth M=3/6tracks; C3 synth M=2/3tracks;
each with its own inline-measured sigma_phi).

| corpus | dK ± SE | D_AB | D_BA |
|---|---|---|---|
| C0 demo | −0.413 ± 0.018 | −5.285 | −0.0007 |
| C1 (4 trk) | −0.415 ± 0.015 | −4.217 | +0.0088 |
| C2 (6 trk, M=3) | −0.335 ± 0.010 | −4.715 | +0.0014 |
| C3 (3 trk) | −0.371 ± 0.031 | −2.439 | +0.0011 |

across-corpus dK: mean −0.383, std 0.038 → roughly CONSTANT. H-GENUINE predicted
corpus-VARYING; observed corpus-CONSTANT → consistent with ARTIFACT (the asymmetry
is the default ordering's fingerprint, ~invariant to corpus content).
DISCLOSED LIMIT (prereg'd): the synthetic corpora are seeded-noise fixtures of
bounded structural diversity; the corpus-constancy is a fixture-scale finding. It
does not by itself force ARTIFACT — but combined with the T-ORD collapse it is the
expected ARTIFACT signature, not the GENUINE one.

## T-REV (TERTIARY — material time reversal) — CONFOUNDED, not independent evidence
Reversed the corpus succession graph read-only (inverted `RealizationIndex.successor`,
736 edges, scratch object; no repo edit) and re-measured on demo.

| condition | dK | D_AB |
|---|---|---|
| forward successor | −0.4125 | −5.156 |
| reversed successor | +0.1284 | +1.672 |

A DID change sign under time-reversal, which superficially matches H-GENUINE. BUT
it is CONFOUNDED: reversing the successor direction is structurally near-equivalent
to reversing the slot-threading order — and indeed the reversed-successor dK (+0.128)
matches the reversed-ORDER dK (+0.104, O2). So T-REV provides NO independent GENUINE
evidence; its change is fully consistent with the ordering mechanism (both reversals
invert run-building direction). Reported as confounded/inconclusive-as-independent.

## Why this rescues Theorem B (the decisive framing)
Under RANDOM slot order, K_AB ≈ 0 and K_BA ≈ 0 — BOTH tilt-tilt cross-derivatives
lie within the noise floor, i.e. Maxwell symmetry approximately HOLDS. The default
greedy left-to-right ordering inflates only K_AB (novelty→continuity) via the
run-building ceiling, breaking the symmetry. The antisymmetric residue is therefore
a SAMPLER-ORDERING artifact, not a legitimate directed-Gibbs residue. Theorem B is
not too strong; the deployed sequential fiber sampler is simply not the joint Gibbs
measure Theorem B describes, and its free ordering choice injects a spurious
antisymmetric term.

## SURFACED, NOT EXECUTED (ARTIFACT branch — per directive; routes to operator)
Do NOT change the musical sampler here. The characterization above (dK ≈ −0.38 at
the default order, collapsing to the floor under permutation, corpus-~invariant) is
the ORDERING BIAS to be SUBTRACTED from the holonomy/reciprocity readout so the
antisymmetric-residue meter reflects only T3, not the fiber ordering. Any actual
change to the greedy sequential threading (e.g. an order-symmetrized or jointly-
settled fiber block) is a SEPARATE pre-registered experiment gated on output
musicality — NOT done here. The P1/P3c FAIL-FINDINGS in Phase-1B are, on this
evidence, the ordering artifact, not a Maxwell/Theorem-B violation in the object.

## Repo integrity proof
`git status --porcelain` at close: EMPTY (byte-identical). HEAD b67a1bea. This
session wrote ZERO repo files; every script/datum is under scratchpad/asym/
(PREREG.md, harness.py, run_asym.py, smoke.py, results.json, RESULTS.md) for
auditor re-run. (At session start HEAD was 0e985899 with two ledger files pending
from a concurrent provenance hook; that hook committed them mid-session — none of
those edits are this session's, whose repo contribution is byte-zero.)
```
$ git status --porcelain
(empty)
```
</content>
