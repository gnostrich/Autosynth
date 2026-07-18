# Typed Control Calculus for Gibbs Free-Energy Models
## Part 1 — the pure object

STATUS TAGS: [proven] = follows from stated assumptions with standard machinery.
[occupied] = known result / known field; we use, not claim. [candidate-original]
= believed-new pending occupancy sweep. [conjectured] = stated, unproven.

---

### 0. Purpose

A trained energy-based model is played, not just sampled. This paper asks: what
IS a control on a Gibbs equilibrium — as opposed to a parameter of it — and why
do human interface grammars (faders, vector pads, key-locks, humanize knobs,
transports) map onto such controls without any wiring being specified?

Answer, in one line: **controls are the thermodynamically conjugate pairs of the
free energy; the human grammar is a folk taxonomy of response signatures; and
signature unification has a unique fixed point, so the interface is discovered,
not designed.**

---

### 1. The base object [occupied machinery]

Configuration: a coupling pi on a product space, constrained to a polytope
Pi_t (clamped marginals: committed past, boundary/panel measures), quotiented
by a gauge group G (frame symmetries: transposition, phase, level).

Free energy, entropic-OT / Schrodinger-bridge form:

    F_t(pi; u) = <c, pi> + eps * H(pi) + KL(pi || K ∘ pi*_{t-1}) + V(pi)

- <c,pi>: transport cost on gauge-invariant (stage-3) cost structure
- eps*H: entropy at temperature eps > 0
- KL(.|| K ∘ pi*_{t-1}): succession bridge (Doob-type h-transform to the
  corpus kernel composed with the previous settlement) — this term is what
  makes the equilibrium a *dynamics*
- V: two-body interaction (masking)

Settlement: pi*_t(u) = argmin_{pi in Pi_t} F_t(pi; u).

[proven] For eps > 0, F is strictly convex on Pi_t; pi*(u) is unique and
C^1 in u by the implicit function theorem on the KKT system. All response
theory below is IFT differentiation of that system. (Differentiable entropic
OT: Peyre–Cuturi school [occupied]. Linear response / Kubo / FDT: [occupied].)

Forward/equilibrium prop: the tape is the sequence (pi*_t); each settlement
re-parameterizes the next bar's bridge term. Training solves the inverse
problem — choose (LAMBDA, world) so the corpus's own bars are the minima of
their scramble orbits (NCE-fit); at optimum the flow is self-consistent with
the corpus's build-order. Parameters are then FROZEN.

---

### 2. Controls are not parameters

Naive view: a knob is d(argmin)/d(theta) for any theta appearing in F. This is
wrong in a specific, important way: LAMBDA appears in F, has a derivative, and
is NOT a knob (frozen, exam-gated, no perceptual conjugate). The classification
below characterizes what IS a knob.

**Definition (control).** A control is a one-parameter perturbation of exactly
one datum of the problem (c, eps, Pi, G, output-map), together with the
observable it is conjugate to.

**Theorem C (five-type classification) [candidate-original as a
classification; each individual type occupied].** Every control factors
through one of:

- **T1 (tilt / force):** c -> c - u*phi for an observable phi. Conjugate pair
  (u, Phi := <phi, pi>). Scalar or vector-valued (direction in role space).
- **T2 (thermodynamic):** eps -> eps(u). No direction; sharpens/softens every
  equilibrium simultaneously. Response is energy–observable covariance, a
  categorically different object from T1's.
- **T3 (frame):** action through / pricing of the gauge group G. Its invariant
  response is not point-valued: by the Masani–Schoenberg / Hodge decomposition
  [occupied, a theorem] it splits into a symmetric displacement component
  (SLIDE) and an antisymmetric cycle component (LOOP, holonomy). T3 is the
  unique type whose response can carry a path-dependent residue.
- **T4 (boundary / clamp):** move the polytope Pi (marginal clamps). Binds
  rather than leans; the intervention species of committed past, panel
  measure, and localized field taps.
- **T5 (clock):** post-compose the output map with time rescaling. Commutes
  with argmin: the settled schedule is invariant; only emission timing
  changes. (Operationally: schedule byte-identity under the control.)

Completeness is a classification of the problem's data; the content is the
claim that *user-legible* controls must factor through these five, each with a
distinct empirical fingerprint (Sec. 4).

