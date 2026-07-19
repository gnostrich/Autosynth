# PREREG revision R3 — field bias at MULTIPLE DRILL GRAINS (track roll-up + unit "channel")

**Status:** operator-directed 2026-07-19 (Phase A = mechanism + gate; NO FE this
phase). Extends `PREREG-channel-bias-squares-REV2-bidirectional.md` (**RATIFIED**);
the REV2 record is left intact. This is a **GRAIN GENERALIZATION of an already-
ratified control**, not a new mechanism: the soft bidirectional `channel_logbias`
addend at `fiber_choice_logits` already leans a candidate by an additive log-weight;
REV3 resolves that addend from MORE THAN ONE grain of the candidate, additively.
**Awaiting ets-auditor PASS.**

## Why this is not a new mechanism (the physics premise, honored)
The fiber choice is a **softmax** over the pooled candidate units at each beat. REV2
biased a candidate by its **source track** (`β_track[track_id]`). REV3 keeps the SAME
softmax addend and resolves it from BOTH grains the candidate distinguishes:

    addend(candidate) = β_track[candidate.track_id]  +  β_unit[candidate.unit_id]

- **unit** = the operator's ultimate **"channel"** (a beat-normalized sound unit),
  addressed by `unit_id`.
- **track** = the **roll-up**: biasing a track leans ALL of its candidate units. It
  is **bit-for-bit unchanged** from REV2, so its ratified gate keeps holding.
- A candidate biased at **both** grains gets the **SUM** (the roll-up plus the unit-
  specific lean on top): "channel is ultimate, same logic applies at track level."

Each grain is an independent bidirectional `amplify ∈ [-1, 1]` map, `β = LAMBDA['T1p']
· amplify` (the same derived F-scale, read live — no hand-set constant). Both ride the
**ONE** `TiltTerms.channel_logbias` (single carrier, **I-1**): one tagged datum
`{"track": {tid→β}, "unit": {uid→β}}`, and `fiber_choice_logits` still receives **ONE**
per-candidate addend array. No second decision channel, no clamp, no new lane.

## Model
    log w(c) = −E_F(c)/T_s + λ_cont·1[cont](c) + λ_novelty·reuse(c) + β(c)
    β(c)     = β_track[c.track_id] + β_unit[c.unit_id],   β_g = LAMBDA['T1p']·amplify_g

- `amplify > 0` → positive addend → up-weight that grain's candidates (amplify).
- `amplify < 0` → negative addend → down-weight (soft damp).
- **empty at EVERY grain** → **no addend** → **byte-identical** fiber draw (hard
  invariant, unchanged from REV1/REV2).

`is_untilted` continues to **exclude** the whole field bias (all grains), so F / the
O-block solve / settlement / render stay **byte-identical**; only the fiber choice
leans. Carrier normalization lives at the single `TiltTerms.__post_init__` boundary
(a bare `{tid→β}` map — the ratified REV2 track projection — is lifted to
`{"track": ...}`), so `realize._choose` reads exactly one tagged form.

## Bias is available at all three drill grains — but by TWO mechanisms, not one
The drill hierarchy is **track → role → unit**. Amplify/damp is available at all
three, each bidirectional — but they do **not** all live at the fiber measure,
because a per-candidate fiber addend can only steer an attribute that **VARIES within
a fiber choice set**:

| grain | key | varies within a choice set? | steering mechanism |
|---|---|---|---|
| track | `track_id` | **yes** (a role/band pool spans tracks) | fiber addend `β_track` |
| unit  | `unit_id`  | **yes** (each candidate is a distinct unit) | fiber addend `β_unit` |
| role  | anchor `k` | **NO** (the set IS "role-k units in band b") | O-block **region lane** |

**Track and unit** are carried as fiber addends (this REV3). **Role is NOT a fiber
grain** — see the wall below.

## WALL (surfaced, not patched, MEASURED) — role is an O-block property
In `realize.FiberThreader._choose(k, b)` the entire candidate set is "role-`k` units
in band `b`" (`build_index` files each candidate under its intrinsic role, realize.py
line ~171), and the role `k` itself is chosen by the **O-block** at `place_slot`
(`k = argmax(col · B[:,b])`), which the fiber never revisits. So a per-candidate
**role** addend `β_role[k]` is the **same constant added to every candidate in the
set** → it cancels in the softmax / Gumbel-argmax → the draw is **byte-identical even
at nonzero role bias** (inert). MEASURED: adding `+LAMBDA['T1p']` to *every* track
equally (exactly the constant a role bias contributes within any one choice set)
leaves the produced rows **bit-identical** to baseline over 16 bars.

