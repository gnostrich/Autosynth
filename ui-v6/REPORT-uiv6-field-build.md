# ui-v6 FIELD surface — build report (for ets-auditor)

Builder session 2026-07-17, against `PREREG-uiv6-field.md`. Base `main` @
`5ff6abd`, tag `pre-uiv6-field-2026-07-17`. architecture-v6 (ui-v5) untouched.

## What exists (vs what the prereg describes)

| Prereg item | State |
|---|---|
| Fork + tag + prereg first | DONE (commit 807daf3 before any build) |
| `field.py`: FieldModel/FieldView, squares, zoom, bias, ring-vs-fill | DONE |
| Brightness = settled telemetry only (FIELD-INV, capability + AST + bites) | DONE, tests/field/test_field_inv.py (6 tests) |
| Hover-scroll bias -> existing region lane only | DONE (`set_region_vector` path; live.py `push_field_bias`) |
| Soft saturation, never hard-mute (FIELD-B) | DONE, incl. REAL-writer disfavor-not-mute test |
| Co-movement + dynamic sensitivity vs REAL writer (FIELD-A) | DONE (unnormalized settled projection; fixture asserts region ARMED, fails loudly if disarmed) |
| Self-sizing drill by participation ratio, pinned to anchors.effective_rank (FIELD-C) | DONE (formula restated, NOT imported; pin test) |
| Outboard: static door + single-lane wire + byte-identical delete test (FIELD-D) | DONE |
| No fabrication (FIELD-E) | DONE (real-or-absent tests) |
| Remove pads/XY/drill in ui-v6 only | DONE: `pads.py`, `tap.py` deleted; `_RegionXYPad` excised (tombstone note); `_RegionStrips` kept hidden as the §8 region control |
| Sliders/tempo/transport/cue/meters/library unchanged | DONE (cue click-to-audition on unit squares keeps ui-v5 semantics + wall) |
| Legacy suites adapted, old version's suites untouched | DONE (mapping below) |

## Test mapping (old surface -> field)

- v5b hover-inert: XY/pad checks -> field edition (no tracking/move handler).
- v5c pick-and-place, uv5c roam, uv5b emit-throttle: DELETED — XY-pad-specific
  mechanics; their surviving invariants (cap on any reachable state; slew-bounded
  single-lane emission; no raw-jump flood) carried by tests/field/test_field_d_
  outboard.py::test_field_gesture_reaches_only_the_region_lane and
  test_field_b_softbias.py. The XY pad itself remains testable one version back.
- v5a outboard: XY gesture block -> panel region entries + field gesture.
- v5d clamp: XY dot/ring tests dropped; clamp backstop + panel-wire tests kept.
- v5f door: `_xy` wiring assertion -> XY-absence + `set_region_vector`->_push.
- pi tap-routes-region -> field bias-routes-region (same single-channel proof).
- pi drill-gesture -> zoom drill + unit fine-bias + CUE (same lean assertions).
- pi ui-cleanup: ITEM 1 strips-hidden (minus XY), ITEM 2 all-M squares render,
  ITEM 3 library display-only unchanged, ITEM 4 NEW: pads/tap/XY GONE in ui-v6.
- f3 tap+affordance: tap envelope tests -> bias accumulate/unwind; disarmed-lane
  affordance kept (minus `_xy`).
- f3b door: sanctioned entry extended to `set_region_vector` (the whole-vector
  twin; same `_push`), both entries proven to route via `_push`.
- f3a outboard / f3c / f3d / f3e / feed / padmodel / unitpool / sound-identical:
  UNCHANGED and passing.

## Invariants touched

NONE of: F, world, LAMBDA, K_src, settlement, writer, render, provenance,
breathing, exam, OSC schema (no new address; H-6 closed set intact), six-lane
law (§8; strips remain the exhaustive region control), R1–R6, CS-1..CS-5.
Engine tree: zero diffs. `cloud/`: zero diffs. Root `ets/`: zero diffs.

## Disclosed walls (not patched)

1. Per-unit brightness is track-grain (engine emits no per-unit sounding
   signal) — carried ui-v5 wall, stated in field.py + unit tooltip + prereg.
2. Drill depth ends at units (no sub-unit telemetry): units atomic by
   construction; "bands/finer" would be fabrication, refused (FIELD-E).
3. ui-v5's stale hover-inert static assertion on main: disclosed in
   OPEN_ENDS #10, NOT patched (immutable history), mooted in ui-v6.
4. Offline monitor app (`app.py`): tracks carry no profiles offline -> track
   squares render atomic there; full depth is the connected instrument.
5. Thin-UI still blocked by shared namespace (OPEN_ENDS #5): full fork again.

## Coverage honesty

- tests/field: 29 tests, all passing, including the two BITE fixtures
  (echo-widget fails the static check; tokenless write raises).
- Adapted pi/v5/instrument suites: 52 passing.
- Full ui-v6 tree run: see final commit message for the complete count.
- NOT verified in this sandbox: real-hardware feel (scroll gesture rates,
  pinch-zoom ergonomics on macOS trackpads) — sandbox is ~100x slower and
  headless; needs the operator's live test. The NativeGesture pinch branch is
  exercised only synthetically.
- The engine-backed FIELD-A/B tests run on the synthetic fixture world (M=2,
  region σ_φ ≈ 0.5–0.64, verified armed and verified responsive to tilt at the
  row level). M=2 is the smallest honest co-movement world; the psytech world
  is too heavy for sandbox test cadence (disclosed, not sampled down secretly).

## What the auditor should scrutinize

1. FIELD-INV: is the capability guard + AST check genuinely closed? (e.g., can
   any FieldView path reach `_ingest` indirectly? `decay` is writer-free but
   model-mutating — it is called only from the app tick, never from handlers;
   verify.)
2. FIELD-D: `field.py` imports `ets.panel.envelope` (SAFE_REGION_MAGNITUDE) and
   `ets.instrument.model.track_palette` — confirm neither reaches the trained
   object transitively.
3. The deleted tests: confirm each deleted invariant is genuinely re-covered by
   a field test (mapping above), not silently dropped.
4. `roles_of_track` shows the top-round(PR) roles of a track's profile —
   confirm this is balanced-truncation-faithful and not a hidden re-ranking
   authority (it is display selection only; bias directions use the FULL
   profile, never the truncated set).
5. The unit-square brightness wall (track-grain) — confirm the tooltip + docs
   state it and no code fakes per-unit weight.
