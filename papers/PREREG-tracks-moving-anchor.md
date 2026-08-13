# PREREG — TRACKS MOVING ANCHOR (capture file, formal text PENDING)

**Status: NOT YET BUILDABLE AS A REGISTERED DIRECTIVE.** This file exists so the
operator's spoken rulings are not lost while the formal amendment text is
outstanding. Nothing is built from this file until the operator's own text
lands and is recorded verbatim, per the standing prereg-before-code rule.

## What is MISSING

The moving-anchor amendment **itself**. The session has the operator's *edit* to
it (referencing clauses M-1 / M-2 / M-3, "M-4 deleted", and MA-1) but not the
amendment those clause numbers belong to. Clause numbers and checks will **not**
be invented — they get recorded from the operator's text.

## What the operator HAS ruled (their words, captured)

1. **Tap plants a travelling anchor.** "when i click it moves along with the
   track so bias is moving" — the anchor is planted at the tapped spot and then
   ADVANCES WITH THE TRACK, so the lean follows the passage rather than sitting
   at a fixed point.
2. **Tap elsewhere replants it.** "when i click elsewhere it starts there and
   moves" — last tap wins; the anchor moves to the new spot and travels from
   there.
3. **Tap the anchor again removes it.** (2026-08-13) Clicking the anchor itself
   clears it — the third state of the same one gesture, so plant / replant /
   clear are all a tap.
4. **No hold-scrub.** The gesture is a tap, not a press-and-hold. This
   SUPERSEDES the currently-live Amendment 2 behavior (hold to steer, release to
   drop) for TRACKS.

## What today's LIVE code already settles (reusable, not re-litigated)

- The anchor's position must advance from **placement telemetry**, never a
  timer — the same law LIVE's playhead follows (LM-3). A frozen engine freezes
  the anchor.
- Emission stays **columns-only** (`["col", r]`, σ-clamped), the Amendment 2
  law: no rows, no cells, no unit ids on the tilt path.
- Release follows the **existing** decay/slew law. No new constant.

## Open questions for the operator's text to settle

- Does the travelling anchor's lean re-read the stored character at its CURRENT
  position each bar (the lean changes as it travels), or does it latch the
  character of the spot where it was planted and merely move visually? The
  phrase "so bias is moving" reads as the former; it is not assumed here.
- Does the anchor survive a view switch, or does V-1 clear it like every other
  lean? (V-1 as written clears it; worth confirming, since a travelling anchor
  is closer to a transport state than to a lean.)
- One anchor at a time, or one per lane?
