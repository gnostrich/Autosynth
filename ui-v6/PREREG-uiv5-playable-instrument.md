# PREREG — ui-v5: the CONNECTED, PLAYABLE instrument (assemble F3 into a real thing)

**Version:** ui-v5 (folder `architecture-v6/`). Supersedes the paused pad-feel scope.
The F3 widgets exist but are a box of tested parts — this assembles them into a
live, connected, playable instrument, and lights up the SAMPLE-BUTTON GRID (the thing
the operator actually asked for — NOT the XY joystick).

## Goal (operator's actual ask)

A grid of sample buttons (one per crate sound / source track, colored by track) that
**lights up as its material plays**, that you can **tap/hold to steer** toward that
material, in **one connected window** driven by the running engine — plus the
now-playing tape view and transport wired live.

## Scope — two layers

### A. UI assembly (pure UI, ZERO engine touch)
- One instrument window that CONNECTS to the engine (real emitter + meter/telemetry
  receiver), not the disconnected smoke app.
- Wire the existing widgets live: `TrackPadGrid` (lit sample buttons), `TapeView`
  (now-playing), `Transport`. Make them share the connected panel.
- Tap/hold to steer: routed via the EXISTING region-tilt path (`RegionTapPads` →
  region sink → panel emitter). HONEST NOTE: tapping a *source-track* button cannot
  steer a *region* (no track→anchor join). So the tappable steer surface stays the
  per-anchor region pads; the source-track grid is the DISPLAY (lights + colour).
  Present both clearly in the one window; do not fabricate a track→anchor join.

### B. The one required engine addition — READ-ONLY "now-playing" telemetry
- The pads can only light up if the engine reports what's currently sounding. Add a
  **read-only OSC telemetry address** (e.g. `/ets/nowplaying`) that the engine emits
  alongside its EXISTING meters — the SAME category as `/ets/meter/*`: pure "here is
  what I am doing" reporting. It carries per-source-track (and, if available, per-
  region) activity for the current frontier/playhead, derived from the provenance the
  engine already generates.
- HARD CONSTRAINT: telemetry is OUTBOUND, READ-ONLY. It reads existing provenance and
  emits; it MUST NOT change settlement, F, the writer, the render, or provenance-
  GENERATION. The audio/arrangement must be **byte-identical** with the telemetry on
  vs off (prove it: same seed, same audio sha256).
- This revises the closed OSC message space (H-6) by ADDING one monitor address. That
  is the pre-registered, justified change; document it in the manifest/ledger. It is an
  `engine-v1 → engine-v1.1` telemetry revision — the SOUND is unchanged (provable), only
  a monitor output is added. Re-bless `verification/canonical_manifest.json` afterward
  with a note that only telemetry output changed.

## Hard lines

- Gesture→engine stays the region-tilt lane only. No new WRITE path into settlement.
- Telemetry is read-only monitor output; no cue/transport/display path writes to the
  engine except the region-tilt tap.
- If lighting up cleanly needs anything that would change the SOUND, stop and report.

## Harness (each bites)

- **PI-A sound-identical** — main-out audio byte-identical with the telemetry + whole
  instrument present vs stubbed, fixed seed (the arrangement is untouched). Run at merge.
- **PI-B telemetry read-only** — the nowplaying emitter reads provenance and sends; a
  test proves it never calls into settlement/writer/render/provenance-generation.
- **PI-C light-up fidelity** — given a known provenance frame, the lit pads + tape
  now-playing match the actually-sounding tracks (mutation flips it).
- **PI-D door** — no new engine-bound gesture beyond region-tilt; telemetry is
  outbound-only.
- **PI-E connected smoke** — the window builds, connects (emitter + receiver), and a
  simulated nowplaying frame drives the grid — headless.

## Build order

B first (the telemetry the light-up needs) → A wiring (connected window: lit grid +
tap-steer + tape + transport). Prereg before build; auditor PASS before merge; walls
surfaced not patched; prove the sound is byte-identical. This is the first PLAYABLE cut;
expect a live-test loop. Cue-to-hardware (F3.5 real second output) is a follow-on.
