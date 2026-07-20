# PREREG (PROTOTYPE) — (track × role) SUB-TRACK field bias

**Status:** **PROMOTED + RATIFIED** (operator-directed 2026-07-20 "do autonomous... run it").
The prototype MEASURED as a LIVE control (ρ=1.0, strong damp, byte-identical off, provably
dodges the role wall), so per operator direction the drill is re-pointed onto it and it ships.
ets-auditor **PASS** on the mechanism (6f00fff) and **PASS** on the FE drill (d860937). Cleared
for merge + deploy. (Originally: PROTOTYPE / exploratory, operator-directed 2026-07-19.) Extends the field-bias
carrier (`PREREG-channel-bias-squares-REV2` track grain + `PREREG-field-bias-REV3`
unit grain, both left intact). Additive, byte-identical when off, single carrier
(I-1). **Awaiting ets-auditor PASS.**

## The idea: bias through an EMERGENT structure, dodging the role wall
REV3 MEASURED the **role wall**: within a fiber choice set
(`realize.FiberThreader._choose(k, b)`) every candidate shares the settled role `k`,
so a **pure** per-role addend is a softmax **constant** that cancels → inert (byte-
identical even at nonzero bias). Role provenance is an O-block property.

But within that same role-`k` set, the **TRACK varies**. So an addend keyed on the
**pair** `(track_id, k)` — applied only to candidates whose track is `T` **and** whose
slot role is `k` — **varies within the set** (only track-`T` candidates receive it) and
therefore **steers**. This is the first bias keyed on an **emergent** structure
(roles are training-emergent, unlike the input-level track/unit grains):

    addend(c) = β_track[c.track_id] + β_unit[c.unit_id] + β_track_role[(c.track_id, k)]
    β_track_role = LAMBDA['T1p'] · amplify,   amplify ∈ [-1, 1]   (same derived scale)

`k` is the slot's settled role — the `_choose(k, b)` argument, i.e. the same
`k = argmax(col · B[:,b])` `place_slot` used to make this the "role-`k` units in band
`b`" set. Empty/zero `track_role` map ⇒ no addend ⇒ **byte-identical**; `is_untilted`
still excludes the whole field bias, so F / O-block solve / settlement / render stay
byte-identical. It rides the ONE `TiltTerms.channel_logbias` tagged datum as a third
grain `{"track_role": {(tid, k) → β}}` (single carrier; the tuple key is coerced at the
single `TiltTerms` boundary alongside track/unit).

## Hypothesis
**H1(track_role):** biasing cell `(T, k)` monotonically raises (amplify) / lowers
(damp, below baseline) that cell's OUTPUT fraction — rows that are BOTH track `T` AND
settled role `k` — soft (coverage-contingent, does not pin), byte-identical at zero.
**Dodge:** a PURE role-`k` bias (ALL tracks in role `k`, equal) stays bit-identical to
baseline (inert), while the `(T, k)` cell bias MOVES — same grain, one track vs all.

**Null / disarm:** if the `(T, k)` pull is mushy (rank trend below the strong-monotone
bar), or a pure-role bias is NOT inert (would break the wall analysis), or an all-zero
map is not byte-identical (kill), the grain disarms honestly — no clamp is substituted.

## Gate (`cloud/tools/track_role_bias_verify.py`)
World: prefers the real **M=5 `corpus20.etsworld`** (20 tracks — emergent roles are
real there), falls back to `demo.etsworld`. Pick a well-covered `(T, k)` cell (headroom
both ways: `argmax min(cell, role_total − cell)` — competition to win AND presence to
lose). Role per produced row = the **slot role `k`** that produced it (captured by
observing `_choose` — the same `k` the addend keys on, so measurement is consistent
with the mechanism). Measure the cell's output fraction over SEEDS×NBAR bars at
`amplify ∈ {−1, −0.6, −0.3, 0, 0.3, 0.6, 1.0}`. Rare-event instrument (disclosed):
Spearman ρ + endpoints.

- `PULL_HOLDS` ⇔ ρ ≥ 0.7 AND `frac(+1) > frac(0)` AND byte@0.
- `DAMP_HOLDS` ⇔ ρ ≥ 0.7 AND `frac(−1) < frac(0)` AND byte@0.
- `DODGES_ROLE_WALL` ⇔ pure role-`k` bias (all tracks) bit-identical to baseline AND
  the `(T, k)` cell bias moves.

## RESULT — LIVE control (measured)
**`corpus20.etsworld` (M=5, 20 tracks, 2 seeds × 40 bars), cell (track 4, role 2):**

| amplify | −1.0 | −0.6 | −0.3 | **0.0** | 0.3 | 0.6 | 1.0 |
|---|---|---|---|---|---|---|---|
| cell frac | 0.0008 | 0.0090 | 0.0252 | **0.0678** | 0.0775 | 0.0969 | 0.1010 |

