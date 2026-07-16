# Decision — roll back to v1, park the v3 sampler track (TBD)

**Date:** 2026-07-16
**Decision (user):** Keep the **first version (root v1 / psytech) as the canonical,
active version** — it works best in the target genre. **Park the entire
architecture-v3 sampler track as TBD** (do not merge). Bring the pre-fix v1 to
HEAD as the shipping state.

## What "roll back" means here (and what it does not)

Nothing in the v1 tree was ever mutated. All of architecture-v3's work lived in
the **separate `architecture-v3/` folder** (and its own calibration/measurement
artifacts); the root v1 architecture + its psytech instantiation
(`corpus.etsworld`, `ets/functional/f.py:LAMBDA`, `ets/calibration/sigma_phi.json`)
are **byte-unchanged**. So "roll back to the first version" required no revert of
v1 — v1 **is** HEAD's active version. This report simply records that v3 is parked
and v1 stands.

- **Active / canonical:** root v1 (psytech founding instantiation; futuregarage fork).
- **Parked (TBD):** `architecture-v3/` — the divergence/silence fix (A+B+C) and the
  sampler experiments below. Retained in-tree and on-branch for resumption; **not**
  promoted, **not** the active engine.

## Why v1 wins for the target genre

The v3 track was motivated by a **desktop steering blocker**: under aggressive
steering with v1's tiny MAP-calibrated σ (region σ ≈ 0.027), u→λ blew up
(λ up to ~110) → O-block occupancy runaway (divergence) and, separately, an
additive-Gaussian draw could push occupancy negative → floored → dead 255 ms
slots (silences). Both are **steering-time** pathologies.

v1 at **u=0 autopilot** — the way the genre-best music is actually generated —
exhibits neither. The fixes bought robustness for *hard steering* at a cost to the
*sound* (documented below). For the target genre the user does not need hard
steering, so the trade is not worth it. v1 autopilot is the genre-best generator.

## The hard-won finding (preserve this — it is the whole point)

Steered ear-testing on psytech exposed a gap our exam suite never measured:

| Sampler | Marginal variance (std_bias) | Inter-role / temporal coupling | Audible result |
|---|---|---|---|
| **v1 pre-fix** (correlated, over-dispersed) | ~ (higher) | preserved | **genre-best**: commits to sustained textures |
| **v3 moment-match** (per-role independent inverse-CDF) | **0.4525** (best marginals) | **destroyed** | "switch-switch-switch" — never commits |
| **v3 reflected** (correlated, over-dispersed) | 0.5008 | preserved | commits ("instant fix") **but** chaotic in busy/high-T sections |

- `std_bias` measured **marginal-variance accuracy only**. Joint/temporal
  **coherence had no meter** and is not in the preregistered acceptance criteria —
  so the pipeline optimized marginals and stayed blind to coherence until a human
  ear caught the switching. **The ear was the first coherence measurement taken on
  this system.** This is a real gap in the exam suite, not a taste call.
- Sampling `exp(−F/T)` faithfully needs **both** correct marginals **and** correct
  correlations. The moment-match nailed marginals by throwing away coupling; the
  reflected draw kept coupling but over-disperses. Neither is the exact draw.

## Resumption plan (if/when v3 is un-parked): tier-2 sampler

Build a **variance-corrected correlated draw** — keep the eigenvector coupling
`xi = V @ (√var · z)` with `H_O = solver._d2F_dO2_slot(o)` (coherence), and
**calibrate `var`** against the reference MCMC so the post-reflection marginal std
matches true Gibbs (kills the chaos). Positivity by reflection / strictly-positive
support (no clamp/floor-fill), determinism (one z per column), keep the Fix-B
StreamHalt bound. **Two gates, measure-or-wall:** (a) `std_bias < 0.45`; (b) a new
**correlation-fidelity metric** (inter-role covariance vs reference MCMC). If (a)
can't be met without sacrificing (b), wall and report the tradeoff — never silently
trade coupling for marginal accuracy again.

External read-layer notes (unchanged, orthogonal to the engine): drop the SBR-lite
upscale; keep an optional gentle smart-EQ (presence lift, minimal bass cut) in the
mastering stage.

## Two rendering paths — DO NOT CONFLATE (critical version-control note)

v1 has **two distinct render paths**, and the genre-best "driving + spacey" sound
comes from the FIRST one:

1. **Batch settler — `scripts/generate_batch.py`, u=0 (canonical quality path).**
   Settles the WHOLE tape to a global Lyapunov F-descent certificate
   (`generate_batch`, monotone convergence, e.g. n_iter≈8, F 0.6068→0.6043), then
   renders. **Deterministic — it does NOT use the temperature sampler at all.**
   This global settlement is *why* it is maximally coherent (propulsive pulse +
   sustained atmospheric textures held together across the whole tape). This is
   the path that produced the founding-instantiation music the user calls
   genre-best. Reproduce with:
   `python3 scripts/generate_batch.py --seconds N --master --master-lufs -14 --out <path>`
   (world frozen fresh from `cache/ingest`, sigma=median; source units from corpus).

2. **Streaming engine — `Engine.render_offline` / the live writer.** Causal,
   bar-by-bar, WITH the stochastic temperature sampler (`_sample_temperature`).
   **This is the ONLY path the entire v3 divergence/silence/coherence saga was
   ever about.** The switching (independent moment-match) and chaotic-periods
   (over-dispersed reflected) findings are properties of *this* path's draw. They
   do not describe the batch path, which has no such draw.

Implication: the parked v3 work is a fix for the *streaming/steering* path. It is
orthogonal to the batch path that generates the canonical genre music. If we only
ever need great non-interactive tracks in this genre, the batch settler already
delivers and needs none of the v3 sampler work.

## Status

- Builder (moment-match / tier-2) **stopped**. No further v3 spend until un-parked.
- v1 remains the active engine and canonical genre generator; **`generate_batch.py`
  (batch settler, u=0, `--master`) is the reproduction recipe for the genre-best
  quality.**
- architecture-v3 retained in-tree as parked WIP for resumption (streaming path only).
