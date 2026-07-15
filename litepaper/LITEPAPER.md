# Equilibrium Tape Synth (ETS) — Litepaper

*A frozen world, a causal writer, and one free energy.*

Status: post-v1 documentation. Authorities are `ets-spec-v0.md` (functional §5,
invariants §14, panel §8, render §11), `ets-connector-v0.md` (Layer-0 tilt map),
and `REGISTRY.jsonl` (build history and honest numbers). Where those and this
paper disagree, they win.

---

## Abstract

ETS learns a **frozen "world"** from *N* real music tracks and then lets a
performer **play** a causal writer through **six control lanes**. The world is not
a sample generator: it is a single free-energy functional **F** whose equilibria
are the real tracks, fit by contrastive estimation against the tracks' own
disarrangements. The output is a **settled tape** — a progressively clamped
(N+1)-th boundary node of the same hypergraph as the input tracks, whose every
emitted sample is a real source unit at a real metrical slot, provenance-traceable
to `(track, unit, transform)`. Control never edits the world; it enters as a
single **exponential tilt** on gauge-invariant arrangement statistics — the Doob
conditioning induced by clamping the panel as a boundary measure. The system's
distinctive commitment is not its sound but its **method**: a two-state invariant
manifest (14 of 15 invariants enforced by executable checks), an adversarial
builder/auditor pair, prereg-commit-before-run, and an append-only registry in
which *walls are information and silent divergence is the breach class*. This
paper leads with the architecture, gives the Gibbs energy-based model its due as
the centerpiece, and states plainly what is real versus pending — including a
headline dissociation gate (G2, holonomy above null) that **did not pass** at v0
and is reported as-is rather than retuned.

---

## 1. Architecture overview (read this first)

ETS is a pipeline from real audio to a settled tape. Each stage has a plain-terms
job and a formal object; the whole point of the design is that **exactly one stage
makes value judgments** — the functional F — and every other stage either measures,
transports, applies, or reports.

```
   N real tracks (corpus/*.mp3, N=20)
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ INGESTION  (ets/ingestion)                                    MECHANISM   │
│  • beat clock  (beat_this==1.1.0)  → metrical coordinate; wall-clock      │
│    seconds never survive downstream                                      │
│  • filterbank  8-band log-spaced raised-cosine PARTITION OF UNITY         │
│    (not source separation; columns sum to 1 → perfect reconstruction)    │
│  • unitize     beat-synchronous per-band slices; mass = perceptual energy │
│  Track object: {units, masses, C_timbre, C_pitchclass(quotiented),        │
│                 C_metrical(circular), beat_grid, provenance_index}        │
└─────────────────────────────────────────────────────────────────────────┘
        │  within-track cost structures only — no coordinate crosses a track (I-2)
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ FROZEN WORLD  (ets/functional/anchors.py)                     MECHANISM   │
│  • self-size:  M = round(effective_rank( exp(−GW_roledist/σ) ))           │
│                = participation ratio of the cross-track TRAFFIC operator   │
│                → M = 5 anchors on the v0 corpus (eff_rank 5.354)          │
│  • settle:     free-support GW barycenter (D, a, B, θ) at M via F          │
│  Anchors carry ONLY support+mass — no accumulator/pressure (I-3)          │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ F  +  SETTLEMENT   (ets/functional/{f,solver,ot}.py)      THE  EBM        │
│  F = T1 transport(GW)+phase-charge  +  T2 mass  +  T3 masking             │
│      +  T4 unit-successor continuity  +  T5 gauge-fix                     │
│  Gibbs measure  p ∝ exp(−F/T_s + Σ λ_i φ_i)                               │
│  Solver: block-coordinate I-projections, Lyapunov F-descent certificate  │
│  Weights LAMBDA fit ONCE by contrastive NCE (ets/training) — then FROZEN  │
└─────────────────────────────────────────────────────────────────────────┘
        │  frozen weights; the world never moves again
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ WRITER / TAPE   (ets/writer/{settle,realize,stream,tilt,phi}.py)          │
│  The tape = (N+1)-th track-typed BOUNDARY NODE, coupled through the same  │
│  anchor star. Writing = the settlement clamping its own frontier cells in │
│  causal order (receding horizon). Committed past = clamped cells.         │
│  CLAMPS (past history, user demands, knob leans) = the ONE intervention   │
│  species (generalized I-7). Control enters ONLY via the Layer-0 tilt.     │
└─────────────────────────────────────────────────────────────────────────┘
        │  Schedule: unit→slot placements, each carrying its settled mass
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ RENDER   (ets/render/*)                                       MECHANISM   │
│  Beat-synchronous stretch/shift + overlap-add of REAL source units.       │
│  APPLIES the chosen gauge and schedule; makes no choices (I-11, AST-      │
│  checked: no argmax/sort/sample/choice in the render path).               │
│  Coupling IS the provenance record → every sample traces to (track,       │
│  unit, transform) (I-12).                                                 │
└─────────────────────────────────────────────────────────────────────────┘
        │  pure, deterministic tape (byte-identical for a fixed determinism tuple)
        ▼
   [ optional EXTERNAL output master — compressor → EBU R128 → limiter ]
   opt-in, downstream, never touches the object (registry: output-master-external)
```

