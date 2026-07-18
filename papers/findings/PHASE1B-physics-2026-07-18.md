# PHASE 1B RESULTS SHEET — conjugacy reconciliation, empirical physics verification
Run: Sat Jul 18 2026 (UTC). Repo /home/user/Geodesic-Mixing @ 5c23834, READ-ONLY
(git-status proof at end). PREREG.md (same dir, timestamped 08:58:29 UTC) was
written BEFORE any physics run; raw data in raw_runs.json, prereg'd analysis in
analyze_phase1b.py -> results.json; post-hoc diagnostics (labeled) in
posthoc_diagnostics.py -> posthoc.json.

## HEADLINE (per directive: a failed prediction is a finding, reported first)
1. **P1 RECIPROCITY FAILED** (45x floor): tilt-tilt cross-talk on the fixture
   is strongly ONE-DIRECTIONAL (novelty pressure suppresses continuity;
   continuity lean does not move novelty). Survives lambda-normalization AND a
   post-hoc near-linear-regime check (~4 sigma). Maxwell symmetry (Theorem B)
   does not hold for the deployed sequential fiber sampler at fixture scale.
2. **P5 FDT IDENTIFICATION FAILED** for the continuity lane: the deployed
   sigma_phi is a CONSISTENT estimator of the across-bar fluctuation
   (sigma_emp matches it), but that fluctuation is NOT the response kernel —
   the CONTINUITY knob is measured INERT on its own conjugate observable
   (response 0.0 +/- 0.07 where Theorem A predicts 2.80). Paper 1's own
   caveat ("misestimation of A's denominator") is realized on the fixture:
   the across-bar marginal std is history/drift variance, not the
   constrained conjugate fluctuation.
3. Consequence for P3c: since the T1 response kernel has a large antisymmetric
   part, **antisymmetric response is NOT exclusive to T3 as deployed** — even
   though the T3 loop METER itself stays correctly silent on T1 cycles.
These are findings about the theory/papers vs the deployed sampler, reported
as-is; nothing was tuned.

## Environment / fixture (as prereg'd)
Engine: architecture-v6/ets (owns `import ets`, engine_bridge pattern).
Fixture: repo-root demo.etsworld — M=2, sr=44100, s_phase=8, 64 placements/bar
(8 slots x 8 bands), EMBEDDED sigma_phi (sampling writer T_s=1, 24 bars, seed 7):
region=[0.63747, 0.50034], density=0.82195, cont=2.88141, gauge=0.0(degenerate),
novelty=0.07851. Armed: region, density, cont, novelty. Control path:
LaneVector -> Engine._tilt_for -> layer0 (lambda_i = u_i/sigma_i) ->
StreamWriter.write_bar. Runs: fresh writer per seed, 32 bars/run, run mean over
all bars (mirrors deployed estimator). FD step h=0.75 knob units.
Honesty — measured lag-1 bar autocorrelation at u=0 (inflates estimator error):
density 0.018, region0 0.022, cont -0.228, novelty +0.347.
Wall-clock: u0 pool 8.0 s; P1 nodes 16.5 s; P2 sweep 8.6 s; P3 cycles 3.7 s
(total 37.0 s); post-hoc diagnostics 22.2 s; analysis < 1 s. Sandbox ~100x
slower than real hardware — fixture-scale ensembles by design.

---------------------------------------------------------------------------
## P1 RECIPROCITY (Theorem B) — VERDICT: **FAIL-FINDING**
PREREG excerpt: "A=continuity, B=novelty... K_AB = sigma_nov*D_AB,
K_BA = sigma_cont*D_BA; EXPECTED K_AB = K_BA within floor... floor = std over
500 random 24/24 splits of the 48-run u=0 pool of the same estimator...
PASS if |K_AB - K_BA| <= 2*floor_Delta."
Ensembles: 4 nodes (u_cont,u_nov) = (+-0.75, 0), (0, +-0.75), T_s=1;
24 seeds/node (2000-2023, 2100-2123, 2200-2223, 2300-2323) x 32 bars.
Floor pool: 48 seeds (1000-1047) x 32 bars.

| quantity | expected | observed | floor (from u=0 pool) |
|---|---|---|---|
| D_AB = d(phi_cont)/du_nov | — | **-5.437** | 0.0069 (=floor_K_AB/sigma_nov) |
| D_BA = d(phi_nov)/du_cont | — | +0.00239 | 0.0028 |
| K_AB (lambda-normalized) | = K_BA | **-0.4268** | 0.0054 |
| K_BA (lambda-normalized) | = K_AB | +0.0069 | 0.0081 |
| K_AB - K_BA | 0 within 2x0.0097 | **-0.4337 (45x floor)** | 0.0097 |
| Cov(cont,nov) at u=0 (triangulation) | = K_AB = K_BA | -0.0331 +/- 0.0073 | — |

