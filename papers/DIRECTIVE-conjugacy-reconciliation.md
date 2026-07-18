# ETS/autosynth — conjugacy reconciliation: type every control, verify the
# feedback physics, then the UX faithfulness to it

Paste into the build session WITH the two companion papers
(paper1-typed-control-calculus.md, paper2-ets-instrument.md). Those are the
north star; this directive operationalizes them. TWO PHASES: Phase 1 is
READ-ONLY classification + verification (report, no edits). Phase 2 fixes only
what Phase 1 convicts, per doctrine. Auditor (Opus 4.8 or lower) verifies each
phase. Persistent versioning agent logs both to LEDGER.

## The law being checked (from the papers, one paragraph)
Every user control is a thermodynamically conjugate pair: a FORCE the user
holds (entering F through exactly one of five types) and an OBSERVABLE the
machine reports (read-only). T1 tilt (reprices an observable; response =
constrained conjugate fluctuation, sigma_phi its estimator; tilt-tilt
cross-talk Maxwell-SYMMETRIC). T2 thermodynamic (scales eps; directionless).
T3 frame (gauge; the ONLY type whose response carries an antisymmetric /
holonomy component — slide & loop are its two response components, never
summed). T4 clamp (moves the feasible set; binds, doesn't lean). T5 clock
(commutes with argmin; settled schedule byte-identical). Trained parameters
(LAMBDA, world, sigma_phi themselves) are NOT controls and may interface
nothing. Displays show only engine answers (gap/release/brightness emergent,
never UI-shaped).

## PHASE 1 — read-only classification & physics verification (report only)

### 1A. Control inventory & typing table
Enumerate EVERY control on web + desktop (field taps/holds at every zoom,
each scalar slider, crate checkboxes, transport, cue, tempo, any MIDI CC,
any API endpoint that mutates anything). For each, deliver a row:
  control -> claimed type (T1..T5) -> the ONE datum it perturbs (c / eps /
  Pi / G / output-map) -> its entry point in code (the force path) -> its
  conjugate observable -> the meter displaying that observable -> verdict:
  WELL-TYPED / TYPE-ERROR / UNTYPED / PARAMETER-LEAK.
Convictions by definition:
- A control perturbing two data at once, or none: TYPE-ERROR.
- A control with no conjugate observable, or an observable with no meter, or
  a meter not read-only: CONJUGACY-BROKEN.
- Any path from any control to LAMBDA / world / sigma_phi / exam:
  PARAMETER-LEAK (severest).
- REGION lane: field-owned; any second control on it: DOUBLE-AUTHORITY.

### 1B. Physics predictions (run empirically, pre-register expectations first)
  P1 RECIPROCITY (armed T1 lanes): measure d<Phi_A>/du_B vs d<Phi_B>/du_A on
     at least one lane pair (e.g. continuity x novelty), sampling ensemble,
     noise floor measured first. PASS = symmetric within floor.
  P2 CHAOS DIRECTIONLESS: temperature sweep must rescale fluctuation
     magnitudes globally and produce NO directional mean-shift in role space
     beyond floor. PASS = no lean.
  P3 HOLONOMY EXCLUSIVITY: loop negates under cycle-orientation reversal;
     slide does not; NO antisymmetric residue above floor on any T1 lane.
     (Reuse the holonomy-tester agent's P1/P2/P3 protocol.)
  P4 TEMPO: settled SCHEDULE byte-identical across a BPM change (schedule,
     not audio). PASS = identical.
  P5 SIGMA_PHI = FDT: for one armed lane, compare the measured sigma_phi
     against the empirical constrained fluctuation of its conjugate
     observable on the sampling ensemble. PASS = agreement within estimator
     error. (This certifies A's identification, and re-convicts any
     MAP-ensemble calibration.)
  P6 GAP/RELEASE EMERGENT: static check — no easing/tween/damping/clamp code
     touches target-vs-achieved gaps, release convergence, or field
     brightness; all three derive solely from engine reads. Also verify
     release-convergence tracks the engine's unforced relaxation (handle
     follows achieved value, not a timer).
  P7 WORD-PINS-OBSERVABLE (caption-as-conjugacy audit): every control label
     names exactly its conjugate observable's meaning; every meter caption
     names exactly what is measured. Any label whose referent is not its
     conjugate: DISHONEST-LABEL.

### 1C. Deliverable
One table (1A) + one results sheet (1B, expected vs observed vs floor) +
verdict list sorted: PARAMETER-LEAK > DOUBLE-AUTHORITY > CONJUGACY-BROKEN >
TYPE-ERROR > DISHONEST-LABEL > NOT-YET (honest gaps, e.g. unwired meters).
No edits in Phase 1. Repo byte-identical after (scratch cleaned).

## PHASE 2 — remediation (only what Phase 1 convicts)
- Fix by TYPE, per the papers: broken conjugacy -> wire the real observable
  or disarm-and-label the control; type-errors -> re-route the force through
  its single correct datum; parameter-leaks -> sever, incident-logged;
  double-authority -> remove the redundant path; dishonest labels -> relabel
  to the conjugate referent (relabel-directive pattern: face word + true name
  in tooltip).
- FORBIDDEN as fixes: easing/shaping any emergent quantity; hand-set
  sensitivities; summing slide+loop; arming a lane without a measured
  sigma_phi; any synthetic surface captioned as real (real-or-absent).
- Every fix prereg'd, builder->auditor, one commit train per conviction
  class, H-8-style determinism check across, core (ets/*.py) zero-diff unless
  a conviction is IN the core (then it is a wall to report first, not a
  silent fix).

## Acceptance
1. 1A table complete, every control WELL-TYPED or honestly NOT-YET.
2. P1-P7 run with pre-registered expectations; failures either remediated or
   recorded as walls (a physics-prediction failure is a FINDING about the
   theory — report it prominently, do not tune it away).
3. Zero PARAMETER-LEAK / DOUBLE-AUTHORITY / CONJUGACY-BROKEN remaining.
4. Caption audit clean (P7).
5. Auditor re-verifies read-only; LEDGER entries for both phases.

Standing law unchanged: prereg before run, walls surfaced not patched,
one-sentence disclosure of contemplated divergences, coverage honesty. The
papers are the reference; where implementation and papers disagree, that
disagreement is the report's headline, not something to quietly reconcile.