Two orthogonal control paths, and only two:

- **CV lanes** enter the writer through a **single jack** — the h-transform tilt
  (I-1). Six lanes, exhaustive (§8).
- **Clamps** (committed tape, `this unit at bar 33`, knob leans as clamped
  role-space mass) are all the *same* boundary-condition species (I-7, generalized
  by the connector). There is no third intervention mechanism.

The desktop runtime is **two processes** (spec §12): an **ENGINE** (Python core,
streaming writer, audio) and a **PANEL** (PySide6/Qt), communicating over **OSC on
localhost**. Killing the panel never touches the engine; any OSC/MIDI hardware can
replace the panel entirely.

---

## 2. Ingestion, gauge, and the frozen world

**Ingestion.** Audio is resampled to 44.1 kHz, beat-tracked (`beat_this==1.1.0`,
DBN off) to a tatum/beat/bar grid, and decomposed by a **fixed 8-band log-spaced
filterbank** — deliberately *not* a source separator, because "a separator is a
second authority pre-deciding roles before F does" (spec §2.3). The masks are a
raised-cosine **partition of unity** (`ets/ingestion/filterbank.py`, `N_FFT=2048`,
`HOP=512`, `FMIN=40 Hz`): the per-band ISTFTs sum back to the input to numerical
precision, which is exactly what makes the G0 reconstruction identity a
coverage/scheduling test rather than a lossy-model test. Beat-synchronous per-band
slices become **units**; unit mass is perceptual energy.

**Gauge (spec §3).** Per track, the gauge group is transposition × beat-phase
shift × loudness scale × timbre-basis normalization. All cross-track communication
is invariant under independent per-track gauge action; **no coordinate ever
crosses a track boundary** (I-2, enforced: descriptor arrays are private, the only
sanctioned combiner refuses a cross-track pair, pitch-class cost is
transposition-quotiented, metrical cost is circular). Microtiming deviation from
the grid is **not** gauge — it is intrinsic groove content and must survive; this
is precisely what T1's phase-displacement charge later prices.

**The frozen world (self-sizing anchors, spec §4).** All cross-track traffic
factors through **free-support barycenter anchors** in role space; there is no
direct pairwise track coupling. The anchor count is not a hyperparameter — it is
**derived** as the balanced-truncation effective rank (participation ratio
`(Σw)²/Σw²`) of the cross-track GW role-affinity operator `exp(−D_role/σ)`
(`ets/functional/anchors.py:effective_rank`). On the v0 world this is
**M = 5 anchors** (`effective_rank ≈ 5.354`, `σ ≈ 0.553`;
`ets/calibration/sigma_phi.json`). The supports `(D, a, B, θ)` are then settled as
the GW barycenter at that count. Anchors hold **only** support and mass — no
accumulator, EMA, or momentum field (I-3, structurally scanned).

*Honest note on the sizing derivation:* the effective-rank reading is a
**re-derivation after a wall**. The first sizing rule (a GW transport-residual
growth criterion) provably failed — it did not dissociate role-diverse from
same-role corpora and grew with N — and was rejected. The current rule is the
spec's own "McMillan degree of *traffic* / Hankel mass / balanced-truncation"
language read as a spectral rank (`RETRO_AUDIT.md`, anchors row). This is a case
of the discipline working: the wall was reported and the object re-posed, not
patched.

---