Node means (phi_cont): u_nov=+0.75 -> 50.46; u_nov=-0.75 -> 58.61 (huge);
(phi_nov): u_cont=+0.75 -> 0.2055; u_cont=-0.75 -> 0.2020 (nothing).
Disclosure: h=0.75 knob units means lambda_nov = 9.55 (far outside derivative
regime — knob units ARE the deployed interface, so this is the user-experienced
response). POST-HOC DIAGNOSTIC D1 (labeled, seeds 5000-5323): lambda-matched FD
at lambda = +/-1: d(cont)/dlam_nov = -0.247 +/- 0.061 vs d(nov)/dlam_cont =
+0.0025 +/- 0.0021 — asymmetry -0.249, ~4 sigma, and NEITHER equals the
triangulated Cov (-0.033). The failure is not a finite-step artifact.
FINDING: the deployed sampler (mode + per-slot Laplace + SEQUENTIAL fiber
threading) is not the joint Gibbs measure of Theorem B; its tilt-tilt response
kernel is far from symmetric. Cross-talk is real and 45x floor, so this is not
a floor-limited null.

---------------------------------------------------------------------------
## P2 CHAOS DIRECTIONLESS (T2) — VERDICT: **SPLIT — no-lean PASS;
## global-rescale FAIL-FINDING (fiber lanes)**
Pre-run finding (prereg'd): T2 HAS a runtime force path — the sixth lane
TEMPERATURE (LaneVector.T_s -> TiltTerms.T_s: Laplace covariance scale +
fiber logits -E/T_s). Not NOT-YET-WIRED; runnable.
PREREG excerpt: "T_s in {0.5,1.0,2.0}, u=0, 16 seeds/T x 32 bars. EXPECTED
(a) fluctuation of EVERY fluctuating observable increases monotonically
(O-block ~ sqrt(T_s)); (b) role composition rho0 shift T2.0-T0.5 = 0 within
2*combined SE. PASS requires (a) AND (b)."
Seeds: 3000-3015 / 3100-3115 / 3200-3215.

Fluctuations (within-run per-bar std, mean over 16 runs) by T_s = 0.5 / 1.0 / 2.0:
| observable | fluct by T | monotone? | ratio T2.0/T0.5 (sqrt-ideal 2.0) |
|---|---|---|---|
| region0 | 0.400 / 0.569 / 0.714 | YES | 1.79 |
| region1 | 0.397 / 0.551 / 0.744 | YES | 1.87 |
| density | 0.568 / 0.798 / 1.061 | YES | 1.87 |
| cont | 2.971 / 2.945 / 3.513 | **NO** (flat 0.5->1.0 within SE ~0.13, then up) | 1.18 |
| novelty | 0.0971 / 0.0964 / 0.0885 | **NO — DECREASES** (~2x combined SE) | 0.91 |

(b) No-lean: delta_rho0(T2.0 - T0.5) = 0.00023, floor 0.0125 -> **within floor,
PASS** — temperature produces no role-space direction. (Core T2 claim holds.)
(a) O-block lanes rescale ~sqrt(T) (ratios 1.79-1.87 vs ideal 2.0 — bent by the
declared positive-orthant clip); FIBER lanes do NOT rescale globally: cont flat
then up, novelty mildly SHRINKS with T. FAIL of the "rescales fluctuation
magnitudes globally" prediction at fixture scale.
Secondary (prereg'd approximation probe) — mean shifts T2.0 vs T0.5, floor=2SE:
region0 +0.252 (floor 0.070), region1 +0.249 (0.067), density +0.500 (0.082),
cont -3.471 (0.332) — all BEYOND floor; novelty -0.005 (0.012) within.
QUANTIFIED FINDING about the declared Laplace+clip sampler (paper 2 sec. 5):
temperature inflates total scheduled mass (clip bias) and drops continuation
count, i.e. T_s is not a pure sharpness control of the deployed measure — but
it stays directionless in role space.

---------------------------------------------------------------------------
## P3 HOLONOMY EXCLUSIVITY (T3) — VERDICT: (a) **UNDECIDABLE-AT-FIXTURE-SCALE**
## (flag psytech); (b) slide engine-level **NOT-YET**, meter property PASS;
## (c) meter-on-T1 PASS / lambda-curl **FAIL-FINDING (inherited from P1)**
PREREG excerpt: "(a) square region-lean cycle a=1.0, 4 bars/leg, 20 bars,
FWD vs REV, meter loop_g[final] (ets.meters.gauge_loop verbatim), 8 seeds each,
NULL u=0 8 seeds; if |means| <= 2*floor/sqrt(8): UNDECIDABLE... (b) engine
slide structurally zero on v0 (frozen frame) -> NOT-YET-WIRED + meter-math-only
non-negation check... (c) residue K_BA - K_AB expected 0 within P1 floor;
engine T1 cycle loop_g expected within null floor."
Seeds: fwd 4000-4007, rev 4100-4107, null 4200-4207, T1-cycle 4300-4307.

| quantity | expected | observed | floor |
|---|---|---|---|
| loop_g fwd (mean +/- SE) | -rev, if above floor | +0.00024 +/- 0.00034 | null sd 0.00142; 2*sd/sqrt(8)=0.00101 |
| loop_g rev | -fwd | -0.00113 +/- 0.00082 | (rev marginally at 1.1x threshold) |
| negation gap fwd+rev | 0 | -0.00088 | 0.00177 (2x combined SE) — consistent |
| loop_g on T1 (cont/nov) cycle | within null floor | -0.00012 +/- 0.00022 vs null +0.00039 +/- 0.00050 | within — **PASS** |
| T1 antisym residue K_BA - K_AB | 0 within 0.0097 | **+0.4337** | 45x floor — **FAIL-FINDING** |

(a) fwd is below the null floor; rev exceeds threshold by only 1.1x with n=8
(mean/SE ~ 1.4). Signs are opposite (consistent with negation) but magnitudes
are not resolved above the null: verdict per prereg rule is UNDECIDABLE-AT-
FIXTURE-SCALE — matches paper 2 sec. 5's honest flat-corpus null (loop is
corpus-conditional). FLAGGED for psytech-scale on real hardware.
(b) Engine slide: v0 frame frozen at identity (stream.py; tilt.py WALL) —
structurally zero, NOT-YET at engine level (never fabricated; engine_bridge
disarms it). Meter-math-only check (SYNTHETIC trajectory, labeled): phase
charge fwd = rev = 0.4918 — slide is orientation-EVEN, does NOT negate. As the
papers require of the slide component.
(c) The T3 loop METER correctly ignores T1 cycles (cont/nov tilts never touch
the O-block). BUT exclusivity of antisymmetric RESPONSE fails through P1: the
deployed T1 kernel carries a 45x-floor antisymmetric part (lambda coordinates).
Disclosure: this statistic shares P1's estimator (Maxwell symmetry <=> zero
curl — the same measurement read two ways), and the orientation-reversed line
integral of state-point estimates is algebraically -W, so residue-vs-0 is the
physics content.

