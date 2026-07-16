# ARCHIVED — architecture-v3 (failed sound, post sampler fix)

**Status: ARCHIVED / not active. Do not render deliverables from this tree.**

architecture-v3 was an attempt to fix a *streaming/steering-time* divergence +
silence blocker by changing the temperature sampler. The engine fixes worked, but
the **sampler changes failed the ear test** and are archived:

- **Moment-match draw** (per-role independent inverse-CDF): best marginal accuracy
  (std_bias 0.4525) but **destroys inter-role coupling** → arrangement
  "switch-switch-switches", never commits to a texture.
- **Reflected draw** (correlated but over-dispersed, std_bias 0.5008): commits, but
  **chaotic** in busy/high-temperature sections.

Neither matched the genre-best sound. Decision (2026-07-16): **stay on v1**, which
generates the canonical psytech via the streaming engine + low-temperature steered
journeys (see `../samples/genre_set/`) and via the batch settler
(`../scripts/generate_batch.py`). v1 is byte-unchanged and active.

## What is worth keeping from here (the one real finding)

Our exam suite only measured **marginal** variance (std_bias) and had **no meter
for joint/temporal coherence** — so it graded the moment-match as "better" while the
ear heard it as worse. If v3 is ever un-archived, the resumption path is a
**variance-corrected correlated draw** (keep the eigenvector coupling, calibrate
its variance to true Gibbs) gated on BOTH std_bias AND a new **correlation-fidelity
metric**. Full write-up: `../reports/2026-07-16-decision-park-v3-sampler.md`.

Retained in-tree for that finding and for resumption only. Not merged, not shipped.
