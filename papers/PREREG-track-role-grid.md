# PREREG — TRACK × ROLE GRID steering surface

Status: pre-registered before the run. Gate tool: `cloud/tools/track_role_grid_verify.py`.
Scope: `cloud/` front-end + read-only bridge telemetry ONLY. No root `ets/` edit, no
`architecture-v6/ets` engine edit. Byte-identical audio when every grain is neutral.

## The surface

The Play field is laid out as a labeled MATRIX (flag `FIELD_GRID_ENABLED`, default true;
one-flag reversible to today's drill field, which stays intact and dormant under the flag):

- **rows = source tracks** (real ingested names, `fieldTrackName` / `fieldTrackName` from
  `track_names`),
- **columns = roles k=0..M-1** (`R{k}` + live share %, the abstract emergent handle — no
  invented human name, same convention as today's role cells),
- **interior = (track, role) cells**.

Row headers, column headers, and cells are each independently biasable in [-1,1] (scroll /
drag / arrow; up = amplify, down = damp; soft-saturate) — the field's existing look and
interaction, only re-laid-out as a matrix.

## The seen-through routing (each grain -> the step that weighs that type)

| grid element        | lane / step                     | engine datum (existing setter)            |
|---------------------|---------------------------------|-------------------------------------------|
| CELL (track, role)  | CASTING / **fiber pick**        | `track_role_bias` -> `set_track_role_bias`|
| ROW (track)         | CASTING / **fiber pick**        | `channel_bias` -> `set_channel_bias`      |
| COLUMN (role k)     | **SETTLEMENT** (region tilt)    | `region` -> `set_region` (`u_region[k]`)  |

**Why the COLUMN cannot ride the fiber (the measured role wall).** A per-candidate fiber
addend can only steer an attribute that VARIES within a fiber choice set. Within one choice
`FiberThreader._choose(k, b)` every candidate shares the settled role k (the set IS "role-k
units in band b"), and k is chosen by the O-block (`place_slot: k = argmax(col·B[:,b])`). A
PURE role addend is therefore a softmax CONSTANT -> it cancels in the Gumbel-argmax and leaves
the draw byte-identical even at nonzero bias (INERT — measured in PREREG-field-bias-REV3 and
re-asserted by PREREG-track-role-bias's `control_pure_role_inert`). Role provenance is an
O-block property, so a pure-role push steers OCCUPANCY through the region (settlement) lane —
which is exactly `φ_region` (per-anchor = per-role, an O-block tilt through λ_region). The
column is routed to `region` only; routing it to the fiber would be a silent no-op.

Rows and cells DO vary within a choice set (via the track key), so they ride the pick — as
ratified by the channel-bias and track-role-bias gates. All three lanes are INDEPENDENT and
COEXIST (rows/cells on the pick lane, columns on the settlement/region lane): a player can
cast AND arrange at once.

## REGION_SCALE (the column gain — not invented)

`REGION_SCALE = ets.panel.envelope.SAFE_REGION_MAGNITUDE` (= 1.0), the engine's OWN
safe-envelope cap: the value `EngineBridge.set_region` clamps the transmitted region lean to
(`clamp_region`) and the value the pad ring is painted at. amp in [-1,1] maps a single role
column LINEARLY onto the full in-range single-column region tilt [-1,1] with NO clamp
dead-zone (using the KNOBS' nominal ±3 half-range would put amp>1/3 in the clamp's dead zone).
Multi-column combos ride the same `clamp_region` the KNOBS already ride. The value is exposed
as READ-ONLY telemetry `region_cap` on `/api/world` (mirrors the σ_φ.region amplitude the
bridge already reports) so the FE does not hardcode a magic number and tracks the engine
constant. `region_cap` is consumed ONLY by the FE's outbound region scaling — never an
objective, gradient, or settlement input.

## Honest disarm on the column

If region is DISARMED for the corpus (`!world.regionArmed`, i.e. σ_φ.region unidentifiable):
the column headers still RENDER but are DIM + tagged `off` (steer-INACTIVE), the column-bias
gesture is REFUSED (no lean accumulates), and `fieldBiasPayload` emits no region addend. The
engine backstop is the same: `layer0` applies the EXACT identity tilt on an unidentifiable
region lane, so a column push settles no differently. Never a fake control.

## Glow (read-only, byte-identical — the WEBFAB split)

Glow (telemetry) is drawn as fill alpha; the bias RING is separate (accent = amplify, damp
hue = damp). Row header glows by that track's activity (`nowplaying`); each cell glows by its
(track,role) activity (`nowplaying_track_role`); the COLUMN header glows by that role's
activity = Σ over tracks of `nowplaying_track_role[*,k]` (client-side, mass-conserving
reduction). The column SHARE % is that same reduction normalized across columns (a genuine
partition of live placements). No fabricated pulse; glow never enters the bias/steer path.

## Byte-identity invariant

Every publish sends every grain explicit-empty when unbiased: `region` = zero-init base (the
column addend is 0), `channel_bias` all-zero -> None, `track_role_bias` [] -> None,
`unit_bias` {} -> None. Bridge None per fiber grain + zero region -> neutral tilt -> BYTE-
IDENTICAL audio when all neutral.

## Gate (kill conditions)

Run on the real region-ARMED world `corpus20.etsworld` (M=5) if reachable, else `demo.etsworld`.

- (a) COLUMN(role k) region push MEASURABLY moves role-k output share: Spearman ρ ≥ 0.7 AND
      amp+1 > base AND amp-1 < base. Null: ρ < 0.7 or no endpoint separation -> the column
      does not steer settlement (KILL).
- (b) ROW(track) and CELL(track,role) still steer via the PICK: monotone pull (ρ ≥ 0.7,
      amp+1 > base) each. Null: a pick grain went inert (KILL — regression on ratified paths).
- (c) BYTE-IDENTICAL when every grain is explicit-empty. Null: any bit differs (KILL).
- (d) COLUMN honestly DISARMS: under a region-DISARMED sigma (`identifiable['region']=False`,
      the exact bridge `region_armed=False` state) the SAME push is bit-identical to neutral,
      AND under the ARMED sigma that push is NOT inert (the contrast). Null: push moves the
      tape on a disarmed world, or is inert on an armed one (KILL).
- (e) All three COEXIST: column push raises role-k share (settlement), and adding the row +
      cell pick pushes on top of it further raises track-T share and cell-(T,K) share and
      changes the draw (fiber). Null: any of the three fails to act when combined (KILL).

## RESULT (real numbers, pasted from the run)

Run: `python3 cloud/tools/track_role_grid_verify.py` — results JSON at
`papers/track_role_grid_results.json`.

**RUN: `world=corpus20.etsworld  M=5  tracks=20  seeds=2  bars=24  REGION_SCALE=1.0
region_armed=True`  → GRID_VERDICT = PASS (163.9s).** Target column role K=2
(baseline share 0.2464, σ_φ.region[K]=0.0337); target row/cell track T=4.

- **(a) COLUMN(role 2) → SETTLEMENT.** role-2 output share over the amp sweep
  `[-1,-0.6,-0.3,0,0.3,0.6,1]`:
  `0.0176, 0.0299, 0.1016, 0.2464, 0.5729, 0.9378, 1.0000`. base=0.2464, amp+1=1.0000
  (pull gain +0.7536), amp-1=0.0176 (damp drop -0.2288), **Spearman ρ = 1.000** →
  `COLUMN_STEERS_SETTLEMENT = True`.
- **(b) ROW(track 4) → PICK.** track-4 share `0, 0, 0.3034, 0.8854, 0.9840` over
  `[-1,-0.5,0,0.5,1]`; base=0.3034, amp+1=0.9840, **ρ=0.975** → `ROW_STEERS_PICK = True`.
  **CELL(4,2) → PICK.** cell share `0.0013, 0.0081, 0.0830, 0.0827, 0.1162`; base=0.0830,
  amp+1=0.1162, **ρ=0.900** → `CELL_STEERS_PICK = True`.
- **(c) BYTE-IDENTICAL neutral = True** (region zeros + `field_logbias()`=None → bit-for-bit
  the untilted writer, 8 bars).
- **(d) COLUMN honest disarm = True.** Under a region-DISARMED sigma the same amp+1 column
  push is bit-identical to neutral (`column_disarm_inert=True`; engine logs "DISARMED lane
  leaned: region[2] … NO tilt applied" — the identity backstop), while under the ARMED sigma
  that push is NOT inert (`column_armed_moves=True`).
- **(e) ALL THREE COEXIST = True.** Column push alone: role-2 share 0.2464→0.9378
  (`coex_col_acts`). Adding row+cell pick on top: cell-(4,2) share 0.1738→0.6585
  (`coex_cell_acts`), track-4 share 0.1946→0.7172 (`coex_row_acts`), and the draw changes
  (`coex_fiber_changes_draw`). Settlement (column) and pick (row, cell) act independently and
  simultaneously.

Results JSON: `papers/track_role_grid_results.json` (committed with this prereg).
