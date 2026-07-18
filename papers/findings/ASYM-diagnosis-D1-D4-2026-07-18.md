# ASYM-DIAGNOSIS D1–D4 — the fiber-ordering bias as a subtractable instrument error, and the fair (bias-removed) reciprocity/holonomy readouts

Run: Sat 18 Jul 2026 UTC. Repo /home/user/Geodesic-Mixing, **READ-ONLY MEASUREMENT/READOUT diagnosis**.
The SAMPLER, F, world, and output are BYTE-IDENTICAL before and after this work; nothing about the
instrument's sound was changed. This document only characterizes and decontaminates *readouts*.

Harness: `scratchpad/asym/harness.py` — the offline monkeypatch that permutes the greedy fiber
sampler's slot-processing ORDER (`architecture-v6/ets/writer/stream.py` `StreamWriter.write_bar`
step (3), `for s_local in range(grid.n_slots)` → `FiberThreader.place_slot`). NO repo file is edited;
all patching is in-process. **Faithfulness certificate (re-asserted this session): the patched writer
at IDENTITY order reproduces the stock `write_bar` bit-for-bit on all φ** (`assert_identity_matches`,
null and novelty-leaned tilts) — the harness changes ONLY the fiber slot-processing order.

Diagnosis scripts/data (scratch, for auditor re-run): `scratchpad/asymdiag/` —
`common.py`, `run_d1.py` → `d1.json`, `PREREG-D3.md` (timestamped 10:03:56 UTC), `run_d3.py` → `d3.json`.
Prior context: `papers/findings/ASYM-verdict-ARTIFACT-2026-07-18.md` (the T-ORD/T-COR/T-REV run that
forced the ARTIFACT verdict) and `papers/findings/PHASE1B-physics-2026-07-18.md` (P1 reciprocity,
P3 holonomy). Statistic definitions are inherited verbatim from those: A = continuity, B = novelty,
D_AB = d⟨φ_cont⟩/du_nov, D_BA = d⟨φ_nov⟩/du_cont, λ-normalized K_AB = σ_nov·D_AB, K_BA = σ_cont·D_BA,
and the Phase-1B "45×" antisymmetry statistic **dK = K_AB − K_BA**. Holonomy readout = the committed-
region loop-holonomy meter `ets.meters.gauge_loop.loop_g` (verbatim) evaluated on the streamed per-bar
settled occupancy O, scalar = loop_g[final committed cycle]. Fixture: repo-root `demo.etsworld`
(M=2, s_phase=8, embedded σ_φ: σ_cont=2.8814, σ_nov=0.07851). h=0.75 knob step, 24 bars/run,
N=16 seeds/node, paired seed blocks (identical block across all orders → only the fiber order differs).

---

## Headline
1. The 45× tilt cross-talk asymmetry is a **subtractable ordering-bias instrument error**, and the bias
   is concentrated **entirely in one directed lane component** — K_AB (novelty→continuity). K_BA and
   both holonomy readouts carry **no ordering bias above their own floors**.
2. On the **FAIR (order-averaged, bias-removed)** readout, with pre-registered floors fine enough to
   decide: **the reciprocity residue is RESIDUAL-NULL** and **the holonomy residue is RESIDUAL-NULL**.
   Nothing antisymmetric survives fair measurement above its floor. In ETS's deployed sampler, at
   fixture scale, the antisymmetric-residue theme was **entirely the sampler-ordering artifact.**
3. This is a statement about the DEPLOYED GREEDY SAMPLER's readout ONLY. **Theorem B stands** (§D4).

---

## D1 — the ordering bias as a known instrument error (subtractable, per lane pair, with floors)

RAW = the shipped identity order (O1). FAIR = the order-averaged estimate over R=16 uniformly-random
slot permutations (D3 ensemble). Ordering **bias(readout) = RAW(identity) − FAIR(order-averaged)**, with
its own measured noise floor SE = √(SE_RAW² + SE_FAIR²). This bias is the quantity to SUBTRACT from a
readout to decontaminate it.

Lane pair (A = continuity, B = novelty), demo fixture:

