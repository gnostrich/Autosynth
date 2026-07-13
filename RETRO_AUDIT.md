# Retro-audit — connector authority (ets-connector-v0) applied to session work

Required by `ets-directive-followon.md` §2: this session began before the
connector authority existed. Every component built so far is inventoried,
classified (mechanism / instrument / oracle / control), and checked against the
six improvisations the pre-connector spec left underdetermined:

  (a) decoder / readout / render-policy between world and audio
  (b) control path into the writer other than the Layer-0 tilt map
  (c) hand-set knob-scaling constants
  (d) fixed unit→slot table (static keymap)
  (e) pathway from tape/output into anchor growth
  (f) deadline-pressure shortcut (iteration caps, resolution reduction)

Status: DRAFT pending the in-flight step-(c) G1 report; hand to ets-auditor for
a verdict; resume build order only on PASS.

## Inventory + classification + verdict

| Component | Files | Classification | a–f check | Verdict | Action |
|---|---|---|---|---|---|
| Skeleton, invariant manifest, PREREG/REGISTRY | `tests/invariants/*`, `PREREG.md`, `REGISTRY.jsonl` | INSTRUMENT (harness) | none apply | CLEAN | none |
| Ingestion: beat clock, filterbank, unitize, Track, cost | `ets/ingestion/*` | MECHANISM | (d) unit sits at its own *source* tatum slot = source arrangement, not an output keymap; no decoder | CLEAN | none. Note: connector re-types G0 reconstruction as the consistency test of a fully-clamped tape-node — compatible, no change |
| Anchors (Hankel self-size, floor-prune) | `ets/functional/anchors.py` | MECHANISM | (e) growth from **input** cost only; no tape reference; no accumulator/pressure field (I-3) | CLEAN (pending Hankel-wall note from c-report) | confirm c-report on the anticipated Hankel WALL |
| **F terms T1–T5** | `ets/functional/f.py` | MECHANISM | **(c) `LAMBDA={T2:1.0,T3:0.5,T4:0.25,T5:0.1}` HAND-SET** | **FINDING** | LAMBDA must be **derived** by step-(d) contrastive calibration; no gate result may stand on the hand-set values. If G1 ran the solver with these, mark G1 PROVISIONAL and re-run post-calibration. "Every constant shows its derivation or dies." |
| Solver (block-coordinate I-projections) | `ets/functional/solver.py` | MECHANISM | (f) termination = Lyapunov F-descent certificate (`|ΔF|<tol`) + monotone accept-guard; Sinkhorn `n_iter=200` is batch OT convergence budget, not a real-time cap | CLEAN | none |
| Render (§11) | `ets/render/*` (worktree) | MECHANISM | (a) NO decoder/policy/learned net (AST-checked, I-11 enforced); executes schedule only; coupling=provenance (I-12) | CLEAN — connector-compliant, auditor-pending merge | merge after retro PASS |
| Scramble comparison class (§6) | `ets/training/scramble.py` (worktree) | INSTRUMENT | real-units-only; no decoder/keymap/tape | CLEAN (auditor PASS) | merge; wire `assert_family_fixed` into the step-(d) training path |
| Layer-0 tilt map, σ_φ calibration, amortizer, dual-estimator, C-1..C-3 | — | MECHANISM / INSTRUMENT / ORACLE | — | NOT BUILT | build at step (f)/(g) per connector — no gambiarra to wipe |
| Tape port ((N+1)-th node) + writer | — | MECHANISM (tape-node causal eval order) | — | NOT BUILT | build at (f): tape as boundary node, writer = its evaluation order, NO decoder, NO self-ingestion |
| Panel (§8 → connector) | — | CONTROL (clamped role-space measure) | — | NOT BUILT | build at (g) consuming boundary-measure typing, not a bespoke API |

## Findings requiring action (before/with resume)

**F-1 — hand-set F-term weights (`f.py:32`).** The relative term weights are
hand-picked, not derived. Required correction: step (d)'s contrastive/NCE
estimator MUST fit these (they are exactly the F-weights §6 calibrates); until
then they are an undischarged constant. Any gate that consumed them (candidate:
G1) is PROVISIONAL and must be re-evaluated after calibration. This does not
require wiping (c) — the F *structure* is correct — but it forbids treating the
current LAMBDA as authoritative.

## Connector obligations for the not-yet-built layers (carry into build order)

- Writer = tape-node's causal evaluation order (not a separate mode); tape is
  the (N+1)-th track-typed boundary node; NO decoder; NO self-ingestion
  (tape never spawns anchors; anchors frozen at world-freeze).
- Control enters ONLY via the Layer-0 tilt map `p(a) ∝ exp(−F/T_s + Σ λ_i φ_i)`
  with derived `λ_i = u_i/σ_{φ_i}` (σ from the untilted-writer calibration pass,
  registered instrument). No hand-set λ. Panel = clamped role-space measure
  (one intervention species with committed tape + user demands; generalized I-7).
- Amortizer is ORACLE-only (warm start; deleting it changes wall-clock, never the
  settled schedule); dual-estimator standing check; cold-solve deadline miss = WALL.
- New CI tests C-1 (knob→render bypass: same schedule + different u ⇒ bit-identical
  audio), C-2 (machine-precision gauge invariance of every φ), C-3 (static: panel
  reaches writer only via Layer-0 map).