- **PULL_HOLDS** (Spearman ρ = **1.000**, gain +0.033) and **DAMP_HOLDS** (drop −0.067
  — damp drives the cell to ~0.001, nearly removing track 4 from role 2).
- **byte-identical@zero:** True.
- **DODGES_ROLE_WALL:** True — a pure role-2 bias across ALL 20 tracks is **bit-
  identical** to baseline (inert), while the (4, 2) cell bias moves.

**`demo.etsworld` (M=2, 4 seeds × 64 bars), cell (track 1, role 0):** baseline 0.147 →
+1: 0.482, −1: 0.0003 (ρ ≈ 1.0); pure-role inert, cell moves. Same story at M=2.

## Magnitude — where does (track × role) land?
- **whole-track** pull: strong, ~0.2 → 0.95 (up-weights track T's units EVERYWHERE).
- **single-unit** pull: weak, ~0.2% share (one unit vs a ~100-unit pool).
- **(track × role)** cell: **in between, and directional** — a strong DAMP (0.068 →
  0.001; 0.147 → 0.0003) and a moderate AMPLIFY (0.068 → 0.101; 0.147 → 0.482). It
  saturates below 1.0 because cell `T` competes with the other tracks' role-`k` units
  and cannot fully monopolize the role. It is a **LIVE, directional handle**, not mush.

## Honest verdict
The (track × role) handle is a **LIVE control**, not mush: a clean monotone rank trend
(ρ=1.0 on the real M=5 world), a decisive damp, byte-identical when off, and — the load-
bearing point — it **genuinely dodges the role wall** (the pure-role control is measured
inert while the cell moves). It is the first field handle that steers through an
emergent (training-derived) structure. Prototype only; no FE, no merge/deploy.

## FE WIRING (2026-07-20) — the field drill re-enabled onto ROLE cells
The field drill (`FIELD_DRILL_ENABLED`, `index.html`) is re-enabled and **repointed from
units to the (track × role) cells** — the proven emergent handle above. FE + engine_bridge
telemetry + app.py routing ONLY; the bias mechanism (`channel_bias.py`/`tilt.py`/
`realize.py`/engine) is FROZEN this phase; no root `ets/`. Byte-identical audio at neutral.

- **Drill:** a TRACK opens into its ROLE cells (`fieldTrackRoles(st, t)`): one cell per
  role `k` the track covers, self-sized by the participation-ratio noise floor
  (`fieldClearsFloor(profile)` gates the track; the top-`round(PR(profile))` covered roles
  are shown). A mushy/uncovered track drills to nothing — honest disarm. Role cells are
  atomic (no deeper level). The UNIT infra (`fieldTrackUnits`, `track_unit_pool`,
  per-unit glow, `unit_bias`) is retained **DORMANT** (defined but unreached). Still
  **one-flag shelve-able**: `FIELD_DRILL_ENABLED=false` restores track-level-only.
- **Bias:** a role cell (`["role", t, k]`) scroll/drag/arrow → a `(track, role)` amplify
  in [−1,1] → the JSON-safe wire form `track_role_bias = [[t, k, amp], …]`, coerced in
  `app.py` (`/api/steer`) to the `{(tid, role) → amp}` map `set_track_role_bias` consumes.
  Track squares still bias the whole track via `set_channel_bias` (additive roll-up,
  unchanged). Every publish sends all grains explicit-empty when unbiased ⇒ bridge None
  per grain ⇒ byte-identical.
- **Glow:** each cell glows by its OWN live share — `engine_bridge.track_role_activity`
  reduces the produced bar by `(track_id, slot-role k)`, the SAME emergent `k` the
  mechanism keys on, reconstructed from the committed `O` (for slot `s`, band `b`:
  `k = argmax(O[:,s]·B[:,b])`, mass `sqrt((O[:,s]@B)[b])`; rows matched to bands by mass).
  Read-only (no settle/write/render) ⇒ byte-identical. Normalized by peak cell mass to
  0..1, EMA-smoothed like the per-unit glow, emitted as `nowplaying_track_role` (`"tid,k"`);
  the FE reads it into each cell's `settled`. Glow (telemetry) stays separate from the bias
  ring (WEBFAB split). Label: `R{k}` + its live share % (an abstract emergent part; no
  invented human name).
- **Verified:** mass-conserving reduction (`sum track_role_activity == sum row mass`),
  per-cell divergence across bars; node drive of the FE pure logic (root=tracks →
  drill=role cells, cell bias → `track_role_bias`, own-glow, mushy-track disarm, neutral
  payload empty); app-route test coerces `[[t,k,amp]]` → `{(t,k):amp}` and clears on
  absent; `test_channel_bias` mechanism byte-identity unchanged.
