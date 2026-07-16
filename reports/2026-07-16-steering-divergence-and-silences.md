# Runtime diagnosis — live-steering divergence & render silences (v1 engine)

**Status: REPORTED, NOT PATCHED.** Two runtime bugs surfaced from desktop use
(live steering + the futuregarage renders). Both are diagnosed, reproduced, and
have proposed real fixes. No fix is implemented yet — this document is the wall,
recorded for a deliberate fix decision. Any fix lands in a new **architecture-v3**;
v1/v2 stay immutable.

Both bugs trace to **one fragile component**: the temperature "looseness" draw
`ets/writer/stream.py::_sample_temperature` — an additive-Gaussian-in-O Laplace
draw around the settled mode, `O = O* + noise`, clamped at a `1e-12` floor. It is
fragile at *both* extremes: it can blow up (Bug 1) and it can collapse a slot to
silence (Bug 2).

---

## Bug 1 — live-steering divergence ("horrible sounds")

**Symptom (desktop):** under normal in-range knob input, per-bar settlement stops
converging and φ_density overflows to ~4.1×10¹⁶; ~30 s of garbage audio; process
ends with no traceback (the divergence is stably pinned, not self-crashing).

**Root cause.** `λ = u/σ`, and `σ_region` is calibrated pathologically small
because it is measured on the near-deterministic u=0 **MAP** writer, whose
O-marginals barely fluctuate:

| lane | σ (MAP calibration) |
|---|---|
| region (per anchor) | **[0.063, 0.027, 0.072, 0.080, 0.096]** |
| density | 0.0 (disarmed) |
| continuity | 0.301 |
| gauge | 0.0 (disarmed) |
| novelty | 0.330 |

A hard **per-anchor** XY-pad lean (in-range: u up to 3) on the σ=0.027 anchor
gives **λ ≈ 110**. The settled mode then puts large occupancy on that anchor,
which shrinks the T2 curvature (`d²T2/dO² = L2/O`), which inflates the Laplace
draw variance (`T_s / curvature`) — a bar-over-bar positive feedback that runs
occupancy away.

**Reproduction (psytech world, streaming writer):**

| condition | λ_max | outcome (O.sum) |
|---|---|---|
| uniform u_region=0.61 (+cont+nov) | 22 | stable, bounded |
| per-anchor max u=3 on σ=0.027 anchor | 110 | **4.7×10¹³** |
| per-anchor max + mid-stream onset + T_s 1.7 | 110 | **3.88×10¹⁵**  (≈ desktop 4.1×10¹⁶) |
| all anchors + cont + nov maxed, T_s 2.0 | 21/110 | **1.22×10¹⁸** |

The uniform 0.61 case (λ=22) stays bounded; the divergence needs the *per-anchor*
throw the XY pad allows. (Correction to a first pass: an initial "NaN at bar 31"
reproduction was a **probe bug** — it read a non-existent `r.O_bar` and recorded
`nan` every bar. The real mechanism is the per-anchor runaway above.)

**Proposed fix A (validated).** Recalibrate the O-block observables' σ under a
**T_s>0 sampling ensemble** instead of the u=0 MAP — exactly what the existing
`sigma_phi` docstring already prescribes for density ("a density scale becomes
measurable only from a sampling writer"). Region has the same near-degeneracy.

Measured sampling-ensemble σ_region ≈ **[0.132, 0.144, 0.146, 0.137, 0.136]**
(uniform, 2–5× larger; the pathological anchor 0.027 → 0.144). Validation at the
exact trigger condition:

| condition | MAP σ | recalibrated σ |
|---|---|---|
| per-anchor max, T_s 1.7 | O.sum = 3.88×10¹⁵ | **O.sum = 338** |
| all anchors max, T_s 2.0 | O.sum = 1.22×10¹⁸ | **O.sum = 581** |

Recalibration caps λ at ~21 even at max knobs and keeps occupancy bounded — a
~13-order-of-magnitude collapse of the runaway. This is a real re-derivation of
the calibration instrument, **not** a clamp on λ or O (a clamp would hide the
mis-calibration — the forbidden silent-divergence patch).

**Proposed fix B (safety).** The writer currently emits NaN bars **silently**
(reproduced: bars go non-finite and `write_bar` does not raise). It must detect
non-finite / runaway occupancy and **`StreamHalt` loudly** — turning silent
divergence into a reported wall, so garbage can never reach the speakers,
independent of A.

---

## Bug 2 — seed-dependent 255 ms silences (render breaks)

**Symptom:** sharp sudden silences in the futuregarage clips — e.g. abyss had 8,
tide 10, nocturne 9; aphotic and current had **zero**.

**Findings.** Each silence is exactly **one grid slot** (255.4 ms; observed 255 ms,
ratio 1.00). At the gap slots:
- placements are present (8 bands placed — **not** empty/starved slots);
- the placed **source units are healthy** (RMS 0.02–0.17 — not silent audio);
- but the **placement mass is near zero**: slots 79/213 = 0.0 (settled energy at
  the 1e-12 floor); slots 58/118/224 small vs the ~1.25 median.

**Root cause.** The **same** `_sample_temperature` Gaussian draw occasionally
pushes a slot's occupancy *negative*; the `max(·, 1e-12)` clamp then floors the
whole slot → the realizer carries the field whole (no floor-fill, by design) → a
single dead 255 ms slot. **Seed-dependence is the proof**: the settled *mode* is
seed-independent, so only the seeded Laplace draw can produce a per-seed gap
pattern (seed 11 → 5 gaps in 60 s; seed 37 → 0).

**Proposed fix C.** Make the temperature draw **positivity/mass-preserving** —
sample in log/simplex geometry (the same mirror geometry the settlement's own
mirror-descent uses) or reflect negative draws — so "looseness" perturbs *which*
material sits where without ever zeroing a slot. Not a floor-fill patch (that
would fabricate energy the field never settled); a geometry-correct sampler.

---

## Through-line & fix summary

`_sample_temperature`'s additive-Gaussian-in-O draw is the shared fragile point:
it explodes when the variance is large (Bug 1, amplified by the σ mis-calibration)
and collapses a slot when the noise is negative (Bug 2). Proposed fixes:

- **A** — recalibrate O-block σ under a sampling ensemble (validated; fixes Bug 1's driver).
- **B** — finite-occupancy `StreamHalt` (safety; never emit garbage).
- **C** — positivity/mass-preserving temperature sampler (fixes Bug 2; also removes Bug 1's amplifier).

**Scope.** All three are engine changes to the shared machine → a new
**architecture-v3** (full-fork of v1, per the operator's isolation choice), with
v1/v2 immutable. The delivered u=0 futuregarage clips are unaffected by Bug 1;
Bug 2's silences are present in them at the rates above.

**Not implemented.** Awaiting a fix-scope decision.
