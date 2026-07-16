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

An instantiation takes one of **two shapes**:

```
<architecture-version> (repo root = v1 architecture + its FOUNDING instantiation):
  ets/  scripts/  tests/                         shared architecture code
  corpus.etsworld, ets/functional/f.py:LAMBDA,   psytech trained model,
    ets/calibration/sigma_phi.json, corpus/        EMBEDDED in place (shape 1)
  instantiations/
    psytech/       README pointer -> the embedded root tree (see asymmetry note)
    futuregarage/  FULL FORK: own ets/ + world + LAMBDA + sigma_phi + receipts
                     (shape 2 — a self-contained trained model in a subfolder)
    <corpus-c>/    ...
```

- **Shape 1 (embedded-founding):** the first instantiation grew up in the root
  tree with the architecture itself. There is exactly one of these: `psytech`.
- **Shape 2 (subfolder):** every later instantiation lands in its own
  `instantiations/<corpus>/` — thin (shared code) or a full fork (own code copy),
  per the isolation chosen at the time. `futuregarage` is a full fork.

- A **corpus retrain** ⇒ new `instantiations/<corpus>/` (shape 2) under the SAME
  architecture version. Siblings untouched.
- An **architecture / implementation change** ⇒ new architecture-version folder.
  Prior architecture version untouched.

### Asymmetry note (logged, on purpose)

`psytech` is **not** physically inside `instantiations/psytech/` — it is embedded
at the repo root, with only a pointer README in the subfolder. This is deliberate:
it is the **founding** instantiation, fused with the protected v1 tree. Moving it
would re-pickle `corpus.etsworld` (**changing v1's H-8 determinism hash**), break
~9 harness/test assertions, and break `pyproject.toml`'s root `ets` discovery —
i.e. it would mutate "what worked." So psytech is **grandfathered in place**.
**Go-forward rule:** every instantiation after psytech uses shape 2 (its own
`instantiations/<corpus>/`) from the start, and any *new architecture version*
created by forking starts clean with this folder structure — the asymmetry is a
one-time artifact of the founding model, not the pattern.

The current tree (`ets/`, its single embedded instantiation — the psytech
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

## Active version

**v1 is the canonical, active engine** (root tree; psytech founding instantiation).
It is byte-unchanged and genre-best at u=0 autopilot. `architecture-v3/` is
**PARKED (TBD)** — retained in-tree for resumption, not promoted. See
`reports/2026-07-16-decision-park-v3-sampler.md` for the decision, the
correlation-vs-marginal-variance finding, and the tier-2 resumption plan.

## Recorded versions

| Architecture version | Marker (commit) | Local tag | State |
|---|---|---|---|
| **v0-validated** | `6eabf6d` | `v0-validated-revr1` | racer-C rev-r1 pass (min held-out sep 0.95); snapshot `legacy/v0-validated/` |
| **v1-stable** | `05a4468` | `v1-stable` | **ACTIVE / canonical.** Live synth (engine+panel/OSC), rev-r1 F on unit-resolved fiber, first instantiation = psytech world/LAMBDA/calibration, drift split, mastering layer, bank cache + float16, 14/15 invariants, 232 tests green |
| **architecture-v3** | (branch WIP) | — | **PARKED / TBD.** Steering-time divergence+silence fix (A+B+C) + sampler experiments. Not merged, not active. Ear-testing found the moment-match draw destroys inter-role coupling (switching); the reflected draw keeps coupling but over-disperses (chaotic). Resumption = tier-2 variance-corrected correlated draw + a correlation-fidelity gate. See decision report. |

(Annotated git tags are created, but remote tag push is blocked by app
permissions, so this committed file is the authoritative marker.)

## Instantiations

| Instantiation | Architecture | Corpus | Location | Gate |
|---|---|---|---|---|
| **psytech** | v1 | first corpus (jungle/psy/house) | repo root (embedded); pointer at `instantiations/psytech/` | separation PASS (rev-r1) |
| **futuregarage** | v1 (**full fork**) | deep/atmospheric halftime, 25 tracks | `instantiations/futuregarage/` | separation PASS, held-out min sep 0.98 |

Isolation note: the user chose **full-fork** isolation for `futuregarage` — a
self-contained copy of the v1 implementation lives under
`instantiations/futuregarage/` so v1's code is **byte-unchanged** (verified: no v1
file staged across any futuregarage commit). Each instantiation re-earns its world +
LAMBDA + σ_φ + separation exam on its own corpus; nothing transfers. `cache/`
(ingest + bank) is git-ignored and rebuilt on demand; the corpus + world file are
committed for reproducibility. See `instantiations/futuregarage/{README,MANIFEST}.json`.
