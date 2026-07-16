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
