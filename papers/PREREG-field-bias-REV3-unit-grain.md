# PREREG revision R3 — field bias at MULTIPLE DRILL GRAINS (track roll-up + unit "channel")

**Status:** **RATIFIED** by operator (2026-07-19) — directed the units-are-ultimate /
track-grouping / roles-internal design; ets-auditor **PASS** on Phase A (unit+track grain,
role-wall confirmed, byte-identical off). Cleared for merge + deploy.
Operator-directed 2026-07-19 (Phase A = mechanism + gate; NO FE this
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

---

# Phase B — the FIELD as the single Play steering surface (UI, FE + routing only)

**Status:** **RATIFIED** by operator (2026-07-19) — field replaces XY, drill track→units,
role internal; ets-auditor **PASS-WITH-NOTES** (two non-blocking dead-code notes; mechanism
frozen, byte-identical at neutral, test changes are legitimate realignment, WEBFAB guard teeth
intact). Cleared for merge + deploy.
Operator-directed 2026-07-19. **FE + app.py routing ONLY** — the bias
MECHANISM (channel_bias.py / tilt.py / realize.py / engine) is FROZEN this phase
(Phase A). No root `ets/` edit. Branch `claude/field-surface-unified-*`.

## What Phase B does
Restores the drill FIELD component (removed in commit `16a8f53`) as the Play steering
surface, **REPLACING the XY pad** — a socket swap of the pad element, the rest of the
page byte-for-byte unchanged. The field wires the Phase-A bias mechanism at exactly two
grains:

- **TRACK square → the track roll-up bias** — the ratified REV2 `channel_bias` path
  (`set_channel_bias`, the per-channel amplify vector keyed by source track).
- **UNIT square → the unit grain** — `unit_bias = {unit_id → amplify}` (`set_unit_bias`,
  Phase A). The square key is `["unit", role, uid, tid]`; the **uid** drives the setter.

Both are bidirectional `amplify ∈ [-1,1]` (hover-scroll / vertical drag / arrows: up =
amplify, down = damp), reusing the field's existing per-key bias ledger `st.bias[key]`,
now resolved by `fieldBiasPayload(st)` into the two engine datums (this REPLACES the old
region-vector send — the field no longer steers the region lane).

## Drill = TRACK → UNITS (role HIDDEN)
Root shows TRACK squares. Drilling a track opens **that track's own units** from
`static_field().track_unit_pools[track_id]` (`fieldTrackUnits`), still gated by the
participation-ratio noise floor (`fieldClearsFloor(profile)`) so a mushy track disarms.
**Role is never surfaced, labeled, or a bias target** — the bias key's role slot is
internal (key-string only); the bias resolves to `unit_id` → `set_unit_bias`. This
honours the operator's locked hierarchy: units are the ultimate bias target, track is the
roll-up, role is internal to training (it steers, if ever, through the O-block **region
lane**, per the Phase-A role wall — not here).

### Per-track unit pool — an INPUT-LEVEL display fix (pre-Gibbs, read-only, byte-identical)
The first cut gathered units from the ROLE pools (`role_unit_pool`) filtered by
`track_id`. BUG (found on the live set): `role_unit_pool` keeps a GLOBAL top-N per role
ranked by `B[i, band]`; on a degenerate anchor matrix B (k=1: every anchor ranks the
bands near-identically) ONE track's bands sweep the top-N of EVERY role, so all role
pools are the same track — the other tracks clear the noise floor yet drill to **nothing**.
FIX (cloud layer, `engine_bridge.track_unit_pool`, do NOT edit the engine tree): a
per-track pool keyed by the unit's OWN track (from `track.provenance_index`), ranked by
band anchor-salience `max_i B[i, band]` (ties by `unit_id`), capped `top_n = 48`, entry
shape mirroring `role_unit_pool` (`unit_id, track_id, band, profile=B[:, band]`). Membership
is ground-truth provenance, independent of B's degeneracy, so **every floor-clearing track
drills to its own units**. Served in `static_field` as `track_unit_pools` under the SAME
`profile_armed` arming gate as the role `unit_pools` (a band-blind world still disarms the
drill honestly); the role `unit_pools` are KEPT in the payload. This is a static read-only
reduction of the frozen world (B + provenance) — it touches NOTHING in the Gibbs machine,
so **audio is byte-identical** (the bias mechanism and `/api/steer` routing are unchanged).

## Glow vs bias — kept honestly distinct
Square **FILL/glow = LIVE settled telemetry** (`fieldApplySettled`) — the engine's answer,
never the input echoed back. The bias **RING is a SEPARATE bipolar indicator** (accent =
amplify, damp hue = damp, neutral centre, width by `|amplify|`). The two are never
conflated.

### Per-unit OWN glow (telemetry-only, byte-identical)
Operator principle: EVERY square glows by its OWN live settled telemetry. Track squares
already diverge (per-track `nowplaying_activity`). Unit squares previously borrowed the
TRACK's glow (`nowplaying[t]` for every unit), so they could never diverge — a violation.
FIX (telemetry + display only): `engine_bridge.nowplaying_unit_activity(rows)` is the
per-UNIT counterpart of the engine's per-track reduction — it sums the produced bar's row
mass by `src_unit` (`r.rows` = `(slot, tid, uid, sec, mass)`) and normalizes by the bar's
peak unit mass to 0..1 (the SAME scale as per-track). Emitted on the telemetry frame as
`nowplaying_unit`; the FE (`fieldApplySettled` → `fieldNowPlayingUnit`; `fieldTrackUnits`)
sources each unit square's `settled` from `st.nowplayingUnit[uid]` (0 = dark if unplaced).
**Smoothing (disclosed):** per-track glow is fresh-per-bar, but only a sparse subset of
units is placed per bar (~60 of N), so the per-unit map gets a light **EMA** across bars
(`_NP_UNIT_ALPHA = 0.45`, prune below `1e-3`) so a just-played unit FADES over a few bars
instead of strobing. This smooths REAL placement telemetry — a unit only ever lights from
a bar that actually placed it and decays monotonically to 0 once it stops; nothing is
fabricated, and it is never the bias echoed back (the WEBFAB glow/ring split holds). Reads
placed rows only — no settlement / writer / render / F — so **audio is byte-identical**.
Verified: on demo, per-bar per-unit maps carry ~57-64 distinct units with 8-15 distinct
glow values, units WITHIN a track diverge, and the active set changes bar-to-bar.

## Honest disarm (retained, no fakes)
- **Unit drill self-sizes:** a track drills only where its sub-structure clears the
  shuffle floor (`fieldClearsFloor`); a mushy track drills to nothing (honest inert),
  never a fake drill. On a band-blind world (`profile_armed:false`) the server already
  serves EMPTY `unit_pools`, so tracks are non-expandable and the refused drill names the
  wall (`fieldRefuseUnitGrain` → the registered "unit grain disarmed" caption).
- **No track-lean disarm:** the track grain rides the ratified REV2 fiber lean, which does
  NOT route through the anchor band-profile B, so it is never disarmed — the old
  track-lean disarm caption is removed (not orphaned).

## Byte-identity at neutral (the hard invariant)
`fieldBiasPayload` sends BOTH grains on EVERY publish (explicit-empty, never omitted): an
all-zero channel vector ⇒ `set_channel_bias` → None; an empty unit map ⇒ `set_unit_bias`
→ None. No square biased ⇒ no fiber addend ⇒ **bit-identical audio** (Phase-A
`test_channel_bias.py` proves the mechanism-level identity; Phase B does not touch it).
`/api/steer` routes `unit_bias` via `p.set_unit_bias(data.get("unit_bias"))` (absent ⇒
cleared) and keeps the REV2 `channel_bias` path unchanged.

## Socket-swap surface (what changed on the page, and ONLY this)
Removed from the pad-hero: the XY radial pad mount (`#radialWrap`), the flat channel-
squares grid (`#channelSquares`), the aim/shape/squares `padMode` toggle, and the pad-foot
(the puck/mark legend + the now-dead "earned words" toggle). The field canvas + legend +
status take their place. `buildRadialOnce` was decoupled so the KNOBS band extra-mode
strips (a separate surface merely co-located with the pad build) keep working
byte-identically without the pad wrap. Everything else (header, tabs, tracklist,
transport, Train, telemetry lanes, knobs, chrome) is byte-for-byte unchanged.

## Gate / verification (Phase B)
- `cloud/tests/test_field_unit_bias_route.py` (**new**): `/api/steer` routes `unit_bias`
  → `set_unit_bias` (present → map; absent → cleared/None); REV2 `channel_bias` →
  `set_channel_bias` unchanged.
- `cloud/tests/test_track_unit_pool.py` (**new**): per-track membership (every unit in
  track T's pool has `track_id == T`); every floor-clearing track non-empty on a spread
  world; and the bug/fix contrast — the OLD global-role-pool-filtered-by-track move
  starves non-dominant tracks on a degenerate-but-armed B, while `track_unit_pool` gives
  each track its own units; `top_n` cap holds. On `demo.etsworld` the frozen B is
  band-blind (`profile_armed=False`), so the drill honestly disarms there; the fix is
  exercised on an armed multi-track fixture. Ungated, `track_unit_pool(demo.world)` gives
  each of the 4 tracks its own 48 units (all `track_id == T`).
- `cloud/tests/test_web_fab_guard.py`: the restored "settled telemetry" and "unit grain
  disarmed" captions re-registered to their real backings (`fieldApplySettled` /
  `fieldRefuseUnitGrain`).
- `cloud/tests/test_fe_render_smoke.py` + `test_eigenpanel.py`: realigned from the
  field-removed / pad-present state to the Phase-B socket swap (field present, pad gone).
- Node drive of the extracted FIELD PURE LOGIC on a synthetic world: root = tracks;
  drilling a track shows ONLY that track's units (filtered by `track_id`, role hidden);
  breadcrumb carries no role level; neutral `fieldBiasPayload` is empty (byte-identity);
  track bias → `channel_bias[channel]`, unit bias → `unit_bias[uid]`; a mushy track is
  non-expandable (honest disarm). Full-browser drill/bias-under-live-telemetry was NOT
  driven headlessly (it needs a booted world + play loop; the closure-encapsulated field
  state is not reachable from `page.evaluate`) — disclosed, not claimed.
