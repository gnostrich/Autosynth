# PREREG — channel-bias squares interface (clamp-imposed per-channel bias)

**Status:** operator-directed (2026-07-19). Backup tag `pre-sampler-xy-2026-07-19`. Additive,
default-off; the XY pad is preserved as a selectable mode (new squares surface is a *version*,
not a replacement). Commit-before-build.

## Model / hypothesis
Units are beat-normalised at ingest (one shared tatum grid), so the Gibbs forward pass is a
distribution over the pooled channels at each beat. **Imposing a per-channel bias via the
sanctioned clamp channel (I-7) forces the settlement to work AROUND it** — the free slots
re-settle to accommodate the constraint. Unlike F-tilt (rank-1) or covariance-shape (isotropic),
this is a HARD input-level injection of actual channel material, so it does not pass through the
degenerate response bottleneck.

**H1:** amplifying channel T measurably pulls the realized output toward track-T material (a
monotone increase in the track-T unit fraction, provenance-checked, as amplify rises), and the
channels are distinct enough that different squares give perceptibly different results.
**H0:** channels are mushy (biasing one barely shifts the output / tracks overlap) → report the
null; keep the XY pad.

## Method (additive; default-off = byte-identical)
1. **Bias mechanism (clamp / I-7):** per channel (a track, or a group of tracks), an amplify∈[0,1]
   level. Amplify T ⇒ clamp a fraction (∝ amplify) of the bar's slots to track-T material at the
   MATCHING beat-phase: for slot at phase p, select a track-T unit whose metrical phase = p
   (sampled by mass), clamp that slot's role-value. Damp ⇒ exclude/down-weight that track from
   free-slot realization. No new engine channel — this rides the existing `ClampSet`/`write_bar`
   clamp path. No sampler edit, no 7th lane. All-zero bias ⇒ no clamps ⇒ byte-identical.
2. **Bridge:** `set_channel_bias(vec)` (length = #channels), assembled into the per-bar
   `ClampSet` the writer already consumes. Absent ⇒ empty clamps ⇒ byte-identical.
3. **FE:** reuse the field-of-squares render (FIELD work) — each square = a channel, hover-scroll
   = amplify/damp (the existing within-square bias gesture), rectangular for laptop, same on
   mobile; drill-in retained. A pad MODE selector: `xy` (current, default) | `squares` (new).
   XY path untouched and re-selectable.

## Preservation / walls
- Empty bias ⇒ no clamps ⇒ audio byte-identical to `pre-sampler-xy-2026-07-19` (meter test).
- Clamping is a HARD override on clamped slots (they don't settle) — heavy amplify = borrowing,
  not generating. Disclose the bias-strength ↔ generative-freedom tradeoff honestly in the UI.
- **Separability is the make-or-break and is measured, not assumed** (H1 gate). If tracks overlap
  in role-space (mushy), the honest state is disarm — squares that can't pull are shown inert,
  the way region-steering disarms on a degenerate corpus (CLAUDE.md §3). No fake-pull square ships.
- Sampler / F / world / settlement math UNCHANGED — only which slots are clamped, via the
  sanctioned I-7 channel. No root `ets/` edit.

## Success / stop
- H1 (amplify T ⇒ monotone rise in track-T output fraction, distinct across channels, coherent):
  the squares surface is a real control → wire it live as a selectable mode beside the XY pad.
- H0 (mushy / no pull): report the null with the measured pull curve; squares disarm; XY stays.
