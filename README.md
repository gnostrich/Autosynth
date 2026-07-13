# ETS — Equilibrium Tape Synth

Single authority for this repo: **`ets-spec-v0.md`** (root). If code and spec
disagree, the code is wrong or the spec is formally revised (new version,
logged). No third source of truth.

Build is executed by the `ets-builder` agent, audited by `ets-auditor`
(`.claude/agents/`). No gate run or merge without an auditor PASS.

## Layout
- `ets-spec-v0.md` — the spec (§0–§16), the only authority.
- `ets/` — engine package; module docstrings map to spec sections.
- `tests/invariants/` — executable manifest of I-1..I-14 (spec §14). Runs in CI.
- `PREREG.md` / `REGISTRY.jsonl` — pre-registration ledger for gates G0–G6.

## Status
Build order step **(a)**: repo skeleton, invariant test harness, REGISTRY/PREREG
scaffolding. No engine features implemented yet; all invariants PENDING (their
guarded features are unbuilt) and reported as such by the harness.

## Lineage
Music-domain instantiation of the EBR program. `ebr-spec-v1.md` (the parent
spec) is referenced by lineage but is NOT in this repo; its principles apply
only where `ets-spec-v0.md` does not override, and `ets-spec-v0.md` remains the
sole authority here.