---------------------------------------------------------------------------
## P4 TEMPO (T5) — VERDICT: **NOT-YET** (honest gap; no run)
Web: no tempo control exists (cloud/companion exposes only region steer +
transport). Desktop: the runtime control set is the exhaustive SIX lanes —
architecture-v6/ets/panel/lanes.py `_CANONICAL` = {region, density,
continuity, gauge, novelty, temperature}; no tempo/BPM lane; grep of ui-v6 and
architecture-v6 finds no runtime BPM control and no schedule byte-identity
test (only ingestion-side tempo curves and the render time-stretch primitive).
TEMPO is the papers' planned T5 output-map control; pointer recorded, nothing
to run.

---------------------------------------------------------------------------
## P5 SIGMA_PHI = FDT (Theorem A), lane = continuity — VERDICT: **SPLIT —
## calibration-consistency PASS; FDT response identity FAIL-FINDING**
PREREG excerpt: "sigma_emp = mean within-run ddof-1 std of phi_cont over the
48-run u=0 pool; D_AA = d<phi_cont>/du_cont from (+-h,0) nodes; EXPECTED
D_AA ~= sigma_emp^2/sigma_deployed ~= sigma_deployed (= 2.8814); floors: 500
random 24/24 splits (D_AA), seed spread + deployed err24 (sigma match)."

| quantity | expected | observed | floor/error |
|---|---|---|---|
| sigma_emp (u=0 sampling ensemble) | ~= 2.8814 (deployed) | 2.8409 +/- 0.0546 | match floor 0.857 -> **PASS** |
| D_AA = d(phi_cont)/du_cont | 2.801 +/- 0.255 (Var/sigma_dep) | **-0.0087** | FD floor 0.0680 -> **FAIL (>20x combined error)** |
| POST-HOC D2: Delta(cont) across u_cont=+/-2.0 | 11.53 (FDT) | -0.005 +/- 0.34 | knob fully inert |

