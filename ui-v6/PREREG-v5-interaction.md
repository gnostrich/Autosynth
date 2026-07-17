# PREREG — architecture-v5: desktop interaction bugfixes (hover-scroll, pad pick-and-place, safe-envelope + slew)

**Architecture version:** v5 (fork of v4; base verified clean/committed/pushed/in-sync
before fork; pre-change tag `pre-hoverfix-v5-base`). UX/FE line. Engine status quo —
v1 unchanged.

**Nature:** a control/interaction-layer change to the panel + instrument surface. Like
v4 it is OUTSIDE the trained object: ZERO diffs to F, LAMBDA, world, exam, settlement,
writer, render, provenance-generation. Master safety net (inherited): deleting the v5
UI changes ⇒ main-out byte-identical on a fixed seed; runs at EVERY merge.

## Measured facts driving this (scratch measurements, engine untouched)

- Single-anchor region lean is stable across the whole range: 0.20→1.00 all healthy
  (peaks 0.29→0.89).
- The EXACT reported divergence combo (region ~0.61 multi-anchor + continuity 0.81 +
  novelty 0.91 + temperature 1.71) rendered **healthy** offline (peak 0.77), and even
  1.2× was healthy (peak 1.07). The offline-from-bar-0 path does NOT reproduce the
  blow-up. ⇒ the reported scraping is most likely a **live-path transient** (a sudden
  mid-stream OSC lane JUMP at bar ~23 applying at bar 25 with L=2 latency), or a stale
  local build — not a static in-range value. This must be stated in the report and
  verified by local live testing.

## Bugs / features

- **B1 — all controls hover-scroll, never hover-move.** No control may change value on
  passive hover. Scalar lanes already comply (`_ScrollSlider`: wheel-only, click/drag/
  move inert); AUDIT every control and fix any that don't. Add a test that passive
  hover (mouse move with no button, no wheel) over any control emits nothing.
- **B2 — XY region pad: position-based PICK-AND-PLACE.** Remove `setMouseTracking`
  hover-aim (hover must be inert). Interaction: **click to ARM** (dot begins following
  the cursor; value emits live — safe, see envelope), **move** to position (angle =
  which anchors, distance-from-center = magnitude), **click to DROP** (park the dot; it
  stays; stops following). A second click re-arms. Position IS the value (Kaoss/vector-
  synth idiom); no momentum/roll. VISUAL INDEXING (required — the point of the redesign):
  labeled anchors on the circle, a filled draggable dot, a center→dot vector line, a
  magnitude RING that equals the safe boundary (dot cannot exit it), an armed-state
  highlight, and the dominant-anchor highlight + a small numeric lean readout. Emitted
  through the ONE existing region path only (C-3), never a new write path.
- **B3 — anti-divergence, UX-layer only (no engine change, seal intact):**
  1. **Safe-envelope clamp** — cap the emittable region magnitude (the pad radius) and
     steering lanes to a measured-safe maximum (wide; a backstop). The ring = this cap.
  2. **Slew-limit emitted lane values** — a value change ramps smoothly to target over
     a short time constant instead of an instantaneous jump, so no single gesture emits
     a discontinuity. This targets the suspected live-path transient at its source and
     also improves feel. Purely on the OUTBOUND control value; reads/derives nothing
     from settlement.

## Hard lines (unchanged from the surface contract)

- The ONLY gesture→engine path remains the existing region-tilt lane (C-3). No pad/
  transport/cue/monitor/slew path may reach settlement, F, render, or provenance-
  generation. Static door check enforces it.
- If any change alters how F scores, how the writer settles, or what the render emits →
  out of scope: stop and report.

## Harness (each must bite)

- **V5-A outboard** — delete/stub the v5 UI changes ⇒ main-out byte-identical, fixed
  seed. RUNS AT EVERY MERGE.
- **V5-B hover-inert** — passive hover (no button, no wheel) over any control (sliders,
  region strips, XY pad) emits NOTHING; assert the pad only emits between arm and drop.
- **V5-C pad pick-and-place** — arm→move→drop emits the expected position-based vector;
  a second click re-arms; parked dot does not follow the cursor.
- **V5-D clamp** — no emitted region vector exceeds the safe-envelope magnitude, for any
  reachable dot position (the ring is a real wall).
- **V5-E slew** — a target change emits a monotone ramp (bounded per-step delta), not a
  step; and the slew path touches only the outbound value (no settlement/F/render read).
- **V5-F door** (inherited) — static check: no new path into the trained object; the one
  region-tilt emit is the only engine-bound gesture.

## Build order & discipline

B2 pad model (arm/move/drop + hover-inert) → visual indexing → B1 audit/enforce across
controls → B3 clamp + slew → harness. Prereg before build; auditor PASS before merge;
one-sentence disclosure of any contemplated divergence; walls surfaced not patched;
coverage honesty every report. Note for the report: the offline path is stable at the
reported values, so V5 fixes the *interaction* (accidental slam) and *smooths* emits;
the live-path divergence must be confirmed gone by local testing.
