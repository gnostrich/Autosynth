# ETS version scheme (formal)

Adopted 2026-07-16. Supersedes the old single `architecture-vN` counter, which
conflated three independent things and produced burned/gappy numbers.

## Three independent axes

| Axis | What it versions | Counter | Bumps when |
|---|---|---|---|
| **engine** | the machine that makes sound: F, settlement, writer, render, provenance | `engine-vN` | the SOUND/behavior of the machine changes |
| **ui** | the interface on top of an engine: panel, instrument surface, interaction | `ui-vN` | the interface changes (never the engine) |
| **instance** | a trained model on an engine: world + LAMBDA + σ_φ + exam receipts | named by corpus | a new corpus is trained through an engine |

Each axis has its **own** counter. `engine` and `ui` never share numbers. A `ui`
version always runs on a specific `engine` and declares it.

## What "the build you're holding" is: a RELEASE TUPLE

A release is a pinned triple, recorded in `release-manifest.json`:

```
engine-vX · ui-vY · instance-Z
```

e.g. **`engine-v1 · ui-v3 · psytech`** — engine v1, the instrument-surface UI, the
psytech trained model. That string is the whole answer to "what am I running."

## Conventions

- **Sealing a failure:** a version that was built but rejected keeps its number with a
  `-x` suffix and moves to `_sealed/`. It does NOT advance its axis. (The failed
  sampler experiment = `engine-v2-x`, sealed — the engine line stays at `engine-v1`.)
- **Immutability:** once a version is recorded, its folder is immutable (content is
  never rewritten). New work forks to the next number.
- **Go-forward naming:** new version folders are born with their axis name
  (`engine-vN/`, `ui-vN/`). Historical folders keep their old physical names and are
  mapped below (renaming immutable history would break internal path assertions for no
  benefit — the manifest + this map are the source of truth for identity).
- **Thin UI (adopted 2026-07-16):** an `engine` version is full and self-contained
  (rare — only when the sound changes). A `ui` version, from `ui-v5` onward, is a
  **THIN layer**: only UI code + a declared `runs_on: engine-vN`, **no engine copy**.
  This is safe because the outboard byte-identical test *proves* the UI cannot touch
  the engine — isolation comes from the invariant, not from duplicating the engine.
  So there is **no folder per tuple/combination**: a release like
  `engine-v1 · ui-v4 · futuregarage` is just a manifest pin, not a folder. Existing
  full-fork UI folders (`ui-v1..v4`) are kept as immutable history — not retro-slimmed.
- **Verification:** the active engine is byte-verified by `scripts/verify_version.py`
  against `verification/canonical_manifest.json`.

## Mapping — historical folder ⇄ version ID

| Version ID | Physical location | Status |
|---|---|---|
| `engine-v1` | repo root (`ets/`, `corpus.etsworld`, `ets/calibration/`) | **ACTIVE**, verified |
| `engine-v2-x` | `_sealed/architecture-v3-sampler-FAILED/` | SEALED (failed sampler) |
| `ui-v1` | engine-v1 root tree (founding panel: `ets/panel/`) | embedded/founding |
| `ui-v2` | `architecture-v2/` | knob renaming (display-only) |
| `ui-v3` | `architecture-v4/` | instrument surface (pads/tape/cue) |
| `ui-v4` | `architecture-v5/` | interaction fixes (hover/pad/slew) — superseded by ui-v5 |
| `ui-v5` | `architecture-v6/` | connected playable instrument (role pads + XY + tape + transport), drill-in (unit fine-steer), read-only telemetry light-up, live loudness/eardrum-safety cap, library browser — **ACTIVE** (auditor PASS + operator-approved door-test typing refinement, 2026-07-16) |
| `instance:psytech` | repo root (embedded founding) + pointer `instantiations/psytech/` | **ACTIVE** |
| `instance:futuregarage` | `instantiations/futuregarage/` (full fork) | trained, on `engine-v1` |

(Note the old `architecture-v3` number is the sealed `engine-v2-x`; there is no
`architecture-v3` in the active tree. The UI line is now clean: `ui-v1..v5`.)

## Deployment axis (added 2026-07-16)

Cloud/topology work is a fourth, orthogonal axis: it changes *where compute runs*,
not the sound (engine) or the surface (ui). It is named `cloud-mvpN` and pinned in
`release-manifest.json` under `deployment`.

| Deployment ID | Physical location | Status |
|---|---|---|
| `cloud-mvp1` | `cloud/` | **MERGED** (auditor PASS-WITH-NOTES 2026-07-16). Hosted anchor-fit training service (offloads the GW-barycenter geometry). Only stage-3 gauge-invariant cost matrices + masses cross device→cloud (CS-1..CS-5 verified biting); raw audio + recipes never uploaded; no cloud decoder; world returns with device-verifiable receipts. WALL: NCE LAMBDA fit + scramble exam stay device-local (they consume stage-2 recipe data). Deploy-ready (`cloud/service/Dockerfile`); verified locally as the cloud stand-in. |
