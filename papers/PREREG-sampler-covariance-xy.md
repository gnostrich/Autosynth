# PREREG — covariance-shape XY pad (steer the draw's second moment)

**Status:** operator-directed (2026-07-19). Backup tag `pre-sampler-xy-2026-07-19` = current
live SHA. Additive + default-off; the current F-tilt XY pad is preserved (toggle, not removed).

## Motivation / hypothesis
The current XY pad steers **F** (the settled MEAN O*) via λφ tilt; its response is measured
**rank-1 (k=1)** on the trained corpora (region1 mode dominates 10–30×; corpus diversity and
sampler swap both leave it k=1). But the writer's local fluctuation covariance is `T_s·H⁻¹`
with `H = _d2F_dO2_slot` the per-slot Hessian — **positive-definite, full rank (M directions)**.
So the SECOND moment carries independent degrees of freedom the first-moment response cannot.

**H1:** an anisotropic draw — scale the variance per Hessian-eigendirection — steered by the
XY pad gives **≥2 genuinely independent, audible steer axes** (a "how it moves" pad) where the
F-tilt pad collapsed to one. **H0:** it does not (audio doesn't change independently along X/Y,
or the change is incoherent), report and keep the F-tilt pad.

## Method (additive; default-off = byte-identical)
1. **Engine (architecture-v6/ets/writer/stream.py `_sample_temperature`):** accept an optional
   per-eigendirection anisotropy vector `a` (length M, carried on `TiltTerms`, default None →
   treated as ones). The draw becomes `xi = V @ (sqrt(var * a) * z)` where `var = T/w` as now.
   `a = ones` reproduces the EXACT current draw (meter-class: delete/omit → byte-identical audio;
   the `z` consumption and rng alignment are unchanged). Eigendirections ordered by `w` (largest
   curvature first) so the pad axes are stable/deterministic.
2. **Bridge (engine_bridge):** a setter `set_wobble(vec)` that carries the pad's anisotropy into
   `TiltTerms.a` — through the SAME single lane-vector path the other setters use (no new engine
   channel; the draw reads one datum). Reads only the frozen world/Hessian.
3. **FE (index.html):** a pad MODE toggle. `F-tilt` (current, preserved) OR `covariance` (new):
   in covariance mode the puck (x,y) maps to `a` = up-scale variance along Hessian-eigendir 1
   (x) and 2 (y), down-scale the complement, `a` clamped to a safe band (e.g. [0.25, 4]).
   The F-tilt force-vector path is untouched and re-selectable.

## Preservation / walls
- `a = ones` ⇒ byte-identical audio to `pre-sampler-xy-2026-07-19` (verify: delete-the-field
  meter test). The current pad is a toggle away, never deleted.
- This steers the draw's SPREAD/shape (character: tight↔loose, along which aspects), NOT the
  content target. Disclose it as a "how it moves" pad, not "where it goes." Honest naming.
- **Coherence guard (the v3 lesson):** anisotropic *scaling in the Hessian eigenbasis KEEPS the
  correlation structure* (still `V·(…)·z`), so it does NOT decouple roles the way v3 moment-match
  did. But cranking one axis very high approaches over-dispersion (v3 reflected → chaotic). Clamp
  `a` to a safe band and gate acceptance on BOTH: audible independent X/Y response AND a
  joint-coherence check (mean |off-diagonal role-fluctuation corr| stays in the near-greedy band,
  not inflated). No new metric enters any loss (I-5).
- Sampler/F/world/settlement math otherwise UNCHANGED — only the per-direction variance scale of
  the already-existing Laplace draw is modulated. No `ets/` (root, frozen) edit.

## Success / stop
- H1: X and Y each produce an audible change, the two changes are perceptibly different
  (independent), and coherence stays in-band → the covariance XY is a real second axis; propose
  making it the default pad (operator's call), keep F-tilt as a toggle.
- H0: report the null honestly; the F-tilt pad stays; sampler draw reverts to `a=ones` (no-op).
