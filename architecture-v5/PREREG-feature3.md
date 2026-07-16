# PREREG — architecture-v4, Feature 3: the instrument half (pad grid + tape view + cue)

**Architecture version:** v4 (fork of v2; base verified clean/committed/pushed/in-sync
before fork; pre-change tag `pre-feature3-v4-base`). v3 is SEALED (failed engine
experiment, `_sealed/`) — the number is burned, so this UX/FE architecture is v4.

**Nature:** ENTIRELY a **read / tap / monitor layer OUTSIDE the trained object.** It
lets the player SEE what the machine chose, DRIVE it via existing knobs, and PREVIEW
privately. It does NOT pin/force material to a cell and opens NO new write path into
settlement.

## Scope guard (hard invariants)

- **Zero diffs** to F, LAMBDA, world, exam, settlement, writer, render, and
  provenance-generation. Every view READS existing engine state.
- **Master safety net (F3-A):** deleting this entire feature ⇒ main-out audio
  **byte-identical** on a fixed seed. This runs **at EVERY merge in this feature**,
  not only at completion — the outboard claim is re-proven per commit.
- The ONLY sanctioned path from a pad gesture to the engine is a **transient/held
  spike on the EXISTING region-tilt lane** (the one C-3 tilt jack). No pad,
  transport, cue, audition, solo, or mute may open a second path into settlement, F,
  the render, or provenance-generation.
- If any change alters how F scores, how the writer settles, or what the render
  emits → **out of scope: stop and report** (wall, do not patch).

## Features

- **F3.1 pad grid** — material as MPC-style pads (one per role/region, colored by
  source track like the tape diagram); pads LIGHT UP in real time from the
  provenance the engine already emits. Pure display.
- **F3.3 tape / now-playing view** — scrolling output tape (committed left, L-bar
  frontier right, playhead marked), cells colored by source track from their
  existing provenance tag; "now playing" strip driven by provenance, not recomputed.
- **F3.2 pad tap/hold** — TAP = transient spike on the region-tilt lane biasing the
  current moment toward that pad's material (machine still settles — a LIVING loop,
  not a photocopy); HOLD = sustained region-tilt bias; release eases over the lane's
  normal constraint-lag. No new write path. Breathing (temperature/novelty) and drift
  (slide/loop limits) are untouched and not conflated.
- **F3.4 transport** — play/stop/position; offline render-to-file retained. Transport
  moves the playhead/clock (WHEN you listen), never WHAT the writer settles; pausing
  freezes the clock only.
- **F3.5 cue / PFL** — second audio output (MAIN + CUE headphones). Cue monitors the
  settled-but-unplayed L-bar frontier. Optional pad AUDITION routes a pad's
  contribution to the cue bus **without biasing settlement**; if that can't be done
  cleanly, ship cue as frontier-monitor only and **report** (do not fake it). Cue is
  monitor-only: no cue/audition/solo/mute reaches settlement, F, or provenance.

## Affordance-honesty (fold in)

- Disarmed lanes (density, gauge while σ_φ=0) render visibly disabled, not live sliders.
- Surface the Stage-0 slide/loop shadow values on the meter jacks (currently "—") —
  display wire only; they already exist in the registry.

## Harness additions (each must bite)

- **F3-A outboard** — delete Feature 3 ⇒ main-out byte-identical, fixed seed. RUNS AT
  EVERY MERGE.
- **F3-B door** — static check: no pad/transport/cue/monitor path reaches settlement,
  F, render, or provenance-generation, except pad tap/hold via the existing
  region-tilt lane (C-3-consistent).
- **F3-C provenance-display fidelity** — pad light-up + now-playing match the actual
  provenance of sounding cells (spot-check fixture).
- **F3-D transport neutrality** — pause/seek does not change what the writer settles
  for a given (world, LAMBDA, knob trajectory, seed).
- **F3-E cue neutrality** — with cue active and pads auditioned in cue mode, main-out
  is byte-identical to cue-off on a fixed seed.

## Build order & discipline

F3.1 (pad grid) → F3.3 (tape view) → F3.2 (pad tap/hold via existing tilt) → F3.4
(transport) → F3.5 (cue). Affordance fixes may land with panel polish. Prereg before
build; **auditor PASS before every merge**; one-sentence disclosure of any
contemplated divergence; walls surfaced not patched; coverage honesty every report.
The persistent versioning agent updates `LEDGER.md` at every edit (both axes),
append-only, documents only.
