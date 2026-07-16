# architecture-v3 — temperature-sampler fix (Bugs 1 & 2)

**Architecture version v3.** A full-copy fork of the v2 machine (which carried
v1 + the display-layer panel relabel). v3's functional change is the coordinated
**A+B+C fix** to the live-steering divergence (Bug 1) and the seed-dependent
255 ms render silences (Bug 2), both root-caused to `_sample_temperature`
(see `reports/2026-07-16-steering-divergence-and-silences.md`). Prior versions
(v1 root, v2) are immutable; pre-change state tagged `pre-arch-v3-2026-07-16`.

## The one coordinated change (not three separable merges)

All three fixes trace to the same fragile component and each partial state has a
live failure mode, so they land together, exam-gated:

- **A — sampling-ensemble σ recalibration.** Measure the O-block observables' σ
  under a T_s>0 sampling ensemble (as the σ_φ docstring already prescribes for
  density) instead of the near-deterministic u=0 MAP. Re-derivation of the
  calibration instrument — NOT a clamp on λ or O. Changes knob feel (less
  hair-trigger); that is correct — the old feel was the bug.
- **B — loud StreamHalt** on non-finite / runaway occupancy (the writer currently
  emits NaN bars silently). Any finite runaway bound is DERIVED from the
  calibrated occupancy scale, never hand-set.
- **C — positivity/mass-preserving temperature sampler.** Draw in the same
  log/simplex (mirror) geometry the settlement's mirror-descent uses, so
  looseness perturbs which material sits where without ever zeroing a slot. A
  fidelity fix (removes an inconsistency), not a floor-fill.

## Instances

Same as v2: v3 introduces no new instance. `psytech` remains the canonical
default corpus (re-pointed to the root tree); `futuregarage` belongs to v1 and
is not duplicated. Fix A recalibrates the DEFAULT corpus's σ under the new
sampling-ensemble instrument, producing v3's `ets/calibration/sigma_phi.json`;
existing corpus instances recalibrate when retrained on this machine.

## Acceptance (v3 merges only when all hold)

See `reports/` and the v3 prereg: (1) Bug-1 repro bounded O(10²–10³); (2) zero
seed-dependent dead slots on a seed sweep; (3) exam re-run passes at registered
margins; (4) Table-6 bias/clip re-measured and dropped; (5) StreamHalt fires on
an injected runaway fixture; (6) re-rendered futuregarage clips have the reported
silences gone. Auditor PASS before merge.
