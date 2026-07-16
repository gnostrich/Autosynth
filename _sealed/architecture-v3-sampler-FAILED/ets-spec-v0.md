# ETS — Equilibrium Tape Synth — spec v0

Status: v0, pre-build. Name is a placeholder. This document is the SINGLE AUTHORITY
for the build. If code and spec disagree, the code is wrong or the spec must be
formally revised (new version, logged). No third source of truth exists.

Lineage: this is the music-domain instantiation of the EBR program (ebr-spec-v1.md
principles apply wherever not overridden here): gauge-invariant intrinsic-geometry
coupling through self-sizing free-support anchors, one free-energy functional F,
block-coordinate I-projections, meters outside the loss, single-authority discipline.

---

## 0. Object summary

Input: N music tracks (rendered audio only; N arbitrary, appendable).
The system learns a frozen "world" from them: beat-clocked sound-unit clouds,
gauge-quotiented intrinsic geometry, self-sizing role anchors, and F-weights
calibrated so real tracks are equilibria. Then a causal writer (the MZ image of
the equilibrium object) writes an output tape bar-by-bar from the input tracks'
actual sound units, controlled ONLY through six CV lanes and read ONLY through
meter jacks. A thin external planner may drive the lanes to produce closed-loop
pieces. Every emitted sample is provenance-traceable to a source unit.

## 1. Signal typing law (non-negotiable)

Exactly four signal types exist, per modular grammar:
- AUDIO: the writer's output; the source units.
- CLOCK: the beat grid (tatum/beat/bar). Master clock. Derived at ingestion.
- CV: slow controls. Exactly six lanes (Section 8). CV enters the writer through
  ONE jack: the h-transform tilt. No other entry point may exist.
- GATE: phrase end-of-cycle (EOC), section states, comparator outputs.

Any code path that lets control influence the writer other than through the tilt
jack is a REJECT (auditor manifest, invariant I-1).

## 2. Ingestion (per track)

1. Audio in (any sr; resample to 44.1k internal).
2. Beat clock: tempo curve, beats, downbeats, tatum grid (madmom / beat_this
   class tool; pick one, log version). Time coordinate = (metrical position on
   the circle, bar index, metrical level). Wall-clock seconds never appear
   downstream of this step.
3. Channel decomposition, v0 DECISION: fixed filterbank bands (e.g., 8-band
   log-spaced), NOT source separation. Rationale: a separator is a second
   authority pre-deciding roles before F does. Demucs stems are permitted only
   as a tagged ablation arm, never in the main path.
4. Unitization: beat-synchronous slices per band (tatum-level v0), onset-refined
   within grid. Unit mass = perceptual energy/salience.
5. Descriptors (timbre embedding, pitch-class profile, metrical position) are
   used ONLY to build within-track cost matrices. Nothing coordinate-like
   crosses a track boundary (invariant I-2).

Track object schema:
{ units, masses, C_timbre, C_pitchclass (quotiented by transposition),
  C_metrical (circular), beat_grid, provenance_index }

## 3. Gauge structure

Gauge group per track: transposition (pitch-class circle) x beat-phase shift x
loudness scale x timbre-basis normalization. All cross-track communication is
invariant under independent per-track gauge action. Microtiming deviation from
the grid is NOT gauge — it is intrinsic content (groove) and must survive.

## 4. Anchors

Free-support barycenter measures in role space (E_B). All cross-track traffic
factors through anchors; no direct pairwise track coupling in the architecture.
Self-sizing: anchor spawned when unabsorbable residual Hankel mass clears the
calibrated noise floor; balanced-truncation prune below floor. Claim under test
(G1): anchor count tracks the corpus's role diversity (McMillan degree of
traffic), flat in N. No pressure accumulator (removed in EBR v1 audit — do not
reintroduce; invariant I-3).

## 5. F — the single functional

One free energy F over: couplings pi (unit -> role -> metrical slot), channel
gains B, anchor supports/masses, gauge sections. F is posed on the FULL
unit-resolved pi (per §2). The role-occupancy marginal O[k,s] = Σ_units pi is a
MARGINAL and may appear in a term ONLY where that term provably factors through
it; a term that needs the fiber (unit identity/metrical coordinate) must read pi
directly. (Revision r1, dated below: the prior implementation posed F on the
E_B/O aggregate; the scramble family correctly caught the discarded fiber
residue — logged [proven-negative: aggregate-level F].)

