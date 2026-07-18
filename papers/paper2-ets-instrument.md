# The Equilibrium Tape Synth: an Instrument You Negotiate With
## Part 2 — the application, and what it turned out to be an instance of

Companion to Part 1 (Typed Control Calculus for Gibbs Free-Energy Models).
This paper is application-first: the instrument as built, its interface as
converged upon through use, and only then (Sec. 6) the identification of the
whole panel with Part 1's theorems. STATUS TAGS as in Part 1.

---

### 1. The instrument

ETS ingests N music tracks; a beat clock slices them into beat-synchronous,
band-split UNITS of real audio (every unit provenance-tagged to its source
track at birth; the tag is never removed). Training freezes a WORLD: M
self-sized anchors (roles — the corpus's learned sound-categories), a
succession kernel, contrastively-fit weights LAMBDA, and per-lane calibration
scales sigma_phi. At play time a causal WRITER settles each bar to the
minimum of a Gibbs free energy F (transport + entropy + succession-bridge +
masking) given everything currently pinned — committed past, panel state,
user biases — and inks the winning arrangement of real slices to an output
TAPE. Rendering is choiceless stitching; there is no decoder; output is made
only of the user's actual audio.

Two motions are intrinsic, both read off the trained object rather than
added: FORWARD PROGRESSION (each settled bar re-tilts the next bar's energy
through the succession bridge — the corpus's own dynamics continued) and
BREATHING (the equilibrium is a soft basin, not a spike; per-bar sampling
within it yields living variation, not photocopy repetition). M itself is a
measurement: anchors grow only while unexplained structure clears a noise
floor; M = 5 on the reference corpus means the material's effective source
count is five, not that anyone chose five.

### 2. The interface, as converged

**The field.** One surface of recursively drillable squares replaces pads,
XY pad, and hierarchical drill-in. Zoom out: tracks. Mid: roles. In: units.
Deeper: sub-structure — with drill depth SELF-SIZING per square by the same
noise-floor criterion as M (atomic squares render non-expandable; no drill
resolves into noise). Squares are grouped by the trained coupling's OWN
equivalence (same anchor-profile = same sound); a fresh clustering pass is
forbidden as an extrinsic notion of similarity. One gesture: hover-scroll to
bias (soft; saturates at strongly-disfavored; never a mute — hard membership
is the crate checkbox, a different act). Fill brightness = the unit's
re-settled weight, read back from the engine.

**The scalar lanes.** Draggable sliders for continuity (VARY), novelty
(SPREAD), density (DENSITY), gauge stiffness (KEY LOCK), temperature (CHAOS);
tempo (TEMPO) apart. Each slider is TWO marks on one track: the handle (the
user's target) and the machine mark (the achieved value read from settled
output). The gap between them is not drawn — it is the settlement resisting.
On release, the handle drifts to the machine mark: the unforced equilibrium
reclaiming the lane. Lanes whose calibration cannot be measured on the
current corpus render greyed AND inert (disarmed-and-labeled, never faked).

**Meters.** Read-only throughout: per-bar arrangement statistics (region
focus, continuity, novelty, density); the drift pair SLIDE (distance from
home) and LOOP (route residue surviving return — nonzero even at home;
holder of the ending veto); settlement health; clock. Deleting any meter
leaves the audio byte-identical.

**Transport, cue, tempo.** Output layer only: play/stop/position; a private
pre-listen bus tapping the already-settled lookahead frontier (monitor-only —
no path from cue to settlement); master BPM as pitch-preserving time-stretch
of the emitted schedule, under which the settled schedule is byte-identical.

### 3. The governing display law

One invariant covers every surface: **you push, the engine re-settles, the
display shows the engine's answer.** Nothing reaches a pixel without passing
through F. Its two observable signatures: CO-MOVEMENT (bias one thing;
related things you did not touch move) and DYNAMIC SENSITIVITY (the same
push responds differently depending on the current settled state). Both are
emergent from re-settlement and cannot be faked by a display that merely
echoes input — which makes them proofs of realness, and makes their absence
a fabrication detector. The project's incident history (a cosmetic waveform
captioned "settled render"; hardcoded lane values captioned "weights"; a
spread proxy captioned "drift") is exactly the class this law exists to
catch: a caption asserting a data source the surface does not have.
Remediation doctrine: REAL-OR-ABSENT — a surface shows engine truth or is
disarmed and labeled; a better-looking synthetic is still a fabrication.

### 4. What the knobs turned out to be

None of the knobs was given a behavior. A knob reprices one aspect of the
energy; what happens is dictated by the trained landscape's shape in that
direction. Sensitivity is therefore a READOUT of the corpus: responsive
where the material varied, stiff where it was rigid — and measured, per
lane, as sigma_phi on the sampling ensemble. Where the measurement fails,
the knob honestly does not exist (disarmed). The felt resistance when
steering is the equilibrium itself pulling toward what is self-consistent
with past + corpus; the tape records the compromise, bar by bar. Releasing
a control shows the pure forward dynamics resume — the handle converging to
the machine mark is the visible form of the unforced equilibrium.

### 5. Empirical findings [selected, honest]

- Exam (pre-registered scramble contrast): real arrangements beat all four
  scramble classes at min held-out separation 0.95 (bar 0.90) on the
  reference corpus; audit-reproduced bit-exactly.
- Anchor double dissociation passed; anchor count flat in N.
- Holonomy above calibrated null DID NOT PASS on the flat reference corpus
  (kappa_real/kappa_null ~ 0.45, reported as-is, no retune): the loop
  component is corpus-conditional — real as a meter, empty on structureless
  material. [honest negative]
- The temperature sampler is a DECLARED APPROXIMATION of exact Gibbs
  sampling (Laplace + clipping); a geometry-correct (mirror/simplex)
  sampler is specified; low-temperature output is the certified regime.
- Two disarmed lanes (density, gauge) on the reference corpus: their
  constrained fluctuations do not clear the noise floor there — the arming
  criterion operating as designed.

### 6. The reveal: the panel is a theorem

Everything above is Part 1 instantiated, discovered in this order rather
than designed from it:

| ETS object | Part 1 object |
|---|---|
| field tap / scalar tilt lanes | T1 conjugate pairs (force, observable) |
| CHAOS / temperature | T2 thermodynamic (scales eps; directionless) |
| KEY LOCK + SLIDE/LOOP pair | T3 frame control; its response's Hodge split — slide = symmetric part, loop = the system's ONLY antisymmetric response |
| committed past, crate, panel measure, field-at-unit | T4 clamps |
| TEMPO (schedule byte-identity) | T5 clock (commutes with argmin) |
| sigma_phi calibration | Theorem A: sensitivity = constrained conjugate fluctuation, measured |
| disarm-and-label | Theorem A corollary: degenerate FDT, not policy |
| co-movement | Theorem B: off-diagonal covariance; Maxwell-symmetric on tilt lanes |
| target/achieved gap; release convergence | Theorem C': emergent response; unforced relaxation |
| two-marks-on-one-track; field as compressed pair | Theorem D(iii): canonical renderings of conjugacy at two densities |
| the synth-grammar reconciliation succeeding | Theorem D(i–ii): signature unification is unique; the words carry the referents |

The classical-synth reconciliation worked, repeatedly and without forcing,
because it could not have failed: the human grammar and the thermodynamic
types carry the same five response signatures, and signature matching has a
unique fixed point. The interface was discovered, not designed — and every
fabrication the project caught was, in these terms, a violated conjugacy: a
mark not backed by its observable, a force not entering through its type.

### 7. Predictions and checks this identification licenses

P1 Reciprocity: on armed tilt lanes, push A/watch B equals push B/watch A
   within estimator noise. [falsifiable now]
P2 Directionlessness of CHAOS: temperature rescales fluctuation magnitudes
   globally; it cannot lean the arrangement anywhere. [falsifiable now]
P3 Holonomy exclusivity: the antisymmetric (orientation-reversing) response
   component appears on the frame lane only; loop negates under cycle
   reversal; slide does not. [diagnostic specified]
P4 Schedule invariance of TEMPO. [test exists]
P5 No control interfaces a parameter: every shipped control factors through
   exactly one of T1–T5; anything else is a defect. [auditable]
P6 Word-pins-observable: each lane's label denotes exactly its conjugate
   observable (the meter it is paired with); a label that cannot be so
   paired is dishonest. [caption-audit as conjugacy check]

### 8. Ledger

[occupied]: everything load-bearing in the machinery (entropic OT, FDT,
NCE, Hodge/screw decomposition, sampler theory). [candidate-original]: the
conjugacy-as-interface principle and the five-type panel identification
(sweep pending, per Part 1); the slide/loop pair as the frame type's two
response components used as a design invariant; self-sizing drill depth as
recursive application of the model's own noise floor. [honest negatives
kept]: flat-corpus holonomy null; disarmed lanes; declared sampler
approximation. The instrument's authority structure follows the calculus:
forces enter only through their types; observables are read-only; the one
decision-maker is F.
