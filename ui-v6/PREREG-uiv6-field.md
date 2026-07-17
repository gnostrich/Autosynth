# PREREG — ui-v6: the FIELD surface (unified push/zoom field; replaces pads + XY + drill)

Pre-registered BEFORE build, per the operator's FIELD directive (2026-07-17) and
standing law (prereg before build; auditor PASS before merge; walls surfaced).

## Version control (done first)

- **Base**: `main` @ `5ff6abd` (verified: branch at origin/main tip, clean tree,
  ui-v5 suites 98/99 green — the 1 failure is a PRE-EXISTING stale static
  assertion on main, `tests/v5/test_v5b_hover_inert.py::test_tap_surface_has_no_
  hover_move_channel`: `RegionTapPads` gained a `mouseMoveEvent` in the merged
  drill sprint that only cancels the hold-timer and emits nothing, so the
  hover-inert INVARIANT holds but the static check is stale. Disclosed, NOT
  patched: architecture-v6 is now immutable history; the widget is deleted in
  ui-v6, mooting the check there. Engine byte-verify needs the local
  `corpus.etsworld` which is gitignored by design — known fresh-clone shape, R5's
  committed demo world is the self-contained path.)
- **Fork**: `ui-v6/` is a full copy of `architecture-v6/` (thin-UI is still
  blocked by the shared `ets` namespace — OPEN_ENDS #5 — so full fork, disclosed).
  `runs_on: engine-v1`. **architecture-v6 (ui-v5) is preserved IMMUTABLE** as the
  rollback/A-B point; no file under `architecture-v6/` is edited by this build.
- **Tag**: `pre-uiv6-field-2026-07-17` at `5ff6abd` (local; remote tag push is
  app-blocked, this committed file + VERSIONS.md are the authoritative marker).

## Governing invariant (stamped; auditor-enforced)

**You push → the engine re-settles → the display shows the ENGINE'S ANSWER.**
Every interaction loops through the engine; no direct write to a pixel. A
square's fill brightness = its RE-SETTLED weight after bias, never the raw input
echoed back. Proof-of-realness required: (a) CO-MOVEMENT — biasing one square
moves related squares that were not touched; (b) DYNAMIC SENSITIVITY — the same
push yields different response depending on the current settled state.

## What is built

`ets/instrument/field.py` in ui-v6 only:

- **FieldModel** (pure python, no Qt): a tree of squares over engine-emitted
  material, with per-square settled brightness, accumulated bias, and
  self-sized expandability.
- **FieldView** (native Qt, I-13): draws the squares; pinch/Ctrl-scroll zooms
  (drill), plain hover-scroll biases. Optional bias RING on the square's edge
  (input) distinct from the fill (engine response) — implemented (nice-to-have).

### The square tree (every square backed by engine-emitted data; FIELD-E)

| Grain | Squares | Fill brightness (settled weight) | Bias path (gesture → engine) |
|---|---|---|---|
| TRACK (zoom out) | one per source track (`/ets/profiles`, `/ets/nowplaying`) | `/ets/nowplaying[track]` — the engine's settled per-track sounding activity | that track's engine-emitted anchor-mass profile (`/ets/profiles`), scaled by the bias amount → `panel.set_region_vector` (existing whole-vector region path) |
| ROLE (mid) | the M anchors (`/ets/roleactivity`); reached flat or by expanding a track into the roles its profile loads | `/ets/roleactivity[role]` — settled per-role level | `panel.tap_region_anchor(role, bias)` (existing single-anchor region path) |
| UNIT (in) | a role's drill pool (`/ets/unitpool`) | its source track's `/ets/nowplaying` activity — **disclosed wall, carried over from ui-v5**: the engine emits no per-unit sounding signal; unit fill is honest track-grain breathing rendered at the unit cell, not a fabricated per-unit weight | the unit's engine-emitted anchor profile (peak-normalised, bias-scaled) → `panel.set_region_vector` (the existing fine-steer semantics) |
| deeper | **NONE** — units are ATOMIC: the engine emits no sub-unit telemetry, so no square below unit exists. Faking "bands/finer slices" squares would violate FIELD-E; depth honestly ends at units and unit squares render non-expandable. | — | — |

No track→anchor join is fabricated: track-grain bias uses the engine's own
`/ets/profiles` statement of how a track loads the anchors; role squares under a
track are the roles whose profile mass clears the floor (shared roles may appear
under several tracks — true by construction, all cross-track traffic factors
through anchors).

### Self-sizing depth (FIELD-C)

A square expands only while its sub-structure clears the noise floor, by the
SAME criterion that set M: the participation-ratio effective count
`(Σw)² / Σw²` (balanced-truncation effective mode count,
`ets/functional/anchors.py::effective_rank`), applied to the square's
sub-element weight vector; expandable iff `round(PR) ≥ 2`. The FORMULA is
reused, the code is NOT imported (the instrument may not import
`ets.functional` — F3-B door); it is re-stated locally as pure arithmetic on
telemetry vectors and pinned to the anchors.py formula by a test. Atomic squares
render with NO expansion affordance. Depth varies per square; that variation is
honest information.

### One gesture: hover-scroll bias (soft steer)

- Scroll up/down on a hovered square accumulates a bias in [-1, +1] × the
  panel's `SAFE_REGION_MAGNITUDE` envelope. It enters the engine ONLY through
  the panel's existing region-tilt lane (`tap_region_anchor` /
  `set_region_vector` → clamp → slew → `/ets/lanes`). The machine re-settles; it
  is never forced.
