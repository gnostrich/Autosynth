# `_sealed/` — failed / retired work, kept for the record, out of the active set

Nothing in this directory is active. It is preserved (not deleted) so the findings
and provenance survive, but it must not be rendered from, imported, promoted, or
built upon. "Walls are information": these are honestly-reported dead ends.

## `architecture-v3-sampler-FAILED/`

An attempt to advance the **engine line** by changing the temperature sampler to fix
a *streaming/steering-time* divergence + silence blocker. The engine guards (halt,
positivity, recalibration) worked, but the **sampler changes failed the ear test**:

- moment-match draw (per-role independent) → best marginal accuracy but destroys
  inter-role coupling → "switch-switch-switch", never commits;
- reflected draw (correlated but over-dispersed) → commits but chaotic in busy
  sections.

Decision (2026-07-16): the engine stays at **v1** (byte-unchanged, canonical,
verified by `scripts/verify_version.py`). v3 did **not** advance the engine line.

The one keeper — a real gap it exposed — is that our exam suite measured only
marginal variance (std_bias) and had **no meter for joint/temporal coherence**. If
this is ever revived, the resumption path (variance-corrected correlated draw +
correlation-fidelity gate) is written up in
`../reports/2026-07-16-decision-park-v3-sampler.md`.
