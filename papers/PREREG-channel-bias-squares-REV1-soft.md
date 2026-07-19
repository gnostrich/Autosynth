# PREREG revision R1 — channel-bias squares: SOFT mechanism (supersedes the clamp)

**Status:** **RATIFIED** by operator (2026-07-19) — CLAUDE.md §4 sign-off for the
soft fiber-measure engine edit; cleared for merge + deploy. ets-auditor verdict
PASS-WITH-NOTES (both notes cleared: docstring honesty fix committed; this ratification).
Operator-directed mechanism correction (2026-07-19). This is a versioned revision of
`PREREG-channel-bias-squares.md`; the original prereg is left intact as the record.
Phase-1 gate result included.

## Why the original (clamp) mechanism was rejected — the wall
The committed prereg imposes the per-channel bias via the sanctioned **I-7 clamp**
(`unit_demands`): amplify T ⇒ pin a fraction (∝ amplify) of a bar's slots to real
track-T units. Two first-principles problems surfaced in build:

1. **A clamp is a hard direct force, not the intended design.** It PINS slots; the
   settlement does not choose them. The operator's model ("the Gibbs settlement
   PERCEIVES a lean and settles AROUND it") is a SOFT prior, not a boundary
   condition. The clamp "pull curve" is largely tautological (a pinned slot is
   track-T by construction).
2. **The prereg's causal story is false under the actual F.** The prereg says "the
   free slots re-settle to accommodate the constraint." Measured: the settlement F
   is **slot-separable** (`f.term_T2` is a per-(role,slot) generalised-KL;
   `f.term_T3`'s collision sum factors per slot), so a clamp does NOT make free
   slots re-settle. There is no "work around it" — only the hard override.

## The soft mechanism (built)
**Where channels actually live:** the O-block settlement is in ROLE space (M
anchors); tracks/channels re-enter only at the **fiber choice measure** — the
Layer-0 Gibbs draw over the *pooled-channel candidate units* at each beat
(`ets.writer.tilt.fiber_choice_logits`). That is exactly the operator's phrase
"a distribution over the pooled channels at each beat."

**Hook (soft, generative, nothing pinned):** amplify channel T adds a per-candidate
log-weight to that measure:

    log w(c) = −E_F(c)/T_s + λ_cont·1[cont](c) + λ_novelty·reuse(c) + β_T(c)

where `β_T = LAMBDA['T1p'] · amplify` for candidates whose source track is T (0
otherwise). The settlement PERCEIVES the lean and accommodates it: track-T units
are drawn more often **where they are candidates**, and run-continuation / other
bands settle around that. Nothing is pinned; a channel with no candidate at a beat
gets no lean there, so the pull is contingent on the settled O and the channel's
coverage — soft and degeneracy-exposed.

**Strength scale (derived, not hand-set):** `LAMBDA['T1p']` (F's own metrical
phase-charge weight, read live) — amplify=1 leans by one natural unit of preference
on the same log-odds scale the fiber energies live on. amplify ∈ [0,1] = strength;
zero/empty ⇒ no addend ⇒ **byte-identical**.

**Carrier (I-1, single control object):** a new optional `TiltTerms.channel_logbias`
({track_id → log-weight}), threaded through the SAME single construction point
(`_tilt_for → layer0 → TiltTerms`) as the `a` anisotropy. NOT a φ lane, no σ scale,
NO effect on the settled O mode (fiber block only). No new lane, no second channel,
no clamp.

## Engine touch (architecture-v6/ets only; root ets/ untouched)
- `writer/tilt.py`: `TiltTerms.channel_logbias` field (+ validation); `untilted`,
  `layer0` thread it; `fiber_choice_logits` takes an optional per-candidate addend.
- `writer/realize.py`: `FiberThreader._choose` builds the per-candidate addend from
  `tilt.channel_logbias` and passes it (rng draw size unchanged ⇒ zero perturbation
  at zero bias).
- `engine/engine.py`: `_tilt_for(..., channel_logbias=None)` threads it to `layer0`.
- `is_untilted` intentionally excludes `channel_logbias` (like `a`): a channel-only
  lean settles O to the untilted mode and biases only the fiber draw.

## Phase-1 gate (H1) — RESULT: H1 HOLDS
World: **`demo.etsworld`** (4 real committed channels, M=2). NOTE — the prereg names
`scratchpad/corpus20.etsworld` (20 channels); that asset was uncommitted and was
reverted by a container restart, is absent from the repo, and cannot be rebuilt
without its source audio. The gate is corpus-agnostic; only the channel COUNT
differs. (`cloud/tools/channel_bias_pull_verify.py`; results
`papers/channel_bias_pull_results.json`.)

Per-channel track-T output-unit fraction vs amplify {0, 0.3, 0.6, 1.0}:

| channel | 0.0 | 0.3 | 0.6 | 1.0 |
|---|---|---|---|---|
| track 0 | 0.30 | 0.74 | 0.92 | 0.95 |
| track 1 | 0.23 | 0.73 | 0.90 | 0.95 |
| track 2 | 0.27 | 0.78 | 0.95 | 0.97 |
| track 3 | 0.21 | 0.68 | 0.89 | 0.92 |

Monotone (4/4), material (4/4), confusion diagonal-dominant, byte-identical at zero
(rows + settled O bit-identical). The soft lean does NOT saturate at 1.0 — it stays
generative (unlike the clamp). This is the OPPOSITE of the observable/region-lane
collapse, because the lean acts directly on the pooled-channel distribution rather
than through the rank-1 role-occupancy bottleneck.

## Proposed spec change
Replace Method step 1 ("Bias mechanism (clamp / I-7)") and step 2 ("Bridge") of the
original prereg with the soft fiber-measure lean above; keep the FE (step 3),
preservation walls, and success/stop criteria. Awaiting operator ratification.
