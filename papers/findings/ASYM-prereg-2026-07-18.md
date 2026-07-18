# ASYM PREREG — genuine-vs-artifact diagnostic for the 45x tilt cross-talk asymmetry
TIMESTAMPED (date -u): Sat Jul 18 09:31:04 UTC 2026
Repo: /home/user/Geodesic-Mixing @ HEAD 0e985899 — READ-ONLY, REPORT-ONLY.
All scripts/results live under scratchpad/asym/. Written BEFORE any estimand run.
Engine: architecture-v6/ets (forced first on sys.path; `import ets` ownership
asserted, engine_bridge.py pattern). No repo file is edited; no sampler / F /
world / output behavior is changed. The permutation is an OFFLINE monkeypatch
measurement harness applied in this scratch script only.

## The finding being explained (Phase-1B RESULTS.md)
Tilt-tilt cross-talk on the demo fixture is ~45x-floor ONE-DIRECTIONAL:
  D_AB = d<phi_cont>/du_nov = -5.437  (novelty pressure strongly suppresses continuity)
  D_BA = d<phi_nov>/du_cont = +0.00239 (continuity lean does not move novelty)
lambda-normalized residue K_AB - K_BA = -0.4337 (45x the split-floor 0.0097).
Theorem B (paper1 sec 3) predicts tilt-tilt cross-talk is Maxwell-SYMMETRIC; the
only antisymmetric response is T3 holonomy. So this is a prima-facie Theorem-B /
Maxwell violation. TWO explanations, not to be pre-judged:

- H-GENUINE: the corpus dynamics are DIRECTED (tension->release, non-reversible
  time); the deployed object is a directed Gibbs generator whose non-reciprocity
  is legitimate content (the antisymmetric residue). => asymmetry lives in the
  OBJECT: corpus-dependent, structured, INVARIANT to sampler lane order. Theorem B
  would then be too strong (it assumes a conservative/undirected joint measure).
- H-ARTIFACT: the object is symmetric; the greedy sequential fiber sampler's
  arbitrary SLOT-processing ORDER manufactures the asymmetry. => order-dependent,
  roughly corpus-independent; contaminates the holonomy readout.

## Located lane-iteration site (the "greedy sequential fiber sampler")
architecture-v6/ets/writer/stream.py `StreamWriter.write_bar` step (3): the loop
`for s_local in range(grid.n_slots)` calling `self.threader.place_slot(...)`
sequentially. Sequential coupling is via `FiberThreader.run_head[b]` (the band's
run in flight): each slot's continuation option is `successor(run_head[b])`, so
the ORDER in which slots are threaded is the greedy sampler's free ordering
choice. (Temperature/O sampling in step (2) is per-slot and order-independent;
phi_cont is a count and phi_novelty a mass-weighted sum, both aggregate-invariant
to row order — so permuting step (3)'s slot order changes ONLY the run-threading
sequence and the rng-consumption order, nothing else. This is verified: the
identity-order patched writer must reproduce the stock writer's phi bit-for-bit,
asserted in code before any measurement.)

## Common estimator conventions
- A RUN = n_bars bars at fixed (u, T_s=1), fresh StreamWriter(world, seed), one
  seed; per-bar phi recorded; run value = mean over ALL n_bars (mirrors deployed
  calibration; no burn-in). Node value = mean over N seeds of the run values.
- FD step h = 0.75 knob units, central differences (matches Phase-1B P1).
- Lane pair: A=continuity (phi_cont), B=novelty (phi_novelty), both ARMED on demo.
- Coordinate disclosure (from Phase-1B): Theorem B's exact Maxwell symmetry is in
  LAMBDA coords (d<Phi_A>/dlam_B = d<Phi_B>/dlam_A = Cov). Deployed knob u = lam*sigma,
  so raw knob-derivatives are predicted asymmetric by sigma_A/sigma_B as a pure
  coordinate effect. We therefore report BOTH raw D and lambda-normalized
  K_AB=sigma_nov*D_AB, K_BA=sigma_cont*D_BA. The physics-content asymmetry statistic
  is the lambda-normalized residue dK = K_AB - K_BA (invariant to that coordinate
  effect). We also report the directive's ratio A = D_AB/D_BA (unstable when
  D_BA ~ floor; reported with its SE, not used as the sole decider).

## Floors (measured first, per test)
- SEED FLOOR: SE of each node mean = std_over_seeds/sqrt(N). Propagate to
  SE(D_AB), SE(D_BA), SE(dK) by standard first-order error propagation.
- CROSS-ORDER STABILITY FLOOR (T-ORD): pooled SE across the 5 orders' node
  estimates; the deciding comparison is the across-order SPREAD (sample std of
  the per-order statistic across the 5 orders) vs 2x that pooled SE.
- All floors are printed in the results table beside the estimate. A statistic
  whose across-condition spread <= 2x its seed-SE is "invariant within floor";
  a sign flip or a spread >> SE is "order/condition-dependent".