---

### 3. Response theory

**Theorem A (sensitivity = constrained conjugate fluctuation) [machinery
occupied; identification with the deployed calibration is the applied delta].**
For a T1 pair (u, Phi):

    d<Phi>/du = (1/eps) * Cov_{pi*}(Phi, Phi) |_projected

where the projection is the Schur complement of the KKT Hessian onto the
tangent of the active constraints (clamps + gauge quotient). Consequences:

- The response of a lane equals the equilibrium *fluctuation* of its conjugate
  observable, projected to what the constraints allow. "A knob is exactly as
  sensitive as the material is flexible in that direction."
- **Arming corollary [proven given A]:** if the constrained fluctuation does
  not clear the measurement noise floor, the response is indistinguishable
  from zero and no honest control exists on that lane. Disarm-and-label is the
  degenerate case of the fluctuation–dissipation identity, not a policy choice.
- sigma_phi (the deployed per-lane calibration) is the empirical estimator of
  this object; it must be measured on the sampling (T_s > 0) ensemble, since
  the MAP ensemble's fluctuations degenerate (the observed lambda-runaway
  failure mode is the misestimation of A's denominator).

**Theorem B (co-movement and reciprocity) [machinery occupied; the
sym/antisym system-level split is the delta].** For two T1 lanes:

    d<Phi_A>/du_B = (1/eps) Cov(Phi_A, Phi_B) = d<Phi_B>/du_A   (Maxwell)

So all tilt–tilt cross-talk is SYMMETRIC — an empirical prediction (push A,
watch B == push B, watch A, within estimator noise). The ONLY antisymmetric
response in the system is T3's loop component. Hence the response kernel of
the full instrument decomposes as (symmetric tilt/covariance block) ⊕
(antisymmetric frame/holonomy part): informational content that survives
gauge and symmetrization lives in the second summand (the free-lunch
principle as the structure of one matrix).

**Theorem C' (gap and release) [proven given A].** Present a target u; the
achieved value a(u) = Phi(pi*(u)) differs from the target by an amount
governed to first order by the same kernel (stiff lane = small constrained
covariance = large gap). On release (u -> 0), pi* relaxes along the unforced
equilibrium path; any displayed handle tracking a(u) converges to the
machine's value by *engine* dynamics. Interface corollary: the target/achieved
gap and the release-convergence are emergent objects; any UI easing, damping,
or clamping of them is a falsification of the display.

---

### 4. Fingerprints and the naturality theorem

[ARCHIVED 2026-07-18 — see papers/archive/. Theorem D's naturality claim
(human grammar maps naturally onto the control types) is a HUMAN-CHOSEN
BASIS, superseded by the eigenpanel (the object's own eigenbasis). The
physics — T1-T5 as types, Theorems A/B/C', FDT/arming, the sym-antisym split
— STANDS and remains in this paper.]

(Full original text, incl. the fingerprint table and Theorem D(i)(ii)(iii),
preserved verbatim at
papers/archive/paper1-theorem-D-synth-grammar-ARCHIVED.md.)

---

### 5. Honest ledger

[occupied]: entropic OT / Schrodinger bridges; differentiable OT and IFT
response; linear response / Kubo / FDT; Legendre–conjugate structure of
exponential families; Masani–Schoenberg screw decomposition; Hodge/Helmholtz
splitting; EBM training incl. NCE.

[candidate-original]: (a) the five-type classification AS an interface
theorem; (b) Theorem D — thermodynamic conjugacy as the *interface
principle*, with uniqueness of the signature-matching functor; (c) the
system-level sym⊕antisym response decomposition with T3 as sole holonomy
carrier, used as a design invariant. Each requires an occupancy sweep
(HCI-of-physical-systems, cybernetics, control-of-EBMs literature) before any
novelty claim is submitted.

[conjectured]: the anthropological convergence prediction; non-degeneracy of
the loop component on frustrated corpora (empirically corpus-conditional).

Failure modes this calculus catches by construction: hand-set sensitivities
(A says they must be measured covariances); knobs wired to parameters (D
corollary); UI-shaped resistance (C' corollary); conflated frame meters (T3
says slide/loop are the two components of one response and must not be
summed); asymmetric tilt cross-talk claims (B forbids them).