- **SOFT saturation (FIELD-B)**: down-bias saturates at "strongly disfavored"
  (the −envelope cap) and can never hard-mute: the region lane is an exponential
  tilt (h-transform), so settled weight stays > 0 at full down-bias. Membership
  (hard include/exclude) remains the SEPARATE crate/library system, untouched.
- Zoom is a separate gesture (pinch / Ctrl+scroll) so bias and drill never alias.

## What is REPLACED (removed in ui-v6 only; intact in architecture-v6)

- `RegionTapPads` (role pad grid) — deleted; role-grain squares replace it.
- `TrackPadGrid` (material pad grid) — deleted; track-grain squares replace it.
- `_RegionXYPad` (XY / vector pad) — deleted from the ui-v6 panel; biasing
  toward material IS the blend. `_RegionStrips` remains constructed (hidden in
  the instrument window) as the §8-exhaustive region control — the six-lane law
  and the closed OSC schema are untouched.
- `UnitLayerView` / `UnitCellGrid` (hierarchical drill-in) — deleted; zoom drill
  replaces it. The CUE toggle moves to the field's unit interaction unchanged in
  semantics (cue = private audition intent; never main-out).

## What stays UNCHANGED

Sliders (density, vary, key-lock, spread, chaos = the six-lane scalar strips
with v2 naming), global tempo/transport, cue, drift meters (read-only), library
browser incl. its display-only show/hide (the membership-adjacent surface),
and the CORE: F, world, LAMBDA, K_src, settlement, writer, render, provenance,
breathing, exam — zero diffs. Engine-side telemetry addresses: zero diffs (the
field consumes exactly the existing `/ets/roleactivity`, `/ets/rolemeta`,
`/ets/unitpool`, `/ets/nowplaying`, `/ets/profiles`, `/ets/meter/*`).

## Harness (all must bite)

- **FIELD-INV** — nothing reaches a rendered brightness without settlement:
  (1) capability check: `FieldModel`'s settled-brightness setter requires the
  telemetry-applier token; gesture handlers hold no token, so an input→brightness
  write RAISES. (2) static AST check: no input handler (`wheelEvent`, mouse
  events) in `field.py` calls a brightness setter. (3) PROOF IT BITES: a fixture
  widget that echoes wheel input to brightness must FAIL both checks.
- **FIELD-A** — co-movement: on a real settled fixture, biasing one square makes
  related, untouched squares' settled weights move (engine response), and
  (dynamic sensitivity) the same push from a different settled state yields a
  different response.
- **FIELD-B** — soft-bias: driving scroll-down to the stop saturates at the
  −envelope cap; the emitted lean never exceeds the safe envelope; the settled
  weight under full down-bias stays > 0 (never hard-mute) unless membership
  excludes it (separate system).
- **FIELD-C** — drill self-sizing: expandability follows the participation-ratio
  noise-floor criterion (pinned to `anchors.effective_rank` by value); atomic
  squares are non-expandable and render no affordance; no drill resolves into
  noise (a degenerate/flat sub-structure square with PR < 2 refuses to expand).
- **FIELD-D** — outboard: the field changes WHAT IS BIASED, never how F scores
  or the writer settles. Static door test: `field.py` imports nothing from
  `ets.render/engine/writer/functional/geometry`; gestures reach the wire only
  via the panel's existing region path (`/ets/lanes`, no new address). Delete
  test: offline render byte-identical with the field constructed vs absent.
- **FIELD-E** — no fabrication: every square maps to a real track/role/unit id
  present in telemetry; brightness values are traceable to a telemetry frame;
  no synthetic squares, no decorative glow (a telemetry frame naming ids the
  world doesn't contain must not create squares).

## Build order (as directed)

(1) this prereg + fork + tag → (2) field render read-only (FIELD-INV/E) →
(3) hover-scroll bias via the existing lane (FIELD-A/B/D) → (4) self-sizing
drill depth (FIELD-C) → (5) remove pads/XY/drill from ui-v6 + adapt the forked
suites (architecture-v6's suites untouched) → auditor pass → merge. Crate/
library UX re-pointing happens AFTER the field lands (sequencing rule).

## Anticipated walls (disclosed up front)

1. Per-unit brightness is track-grain (no per-unit sounding telemetry) — carried
   ui-v5 wall, restated above. Surfaced in the unit-square tooltip too.
2. Depth ends at units (no sub-unit telemetry) — honest atomicity, not a bug.
3. FIELD-A/B settled-weight tests run against the real settlement on a small
   fixture world (sandbox renders ~100x slower than hardware; fixtures are kept
   minutes-scale). If the fixture cannot arm region steering (degenerate
   corpus), the test must fail loudly, not silently pass.
