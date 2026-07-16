# ETS — version hygiene

This file is the durable, on-`main` record of stable versions and the rule for
upgrades. (Annotated git tags are created too, but remote tag push is blocked by
the app's permissions, so this committed file is the authoritative marker.)

## Rule

1. **A stable version is protected.** Its code and artifacts are not rewritten.
2. **Every subsequent upgrade lands in NEW folders** (e.g. `v2/…`), leaving the
   stable version's files untouched. An upgrade never edits a protected version
   in place.
3. **Everything is on `main`** (branch `claude/basin-build-spec-v01-gmeiqq`).
   Versions are distinguished by folders + tags, not by divergent branches.
4. Exploratory work (e.g. rendering a different corpus) happens entirely in
   scratch / out-of-repo paths and touches no tracked file.

## Versions

| Version | Marker (commit) | Local tag | State |
|---|---|---|---|
| **v0-validated** | `6eabf6d` | `v0-validated-revr1` | racer-C rev-r1 pass (min held-out sep 0.95); snapshot in `legacy/v0-validated/` |
| **v1-stable** | `05a4468` | `v1-stable` | Live synth (engine+panel/OSC), rev-r1 F on unit-resolved fiber (NCE LAMBDA), drift split (slide/loop), conflated jack deleted, external mastering layer, bank cache + float16, 14/15 invariants enforced, 232 tests green |

## What "v1-stable" contains (the protected baseline)

- `ets/` — the runtime (functional/F, writer, render, engine, panel, meters,
  calibration, ingestion, geometry, training, connector).
- `tests/` — the invariant manifest (14/15 enforced) + gate/feature tests.
- `scripts/` — ingest, world-build, calibration, gates, batch tooling.
- `litepaper/`, `LAUNCH.md`, `REGISTRY.jsonl`, `PREREG.md`, `legacy/`.

Upgrades beyond v1 do NOT modify the above in place; they add new folders and,
where an upgrade supersedes a v1 component, leave the v1 component intact and
select the new one explicitly.
