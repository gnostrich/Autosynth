# architecture-v2 — display-layer panel relabel (over v1)

**Architecture version v2.** A full-copy fork of the v1 machine (per the operator's
isolation choice) whose sole functional change is a **display-layer panel relabel**
(face labels + hover tooltips; no engine/OSC/registry/F symbol touched). The prior
version (v1, repo root) is the immutable rollback point, tagged
`pre-panel-relabel-2026-07-16`.

## Clean canonical layout (the go-forward structure)

v2 is the FIRST version built on the clean two-level layout agreed for all forks
after the founding one — it does **not** replicate v1's grandfathered root-embedding:

```
architecture-v2/
  ets/  scripts/  tests/  + governance md      the machine (code, F, invariants),
                                                 with psytech as the embedded
                                                 CANONICAL DEFAULT corpus
  instances/
    README.md          v2 introduces no new instance (see below)
```

- **The machine** is here in full, shipping with **psytech as the canonical default
  corpus** (embedded world + LAMBDA + σ_φ) — the batteries-included corpus a user
  swaps out for their own.
- **v2 introduces no new instance.** A display relabel changes no audio, weight,
  world, or gate, so nothing is retrained. An instance belongs to the version where
  it was first created and is **not duplicated into later versions**: `futuregarage`
  (the worked example of a user swapping in their own corpus) lives once, under v1.
  Only a new corpus trained *on the v2 machine* would land in `instances/`.

## Contrast with v1 (why the asymmetry is one-time)

v1 is embedded at the repo root (the founding architecture + its first instance grew
up together there) and is grandfathered in place because relocating it would mutate
its H-8 determinism hash. Every version FROM v2 ONWARD uses the layout above. See
root `VERSIONS.md` and `LEDGER.md`.

## What changed vs v1 (exhaustively)

Panel face labels + tooltips only (one alias map in `ets/panel/widget.py`). Internal
names (region, density, continuity, gauge, novelty, temperature/T_s, slide, loop,
leash, comma, sigma_phi) are unchanged everywhere non-visual; the six-lane
exhaustiveness law and the OSC/MIDI schema are untouched. See `LEDGER.md` for the
per-edit trail and audit status.

---

## v4 — Feature 3: the instrument half (pad grid + tape view + transport + cue)

Per `PREREG-feature3.md`. A READ / TAP / MONITOR layer OUTSIDE the trained object.
ZERO diffs to F, LAMBDA, world, exam, settlement, writer, render, and
provenance-generation. Additions:

- New package `ets/instrument/` (SEPARATE from `ets/panel` because C-3 forbids the
  panel from importing render/engine; the display reads provenance-shaped data):
  - `model.py` — pure display models (SoundingCell, PadModel, TapeModel,
    MonitorState); reads provenance/occupancy by COLUMN NAME, imports NOTHING from
    the trained object.
  - `pads.py` `tape.py` `app.py` — native-Qt widgets (I-13): TrackPadGrid (F3.1,
    per source track, lit from provenance), TapeView (F3.3), RegionTapPads (F3.2
    tap surface), InstrumentWindow.
  - `tap.py` — RegionTapEnvelope/RegionTapController: pad tap/hold as a
    transient/held spike on the EXISTING region-tilt lane; drives the panel's new
    public `tap_region_anchor` (the same `_push`/emitter — no new OSC channel).
  - `transport.py` — pure playhead (F3.4); no writer handle.
  - `cue.py` — CueMonitor (F3.5) frontier monitor + provenance-highlight audition;
    derives from a COPY of produced audio, never touches main-out.
- `ets/panel/widget.py` (display-only additions): `tap_region_anchor` (public
  region-lane entry for the tap), `apply_disarmed` + welcome-driven wiring
  (affordance honesty: disarmed lanes render visibly disabled).

Harness (all bite): `tests/instrument/` F3-A outboard (byte-identical main-out),
F3-B door (static import graph), F3-C provenance-display fidelity, F3-D transport
neutrality, F3-E cue neutrality, plus tap/affordance behaviour. 17 tests pass.

Disclosed WALLS (safe subset shipped, not patched):
1. LIVE cross-process provenance feed — a new inbound OSC address would break the
   closed message space (H-6); the tape/pad DISPLAY is fed from offline-render
   provenance / an in-process monitor. Tap/transport/cue paths are live.
2. Pad TAP keys on ANCHOR (region lane) while material pads key on SOURCE TRACK
   (provenance); no track→anchor join is fabricated from the trained geometry.
3. Pad AUDITION is a monitor-side provenance-highlight on summed frontier audio,
   not true per-source isolation (isolation would require re-render).
