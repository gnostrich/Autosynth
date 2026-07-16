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

## Retrain = a new version (the load-bearing case)

Training the model on a **different corpus** is not a re-render — it is a new
trained version, and it lands in a new folder (e.g. `v2/`) with v1 frozen:

- **v1 is never overwritten.** In particular `ets/functional/f.py`'s `LAMBDA`,
  the v1 `corpus.etsworld`, the v1 `ets/calibration/sigma_phi.json`, and the v1
  exam results in `REGISTRY.jsonl`/`PREREG.md` stay exactly as they are.
- **A retrain reruns the full discipline on the new corpus:** ingest → freeze a
  new world → **refit `LAMBDA` by the NCE separation exam on the new corpus's own
  scramble family (with the pre-registered KILL condition — an honest exam that
  can fail)** → calibrate `sigma_phi` for the new world → gates. None of this is
  assumed to transfer from v1; it is re-earned.
- **Model weights are versioned artifacts, not a shared global.** v2's refit
  `LAMBDA`, world, and calibration live under `v2/` (its own `f.py`/weights or a
  version-selected weights artifact), so running v2 never changes what v1 does.
- The registry/prereg for a retrain are appended (append-only) and clearly
  namespaced to the new version, so v1's exam receipts remain unambiguous.

When an upgrade prompt requests a retrain, it is built this way by default,
whether or not the prompt restates the hygiene.