- T1 transport cost (intrinsic geometry to anchors; GW-typed) PLUS, per rev-r1,
  a circular phase-displacement charge: the cost of scheduling a unit at a slot
  includes the circular distance between the unit's INTRINSIC metrical coordinate
  (§3: microtiming is intrinsic content, not gauge) and the slot's phase,
  QUOTIENTED by the section gauge phase shift (a global per-section shift is free;
  a per-unit metrical displacement is charged). This is what makes grid-shuffle /
  phase-rotate cost something.
- T2 mass conservation per role per slot (unbalanced-OT marginal penalty).
- T3 spectral masking cost on co-scheduled units.
- T4 continuity: tilted-Markov / Doob h-transform run-continuation term —
  UNIT-successor continuation over pi as originally spec'd (it is inexpressible
  over the O-aggregate; that was half the wall).
- T5 gauge-fixing cost: per-section global transposition/phase choice; never
  per-unit chromatic correction.

Minimization: block-coordinate I-projections (Sinkhorn on pi-blocks,
exponentiated-gradient on B-blocks, unbalanced updates on atom masses).
Batch termination = Lyapunov F-descent certificate. There is no training loss
distinct from F (invariant I-4). Holonomy appears NOWHERE in F (invariant I-5).

## 6. Training (corpus-time)

Condition: each real track is an equilibrium of F; its re-arrangements are not.
Estimator: contrastive/NCE-shaped fit of F-weights where the comparison class is
generated INTERNALLY by disarranging the real track's own units (grid-shuffle,
role-permute, phase-rotate, cross-track-swap). No external "bad music" data
exists anywhere (invariant I-6). The scramble family is an estimator degree of
freedom: it MUST be fixed in PREREG before any training run, with stated
rationale per family member. Per-genre weight variation is allowed as output,
not as a switch (conditioning happens via tilt only).

## 7. Streaming writer (tape mode)

