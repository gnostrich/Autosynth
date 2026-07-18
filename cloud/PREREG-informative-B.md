# PREREG — informative anchor band-profile B at world freeze (2026-07-18)

Status: **PRE-REGISTRATION DRAFT, awaiting operator sign-off.** This is the
**2-NEXT ENGINE CHANGE** of the conjugacy-reconciliation program (OPEN_ENDS #22:
"pre-registered engine change to make B informative … next, with operator
sign-off. (3) receipt strengthening (F_init / verified monotone) rides with 2").
It is committed BEFORE any code change, per standing law ("prereg before build,
auditor PASS before merge, walls surfaced not patched, no engine/theory edit
without a prereg + operator sign-off"). No code is touched by this document.

This change touches the ENGINE tree (the world-freeze path), which is normally
byte-immutable (CLAUDE.md §4). It is therefore gated on explicit operator
sign-off (the block at the end) AND an ets-auditor PASS on the diff, and is
scoped to the FREEZE path only — F, settlement, render, and the world definition
proper are argued unchanged below and pinned by tests.

## Governing rule (papers/paper2-ets-instrument.md §2, the operator-confirmed headline)

> "Squares are grouped by the trained coupling's OWN equivalence (same
> anchor-profile = same sound); a fresh clustering pass is forbidden as an
> extrinsic notion of similarity."

and the arming corollary this change serves (paper2 §6 table):

> "disarm-and-label → Theorem A corollary: degenerate FDT, not policy."

The investigator's Phase-1 finding (OPEN_ENDS #22) is that the shipped
implementation contradicts the headline: the anchor band-profile matrix B — the
carrier of "anchor-profile = same sound" — is UNIFORM on every world ever frozen,
so the "trained coupling's own equivalence" is the trivial one (every square in
one group). This prereg makes B informative at freeze, from a form already in the
tree, so the grouping becomes real; the sibling Remediation-1 (the 1-NOW
role-grain disarm) keeps everything honest until it does.

## Rollback surface

Git tag `pre-informative-B-2026-07-18` at current HEAD, created BEFORE any edit.
Rollback = checkout the tag + re-pin the engine manifest (see VERSIONING). Because
the change is confined to the freeze path, rollback does not touch any existing
`.etsworld`: worlds frozen under either engine load and render identically
(they carry their own stored B; see §5 byte-identity).

---

## 1. FINDING RESTATED (file:line)

**F is band-blind, and uniform B is an exact fixed point of its only B-bearing
term, so every frozen world has flat B.**

- **B is initialized uniform.** `architecture-v6/ets/functional/anchors.py:105`
  (`init_state`): `B = np.full((M, n_bands), 1.0 / n_bands)`. Every anchor's band
  profile starts identical.
- **The solver leaves it uniform.** `architecture-v6/ets/functional/solver.py:80-90`
  (`update_B`, exponentiated-gradient on T3). With every row of B equal to
  `1/n_bands`, `E = O.T @ B` is constant across bands, so
  `dB[k] = 2·L3·(O[k] @ (E − O[k]·B[k]))` is constant across bands for each anchor;
  `B·exp(−η·dB)` renormalized stays uniform. **Uniform B is an exact fixed point**
  — `update_B` is a no-op on the uniform initialization. It never moves.
- **F only sees B through T3 masking, which is band-symmetric at uniform B.**
  `architecture-v6/ets/functional/f.py:164-172` (`term_T3`) is the sole term
  reading B; `f.py:317` sums it into F. T1/T2/T4/T5 do not read B at all. So F has
  no gradient channel that distinguishes bands once B is uniform — F is
  **band-blind** at the fixed point.
- **The played world's B comes from this path.** The shipped/played FState is
  produced by `anchors.build_world` (`anchors.py:129-153`): solve
  (`anchors.py:143`) → prune (`anchors.py:144`) → serialize. The cloud service
  runs exactly this (`cloud/service/app.py:35`), and it is what `encode_result`
  emits as `world.B` (`cloud/common/protocol.py:246`) and what the companion loads
  and plays. **Every world ever frozen and played has flat B.** (All engine trees
  — root `ets/`, `architecture-v6/ets/`, `ui-v6/ets/` — are byte-identical here,
  verified `diff`; the finding and the fix apply to all three.)

**Consequences (the observables that are false today):**

- **Uninformative role/unit grouping.** paper2 §2 groups squares by "same
  anchor-profile". A unit's anchor-profile is a column `B[:, band]`
  (`engine.py:330-333`). With uniform B every column is identical → every unit has
  the same anchor-profile → the field's role/unit grouping is the trivial one.
- **False track attribution via tie + top_n.**
  `engine.role_unit_counts` (`engine.py:306`): `dom = B.argmax(0)` — under exact
  ties numpy returns index 0 for EVERY band, so **all units are attributed to
  anchor 0**. `engine.role_unit_pool` (`engine.py:352`): ranks units by
  `B[i, band]`; all values equal → a stable no-op sort → **every role's pool is the
  same first `top_n` units in the same order** (the docstring at `engine.py:323-328`
  already confesses this: "one anchor tends to win every band's argmax … Forcing a
  unit onto exactly one role would be a fabricated partition").
- **Lock-step role bars.** `engine.track_anchor_profiles` (`engine.py:291`):
  `v = B @ band_mass`; with uniform B, `v` is flat across anchors → peak-normalize
  → **all anchors read 1.0** (identical bars). `engine.bar_role_activity`
  (`engine.py:380`, consumed at `engine_bridge.py:249`): same flat `B @ band_mass`
  → **role activity bars move in lock-step**, never differentiating.

The paper-2 §2 claim this contradicts is the operator-confirmed HEADLINE
disagreement of the reconciliation program (OPEN_ENDS #22): the grouping is
supposed to BE the trained coupling's own equivalence; today it is degenerate.

---

## 2. PROPOSED CHANGE (minimal, exact)

**At world freeze, define B as the coupling-weighted band profile of the settled
couplings — the form ALREADY IN THE TREE at `training/world.py:91-97` — instead of
leaving it at the uniform initialization.** Data-coupled, no new theory, no new
hyperparameter, no new library.

### The form (verbatim, `architecture-v6/ets/training/world.py:91-97`)

```
Bw = np.zeros((M, n_bands)); wsum = np.zeros(M)
for pi, P in zip(pis, protos):
    bp = P.band_profile / (P.band_profile.sum(1, keepdims=True) + 1e-12)
    Bw += pi.T @ bp; wsum += pi.sum(0)
B = Bw / (wsum[:, None] + 1e-12)
B = B / (B.sum(1, keepdims=True) + 1e-12)
```

Each anchor's band profile becomes the mass-weighted (by coupled mass
`pi.sum(0)`) mean of its units' own band profiles, on the simplex. This is
**exactly the B that the NCE reference world already carries** — the world the
weights LAMBDA were fit and examined against uses this form (see §3, exam). The
change imports that already-blessed form into the freeze path; it does not invent
one.

### Exact code sites

Add a small helper and one assignment to `build_world`, in **all three
byte-identical engine trees** (they must stay byte-identical; the finding and fix
are common to them):

- `ets/functional/anchors.py`
- `architecture-v6/ets/functional/anchors.py`
- `ui-v6/ets/functional/anchors.py`

In `build_world` (`anchors.py:142-153`), **after** `batch_solve` and `_prune`
(so the couplings and anchor set are the settled, pruned ones), and before
building `info`:

1. Compute `B_informative` from `state.pis` and `[P.band_profile for P in protos]`
   using the `world.py:91-97` form (the pis here are the world's OWN settled,
   pruned couplings — "the fitted pi's").
2. `state = replace(state, B=B_informative)`.
3. Recompute `F_final = ff.F(state, protos)[0]` on the FROZEN state (so the
   receipt certifies the world AS FROZEN, with its informative B — see §7 wall).
4. Add `F_init` and `seed` to `info` (the receipt strengthening, §4).

**Two-tree byte-identity, addressed explicitly:** the three `anchors.py` are
byte-identical today (`diff` confirmed) and MUST remain so; the same patch lands
in each, verified by a `diff -q` gate in the version-bump step (§6). The cloud
`service` imports root `ets` (`cloud/service/app.py:17`); the companion renderer
imports `architecture-v6/ets`; `ui-v6/ets` is the local desktop engine — all must
agree or the offloaded fit and the local render would disagree on B. The
byte-identity gate is a hard part of this change, not an afterthought.

### What does NOT change

- **F itself** (`f.py`): untouched. T3's math, LAMBDA (`f.py:70-71`), the term set,
  I-4/I-5/I-14 — all unchanged.
- **The solver / settlement** (`solver.py`, `writer/settle.py`): untouched. The
  block-coordinate descent still runs with B held at the uniform fixed point
  THROUGH the solve (`update_B` remains a no-op on uniform init), so the settled
  `D, a, θ, π, gauge` are **bit-identical to today's**. Only the FINAL frozen B
  differs. B remains FROZEN post-training (a run-time control never edits it, I-9).
- **The render** (`writer/realize.py`, `writer/stream.py`) and **`build_index`**
  (`realize.py:91`): code untouched. `build_index`'s role→track materialization
  reads membership + `P.band_profile` (`realize.py:111,119-120`), **not** `fstate.B`
  — so which real unit renders per (role, band) is B-independent. `fstate.B` enters
  render only at the settled-energy band split `e = col @ B`
  (`realize.py:313`); that code is unchanged, but its INPUT B differs on
  newly-frozen worlds (intended; §3).

**The change is WHERE the frozen B value comes from** (a data-coupled readout of
the settled couplings) **rather than an arbitrary uniform initialization the
solver never moves.**

---

## 3. CONSEQUENCE ANALYSIS

### What becomes REAL

- **Role/unit grouping = the trained coupling's own equivalence** (paper2 §2).
  `B[:, band]` now differs across bands, so anchor-profiles differentiate; the
  field's grouping is the coupling's equivalence, not the trivial one.
- **Pool ranking de-tied.** `role_unit_pool` (`engine.py:352`) ranks by real,
  distinct `B[i, band]` → per-role pools differ; the tie+top_n degeneracy is gone.
- **Role bars differentiated.** `track_anchor_profiles` (`engine.py:291`) and
  `bar_role_activity` (`engine.py:380`) return differentiated per-anchor vectors;
  bars stop moving in lock-step.
- **`role_unit_counts` (`engine.py:306`) argmax spreads** across anchors instead of
  collapsing to anchor 0.

### What could REGRESS — every B-reader analyzed

| Reader | file:line | Reads B how | Behavior under informative B | Regression risk |
|---|---|---|---|---|
| `role_unit_pool` | engine.py:352 | rank units by `B[i,band]` | de-tied, per-role pools differ | none (improves); pinned by `test_pi_unitpool` |
| `role_unit_counts` | engine.py:306 | `B.argmax(0)` per band | spreads across anchors | see WALL §7 (row-normalization / column-argmax convention) |
| `track_anchor_profiles` | engine.py:291 | `B @ band_mass` | differentiated | none (improves) |
| `bar_role_activity` | engine.py:380 | `B @ band_mass` | differentiated | none (improves) |
| `Realizer` band split | realize.py:313 | `e = col @ B` | per-anchor band energy differentiates → **render differs on newly-frozen worlds** | intended; existing worlds byte-identical (§5) |
| `build_index` role→track | realize.py:111,119-120 | **does not read B** (uses `P.band_profile` + membership) | unchanged | none |
| NCE exam | nce.py:57 | reads `WorldFreeze.B` from `build_reference_world` | **already informative** (see below) | none |

**Interaction with the NCE exam (determined, stated loudly):** the exam does NOT
consume the frozen FState's B. `nce.feature` scores real vs scramble with
`ff.raw_terms_O(O, world.D, world.a, world.B, world.theta)` (`nce.py:57`) where
`world` is the `WorldFreeze` from `training/world.build_reference_world` — which
ALREADY carries the coupling-weighted B (`world.py:91-97`). **So the exam is
unaffected by this change, and NO re-blessing of the scramble contrast / LAMBDA
fit is required.** The change makes the PLAYED world's B agree with the form the
weights were already fit and examined against, rather than shipping a uniform B
the exam never saw. (Caveat, honest: the exam uses PURE entropic-GW couplings;
the freeze uses the world's OWN settled couplings `state.pis`; the two B's use the
same FORM but different π, so they are not byte-equal — see §7 π-source note. This
is a choice, not a break: B should reflect THIS world's couplings.)

**Interaction with σ_φ calibration (honest):** the region lane is per-anchor and
its σ_φ is the untilted fluctuation of φ_region (anchor occupancy). φ_region is
`O` over anchors, which does not read B directly, but the SETTLED O depends on B
through T3 during settlement — so a newly-frozen world's untilted region
fluctuation can differ from the uniform-B world's. This needs no separate action:
σ_φ is measured **per-corpus, in-pipeline, AFTER the freeze**
(`cloud/companion/train_local.py`, mirroring `scripts/run_sigma_phi.py`), so a
newly-trained world measures σ_φ against its own informative-B settlement
automatically and consistently. **Honest unknown:** informative B may change which
lanes clear the arming floor (a disarmed lane could arm, or vice versa) — that is
the arming criterion operating as designed on a now-band-aware settlement, and is
a thing to MEASURE (§5), not a regression to suppress. Existing worlds keep their
(uniform-B, matching σ_φ) pair untouched (§5), so no stale mismatch is created.

**Existing trained worlds / `demo.etsworld` — re-freeze or not:** they are NOT
auto-re-frozen. A world file is a pickle of the World holding its own `fstate.B`
(`engine/worldfile.py:3,49,77`); loading unpickles the stored (uniform) B and
`build_world` is never called on load. So old worlds keep flat B and render
identically (§5). They are kept HONEST by the sibling **Remediation-1 (the 1-NOW
role-grain disarm** of OPEN_ENDS #22, the arming-corollary disarm): when B is
degenerate (flat), the role grain DISARMS and labels rather than presenting the
false grouping. Whether or not an old world is ever re-frozen, it surfaces as
honestly-disarmed, not falsely-grouped. Re-freezing an old corpus (re-running the
fit) is the way to give it a real grouping; that is a user action, not an
auto-migration, and it is the honest path (a re-frozen world gets a new world hash,
§5).

---

## 4. RECEIPT STRENGTHENING (rides along, per #22 item 3)

Goal: the device-verifiable receipt should certify not just WHERE the world
settles (`F_final`, already checked) but that it settled DOWNHILL from a real
start, and that its own descent was monotone.

### Exact `cloud/common/protocol.py` sites

- **`anchors.build_world` info** (all three trees): add
  `info["F_init"] = float(ff.F(init_state(protos, M=M, seed=seed), protos)[0])`
  (F of the INITIAL state, uniform B) and `info["seed"] = int(seed)`.
  `F_monotone` is already emitted (`anchors.py:151`, the solve-trajectory
  monotonicity) — kept.
- **`encode_result`** (`protocol.py:242-258`): unchanged mechanically — it already
  serializes every `info` item as `receipt.*`, so `F_init`/`seed` ride
  automatically.
- **`verify_receipt`** (`protocol.py:289-331`):
  1. Add `"F_init"`, `"F_monotone"`, `"seed"` to the required-keys check
     (`protocol.py:305`).
  2. **Recompute** `F_init` independently:
     `state0 = an.init_state(protos, M=int(round(er)), seed=int(r["seed"]))` then
     `F_init_re, _ = ff.F(state0, protos)`; raise `ReceiptError` unless
     `abs(F_init_re − r["F_init"]) ≤ max(atol, 1e-6·|F_init_re|)`. (init_state is
     deterministic given (M, seed); this is a real re-derivation, not a trust.)
  3. **Require descent:** raise unless
     `float(r["F_final"]) ≤ float(r["F_init"]) + max(atol, 1e-6·|F_init|)`.
  4. **Sanity-check monotone:** raise unless `bool(r["F_monotone"]) is True`.
     Stated honestly: the verifier does NOT re-run the block solve, so it cannot
     independently reconstruct the F-trajectory; it enforces that the field is
     PRESENT and TRUE (a world whose own solver reported a non-monotone descent is
     rejected). The independent `F_final` (already checked, `protocol.py:326-330`)
     and `F_init` (new, step 2) bounds catch a lying monotone flag in the cases
     that matter (a world that does not actually sit at its certified `F_final`, or
     did not descend below its start, is rejected regardless of the flag).

### Backward compatibility policy (stated explicitly)

The new fields are **REQUIRED** — a receipt lacking `F_init`/`F_monotone`/`seed`
is rejected. This is safe and honest because receipts are **ephemeral and
device-verifiable in the same round-trip**: a receipt is produced by a fit and
verified immediately by the client that requested it; receipts are not persisted
for later re-verification (the trained world is persisted, not its receipt). No
compatibility shim is added — a branch that SKIPPED the new checks for "old"
receipts would be a forbidden silent fallback. Any receipt minted before this
change is re-minted by re-running the (cheap: one F eval + one eigendecomposition)
verify against a fresh fit. If the operator knows of any persisted pre-change
receipt that must remain verifiable, that is a wall to raise NOW (§7), not to shim
around.

---

## 5. VERIFICATION PLAN

All tests pre-registered here; kill conditions explicit. Invariant-style tests
live under the engine tree's `tests/`; cloud-seam tests under `cloud/tests/`.

1. **Informative B (positive).** On a STRUCTURED fixture corpus (units whose
   `band_profile` genuinely varies across prototypes), assert the frozen
   `state.B` has `row-ptp > 0` for at least one anchor and column variation across
   bands (`B.argmax(0)` takes ≥2 distinct values when M≥2 and the corpus supports
   it). KILL: if B is still flat on a structured corpus, the change did not take.

2. **Flat corpus stays honestly flat (no fabricated spread).** On a DEGENERATE
   fixture (all prototypes share one band profile), assert the frozen B is
   near-flat (`row-ptp ≈ 0` within 1e-9). We do NOT manufacture spread where the
   data has none. KILL: any injected floor/jitter that fakes non-flat B on a flat
   corpus.

3. **1-NOW degeneracy disarm ARMS on the new worlds (end-to-end).** Train the
   structured fixture end-to-end → assert the role grain is ARMED (not disarmed) —
   i.e. Remediation-1's degeneracy check sees a non-degenerate B and lets the
   grouping through; and on the degenerate fixture the grain still DISARMS. KILL:
   grain armed on a degenerate corpus, or disarmed on the structured one.

4. **Exam / scramble contrast: NO re-run required — asserted, not assumed.** A
   test that the NCE path reads `build_reference_world`'s B (`nce.py:57`), which is
   independent of `anchors.build_world`, so the held-out separation numbers
   (paper2 §5: min sep 0.95) are unchanged bit-for-bit. If this assertion FAILS
   (the exam turns out to read the frozen FState's B after all), STOP: the exam
   must be re-blessed under a fresh PREREG before this change ships, and that fact
   is reported LOUDLY. (Determination on current code: the exam does not read it;
   this test pins that.)

5. **BYTE-IDENTITY of u=0 renders on an UNCHANGED world file (the pin).** Load an
   existing committed `.etsworld` (e.g. `demo.etsworld`) BEFORE and AFTER the
   change; render N bars at u=0; assert **bit-identical audio** and identical world
   hash. The change touches freeze only; existing files carry their stored uniform
   B and `build_world` is not called on load, so this MUST hold. KILL: any
   difference → the change leaked out of the freeze path (H-8 breach).

6. **Receipt checks bite.** (a) A world with `F_final > F_init` → `verify_receipt`
   rejects. (b) A receipt with `F_monotone=False` → rejects. (c) A tampered
   `F_init` (≠ recomputed) → rejects. (d) A valid fresh fit → passes. Plus: measure
   on the structured fixture whether `F_final ≤ F_init` actually HOLDS with the
   informative-B swap (see §7 wall) — if it fails on any honest fixture, that is a
   FINDING to report, not a threshold to loosen.

7. **Full suites green + engine byte-identity gate.** `cloud/tests` suite green;
   the three `anchors.py` verified byte-identical (`diff -q`) post-patch; engine
   invariant suite green (I-4/I-5/I-14 untouched: F unchanged).

---

## 6. VERSIONING

- **Engine bump.** `release-manifest.json` pins `engine: {id: "engine-v1"}`,
  verified by `scripts/verify_version.py` against
  `verification/canonical_manifest.json`. This is a freeze-path revision of the
  engine → bump to **`engine-v1.1-freeze`** (per the OPEN_ENDS #1 precedent
  "engine-v1 → v1.1 …, re-bless the verifier"): re-generate the canonical manifest
  for the changed `anchors.py` (three trees), update `release-manifest.json`
  `engine.id` + `engine.verified_by`, and record in `LEDGER.md` /
  `VERSION_LEDGER.jsonl` / `release-manifest.json` per repo convention.
- **Both/all-three-trees policy.** The patch lands identically in `ets/`,
  `architecture-v6/ets/`, `ui-v6/ets/`; a `diff -q` byte-identity gate across the
  three `anchors.py` is part of the merge checklist (the cloud fit uses root `ets`,
  the companion render uses `architecture-v6/ets`, the desktop uses `ui-v6/ets` —
  they MUST agree on B).
- **Tag.** `pre-informative-B-2026-07-18` at pre-edit HEAD (rollback);
  `engine-v1.1-freeze` at the merge commit.
- **Rollback.** Checkout the pre-edit tag + restore the prior canonical manifest.
  Existing `.etsworld` files are unaffected either way (they store their own B),
  so rollback is clean; only worlds frozen under v1.1-freeze carry informative B,
  and re-freezing under v1 would return them to flat B (a deliberate user action,
  not silent).

---

## 7. WALLS / UNKNOWNS (honest, for the operator — not resolved silently)

1. **B stops being an F-decision-variable; it becomes a derived readout — surface
   the type change.** Today B is nominally a free variable of F (`update_B` is in
   the solver block list) but is inert (uniform is a fixed point). This change
   DEFINES the frozen B as a deterministic function of the settled couplings, for
   FIDELITY (paper2 §2), independent of whether that B minimizes T3. So the world
   as frozen is deliberately NOT the F-argmin in the B-direction. This is the crux
   of the reconciliation: paper2 wants B = the coupling's band equivalence
   (fidelity); F (via T3 masking) is band-indifferent and its critical point is
   flat. Making B a derived readout is arguably the CORRECT typing (B joins θ and a
   as learned world-structure, exactly as the NCE reference world already treats
   it) — but it means "the one decision-maker is F" no longer literally governs B.
   **Operator decision:** accept B as a derived freeze-time readout (recommended,
   and consistent with the NCE reference world), versus a larger redesign that
   makes B a genuine F-variable with a band-discriminating term. This prereg takes
   the minimal readout path; the larger redesign is explicitly OUT OF SCOPE.

2. **Monotonicity vs. the swap: `F_final ≤ F_init` is asserted, not proven.** The
   block-solve trajectory stays monotone (B held at the uniform fixed point through
   the solve, so `F_monotone` over the solve is unchanged and honest). But
   `F_final` is now F of the FROZEN world (post-B-swap). If the informative B
   raises T3 masking above the uniform-B critical value, `F_final` can EXCEED the
   solve's terminal value. The receipt's `F_final ≤ F_init` bound (uniform-B random
   start → informative-B settled end) is expected to hold by a wide margin (the
   solve reduces F a lot; the B-swap perturbs only T3), but it is **not guaranteed**
   and is MEASURED in §5.6. If it fails on any honest fixture, that is a real
   FINDING (the world does not settle below its start once B is band-honest) — to
   report, not to patch by loosening the bound.

3. **π-source: settled vs pure-GW couplings.** The freeze uses the world's OWN
   settled `state.pis`; the NCE reference world uses pure entropic-GW couplings.
   Same FORM (`world.py:91-97`), different π, so the played B and the exam's B are
   not byte-equal. Chosen deliberately (B should reflect this world's couplings),
   but flagged: if the operator wants the played B to exactly match the examined B,
   the freeze should use pure-GW couplings instead — a one-line choice, called out
   here rather than made silently.

4. **Reader normalization convention (`role_unit_counts`).** The coupling-weighted
   B is ROW-normalized (each anchor's band profile sums to 1). `role_unit_counts`
   (`engine.py:306`) does `B.argmax(0)` — a COLUMN comparison (which anchor
   dominates band b). With independent row normalization, a "narrow" anchor
   (concentrated on few bands) shows high per-band mass and can win columns over a
   "broad" anchor. This is not obviously the intended grouping — column-argmax on a
   row-normalized matrix mixes "anchor b-affinity" with "anchor breadth". It is not
   obviously WRONG either (the reader already used argmax semantics). Flag for the
   operator: sanity-check whether role/band assignment should use row-normalized B,
   a column-normalized (per-band anchor share) view, or an explicit joint criterion.
   This prereg does not change the readers; it only makes B informative — but the
   reader convention becomes load-bearing the moment B is non-flat, so it must be
   examined, not assumed correct.

5. **θ is still a uniform prior in the FState (related, out of scope).** For full
   paper2 fidelity one might also want the played θ learned from the corpus (as
   `build_reference_world` already does), instead of the solver's fixed uniform θ
   (`solver.py:138-141`). This prereg addresses only B, per the operator's 2-NEXT
   scope. θ-learning in the freeze is a separate future item — flagged, not touched.

6. **Arming shift is a measured consequence, not a target.** Informative B changes
   the settled O and thus which σ_φ lanes clear the floor. This is the arming
   corollary working as designed; but if a lane that mattered to the operator
   (e.g. region on `demo.etsworld`-class corpora) flips armed↔disarmed on
   re-freeze, that is a real behavioral change to disclose in the build report,
   measured on the fixtures in §5, never tuned.

---

## OPERATOR SIGN-OFF

Approving this prereg authorizes the builder to implement EXACTLY the following,
under builder→ets-auditor pairing, auditor PASS required before merge:

- [ ] **Informative B at freeze.** In `build_world` (all three byte-identical
      trees: `ets/`, `architecture-v6/ets/`, `ui-v6/ets/`
      `functional/anchors.py`), after solve+prune, set B to the coupling-weighted
      band profile of the settled couplings using the existing
      `training/world.py:91-97` form; recompute `F_final` on the frozen state.
      No change to F, LAMBDA, the solver's descent, settlement, render, or
      `build_index`.
- [ ] **Receipt strengthening.** Add `F_init` + `seed` to `build_world` info;
      `verify_receipt` (`cloud/common/protocol.py`) independently recomputes
      `F_init`, requires `F_final ≤ F_init`, and requires `F_monotone == True`.
      New receipt fields REQUIRED (no old-receipt shim; policy stated in §4).
- [ ] **Verification** per §5 (informative-B positive + flat-corpus honesty +
      1-NOW arms + exam-unaffected assertion + u=0 byte-identity on an unchanged
      world file + receipt bite + `diff -q` three-tree byte-identity).
- [ ] **Versioning** per §6: bump `engine-v1 → engine-v1.1-freeze`, re-bless
      `scripts/verify_version.py` / `canonical_manifest.json`, update
      `release-manifest.json` + `LEDGER.md` + `VERSION_LEDGER.jsonl`, tags
      `pre-informative-B-2026-07-18` and `engine-v1.1-freeze`.

Explicitly OUT OF SCOPE (require a separate prereg + sign-off): making B a genuine
F-variable / adding a band-discriminating F term (§7.1); learning θ in the freeze
(§7.5); changing any B-reader's normalization convention (§7.4); using pure-GW
couplings for the freeze B (§7.3).

Operator must ALSO adjudicate the four flagged decisions before or at sign-off:
§7.1 (B as derived readout — accept?), §7.3 (settled vs pure-GW π for the freeze
B), §7.4 (`role_unit_counts` argmax convention), and acknowledge the measured
risks §7.2 (`F_final ≤ F_init` not proven) and §7.6 (arming shift on re-freeze).

Signed-off by: ______________________  Date: ____________
