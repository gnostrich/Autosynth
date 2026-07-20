# PREREG (PROTOTYPE) — (track × role) SUB-TRACK field bias

**Status:** PROTOTYPE / exploratory (operator-directed 2026-07-19). Build the
mechanism + a gate, MEASURE, report — **do NOT merge/deploy**. Extends the field-bias
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