## 3. The Gibbs energy-based model (centerpiece)

The heart of ETS is a **single free-energy functional F** (invariant I-4: there is
no training loss distinct from F). Correctly framed, ETS is an **energy-based
model**: the energy is F, the sampling looseness is a **temperature** `T_s`, and
control is an **exponential tilt** in a set of sufficient statistics φ. Real music
tracks are the low-energy equilibria; their rearrangements are not.

### 3.1 F over the unit-resolved coupling

F ranges over couplings **π** (unit → role → metrical slot), channel gains **B**,
anchor supports/masses `(D, a)`, and gauge sections `g`. Crucially, **F is posed on
the FULL unit-resolved π**, not on its role-occupancy marginal
`O[k,s] = Σ_units π`. A term may use the marginal *only where it provably factors
through it*; a term that needs the fiber (which real unit sits where) must read π
directly. The five terms (`ets/functional/f.py`, rev-r1):

| Term | Meaning | Posed on | Reads |
|---|---|---|---|
| **T1** | GW-typed intrinsic-geometry transport to anchors **plus** a circular metrical **phase-displacement charge** | full-π | GW factors through prototypes; the phase charge reads π's unit fiber |
| **T2** | mass conservation (unbalanced-OT generalized-KL of `O` vs `a·θ`) | marginal `O` | with a *written* factorization proof |
| **T3** | spectral masking (quadratic collision `Σ E²−self`, `E=OᵀB`) | marginal `O` | with a *written* factorization proof |
| **T4** | unit-successor run-continuation (Doob h-transform continuity reward) | full-π | π's fiber — inexpressible over `O` |
| **T5** | per-**section** gauge-fixing (global transpose/phase), never per-unit | gauge | neither π nor `O` |

