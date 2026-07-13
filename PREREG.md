# PREREG — pre-registration ledger for ETS gates

Discipline (spec §13, builder rule 4, auditor §4):

- No gate G0–G6 may run before its pre-registration entry below is COMMITTED.
- Each entry states: hypothesis, procedure, null construction, kill condition.
- The null must be calibrated (solver floor measured first).
- No metric named in a prereg may also appear in any objective/loss (I-5).
- `REGISTRY.jsonl` is append-only and committed before each run; a run that
  invalidates an instrument is fixed by a NEW pre-registered entry, never by
  editing an old one.

Entry template (copy per gate, fill, commit before running):

## G<k> — <name>  (status: DRAFT | REGISTERED | RUN)
- prereg_commit: <sha, filled at registration>
- hypothesis:
- procedure:
- null construction (and solver-floor calibration):
- kill condition:
- registry_ids: [<REGISTRY.jsonl ids appended for this gate>]

---

## G0 — ingestion + beat-clock sanity + reconstruction identity  (status: REGISTERED)
- prereg_commit: this commit (registers the entry); code_under_test: 78cf26f
- registry_ids: [g0-ingestion-2026-07-13]
- corpus: corpus/*.mp3, 20 tracks, 44.1 kHz internal.
- tool logged: beat_this==1.1.0 / checkpoint final0 / dbn=False.

- hypothesis:
  (i)  Each corpus track carries a measurable, regular pulse, and the derived
       beat grid sits on the audio's real events (grid→onset aligned).
  (ii) The fixed-filterbank unitization is an IDENTITY representation: scheduling
       a track's own units at their own tatum slots (identity transform,
       rectangular overlap-add) reproduces the track over the grid-covered span
       within tolerance. (Because the filterbank is partition-of-unity /
       perfect-reconstruction, this half certifies COVERAGE + SCHEDULING
       completeness — an off-by-one, uncovered lead-in/out, or mis-placed slot
       would break it. Stated openly, not as a hidden strength.)
       [CORRECTION 2026-07-13 — the parenthetical above is RETRACTED; the phrase
       "an off-by-one ... or mis-placed slot would break it" is FALSE. See
       "G0 CORRECTION NOTE" at the end of this entry for the true, verified
       characterization. registry: g0-correction-2026-07-13.]

- procedure:
  Per track: load→44.1k mono; beat_this→beats,downbeats; build tatum grid
  (2 tatums/beat) + onset-refined boundaries; STFT partition-of-unity 8-band
  filterbank; per-(slot,band) unit with mass + descriptors.
  (i)  pulse_present := n_beats ≥ 32 AND fraction of IBIs within [0.5,2.0]×median
       ≥ 0.80 (breakdown gaps tolerated). align := median beat→nearest-onset
       distance over beats with an onset within 100 ms search window.
       Report modal beats-per-bar (info).
  (ii) recon := relative L2 of (own-unit overlap-add) vs source over the
       grid-covered span [first tatum, last tatum].
  Domain note: wall-clock outside [first tatum, last tatum] is not part of the
  metrical object; covered_fraction reported per track.

- pass tolerances (pre-stated, fixed; NOT used in any objective — I-5):
  - MIN_BEATS = 32
  - regular-IBI fraction ≥ 0.80
  - median grid→onset alignment ≤ 50 ms
  - reconstruction relative L2 ≤ 1e-3  (−60 dB)
  A track PASSES G0 iff pulse_present ∧ (median_align ≤ 50 ms) ∧ (recon ≤ 1e-3).

- null construction (and solver-floor calibration):
  Reconstruction floor measured first on synthetic audio (band-sum round-trip):
  observed ≈ 1e-8 (−157 dB) ≫ below the 1e-3 tolerance, so the tolerance is not
  floor-limited — it is a coverage/scheduling budget with ~5 orders of margin.
  Beat-clock null: a shuffled/rotated grid (beats replaced by uniform-random
  times at the same rate) would give median align ≈ (tatum/2) ~ 90–180 ms and
  regular-IBI fraction near the [0.5,2.0] band's chance mass; passing tracks must
  beat that by construction (median align target ≤ 50 ms). No trained metric
  here, so no learned-solver floor applies.

- kill condition (WALL PROTOCOL, spec §2):
  - If a track has pulse_present == False → it has NO measurable pulse: STOP,
    record as a wall, do NOT special-case or patch the clock.
  - If any track's recon > 1e-3 with correct coverage → filterbank/unitization
    cannot meet the identity: STOP, re-derive; do not loosen the tolerance.
  Either outcome is reported to the human as a candidate spec revision, never
  silently worked around.

### G0 CORRECTION NOTE  (appended 2026-07-13; registry g0-correction-2026-07-13)

Append-only correction. The G0 RUN and its RESULT stand unchanged (20/20 PASS,
worst recon_rel_l2 = 1.3e-8, worst align 41.6 ms; g0_results.json). What is
corrected here is a FALSE CHARACTERIZATION in the (ii) parenthetical above — not
any measured value. Retracted claim: "an off-by-one or mis-placed slot would
break it." That is false, verified empirically.

What G0(ii) `g0.reconstruction_identity` ACTUALLY certifies:
  1. Filterbank perfect-reconstruction (partition of unity): sum_k band_k(y)==y.
  2. The shipped grid is a VALID MONOTONE TILING of [first tatum, last tatum]
     — no overlap, no double-count. A broken (non-monotone) tiling DOES bite:
     verified recon_rel_l2 ~ 0.6, recon_ok=False on a scrambled non-monotone
     grid. (A pure interior HOLE is structurally impossible under forward-fill of
     consecutive boundary pairs, so this half guards tiling INTEGRITY, i.e.
     monotonicity / non-overlap.)
  3. covered_fraction = fraction of wall-clock spanned by the metrical grid
     (reported per track; this is where lead-in/lead-out shortfall shows up).

What G0(ii) does NOT do: it does NOT discriminate interior slot PLACEMENT. Any
monotone re-placement of the interior boundaries — even fully random positions
within [first tatum, last tatum] — yields BIT-IDENTICAL reconstruction error
(verified: true grid and random-monotone grid both give rel_l2 = 1.1645557e-8 to
the last digit). The overlap-add sum depends ONLY on the two endpoints and the
filterbank PR; it never reads `units`, provenance, or interior boundary
positions. Therefore an off-by-one that keeps a monotone tiling does NOT break
(ii).

Where interior-placement discrimination actually lives: G0(i) grid->onset
ALIGNMENT (median align <= 50 ms). That half is what certifies the slots sit on
the audio's real events; (ii) certifies filterbank PR + tiling integrity + span.
The two halves are complementary and neither is redundant.

---

## G1 — anchor double dissociation: count tracks role diversity, flat in N  (status: RUN)
- RESULT (g1_results.json, code a8bd1ae): G1 PASS. eff_rank SAME_6=2.38 <
  NULL=3.30 < DIVERSE_6=4.43 (H1 margin 2.04 >= 1.0); gauge-copy eff_rank flat
  1.02->1.036 over N=2..8 (< 1.2; role_dist_max 0.011 -> gauge-invariant);
  slope SAME 0.28 < DIVERSE 0.61 (H2-real). Barycenter settle F-monotone (SAME
  M*=2, DIVERSE M*=4). Arms (algorithmic output): SAME=[2,6,1,4,15,8],
  DIVERSE=[0,2,7,18,12,14]; sigma_frozen=0.553.
- prereg_commit: this commit (registers the entry); code_under_test: a8bd1ae
- registry_ids: [g1-anchors-2026-07-13]
- corpus: cache/ingest/track_00..19 (the 20 G0-passing tracks). Instruments are
  instrumentation only; none appears in F (I-5) — verified: F uses no
  role-distance / effective-rank / anchor-count symbol.

- claim under test (spec §4, §13-G1): the SELF-SIZED anchor count tracks the
  corpus's role diversity (McMillan degree of the cross-track traffic), FLAT IN N.

- instrument (self-sizing, spec §4 "residual Hankel mass / balanced-truncation"):
  anchor count := effective_rank(A), A[s,t] = exp(-GW_role_dist(s,t)/sigma), the
  participation ratio (sum w)^2/sum w^2 of the traffic operator's spectrum — a
  balanced-truncation effective mode count (below-floor modes contribute ~0).
  GW_role_dist is entropic Gromov-Wasserstein between two tracks' role-prototype
  spaces (internal costs only; no coordinate crosses a boundary, I-2). sigma is a
  FROZEN corpus-level scale = median off-diagonal role-distance over ALL 20 tracks,
  calibrated ONCE and applied to every arm (never recomputed per arm). The
  F/solver then settles the free-support barycenter supports at M*=round(eff_rank)
  and its Lyapunov F-descent is recorded (settlement, not the readout).
  NOTE: a transport-RESIDUAL self-sizing (GW-barycenter T1 reduction vs a noise
  floor) was built first and REJECTED — it does not dissociate diverse vs
  same-role corpora and grows with N (verified; see build report). The Hankel /
  balanced-truncation reading above is the spec's actual language and is used.

- arm construction (ALGORITHMIC, pre-committed; members are the deterministic
  output of these rules, computed at run time):
  1. Compute the 20x20 GW role-distance matrix D and sigma = median(offdiag(D)).
  2. SAME-role arm (low diversity): greedy tightest cluster — seed = the closest
     pair argmin D; iteratively add the track minimising mean role-distance to the
     current cluster. Ordered; prefixes give N = 2,3,4,6.
  3. DIVERSE arm (high diversity): greedy farthest-point sampling — seed = the
     pair argmax D; iteratively add the track maximising its MIN role-distance to
     the current set. Ordered; prefixes give N = 2,3,4,6.
  4. GAUGE-COPY arm (strict flat-in-N + gauge-invariance control): N gauge actions
     (transposition, metrical-phase roll, loudness scale) applied to a fixed
     reference track (track_00). By spec §3 these carry identical intrinsic
     content, so role diversity is EXACTLY fixed. N = 2,4,6,8.

- hypothesis (double dissociation):
  H1 (diversity):  eff_rank(DIVERSE_6) > eff_rank(SAME_6)  by a clear margin.
  H2 (flat in N):
     - strict:  eff_rank(GAUGE-COPY, N) is flat in N (≈ 1), because gauge copies
       add no role diversity. Any growth flags a gauge / I-2 break.
     - real:    across N = 2,3,4,6, eff_rank(SAME) grows SLOWER than eff_rank(DIVERSE)
       (the same-role stack plateaus toward its small role vocabulary; the diverse
       stack keeps adding roles).

- null construction (and solver-floor calibration):
  - Role-scrambled null: independently permute each track's prototype geometry
    (destroys shared cross-track traffic while preserving within-track scale).
    Its effective rank is the NOISE reference. Pre-stated expectation:
    eff_rank(SAME) < eff_rank(NULL) < eff_rank(DIVERSE) — shared structure pulls
    rank BELOW noise; genuine diversity pushes it ABOVE noise.
  - Solver floor: the sizing is SPECTRAL, not a solver residual, so the relevant
    floor is the null effective rank (the rank noise alone produces). The
    barycenter F-solve is separately Lyapunov-certified; F monotonicity at each
    settled arm is recorded as a solver-health check (not the G1 readout).

- pass criterion (pre-stated): G1 PASSES iff
    (H1) eff_rank(DIVERSE_6) - eff_rank(SAME_6) >= 1.0  AND
    (H2-strict) max_N eff_rank(GAUGE-COPY,N) < 1.2  AND
    (H2-real)  eff_rank(DIVERSE) grows faster than eff_rank(SAME) over N=2..6
               (slope_DIVERSE > slope_SAME)  AND
    (ordering) eff_rank(SAME_6) < eff_rank(NULL_6) < eff_rank(DIVERSE_6).

- kill condition (WALL PROTOCOL, spec §4):
  - If eff_rank(SAME) >= eff_rank(DIVERSE) (no dissociation) → the self-sized
    anchor count does NOT track role diversity: STOP, report as a wall +
    candidate spec revision; do NOT tune sigma / clustering / arm rules to force
    a split.
  - If the GAUGE-COPY count grows with N → the sizing counts elapsed material,
    not role diversity, and the machine is not gauge-invariant (also an I-2
    smell): STOP and report.
  - No post-hoc adjustment of sigma, the clustering, or the arm definitions to
    rescue a null result. A null G1 is reported as-is.


## Scramble family (training comparison class)  (status: REGISTERED)
- prereg_commit: this commit (registers the family + activation); code_under_test: step d
- registry_ids: [train-nce-2026-07-13]

Scope: spec §6 requires the internal scramble family — the comparison class for
the contrastive/NCE fit of F-weights — to be FIXED IN PREREG before any training
run, with a stated rationale per member (which equilibrium property each member
breaks). This entry FIXES that family and is REGISTERED commit-before-run for the
step-d training. All four members are now IMPLEMENTED: step c built the anchors +
coupling, ACTIVATING the two role-level members (role-permute, cross-track-swap)
that were correctly refused before the role map existed. The family (four names)
is frozen; the negatives are drawn ONLY through it (`nce.draw_pairs` calls
`assert_family_fixed` and iterates `scramble.family()`; no second scrambler path).

Invariant: I-6 (no external negative data; comparison class from GOOD tracks
only; family fixed here). The family is enforced as a CLOSED, enumerated set by
`ets.training.scramble.PREREGISTERED_FAMILY` /`assert_family_fixed`, and the I-6
manifest check (tests/invariants/manifest.py) verifies (a) every op consumes only
real Track units (no external data / no fabrication), (b) the registered family
is EXACTLY the four names below (adding an unregistered scrambler fails), and
(c) outputs preserve the unit inventory (re-arrangement, not fabrication).

Determinism: every op is a pure, seedable function of (track(s), seed).

Fixed family — the ONLY four members (spec §6, verbatim names):

1. grid-shuffle  —  arity: Track → Track  —  status: IMPLEMENTED
   Operation: within each filterbank band, re-deal the real units to different
   metrical slots (permute the CONTENT bundle — source span, mass, timbre &
   pitch-class descriptors — while holding the metrical grid and the band/role
   labels fixed).
   Breaks: METRICAL PLACEMENT. The pairing of a unit to its beat/bar position
   (groove) is destroyed; the band inventory and the grid itself survive, so the
   negative differs from the real track ONLY in metrical arrangement.

2. role-permute  —  arity: (Track, world) → Arrangement  —  status: IMPLEMENTED
   Operation: couple the track's prototypes to the frozen anchors (pure-GW
   transport map, world.couple), then DERANGE the anchor columns of that coupling
   — reassign which learned ROLE (anchor) each prototype plays. Returns a role-
   space Arrangement (anchor×slot occupancy + transport).
   Breaks: ROLE ASSIGNMENT (unit→role coupling, spec §5 π). The permuted coupling
   no longer matches the barycentric geometry, so transport (T1) and the occupancy
   terms move.
   ACTIVATED at step c: "role" is the anchor assignment (spec §4/§5), which now
   exists. The filterbank `band` is NOT used as a role (spec §2 step 3). No role
   is fabricated — only the real coupling is permuted (I-6 via
   `assert_arrangement_real`).

3. phase-rotate  —  arity: Track → Track  —  status: IMPLEMENTED
   Operation: rotate the metrical phase by a DIFFERENT offset per band
   (incoherent across bands); content (audio, mass, descriptors) untouched.
   Breaks: GAUGE PHASE. A single GLOBAL beat-phase shift is pure gauge (spec §3)
   and leaves F invariant — useless as a negative. Making the rotation per-band
   destroys the single consistent gauge-phase frame the track settles into (T5
   gauge-fixing) and the cross-band phase lock, without touching any audio.
   (Requires ≥2 bands; a single band admits only the F-invariant global shift.)

4. cross-track-swap  —  arity: ([Track,Track], world) → Arrangement  —  status: IMPLEMENTED
   Operation: couple BOTH tracks to the SAME frozen anchors and swap a subset of
   ANCHOR (role) ROWS of their occupancies. Returns a role-space Arrangement whose
   transport is the mass-weighted sum of each track's OWN transport.
   Breaks: ANCHOR-MEDIATED CROSS-TRACK COHERENCE. All legitimate cross-track
   traffic factors through anchors in gauge-invariant role space (spec §4); a
   swapped occupancy breaks the within-track coherence that anchors certify.
   ACTIVATED at step c: the ONLY thing crossing the track boundary is anchor-space
   (role) mass — gauge-invariant, I-2-legal. No raw cross-track descriptor/cost is
   ever formed, and no foreign unit is injected into a single-`track_id` Track
   (the output is an Arrangement in shared role space, not a Track), so I-12 /
   single-source is not violated either. I-6 via `assert_arrangement_real`.

Kill / discipline: this family is frozen for step d. If a run shows the comparison
class is mis-specified, the fix is a NEW pre-registered family entry (new version),
never an edit to this one (append-only discipline).


## Training — real-tracks-are-equilibria separation  (status: RUN)
- prereg_commit: this commit (registers the check); code_under_test: step d
- registry_ids: [train-nce-2026-07-13]
- corpus: cache/ingest/track_00..19 (the 20 G0-passing tracks); frozen LAMBDA-free
  reference world (ets.training.world.build_reference_world).

- claim under test (spec §6): each real track is an EQUILIBRIUM of F; its
  re-arrangements are not. Operationally: with LAMBDA fit by the convex logistic
  NCE (T1 = reference scale 1), F(real) < F(scramble) for EVERY member of the fixed
  scramble family, by a margin, on held-out scramble seeds.

- fit vs validity metric (I-5 — disjoint, so no fit metric is a gate metric):
  * FIT metric  : logistic NCE loss on the fit seeds {1,2,3} — used to fit LAMBDA.
  * VALIDITY metric : per-member SEPARATION RATE = fraction of (real,scramble)
    pairs with F(real) < F(scramble), evaluated on HELD-OUT seeds {4,5}. Distinct
    quantity, distinct data. Not used to fit LAMBDA.

- procedure: build the LAMBDA-free world; draw negatives ONLY through the fixed
  family (assert_family_fixed); phi = (T1,T2,T3,T4) at native gauge (T5 == 0 for
  every member — a global section-gauge move is orthogonal to every re-arrangement,
  so lambda_5 is NOT corpus-time identifiable); fit lambda_{T2,T3,T4} >= 0 by
  projected-gradient logistic NCE on fit seeds; measure per-member held-out
  separation; apply the kill.

- null: a scramble that is a NO-OP would give separation ~0.5 (chance). A member
  whose F is invariant to the disarrangement sits at chance and fails.

- pass / KILL (pre-registered): PASS iff min over members of held-out separation
  rate >= SEP_MIN = 0.90. KILL iff any member < 0.90 — then F does not separate
  real from that re-arrangement for the fitted LAMBDA, i.e. an F term is
  mis-specified for that member (WALL PROTOCOL): STOP, do NOT emit an authoritative
  LAMBDA, do NOT hand-tune LAMBDA or drop the offending member to force a split,
  do NOT add external negatives. Report the wall + candidate spec revision.

### RESULT (training_results.json; registry train-nce-2026-07-13): KILL — WALL.
The estimator is well-posed for the transport/role weight but NOT for the
occupancy-term weights on this corpus. Held-out per-member separation:
role-permute ~1.0 (separates, but ONLY via T1, whose weight is FIXED = 1 —
identifies no lambda); grid-shuffle ~0.55; phase-rotate weak; cross-track-swap
~0.50 with a NEGATIVE median margin (F(swap) is not above F(real)). The logistic
fit drives lambda_2 = lambda_3 = 0 because grid-shuffle and phase-rotate demand
OPPOSITE-SIGN T2 gradients (verified: mean dT2 = -0.19 vs +0.15) — no lambda_2 >= 0
satisfies both. Diagnosis (first principles): F's occupancy terms live at anchor×
slot resolution (M~5 × S=8), which is near-invariant to within-track unit
re-arrangements (the discriminative groove signal is finer than the occupancy
marginals); and T2's shared target is necessarily smoother than an individual
groove, so within-track shuffles move TOWARD it (wrong sign). F-1 is therefore NOT
discharged; LAMBDA remains the step-c placeholder (undischarged) pending the spec
revision below. See the step-d builder report (session hand-off) + f.py LAMBDA note.

### Proposed spec revisions (for the human; not applied)
  R1 (§5/§6): the occupancy-level T2/T3/T4 cannot be contrastively fit against
     within-track re-arrangements at anchor×slot resolution. Either (a) T3
     (masking) / T4 (continuity) are re-typed at unit / fine-π resolution so a
     within-track shuffle registers, or (b) §6 acknowledges that grid-shuffle and
     cross-track-swap do not identify the occupancy weights and names the members
     that do. Changing F is a step-c revision, not a step-d patch.
  R2 (§5/§6): T2's "mass conservation" target must be a per-role GROOVE profile in
     a gauge-aligned frame, not a corpus mean (which is smoother than individuals
     and inverts the T2 gradient under shuffle). Requires a gauge-alignment pass.
  R3 (§6/§8): lambda_5 (T5 gauge-fixing weight) is NOT corpus-time identifiable —
     no re-arrangement perturbs the global section-gauge variable. It is a run-time
     gauge-stiffness baseline (panel knob 4), to be derived at the writer
     calibration (connector σ-scaling, step f), NOT at corpus-time NCE.

Kill / discipline: this is a RUN entry; its result stands. A future attempt with a
revised F (R1/R2) is a NEW pre-registered entry, never an edit to this one.


## Training rev-r1 — real-tracks-are-equilibria separation (fork C)  (status: REGISTERED)
- prereg_commit: this commit (registers the check); code_under_test: F rev-r1
- registry_ids: [train-nce-revr1-2026-07-13]
- corpus: cache/ingest/track_00..19 (20 tracks); frozen LAMBDA-free reference world
  (ets.training.world.build_reference_world). SAME corpus/world/seeds/threshold as
  the killed train-nce-2026-07-13; only F is revised (spec §5 rev-r1). This is a NEW
  entry (the prior KILL stands, unedited; R1/R2 are now APPLIED as rev-r1 F).

- what changed (spec §5 rev-r1; fork C = "go finer than the marginal"): F is posed
  on the unit-resolved fiber, not the anchor×slot marginal O. Two terms now read the
  fiber directly (inexpressible over O — that discarded residue was the wall):
  * T1 phase-displacement charge (applies R2): per placed unit, the GAUGE-ALIGNED
    circular distance between the unit's INTRINSIC metrical coordinate (bar-phase of
    its SOURCE content, read from provenance src_start via the beat grid; §3 micro-
    timing is intrinsic) and the phase of the slot it occupies; a single per-section
    global phase δ is quotiented out in closed form (charge = 1 - |Σ m e^{i2πx}|).
    Real groove = 0; incoherent metrical displacement (grid-shuffle) or per-band
    rotation (phase-rotate) cannot be removed by any global δ → strictly positive.
  * T4 unit-successor run-continuation (applies R1): mass-weighted fraction of
    output-adjacent same-band pairs whose content is a genuine SOURCE successor.
    Real = 1.0; grid-shuffle re-deals content → ~0; a cross-track graft inserts
    units that are no track's successor → the run breaks.
  T2/T3 remain on O (they provably factor through it). The O-aggregate role-
  continuation (old T4) is RETIRED. R3 stands: T5/λ5 is not corpus-time identifiable
  (0 for every family member at native gauge) and is not fit here.

- feature map: φ = [T1_gw, T2, T3, T4_raw=-succ_reward, phase_charge] (LAMBDA-free,
  computed at the frozen world). T1_gw is the reference scale (weight fixed 1); the
  convex logistic NCE fits λ = [T2, T3, T4, T1p] ≥ 0 on fit seeds {1,2,3}.

- fit vs validity metric (I-5, disjoint): FIT = logistic NCE loss on seeds {1,2,3}.
  VALIDITY = per-member SEPARATION RATE (fraction of (real,scramble) pairs with
  F(real) < F(scramble)) on HELD-OUT seeds {4,5}. Distinct quantity + data.

- PRE-REGISTERED EXPECTED MARGINS (declared before the registered 20-track/held-out
  run; derived from the term construction + de-risk probes on the frozen tracks):
  * real track: phase_charge ≡ 0 (each unit at its own slot), succ_reward ≡ 1
    (output order == source order) — both EXACT by construction.
  * grid-shuffle : phase_charge ~0.96-0.98 AND succ_reward ~0 → sep 1.00, large +margin.
  * phase-rotate : phase_charge ~0.20-0.57 (per-band incoherent, δ-irremovable) → sep 1.00.
  * role-permute : fiber ~unchanged (charge 0, reward 1); separates via T1_gw
    (permuted coupling ≫ real GW distortion) → sep ~0.95-1.00.
  * cross-track-swap : succ_reward ~0.3-0.5 (grafted foreign units break runs) → sep ~0.95-1.00.
  Predicted overall_min_sep ≥ 0.95; each per-member median margin > 0.

- pass / KILL (pre-registered; SAME threshold as the prior entry): PASS iff min over
  members of held-out separation rate ≥ SEP_MIN = 0.90. On PASS the NCE emits an
  authoritative LAMBDA = [1, λ] and F-1 (frozen-weight discharge) is discharged.
  KILL iff any member < 0.90 → an F term is STILL mis-specified → WALL PROTOCOL:
  STOP, emit NO LAMBDA, do NOT hand-tune/loosen/drop a member; report the residual
  wall + first-principles analysis. No threshold is weakened relative to the KILL.

- scramble family: UNCHANGED — the same four fixed members (grid-shuffle,
  role-permute, phase-rotate, cross-track-swap). "channel-desync" is NOT added: a
  per-band incoherent phase rotation IS channel/phase desynchronization, and that is
  exactly what phase-rotate already does (spec §6) — a separate member would
  duplicate phase-rotate and break the closed spec-§6 family (I-6). Decision logged:
  channel-desync ≡ phase-rotate; family stays at the four spec-mandated names.

- null: a NO-OP scramble gives separation ~0.5 (chance); a member whose F is
  invariant to its disarrangement sits at chance and fails the 0.90 threshold.
