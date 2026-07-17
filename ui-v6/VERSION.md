# ui-v6 — the FIELD surface (unified push/zoom field over engine-v1)

**UI version `ui-v6`** (UX/FE axis; see root `VERSION_SCHEME.md`). A full-copy
fork of `architecture-v6/` (= `ui-v5`) whose sole change is the INTERFACE:
the pad grid, the XY/vector pad, and the hierarchical drill-in are REPLACED by
ONE unified surface — a field of squares you push (bias) and zoom (drill).
`runs_on: engine-v1`. **ZERO diffs** to F, world, LAMBDA, K_src, settlement,
writer, render, provenance, breathing, exam, or any OSC address.

- **Fork base**: `main` @ `5ff6abd`, tag `pre-uiv6-field-2026-07-17`.
- **Prior version**: `architecture-v6/` (`ui-v5`) is preserved IMMUTABLE as the
  rollback / A-B point. It is not edited by this build.
- **Why a full fork, not thin**: the shared `ets` namespace still couples
  engine+UI in one package (OPEN_ENDS #5); thin-UI awaits that refactor.
- **Prereg**: `PREREG-uiv6-field.md` (governing invariant, square tree,
  FIELD-INV + FIELD-A..E harness, disclosed walls).

## Governing invariant

You push → the engine re-settles → the display shows the ENGINE'S ANSWER.
A square's fill brightness is its live settled weight from read-only telemetry,
never an echo of the input. Bias enters ONLY via the panel's existing
region-tilt lane (clamp + slew → `/ets/lanes`).

## What changed vs ui-v5 (exhaustively)

- NEW `ets/instrument/field.py` — FieldModel (pure) + FieldView (native Qt):
  track/role/unit squares, hover-scroll bias (soft-saturating, never hard-mute),
  pinch/Ctrl-scroll zoom drill self-sized by the participation-ratio noise-floor
  criterion (the same formula that set M), bias ring vs settled fill.
- REMOVED from this version only: `TrackPadGrid`, `RegionTapPads`,
  `UnitLayerView`/`UnitCellGrid` (pads + drill), `_RegionXYPad` (XY pad).
  `_RegionStrips` remains constructed (hidden in the instrument window) as the
  §8-exhaustive region control; six-lane law + closed OSC schema untouched.
- `ets/instrument/live.py` / `app.py` rewired to the field; sliders, tempo,
  transport, cue, meters, library browser unchanged in behavior.
- Forked test suites adapted to the field (FIELD-INV, FIELD-A..E added);
  architecture-v6's own suites untouched.

See root `LEDGER.md` for the per-edit trail and audit status.