| readout | RAW (identity, as shipped) | FAIR (order-averaged) | **BIAS = RAW − FAIR** | \|bias\|/floor |
|---|---|---|---|---|
| **dK = K_AB − K_BA** | −0.4170 ± 0.0176 | −0.0142 ± 0.0163 | **−0.4028 ± 0.0240** | **16.8×** |
| **K_AB (novelty→continuity)** | −0.4030 ± 0.0118 | −0.0149 ± 0.0162 | **−0.3882 ± 0.0200** | **19.4×** |
| **K_BA (continuity→novelty)** | +0.0139 ± 0.0131 | −0.0006 ± 0.0020 | +0.0146 ± 0.0132 | 1.1× |
| **holonomy loop_g (null, u=0)** | −0.00009 ± 0.00022 | +0.00011 ± 0.00029 | −0.00020 ± 0.00036 | 0.8× |
| **holonomy loop_g (novelty-leaned)** | +0.00046 ± 0.00032 | +0.00014 ± 0.00026 | +0.00032 ± 0.00041 | 1.0× |

**Order-dependence profile of dK across the built permutation set** (D1, `d1.json`; reproduces
`ASYM-verdict-ARTIFACT` exactly):

| order | dK ± SE | K_AB ± SE | K_BA ± SE | loop_g null | loop_g lean |
|---|---|---|---|---|---|
| O1 identity (default) | **−0.4170 ± 0.0176** | −0.4030 ± 0.0118 | +0.0139 ± 0.0131 | −0.00009 ± 0.00022 | +0.00046 ± 0.00032 |
| O2 reversed | +0.1041 ± 0.0315 | +0.1010 ± 0.0309 | −0.0031 ± 0.0058 | −0.00013 ± 0.00021 | +0.00034 ± 0.00021 |
| O3 random | +0.0081 ± 0.0280 | +0.0087 ± 0.0263 | +0.0007 ± 0.0095 | −0.00008 ± 0.00026 | +0.00037 ± 0.00023 |
| O4 random | +0.0697 ± 0.0412 | +0.0577 ± 0.0407 | −0.0121 ± 0.0066 | +0.00003 ± 0.00030 | −0.00008 ± 0.00019 |
| O5 random | +0.0458 ± 0.0288 | +0.0413 ± 0.0280 | −0.0045 ± 0.0070 | −0.00032 ± 0.00021 | −0.00012 ± 0.00015 |

**Interpretation of the bias profile.**
- The ordering error is a **single directed term**: it lives ~entirely in **K_AB (novelty→continuity)**
  — the continuity response to a novelty push — at 19× its floor. The reverse direction K_BA
  (continuity→novelty) has bias +0.015 ± 0.013 (1.1× floor, i.e. within one floor of zero), and both
  holonomy readouts have bias ≤ 1× floor. So the "45× reciprocity break" is not a two-sided
  distortion; it is the greedy left-to-right order inflating exactly one cross-derivative through the
  run-building continuity ceiling (identity order builds φ_cont ≈ 58, near the 64 ceiling; novelty
  then breaks long runs for a large −D_AB — the mechanism named in `ASYM-verdict-ARTIFACT`).