The **phase-displacement charge** is the term that makes groove cost something.
For each placed unit it charges the circular distance between the unit's
**intrinsic** metrical coordinate and the phase of the slot it occupies,
**quotiented by a single per-section global phase shift** δ (a global beat-phase
shift is free gauge; a per-unit displacement is charged). The δ-quotient is solved
in closed form — minimizing `Σ mᵤ(1−cos2π(xᵤ−δ))` over δ gives
`1 − |Σ mᵤ e^{i2πxᵤ}|` (masses normalized). It is exactly zero when every unit
sits at its own intrinsic slot up to one global shift (a real track's groove) and
strictly positive for incoherent metrical displacement. **T4** rewards
output-adjacent slots that hold genuine *source* successors — a grid-shuffle
re-deals content so almost no adjacency survives; a cross-track graft inserts units
that are no track's successor, so the run breaks.

Both fiber terms are **gauge-invariant by construction** (they read only
within-track content adjacency and transposition-quotiented metrical phase, I-2).
Holonomy, drift, novelty, and any meter appear **nowhere** in F (I-5, I-14,
enforced by an AST scan that bites on a `holonomy_drift` identifier and on any
`ets.meters` import in the F path).

### 3.2 The Gibbs measure and the Layer-0 tilt

The equilibrium/Gibbs measure over an arrangement `a`, with control applied, is

```
p(a) ∝ exp( −F(a)/T_s  +  Σ_i λ_i · φ_i(a) )                    (connector Layer 0)
```

- `T_s` is the **temperature** — sampling looseness around the settled optimum; it
  scales settlement sharpness and carries no φ.
- `φ_i` are five **gauge-invariant arrangement statistics** (region occupancy,
  density, continuity, gauge-move magnitude, novelty), computable from the
  candidate arrangement alone (`ets/connector/phi.py`).
- The tilt is not a bolt-on mechanism: it is the **Doob conditioning** the
  settlement inherits when the panel's boundary measure is clamped. Two of the five
  φ (region, density) are linear in `O` and enter the O-block; continuity and
  novelty live on the fiber block; gauge on the (v0-frozen) gauge block.

This is what "control never edits the world" means concretely: the run-time knobs
move `λ` and `T_s`, never F's term weights (I-9).

### 3.3 Contrastive (NCE) training — and the honest KILL

The weights `LAMBDA` are **fit once, at corpus time**, by a convex logistic NCE
(spec §6, `ets/training/nce.py`). The condition is *each real track is an
equilibrium of F; its rearrangements are not*. There is **no external "bad music"
data anywhere** (I-6): the comparison class is generated **internally** by
disarranging each real track's own units, drawn only from a **fixed,
pre-registered scramble family**:

| Scramble | What it breaks | Arity |
|---|---|---|
| **grid-shuffle** | metrical placement (re-deals real units to different slots within a band) | Track→Track |
| **phase-rotate** | the single gauge-phase frame (incoherent *per-band* rotation; a global one is pure gauge) | Track→Track |
| **role-permute** | role assignment (derange the anchor columns of the pure-GW coupling) | (Track, world)→Arrangement |
| **cross-track-swap** | anchor-mediated cross-track coherence (swap anchor rows; only gauge-invariant role mass crosses) | (Track², world)→Arrangement |

Because F is linear in the weights and φ is computed at the frozen LAMBDA-free
world, the NCE objective is **convex** with an exact gradient — no circularity. The
fit uses seeds {1,2,3}; held-out validity is measured on **disjoint** seeds {4,5}
(so no fit metric is a gate metric, I-5).

**The KILL, then rev-r1 (the load-bearing part of the story).** The *first* F was
posed on the occupancy **marginal** `O`. It **failed**: on the marginal, F could
not separate real tracks from grid-shuffle — held-out separation ≈ 0.35, a
**negative margin** — because the marginal is blind to *which* unit sits at *which*
slot (`f.py` comments; registry `train-nce-2026-07-13` KILL). This was ruled a
**fidelity breach**: a silent aggregate projection of π, an *unfaithful*
implementation plus a missing invariant (registry `fidelity-breach-2026-07-13`).
Per the wall protocol it was **reported, not patched**: no LAMBDA was emitted, the
referee was left incorruptible, and the functional was **re-posed on the full
unit-resolved fiber** (rev-r1). A new invariant, **I-15** (no premature
aggregation / structure-deleting projection), was added to forbid the class going
forward.

The re-posed F (fork C: richer fiber + gauge-aligned groove target) **passed**
(`training_results.json`, registry `train-nce-revr1-2026-07-13`):

| Family member | held-out separation | median margin |
|---|---|---|
| grid-shuffle | **1.00** | 18.79 |
| role-permute | **0.95** | 1.07 |
| phase-rotate | **1.00** | 6.02 |
| cross-track-swap | **0.975** | 7.33 |
| **overall min** | **0.95** ≥ 0.90 (pre-registered) | — |

(logistic loss 0.0908, grad-norm 0.0024, 240 pairs.) The emitted weights, now
**frozen** and read live by the writer (I-9):

```
LAMBDA = { T2: 4.9923,  T3: 0.8023,  T4: 10.4577,  T1p: 8.7581,  T5: 0.1 }
         with T1's GW transport as the reference scale (weight 1).
```

(`ets/functional/f.py`. `T5 = 0.1` is a run-time gauge baseline, **not**
corpus-identifiable — a global section-gauge move is orthogonal to every
rearrangement, so it carries no contrastive signal.) An independent audit re-ran
the fit and reproduced LAMBDA bit-exactly to 16 digits.

### 3.4 Settlement as certified I-projections

Minimization is **block-coordinate I-projections** (`ets/functional/solver.py`):
Sinkhorn on π-blocks, exponentiated-gradient (mirror descent) on B-blocks,
unbalanced multiplicative updates on masses, closed-form GW-barycenter on `D`,
exact minimization on the gauge block. The certificate is a **Lyapunov F-descent
guard**: every block step is accepted *only* if F does not increase, so the
F-trajectory is monotone non-increasing and the run stops at `|ΔF| < tol`. The
accept/reject decision reads **F and nothing else** — no second objective, no meter
(I-4/I-14, verified structurally by parsing `batch_solve` and confirming the guard
compares `F_cand`/`F_cur`). In streaming mode the batch Lyapunov certificate is
replaced by a per-step frontier F-descent plus a **bounded-state** certificate:
state growth on stationary input is a broken instrument — **halt and report**
(I-8).

---

## 4. The control surface

Six CV lanes, exhaustive (spec §8); adding a seventh requires a spec revision.

| # | Lane | φ statistic (`ets/connector/phi.py`) | v0 status |
|---|---|---|---|
| 1 | **REGION TILT** (XY pad / channel strips over discovered roles) | `φ_region` — M-vector of scheduled mass by anchor role | armed (σ per anchor) |
| 2 | **DENSITY** | `φ_density` — bar scheduled mass (region marginal) | **disarmed** (σ=0 at u=0) |
| 3 | **CONTINUITY ↔ RECOMBINATION** | `φ_continuity` — source-successor continuation count | armed (σ ≈ 0.301) |
| 4 | **GAUGE STIFFNESS** | `φ_gauge` — frame-move group-metric magnitude | **disarmed** (σ=0, frozen frame) |
| 5 | **NOVELTY PRESSURE** | `φ_novelty` — 1/Δ-recency-weighted unit reuse | armed (σ ≈ 0.330) |
| 6 | **TEMPERATURE** | *(no φ)* — settlement sharpness | armed |

**The knob-scaling law is derived, not hand-set.** Each lane's scale is
`λ_i = u_i / σ_{φ_i}`, where `σ_{φ_i}` is the **equilibrium fluctuation** of φ_i
under the *untilted* writer, measured by a registered calibration pass at
world-freeze (`ets/calibration/sigma_phi.json`, instrument
`sigma-phi-untilted-2026-07-15`). The derivation is fluctuation-dissipation:
`p_u ≈ p_0 exp(λφ)` ⇒ `d⟨φ⟩/dλ|_0 = Var_0(φ)`, so `λ = u/σ` makes `d⟨φ⟩/du|_0 = σ`
— **one knob unit = one equilibrium-σ lean**. σ is the *unique* normalizer with
this property and makes the tilt invariant to any rescaling of φ. No hand-set λ
scale exists anywhere in the runtime (`ets/writer/tilt.py` contains no numeric
scale beyond the map's own mathematics). The calibration ensemble was **7495 bars**
(the corpus bar count — the evidence scale, not a hand constant), `s_phase = 8`.

**Two lanes are honestly disarmed at v0.** The untilted writer settles by a
deterministic MAP descent on a bar-periodic anchor field, so `φ_density` (an
O-marginal) is *pinned* to a constant (σ = 0 exactly), and the single identity-gauge
section makes `φ_gauge ≡ 0`. Rather than invent a floor, the loader marks these
lanes `identifiable=false`: **u still transmits, but no tilt is applied, and the
engine surfaces the disarmed state** (`WorldNotCalibrated` on a lean into an
uncalibrated world; `tilt.py` distinguishes an *identifiable* σ=0 — a proven
constant, exact identity tilt — from an *unidentifiable* lane). This is a theorem
about degenerate exponential families reported as a wall, not an error-hiding
branch.

**Two processes over OSC (spec §12).** The **ENGINE** (`ets/engine`) owns the
frozen world, the streaming writer, and audio (`sounddevice`, lazy; headless-
graceful). The **PANEL** (`ets/panel`, PySide6/Qt) is a pure control surface: six
lanes, XY vector pad, meter jacks as LEDs, patch-cable feedback metaphor, MIDI CC
learn. IPC is **OSC over localhost** (`python-osc`) — no web technology anywhere in
the runtime (I-13, enforced by an AST import scan that even distinguishes the
runtime's own `ets.panel` from the forbidden HoloViz `panel`). Control latency is a
**declared** `L` bars measured by buffer math on the host (desktop profile: `L = 2`
bars, `T_prod` mean 0.568 s < `T_bar` 1.486 s; `latency_desktop.json`); an underrun
inside `L·T_bar` is a **WALL** (halt and report) — there is no degraded-quality
fallback.

**Meter jacks (output instrumentation).** Read-only, and never in any
objective/gradient/settlement (I-5). The conflated DRIFT jack was **split** into
two shadow meters: `slide[g]` (per-bar displacement-from-home of the settled gauge
frame, in F's own quotient) and `loop[g]` (a per-committed-bar transplant of the
G2 loop-defect integrator on the settled tape coupling). At v0 both read honest
zeros on the identity-gauge tape (the frame never moves), with non-vacuity
established on curved fixtures — and the old conflated jack was **deleted outright**
after a registered one-shot regression showed it is exactly informationless on
every producible trace (residual 0.0 at machine precision, registry
`conflation-regression-stage1-2026-07-15`).

---

## 5. The faithfulness discipline (the project's identity)

ETS treats faithfulness as an engineering surface with teeth, not a virtue.

**Two-state invariant manifest (`tests/invariants/manifest.py`).** Every invariant
I-1..I-15 is registered with exactly one of two statuses — **ENFORCED** (an
executable check that raises on violation) or **PENDING** (the guarded feature does
not exist yet). There is **no third state**: PENDING never means "we chose not to
check," and no invariant may be absent or satisfied vacuously. When a feature
lands, its invariant must move to ENFORCED *in the same change* or the auditor
rejects the diff. Current state: **14 of 15 enforced**; only **I-10 (thin planner)
is PENDING**, because the planner is not built. The checks are aggressively
**non-vacuous** — each proves it *bites* against a planted mutant (a choosing
render, an accumulator field, an η·KL tether, a web import, an EOC-forked
settlement guard).

The 15 invariants, briefly:

| | Invariant | Enforced |
|---|---|---|
| I-1 | single tilt jack — no control path but the h-transform tilt | ✓ |
| I-2 | gauge law — no coordinate crosses a track boundary | ✓ |
| I-3 | no pressure accumulator / duplicate smoothing | ✓ |
| I-4 | one F — no training loss distinct from F | ✓ |
| I-5 | meters never in objective/gradient/settlement | ✓ |
| I-6 | no external negatives; scramble family fixed in PREREG | ✓ |
| I-7 | all interventions are clamped cells; no recovery modes | ✓ |
| I-8 | streaming stability; halt on state growth under stationary input | ✓ |
| I-9 | run-time controls are tilt parameters only; F weights frozen | ✓ |
| **I-10** | **planner stateless, external, thin** | **PENDING** (no planner) |
| I-11 | rendering applies, never chooses | ✓ |
| I-12 | provenance — every sample traces to (track, unit, transform) | ✓ |
| I-13 | no browser/web tech in the runtime | ✓ |
| I-14 | Hankel/holonomy are instruments; no fork of F's authority | ✓ |
| I-15 | no premature aggregation / structure-deleting projection | ✓ |

**Builder/auditor adversarial pair.** Implementation is done by an `ets-builder`
agent and must be paired with a read-only `ets-auditor`; no gate runs and no merge
happens without an auditor PASS. The auditor reports verdicts and never fixes code.

**Prereg-commit-before-run, append-only registry.** Every gate's hypothesis,
procedure, null, and kill condition is appended to `PREREG.md` and committed
**before** the run; `REGISTRY.jsonl` is append-only, commit-before-run. Corrections
are new entries, never edits ("the original entry is not edited").

**The operating slogan:** *walls are information, patches are sabotage, silent
divergence is the breach class.* A wall (a gate that fails, a scale that is
non-identifiable, a deadline that cannot be met) is surfaced and owned; the failure
mode the discipline exists to catch is a *silent* divergence between what the spec
defines and what the code does.

### Case study — the fidelity breach (the discipline working)

The single most instructive event in the build is a **fidelity breach that was
caught before delivery** (registry `fidelity-breach-2026-07-13`). An early
implementation silently collapsed the unit-resolved coupling π to its role
occupancy marginal `O` — a structure-deleting conversion shim. The spec defines π
as unit-resolved (§2/§5); the implementation aggregated without presenting the
divergence. It was caught not by luck but by the **pre-registered exam**: the fixed
scramble family correctly refused to separate (grid-shuffle held-out ≈ 0.35,
negative margin), the KILL condition fired, and — critically — **no LAMBDA was
emitted and the wall was surfaced pre-delivery**. Remediation: (1) F re-posed on
the full fiber; (2) a new invariant **I-15** with two teeth — a term-input contract
in `f.py` behaviorally verified against an O-preserving π rearrangement, and a
referee-non-degeneracy check that the scored corpus-time feature *must* consume a
unit-resolved fiber. The incident is logged `logged-permanent-no-relitigation`.
This makes the paper *stronger*, not weaker: the mechanism that was supposed to
catch an unfaithful implementation did catch it, and left a durable guard behind.

---

## 6. Honest limitations — what is real vs pending

The project's identity forbids overselling. The status table below is the honest
state as of v1.

| Item | Status | Note |
|---|---|---|
| Ingestion → world → F → writer → render pipeline | **REAL** | end-to-end; deterministic pure render (H-8 receipt) |
| Anchor self-sizing (effective rank of traffic) | **REAL** | M=5 on v0 corpus; G1 passed |
| Contrastive NCE fit of LAMBDA (rev-r1) | **REAL** | overall min held-out sep 0.95 ≥ 0.90; audit-reproduced bit-exactly |
| 14/15 invariants enforced | **REAL** | only I-10 pending |
| Two-process engine+panel over OSC, MIDI CC learn | **REAL** | headless-graceful; L=2 bars declared |
| **G0** ingestion/reconstruction | **PASS** | recon rel-L2 ≈ 1.16e−8 |
| **G1** anchor double dissociation | **PASS** | diversity eff-rank gap 2.04; SAME 2.38 < NULL 3.30 < DIVERSE 4.43; flat-in-N under gauge copies |
| **G2** holonomy above calibrated null | **DID NOT PASS** | see below — reported as-is, no retune |
| REGION / CONTINUITY / NOVELTY / TEMPERATURE lanes | **ARMED** | derived σ_φ scales |
| **DENSITY / GAUGE lanes** | **DISARMED** | σ_φ = 0 at u=0 (density pinned by MAP settlement; gauge frame frozen). λ undefined, no tilt, surfaced |
| Greedy fiber realization | **DECLARED APPROX** | run-continuation is greedy/uncertified vs a joint fiber settlement; audit PASS-legal with declaration |
| Streaming temperature sampler | **DECLARED APPROX** | per-slot Laplace 2nd-order truncation + positive-orthant clip (~0.11 std bias, ~13% clip at T_s=1 on CI world); `T_s→0` does not reproduce batch bit-exactly |
| `mass = √e[b]` settled-mass render | **DECLARED APPROX** | exact on the schedule; adjacent-band crossover energy leakage (~+0.15–0.20 worst case) from the overlapping filterbank masks |
| **I-10 planner** | **PENDING / NOT BUILT** | the closed-loop form thesis (G3–G6) is untested |
| Mono | **DECLARED v0** | ingestion is mono; stereo restoration is real future scope, not a patch |
| External output master | **OUTSIDE the object** | opt-in compressor→R128→limiter; never touches synth/world/F/tape; pure render byte-identical by default |
| u=0 dynamic-range / near-silence | **OPEN quality finding** | streaming per-bar mass varies widely; global peak-normalize crushes low-drive passages. No extrinsic AGC applied (would be the structure-deleting class); flagged for a possible settled loudness gauge |

### G2 in detail (the headline that did not land)

G2 tests whether the frozen world carries **holonomy (loop-defect curvature) above
a residual-conditioned null** — the dissociation that would support the conjecture
that musical structure is real geometric curvature, at a demanding 20× separation
target. It **failed** (`g2_results.json`): real median curvature came in *below*
the null (`κ_real/κ_null ≈ 0.45`), dominance-over-null-p95/p99 both false,
`signal_present_above_null = false`. Real curvature *did* clear the solver floor
(`κ_real/κ_floor ≈ 2.0`), but not the residual-conditioned null. Per the
pre-registered kill condition this is **reported as-is, with no null-swap and no
retune**. Two consequences stated plainly: (i) the strong "curvature = structure"
claim is **unsupported at v0**; (ii) the instrument (the loop-defect integrator)
survives as a read-only meter (`loop[g]`) regardless. The pairwise-blindness and
closed-loop *form* theses (G3–G6) depend on the planner, which is **not built**
(I-10 pending), so they remain untested.

---

## 7. What ETS is, in one paragraph

ETS is an instrument whose "world" is a single Gibbs free energy fit so that real
tracks are its equilibria, played by a causal writer that clamps its own frontier
in real time and steered by an exact exponential tilt on gauge-invariant
statistics whose knob scales are derived from equilibrium fluctuations. Its output
is a settled tape of real source units, provenance-complete, not a synthesized
sample. Its distinctive contribution is a **method**: one authority (F), two-state
invariants with executable non-vacuous checks, an adversarial auditor, and an
append-only registry where a caught fidelity breach and a failed headline gate are
recorded as first-class results. The honest ledger — 14/15 invariants enforced, two
lanes disarmed, one greedy realization, a failed G2, a pending planner — is not an
apology; it is the artifact.

---

*All figures above are from the committed sources listed in `README.md`. Where a
result is a declared approximation or an unpassed gate, this paper reports it
rather than rounding it up.*
</content>