FINDING (the P5 re-conviction the directive anticipated): the deployed
sigma_phi (embedded via worldtools.measure_sigma_inline — across-bar std on the
T_s=1 sampling writer) is a consistent estimator OF THAT MARGINAL FLUCTUATION,
but that quantity is NOT Theorem A's constrained conjugate fluctuation: the
continuity lane's actual linear response is ZERO within a floor 40x smaller
than the prediction. Mechanism evidence: phi_cont is near its ceiling
(64 placements/bar fixed; ~91% already continuations at u=0 — probe in this
sheet's log), so the across-bar sigma = 2.88 is history/drift variance
(lag-1 = -0.23, oscillatory), not per-settlement thermal freedom the tilt can
couple to. Per Theorem A's arming corollary, the honest sensitivity of this
lane on this fixture is ~0 — the lane is armed by a calibration that measures
the wrong ensemble statistic. This is the same failure class Paper 1 names
("the observed lambda-runaway failure mode is the misestimation of A's
denominator"), now demonstrated on the SAMPLING (T_s>0) ensemble as well: the
across-bar estimator is not the Schur-projected covariance. NOTE: the corpus
artifact (scripts/run_sigma_phi.py) uses a batch-MAP across-bar estimator —
a fortiori subject to the same conviction.

---------------------------------------------------------------------------
## Ensemble & seed register (exact)
- u=0 pool: 48 runs, seeds 1000-1047, 32 bars, T_s=1 — floors, Cov, sigma_emp.
- P1 nodes: 24 runs x 4 nodes, seeds 2000-2023/2100-2123/2200-2223/2300-2323.
- P2: 16 runs x 3 temperatures, seeds 3000-3015/3100-3115/3200-3215.
- P3: 8 runs x 4 conditions (fwd/rev/null/T1-cycle), seeds 4000-4007/
  4100-4107/4200-4207/4300-4307, 20 bars each.
- Post-hoc D1: 24 runs x 4 nodes, seeds 5000-5023/5100-5123/5200-5223/
  5300-5323; D2: 12 runs x 2, seeds 5400-5411/5500-5511.
- Analysis RNG (splits only): seed 20260718; 500 splits per floor.

## Verdict list (directive severity order)
- P5 FDT identity: **FAIL-FINDING** (calibration is not Theorem A's estimator;
  cont lane armed-but-inert = a conjugacy-calibration defect).
- P1 reciprocity: **FAIL-FINDING** (45x floor; survives linear-regime check).
- P3c antisym exclusivity (response-level): **FAIL-FINDING** (inherited P1).
- P2 global-rescale half: **FAIL-FINDING** (fiber lanes do not rescale; clip
  bias shifts density/region/cont means beyond floor — declared approximation
  quantified).
- P2 directionless half: **PASS** (no role-space lean, 0.0002 vs floor 0.0125).
- P3a loop negation: **UNDECIDABLE-AT-FIXTURE-SCALE** — flag psytech.
- P3b slide: engine **NOT-YET** (v0 frozen frame); meter property (no
  negation) verified on labeled synthetic input.
- P3c meter-on-T1: **PASS** (loop_g silent on T1 cycles).
- P5 calibration consistency: **PASS** (sigma_emp = deployed within floor).
- P4 tempo: **NOT-YET** (no control exists; pointer recorded).

## Repo integrity proof (surfaced honestly, not patched)
This session performed ZERO writes to the repo: every Edit/Write went to
scratchpad/phase1b/; all engine access was import-and-drive.
`git -C /home/user/Geodesic-Mixing status --porcelain` at close shows:
    M LEDGER.md
    M VERSION_LEDGER.jsonl
Both diffs are additions-only (7 + 5 lines) made at 2026-07-18T09:04:33-
09:05:40Z by the repo's provenance hook recording OTHER concurrent agents'
worktree activity (paths `.claude/worktrees/agent-a56907d43308a9667/...` and
`agent-ab2cc6f9a9eab6f74/...` — not this session, which has no worktree and
edited no repo path; repo was clean at session start, HEAD 5c23834 unchanged).
Reverting another session's provenance ledger would destroy the record the
repo hygiene rules require, so it is surfaced here instead of patched: THIS
session's contribution to the working tree is byte-zero; the two ledger files
carry concurrent sessions' entries. No other tracked or untracked repo change
exists (porcelain shows nothing else).
All scripts/data remain under scratchpad/phase1b/ (PREREG.md, run_phase1b.py,
raw_runs.json, analyze_phase1b.py, results.json, posthoc_diagnostics.py,
posthoc.json, RESULTS.md) for auditor re-run.