- **Why the holonomy readout carries no ordering bias (mechanistic, measured).** The slot permutation
  acts on step (3) fiber threading, which is *downstream* of the settled occupancy O (produced in
  step (2)). loop_g reads O. The permutation therefore perturbs O only *indirectly*, by shifting the
  rng stream (fiber `_choose` draws Gumbel noise; a permuted order changes the draw order/count, so
  later bars' O re-samples). We measured this directly: the full-tape O is **not** bit-identical across
  orders (max|ΔO| vs identity ≈ 0.71–1.00 for reversed/random; bar-0 O is identical because the rng is
  untouched before its settlement). Yet loop_g is unmoved above its floor at every order. That is the
  clean signature that the permutation re-samples O without a *systematic* holonomy effect: the fiber
  order injects a systematic antisymmetric term into the φ-based reciprocity readout, but only rng
  re-sampling noise into the O-based holonomy readout.

The bias column above is the deliverable: to decontaminate any single-order reciprocity readout on this
fixture, subtract bias(dK) = −0.403 ± 0.024 (equivalently, subtract bias(K_AB) = −0.388 ± 0.020 from the
one component that carries it). The holonomy readout needs no correction (bias within floor).

---

## D2 — decontaminated readouts (RAW and FAIR, both labeled, neither deleted)

**P1 RECIPROCITY (Theorem B object) — demo fixture**

| form | dK | K_AB (nov→cont) | K_BA (cont→nov) |
|---|---|---|---|
| **RAW** (sampler-ordered, as shipped) | **−0.4170 ± 0.0176** | −0.4030 ± 0.0118 | +0.0139 ± 0.0131 |
| **FAIR** (order-averaged / bias-subtracted) | **−0.0142 ± 0.0163** | −0.0149 ± 0.0162 | −0.0006 ± 0.0020 |

RAW is what the deployed greedy sampler shows: a strong one-directional 45×-floor non-reciprocity.
FAIR is the estimate of the TRUE joint-Gibbs object's reciprocity the shipped ordering was hiding:
**both cross-derivatives sit within the noise floor — the order-symmetrized deployed object's
tilt response is approximately Maxwell-symmetric.** The shipped left-to-right ordering is what broke it.

**P3 HOLONOMY (loop_g, committed-region) — demo fixture**

| form | loop_g null (u=0) | loop_g novelty-leaned |
|---|---|---|
| **RAW** (sampler-ordered, as shipped) | −0.00009 ± 0.00022 | +0.00046 ± 0.00032 |
| **FAIR** (order-averaged) | +0.00011 ± 0.00029 | +0.00014 ± 0.00026 |

Here RAW and FAIR agree and are both null: the deployed ordering was **not** hiding any holonomy —
there was none to hide at this fixture scale. (The richer P3a fwd/rev loop-negation test in Phase-1B
was UNDECIDABLE-AT-FIXTURE and remains flagged for psytech; this diagnosis adds that its meter also
carries no ordering bias.)

---

## D3 — is there residual non-reciprocal / holonomy signal ABOVE ITS FLOOR on the FAIR readout?

**Pre-registered** in `scratchpad/asymdiag/PREREG-D3.md` (timestamped `date -u` = Sat Jul 18 10:03:56
UTC 2026), written and frozen BEFORE the fair estimation was run (commit-before-run). Frozen estimator:
R=16 random orders (seeds 9001–9016), paired seed block s0=50000, N=16, 24 bars; λ-normalized K's;
holonomy from 12 seeds (40000–40011), null and leaned. Frozen floors: SE_fair(X) = std_r(X_r)/√R
(across-permutation SE of the order-mean, which already carries each order's seed noise);
inst_floor(dK) = median per-order se_dK; binding_holo_floor = max(SE_fair, per-order seed-SE). Frozen
confound guard: recompute the fair reciprocity at h=0.375 (half step, λ_nov halved from 9.55) — a
residue counts as linear-regime-robust only if resolved above floor with the SAME sign at BOTH steps.
Frozen resolution targets: τ_dK = 0.05, τ_holo = 0.001 (if 2·SE_fair exceeds τ the fixture cannot
decide → UNDECIDABLE). Full verdict rule text is in the prereg and was applied unaltered.

**Fair-readout results (`d3.json`):**
- dK_fair(h=0.75) = **−0.0142**, 2·SE_fair = 0.0325, inst_floor = 0.0315.
  Floor check: 2·SE_fair = 0.0325 < τ_dK = 0.05 → **the fixture CAN decide** (not floor-limited).
  Residue check: |dK_fair| = 0.0142 ≤ 2·SE_fair = 0.0325.
- dK_fair(h=0.375) = **+0.0147**, 2·SE_fair = 0.0555 — also within floor, and **opposite sign** to the
  h=0.75 fair value: no stable residue survives the step change (confound guard would fail anyway).
- holo_null_fair = **+0.00011**, binding floor = 0.00029 (< τ_holo = 0.001 → decidable);
  |holo_null_fair| = 0.00011 ≤ 2·floor = 0.00058. holo_lean_fair = +0.00014, within floor likewise.

**VERDICT — reciprocity: RESIDUAL-NULL.** |dK_fair| ≤ 2·SE_fair with the floor fine enough to resolve a
residue at the τ_dK = 0.05 level. The small positive fair-dK seen in the 3-order D1 sample (+0.04) was
small-sample noise: the R=16 estimate is −0.014 and flips sign to +0.015 at half-step. Nothing
antisymmetric survives fair measurement above its floor.

**VERDICT — holonomy: RESIDUAL-NULL.** |holo_null_fair| ≤ 2·binding_floor, floor below τ_holo.

**Consequence (honest negative).** After removing the fiber-ordering bias, the antisymmetric-residue
theme — non-reciprocal tilt cross-talk (P1) and loop holonomy (P3) — **does not survive** in ETS's
deployed sampler at fixture scale. The theme was, on this evidence, **entirely the sampler-ordering
artifact in ETS.** (This is the "RESIDUAL-NULL" branch of the pre-registered trichotomy; the
"UNDECIDABLE-AT-FIXTURE" branch did not obtain here because the fair floor 2·SE_fair = 0.033 resolved
below the 0.05 target. The richer Phase-1B P3a fwd/rev loop-negation object — a different, orientation-
paired statistic — separately remains UNDECIDABLE-AT-FIXTURE and is the one flagged for a psytech run:
the loop is corpus-conditional and needs an ensemble that resolves ~1×10⁻³ loop_g on a non-flat corpus
on real hardware, routed to `tools/physrunner/`. This diagnosis does not re-open it; it only certifies
that the loop_g meter carries no ordering bias.)

---

## D4 — scope (stated precisely so this cannot be misread)

This diagnosis concerns **ETS's DEPLOYED GREEDY SAMPLER ONLY** — the sequential fiber threading in
`architecture-v6/ets/writer/stream.py` `write_bar` step (3). Its free choice of slot-processing order
injects a spurious antisymmetric term into the reciprocity readout; order-averaging removes it, and
what remains (dK_fair, loop_g_fair) is null within floor.

- **Theorem B (exact joint-Gibbs symmetry / Maxwell reciprocity) STANDS.** Theorem B is a statement
  about the *exact joint Gibbs measure*. The deployed sampler is NOT that measure — it is mode +
  per-slot Laplace + sequential (greedy, not jointly-settled) fiber threading. The FAIR readout is
  fully consistent with Theorem B: the order-symmetrized object is Maxwell-symmetric within floor.
  Order-averaging removes only the ORDERING artifact; the mode/Laplace/greedy approximations remain, so
  even a *resolved* small dK_fair would have been a residue of THOSE approximations, still not a
  Theorem-B violation — and in fact none was resolved (RESIDUAL-NULL).
- **The program's other non-reciprocal threads are UNTOUCHED by this instrument's verdict.** The
  markets thread, the Hopfield thread, and the abstract Gibbs-generator thread are separate objects
  with their own antisymmetric structure; nothing here measures, bounds, or refutes them. This verdict
  is not a claim about the theory or about those threads.
- **The SAMPLER STAYS.** This is diagnosis only. No change was made to the sampler, F, world, or output;
  the deployed greedy threading is the protected baseline (its feedback output is impressive) and is not
  touched. Any order-symmetrized/jointly-settled fiber block is a SEPARATE pre-registered experiment
  gated on output musicality — NOT done here. The correct use of the D1 bias column is to *decontaminate
  a readout* (subtract bias(dK) = −0.403 ± 0.024 from a single-order reciprocity meter), not to alter
  the instrument.

---

## Repo integrity proof (surfaced, not patched)
This session performed exactly ONE authorized repo write: this findings document
(`papers/findings/ASYM-diagnosis-D1-D4-2026-07-18.md`), of the same class as the existing
`papers/findings/*` docs. Every script and datum is under `scratchpad/asymdiag/` (and the reused
harness under `scratchpad/asym/`). The SAMPLER / F / world / output code is byte-identical; the
identity-order faithfulness certificate was re-asserted before any measurement.

`git status --porcelain` at close additionally shows `M LEDGER.md` and `M VERSION_LEDGER.jsonl`. Those
two diffs are **not this session's**: they are additions-only entries written by the repo's provenance
hook at 2026-07-18T10:00–10:03Z recording OTHER concurrent agents' worktree activity (paths
`.claude/worktrees/agent-ad4f2a43.../…`, `.claude/worktrees/agent-aa9a7bf2.../…`). This session has no
worktree and edited no `ets/`, `cloud/`, or `architecture-v6/` path. Reverting another session's
provenance ledger would destroy the record the repo-hygiene rules require, so it is surfaced here
rather than patched. This session's contribution to tracked code is byte-zero; its only intended
tracked addition is this findings doc.