A role addend at the fiber measure would therefore be a **silent no-op**, so it is
**surfaced, not built**. Role steering is an **O-block** phenomenon: `φ_region` is
per-anchor = **per-role** (an O-block tilt through `λ_region`), and that control
**already exists** as the first-class **REGION lane**. The clean resolution is:

> Role amplify/damp = the existing region lane (`u_region[k]`), NOT a duplicate fiber
> addend. Track and unit steer at the fiber; role steers at the O-block.

If a future need calls for a role "square" with the same UI affordance as the track/
unit squares, it must be wired to the region lane (an O-block tilt, σ_φ-scaled),
which is a **separate, region-lane-scoped change** — out of scope for this fiber-
measure REV3, and offered here as the proposed spec resolution rather than a fiber
gambiarra.

## Hypothesis
**H1(unit):** biasing a UNIT monotonically **raises** (amplify) / **lowers** (damp,
below the amplify=0 baseline) **that unit's** own provenance share, **soft** (it does
not pin — a unit only leans where its (role, band) makes it a candidate; the pull is
**coverage-contingent**), **byte-identical at zero**. The track half (REV2 H1) is
unchanged and re-measured for regression.

**Null (H0):** the unit lean does not move the unit's provenance share monotonically,
or the all-zero field is no longer byte-identical.

**Kill condition:** any all-zero (any-sign, any-grain) input that is not byte-
identical is a kill (invariant breach). If the unit pull is mushy (rank trend below
the strong-monotone bar), the unit grain **disarms HONESTLY** — never patched with a
hard clamp, exactly as REV1/REV2 disarm a mushy channel.

## Gate (`cloud/tools/field_bias_unit_verify.py`, on committed `demo.etsworld`)
Pick a real `unit_id` from `static_field()['unit_pools']` with nonzero baseline
occurrence. Over `SEEDS × NBAR` fresh-writer bars per amplify, measure the TARGET
unit's provenance share (fraction of `r.rows` whose `unit_id == target`) at
`amplify ∈ {−1, −0.6, −0.3, 0, 0.3, 0.6, 1.0}`.

**Instrument choice (disclosed):** a single unit's provenance is a **rare-event**
statistic (~0.7% of rows on demo, where M=2 → ~100-unit choice sets), so its per-step
deltas sit **below sampling noise** while the endpoints move materially — the signal
concentrates at `|amplify|→1`. The noise-robust operationalization of "monotonically
raises/lowers" is therefore the **Spearman rank correlation** ρ(amplify, share) over
the full bidirectional sweep, plus endpoint ordering. This is instrument design for a
rare-event statistic, **not** a loosened threshold.

- `UNIT_PULL_HOLDS`  ⇔  ρ ≥ **ρ_min = 0.7** (strong positive rank trend) **AND**
  `share(+1) > share(0)` (rises above baseline) **AND** byte-identical@zero.
- `UNIT_DAMP_HOLDS`  ⇔  ρ ≥ **ρ_min = 0.7** **AND** `share(−1) < share(0)` (falls
  below baseline) **AND** byte-identical@zero.
- `ROLE_WALL_CONFIRMED` ⇔ a per-choice-set-constant addend (every track +β equally)
  yields **bit-identical** rows to baseline (role is inert at the fiber; reported,
  not gated as a pull).
- Regression: re-run `cloud/tools/channel_bias_pull_verify.py` and confirm the track
  grain still `H1_HOLDS` + `DAMP_HOLDS`, **unchanged**.

## Success / stop
SUCCESS: the unit lean raises/lowers the unit's own provenance share with a strong
monotone rank trend and material endpoint moves, byte-identical at zero; the track
regression is unchanged; the role wall is confirmed and its region-lane resolution is
recorded. STOP/DISARM: if the unit pull is mushy on demo (ρ < ρ_min), the unit grain
disarms honestly — the mechanism is retained (it is coverage-contingent; Phase B's
drill exposes units only where sub-structure clears the noise floor) and NO clamp is
substituted.
