# ETS — versioning

Two axes, kept distinct on purpose. Everything is on `main`
(branch `claude/basin-build-spec-v01-gmeiqq`); versions and instantiations are
folders + a ledger, never divergent branches.

## The two axes

1. **Architecture / implementation version** — the code: the F structure, the
   pipeline, the invariants, the engine/panel. This is what "v1", "v2", …
   denote. A change to the architecture or its implementation is a new
   **architecture version** and lands in new folders; the prior architecture
   version is never rewritten or deleted.

2. **Instantiation** — a *trained model* produced by running an architecture
   version's pipeline on a specific corpus: its frozen world, its NCE-fit
   `LAMBDA`, its `sigma_phi` calibration, and its exam receipts. Instantiations
   live in **subfolders under their architecture version**. Retraining on a
   different corpus creates a **new instantiation subfolder** — it does NOT
   create a new architecture version, and it does NOT delete or overwrite any
   sibling instantiation.

```
<architecture-version>/                 e.g. the v1 architecture
  <shared architecture code/tests>
  instantiations/
    <corpus-a>/   world + LAMBDA + sigma_phi + exam receipts   (trained model A)
    <corpus-b>/   world + LAMBDA + sigma_phi + exam receipts   (trained model B)
    ...
```

- A **corpus retrain** ⇒ new `instantiations/<corpus>/` under the SAME
  architecture version. Siblings untouched.
- An **architecture / implementation change** ⇒ new architecture-version folder.
  Prior architecture version untouched.

The current tree (`ets/`, its single embedded instantiation — the Jörmungandr
world/`LAMBDA`/calibration — and `tests/`, `scripts/`, etc.) is the **v1
architecture with its first instantiation**. Future instantiations do not edit
`ets/functional/f.py`'s `LAMBDA`, the v1 world, or the v1 calibration in place;
they are selected from their own instantiation folder (a versioned weights
artifact), so running one instantiation never changes another.

## Discipline

- A stable architecture version and every instantiation are **immutable** once
  recorded; new work adds folders, never rewrites.
- A retrain **re-earns** everything on its corpus: ingest → freeze world →
  refit `LAMBDA` by the NCE separation exam on that corpus's own scramble family
  (with the pre-registered KILL condition — an honest exam that can fail) →
  calibrate → gates. Nothing is assumed to transfer between instantiations.
- Model weights are **versioned artifacts, not a shared global.**
- Registry / prereg entries are append-only and namespaced to their
  architecture-version + instantiation.
- Exploratory work (rendering, probes) runs in scratch / out-of-repo paths and
  touches no tracked file.

## The ledger

`VERSION_LEDGER.jsonl` is an append-only, auto-maintained record of every edit
to a tracked file (a PostToolUse hook appends one entry per Write/Edit:
timestamp, tool, path, git HEAD). It is the running provenance of how each
architecture version and instantiation came to be — the fine-grained companion
to the coarse table below.

## Recorded versions

| Architecture version | Marker (commit) | Local tag | State |
|---|---|---|---|
| **v0-validated** | `6eabf6d` | `v0-validated-revr1` | racer-C rev-r1 pass (min held-out sep 0.95); snapshot `legacy/v0-validated/` |
| **v1-stable** | `05a4468` | `v1-stable` | Live synth (engine+panel/OSC), rev-r1 F on unit-resolved fiber, first instantiation = Jörmungandr world/LAMBDA/calibration, drift split, mastering layer, bank cache + float16, 14/15 invariants, 232 tests green |

(Annotated git tags are created, but remote tag push is blocked by app
permissions, so this committed file is the authoritative marker.)