## Ensemble sizes (set from the disclosed 5 ms/bar smoke; NOT an estimand)
T-ORD: 5 orders x 4 nodes x N=16 seeds x 24 bars = 7680 bar-writes.
  Seeds per node fixed & disjoint across nodes AND orders:
    base seed block s0=10000; node j in [0..3], order o in [0..4]:
    seeds = s0 + 1000*o + 100*j + range(16).
T-COR: >=4 corpora x 4 nodes x N=16 seeds x 24 bars, default order O1.
T-REV: demo world, forward vs reversed successor, 4 nodes x N=16 x 24 bars.

## TEST T-ORD (PRIMARY — lane-ordering invariance)
Quantity: per order o in {O1=identity[0..7], O2=reversed[7..0], O3,O4,O5=random
perms (numpy default_rng seeds 8003,8004,8005)} measure D_AB(o), D_BA(o),
K_AB(o), K_BA(o), dK(o)=K_AB-K_BA, and A_ratio(o)=D_AB/D_BA on the demo fixture.
PRE-REGISTERED PREDICTIONS:
  * H-GENUINE: sign(D_AB) and sign(dK) IDENTICAL across all 5 orders AND the
    across-order spread of D_AB and of dK <= 2x pooled seed-SE (magnitude stable).
    i.e. slot order does NOT manufacture the asymmetry.
  * H-ARTIFACT: D_AB and/or dK FLIP SIGN across orders, OR collapse toward the
    seed floor under permutation, OR their across-order spread >> 2x pooled SE
    (vary wildly). i.e. the asymmetry is a fingerprint of the default ordering.
VERDICT MAP: stable+same-sign within floor -> supports H-GENUINE (order is not
the cause). flip/collapse/wild -> supports H-ARTIFACT.

## TEST T-COR (SECONDARY — corpus dependence)
Corpora: C0=demo.etsworld (reference, M=2); C1..C3 = distinct synthetic worlds
(ui-v6 worldtools.build_synthetic_world) with different seeds AND different
(n_tracks, n_slots): C1=(seed=101,n_tracks=4,n_slots=24), C2=(seed=202,
n_tracks=6,n_slots=32), C3=(seed=303,n_tracks=3,n_slots=16). Each carries its own
inline-measured sigma_phi (worldtools.measure_sigma_inline). Measure D_AB, D_BA,
dK, A_ratio at default order O1.
DISCLOSED LIMIT: the synthetic corpora are seeded-noise fixtures; they differ in
anchor geometry and successor graph but are drawn from one generative process, so
their structural diversity is bounded. If all synthetic corpora yield near-identical
A (within floor), T-COR is POWER-LIMITED and flagged UNDECIDED-AT-FIXTURE-SCALE
for the corpus axis (real musical corpora specified as the hardware-scale run).
PRE-REGISTERED PREDICTIONS:
  * H-GENUINE: dK / A_ratio CHANGES across corpora beyond the pooled seed floor
    (the asymmetry tracks corpus content).
  * H-ARTIFACT: dK / A_ratio roughly CONSTANT across corpora within floor.

## TEST T-REV (TERTIARY — material time reversal)
Reverse the corpus succession structure read-only: build a scratch RealizationIndex
(dataclasses.replace) whose `successor` maps each unit to its source-PREVIOUS unit
(the inverse of the source-consecutive graph), leaving anchors/candidates/roles
intact; inject it into a scratch World copy; drive StreamWriter with it. No repo
edit; the reversed index is an in-memory scratch object. Measure D_AB, D_BA, dK,
A_ratio forward vs reversed on demo.
PRE-REGISTERED PREDICTIONS:
  * H-GENUINE: dK / A_ratio NEGATES or materially CHANGES under time-reversal
    (the asymmetry is carried by the direction of the succession dynamics).
  * H-ARTIFACT: dK / A_ratio UNAFFECTED (the asymmetry is order/ceiling, not time).
If reversal cannot be done read-only, report NOT-RUN with the reason.

## Third-mechanism honesty (ceiling)
Phase-1B identified phi_cont near its ceiling (~91% continuations at u=0) as the
proximate mechanism. A ceiling asymmetry that is BOTH order-invariant (T-ORD
stable) AND corpus-constant (T-COR flat) AND time-reversal-invariant (T-REV null)
is NEITHER the ordering artifact NOR clean directed-corpus content: it is a
FIXTURE-CEILING artifact. That outcome is a valid MIXED/UNDECIDED verdict and will
be surfaced as its own mechanism, not forced into GENUINE or ARTIFACT.

## VERDICT LOGIC (stated before running)
- T-ORD stable + T-COR corpus-varying (+ T-REV responsive) -> GENUINE.
- T-ORD ordering-dependent (+ T-COR corpus-constant) -> ARTIFACT.
- T-ORD stable + T-COR constant + T-REV null -> UNDECIDED (ceiling mechanism),
  hardware-scale run specified.
- any other mix -> UNDECIDED with the deciding hardware-scale run specified.
No prediction outcome is forced; a failed prediction is a FINDING. Repo byte-
identical at end (git status --porcelain empty), verified and stated.
</content>
</invoke>