The causal writer is the MZ projection (P = E_B) of the equilibrium object:
receding-horizon settlement. Committed past = clamped cells (frozen boundary
conditions). Frontier window (next bar) settled by the same I-projections;
commit; slide. Never rewrites committed tape. User demands ("this sample at bar
33") enter as clamped future cells — same type as history, no new mechanism
(invariant I-7).

State (the working tape): anchor occupancies, runs in flight, gauge frame,
memory-kernel modes. Self-expands by the Hankel/noise-floor criterion; state
dimension must track McMillan degree of material heard, not elapsed time.
Stability certificate replaces Lyapunov in streaming mode: per-step frontier
F-descent AND bounded state growth on stationary input. State growth on
stationary input = broken instrument, halt and report (invariant I-8).

## 8. Panel — the six CV lanes (complete control interface)

Typed to standard module vocabulary. MIDI CC-mappable (CC learn), MIDI clock
sync in/out. This list is exhaustive; adding a seventh control requires spec
revision.

1. REGION TILT — vector mixer over discovered roles (growable channel strips /
   XY vector pad). Enters as h-transform tilt.
2. DENSITY — trigger-probability / clock-division CV.
3. CONTINUITY <-> RECOMBINATION — Turing-Machine/DEJA-VU-typed knob on T4
   strength.
4. GAUGE STIFFNESS — quantizer strength + slew on the gauge-section lane
   (modulation cost, live).
5. NOVELTY PRESSURE — anti-repeat bias CV.
6. TEMPERATURE — sampling looseness around the settled optimum.

All six are tilt-jack parameters. None may edit F's term weights at run time
(weights are frozen at train time; invariant I-9).

## 9. Meters (output jacks)

- DRIFT CV OUT, one jack per gauge component (key-drift, phase/feel-drift,
  timbre-drift): accumulated holonomy of the running frame. Gauge-invariant by
  construction; computed from couplings the machine already produces.
- PHRASE EOC GATE.
- NOVELTY SATURATION CV.
Meters are read-only instrumentation. A meter appearing in any objective,
gradient, or settlement decision is a REJECT (invariant I-5). Meters MAY be
consumed by the planner and by feedback patching at the CV lanes (that is their
sanctioned consumer).

## 10. Planner (external component — the only new box)

Stateless. Reads: holonomy map of the frozen world (offline survey over
region graph: nodes = flat patches, edges = seams with drift prices), live
meter jacks. Writes: CV lane schedules (scenes + ramps), clocked by phrase
gates. Constraint: loop closure — drift sums to zero at wrap, or to a
deliberately owned residue (logged as such). Implementation: shortest-path /
Dijkstra-with-closure-constraint over the region graph. If the planner needs to
be smart, the map or the writer is broken — report the wall, do not fatten the
planner (invariant I-10).

Modes: (1) lanes constant = stream; (2) human on lanes (MIDI) = instrument;
(3) planner schedule = piece; (3b) feedback patch (EOC -> scene advance,
drift comparator -> return trigger) = self-playing.

## 11. Rendering

Beat-synchronous stretch/shift (rubberband-class), overlap-add scheduling of
real source units. Rendering APPLIES the chosen gauge and schedule; it makes no
choices. Any aesthetic decision in the render path is a second authority =
REJECT (invariant I-11). Every output sample carries provenance
(track, unit, transform applied).

## 12. Desktop architecture (no browser)

Two processes, native desktop:
- ENGINE: Python core (numpy/torch DSP, POT/OT solvers, model, writer),
  real-time audio via sounddevice callback; also offline render mode.
- PANEL: PySide6 (Qt) native app — six lanes, XY pad, meter jacks visualized as
  jacks/LEDs, patch-cable metaphor for feedback routing, MIDI CC learn.
- IPC: OSC over localhost (standard for audio control; keeps panel/engine
  separable and lets hardware MIDI/OSC controllers replace the panel entirely —
  the true "standard interface" property).
No web technology anywhere in the runtime (no Electron, no Tauri, no localhost
web UI). JUCE port is the eventual faithful target; out of scope v0.

## 13. Gate ladder (pre-registered, in order; REGISTRY discipline applies)

- G0: ingestion + beat-clock sanity (grid alignment error bounds; unit
  reconstruction identity: scheduling a track's own units at their own slots
  reproduces the track within stated tolerance).
- G1: anchor double dissociation — anchor count tracks role diversity, flat in
  N. Corpus designed for this (same-genre stack vs cross-genre stack).
- G2: holonomy above calibrated null on real track sets (parametric,
  residual-conditioned null; solver floor measured first; target separation
  standard: G4-class, order 20x).
- G3: pairwise-blindness dissociation — triangle loop defect predicts mash
  failure beyond pairwise (key+tempo) baselines.
- G4: generation mode 1 — 10-minute stream stays natural (no sludge, no
  gray-out, no state growth on stationary input).
- G5: steering tracks tilt trajectories with constraint-lag, naturalness flat.
- G6: composition blind test — planner closed-loop vs arbitrary-steered vs
  free-run, same material; claim (c) > (b) > (a) on "went somewhere and came
  back," no difference on bar-level naturalness. Kill condition for the form
  thesis; instrument survives independently.

Pre-registration: PREREG.md entry (hypothesis, procedure, null, kill condition)
appended and committed BEFORE any gate run. REGISTRY.jsonl append-only,
commit-before-run.

## 14. Invariants (auditor checklist source)

I-1 single tilt jack: no control path into the writer except h-transform tilt.
I-2 gauge law: no coordinates cross a track boundary; only normalized intrinsic
    cost structure.
I-3 no pressure accumulator or any duplicate smoothing mechanism.
I-4 one F: no training loss distinct from F; no eta-KL tether or second
    authority over equilibrium gains.
I-5 meters never in any objective/gradient/settlement decision.
I-6 no external negative data; comparison class derived from good tracks only;
    scramble family fixed in PREREG.
I-7 all interventions (past, human demands) are clamped cells; no exception
    paths, no recovery modes.
I-8 streaming stability certificate; halt-and-report on state growth under
    stationary input.
I-9 run-time controls are tilt parameters only; F term-weights frozen after
    training.
I-10 planner stateless, external, thin; reads meters/map, writes lanes only.
I-11 rendering applies, never chooses.
I-12 provenance: every output sample traceable to (track, unit, transform).
I-13 no browser/web tech in runtime.
I-14 Hankel/holonomy quantities are instruments; event triggers must not fork
     decision authority from F (Hankel demoted to instrument, per EBR audit).

## 15. Open items (user decisions pending)

- Corpus: concrete track set with G1-designed diversity structure. BLOCKING G1.
- MIDI hardware target (if any) for CC map defaults.
- Name.

## 16. Occupancy ledger (positioning, not build-blocking)

[occupied primitives]: OT audio transport (Henderson-Solomon), audio mosaicing /
concatenative synthesis (Schwarz, CataRT), AutoMashUpper/mashability, source
separation, beat tracking, DEQ, NTM/DNC, receding-horizon control, inverse
OT / ME-IRL, contrastive estimation.
[candidate-original — conjunction]: gauge-invariant intrinsic coupling through
self-sizing free-support anchors on beat-clocked unit clouds + drift-CV
instrumentation + closure-planned form. Protect via G1/G2/G3 dissociations,
not via claims.
[conjectured]: musical form = closed loops with budgeted drift (G6 tests it).
[unswept]: structure-from-intrinsic-geometry literature; mid-2026 window.
