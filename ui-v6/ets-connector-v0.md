# ETS connector spec v0 — panel-to-writer stack

Status: companion authority to ets-spec-v0.md. Governs the interface between
the CV lanes (spec §8) and the settlement (spec §5/§7). Supersedes §8's knob
wording where they differ (specifically: knob 3 acts by tilt on its sufficient
statistic, NOT by editing T4's weight — I-9 stands; the exponential-family
equivalence makes these reachably identical, which is why the single-jack law
costs nothing).

Conventions inherited verbatim from the EBR program (ebr-spec-v1 /
ebr-directive-v1.1) — not restated here, binding: single-authority principle
(F decides; everything else is mechanism / instrument / oracle / control, and
every commit classifies its change as one of these or stops); oracle-not-
authority (FIX-1); amortization-gap training; dual-estimator standing check;
DeepSets equivariance over growable supports; every constant shows its
derivation (F-term, null quantile, or pre-registered) or dies; registry
commit-before-run.

---

## Architectural typing (normative, governs everything below)

The panel is NOT an external operation on the writer. It is a boundary node
of the hypergraph: a clamped measure on role/statistic space, coupled through
the same anchor star as all other traffic. Knob leans = hand-set reweighting
of that clamped measure's mass. The h-transform tilt below is not an added
mechanism — it is the Doob conditioning induced on the settlement by clamping
this boundary measure. Consequently spec I-7 generalizes to the system-wide
law: committed tape (clamped past cells), user demands (clamped future
cells), and knob leans (clamped role-space mass) are ONE intervention type —
boundary conditions on a single settlement. No other intervention species may
exist. The connector inherits the hypergraph connector idiom in full
(connector = measure, factored through anchors; hidden width = measured
McMillan degree; expand/contract by FW-atom/floor-prune; settlement not
forward pass; gauge-invariant boundary traffic only).

THE TAPE PORT. The output tape is the (N+1)-th track-typed boundary node:
identical schema to ingested tracks (units at metrical slots under a gauge
frame), coupled through the same anchor star. Input tracks = fully clamped
instances; the output tape = a progressively clamped instance (writing =
the settlement clamping its own frontier cells in causal order — the MZ
writer is this node's evaluation order, not a separate mode). Consequences,
normative: (i) no decoder / readout head / world-to-audio translation layer
may exist — the tape-node's coupling IS the output and the render executes
its schedule (its coupling is also the provenance record, discharging I-12
architecturally); (ii) G0's reconstruction identity is the consistency test
of a fully clamped tape-node — input/output symmetry is testable; (iii)
NO SELF-INGESTION: the tape-node carries read/write traffic (continuity and
novelty statistics may see committed cells) but has ZERO structural
authority — it may never spawn anchors or expand world structure; anchor
expansion is driven by input material only, frozen at world-freeze. A tape
feeding its own output into anchor growth is the I-8 confabulation failure
with a mechanism attached, and is a named patch signature.

## Layer 0 — Exact tilt map [MECHANISM]

Panel state: lane vector u = (u_region (vector over anchors, from XY pad /
channel strips), u_density, u_continuity, u_gauge, u_novelty) plus
temperature T_s. Settlement measure per bar (the induced Doob tilt):

    p(a) ∝ exp( −F(a)/T_s + Σ_i λ_i · φ_i(a) )

φ_i are the normative arrangement statistics (gauge-invariant, computable from
the candidate arrangement alone):

  φ_region   = anchor-occupancy vector of the bar's scheduled mass
  φ_density  = filled-slot count / scheduled mass
  φ_cont     = count of source-successor continuation events
  φ_gauge    = frame-move indicator × magnitude on the section-gauge variable
  φ_novelty  = recency-weighted unit reuse vs the committed tape

Scaling (the only would-be constant, derived): λ_i = u_i / σ_{φ_i}, where
σ_{φ_i} = equilibrium fluctuation of φ_i under the UNTILTED writer, measured
in a calibration pass at world-freeze (instrument; registered; re-run on any
anchor spawn/prune). Knobs therefore read in natural units: standard
fluctuations of lean. No hand-set λ scales exist anywhere.

T_s (temperature) is typed separately: it scales settlement sharpness, has no
φ, and enters only at the settlement step. Five direction-lanes + one
sharpness-lane; the panel remains exhaustive.

Faithfulness tests (CI, tests/invariants/):
  C-1 knob-to-render bypass: same settled schedule + different u ⇒
      bit-identical audio.
  C-2 gauge invariance of every φ under per-track gauge scrambles
      (machine-precision, EBR-style fixture).
  C-3 tilt-only entry: static check that u reaches the writer solely via the
      Layer-0 map (spec I-1).

## Layer 1 — Settlement amortizer [ORACLE]

Purpose: frontier settlement is an I-projection solve with a real-time
deadline. The amortizer is a warm-start oracle ONLY.

Architecture: DeepSets / attention pooling over per-anchor invariant blocks —
equivariant over anchors (anchors self-size; any fixed-width input
reintroduces fixed-K through the back door). Small (~10^4–10^5 params).
Input: (anchor occupancies, runs-in-flight intrinsic stats, drift frame,
lane vector u, clamped-cell mask for the frontier).
Output: initial coupling guess as barycentric weights over anchor supports +
gauge-section initialization. The settlement then runs its block-coordinate
I-projections FROM this guess TO its certificate. The certificate, not the
oracle, terminates.

Training: amortization gap (distance from oracle guess to converged
settlement), on (state, u, converged-settlement) triples harvested from
normal operation — self-supervised replay buffer, no labels, no external data
channel.

Authority contract (structural, testable): no term of F references the
oracle; deleting the oracle changes wall-clock only, never the settled
schedule (test: cold vs warm final schedules agree within certificate tol on
a fixed seed suite).

## Layer 2 — Standing correctness instrument [INSTRUMENT]

Dual-estimator check: at pre-registered rate p per bar in production, run the
cold solve alongside the warm-started solve; require equilibrium agreement
within tolerance. Divergence ⇒ oracle quarantined (automatic cold fallback),
event logged to REGISTRY.jsonl with state hash. Tolerances and p: derived
from the calibration pass's certificate statistics, not hand-set.

## Real-time typing [CONTROL]

The writer runs L bars ahead of the playhead (declared latency buffer; knob
changes bind at the write frontier, so control latency = L bars — plugin-
latency semantics, surfaced on the panel, not hidden). If the COLD solve
cannot meet the deadline within buffer L, that is a WALL: halt and report.
Shipping the oracle's unverified guess as output, reducing frontier
resolution under load, or any silent quality fork under deadline pressure is
a named patch signature (auto-REJECT). L is pre-registered per hardware
profile.

## Classification summary

  Layer 0 tilt map ............ MECHANISM (exact, zero learned content)
  σ_{φ} calibration pass ...... INSTRUMENT (registered, re-run on resize)
  Amortizer ................... ORACLE (warm start only, replay-trained)
  Dual-estimator check ........ INSTRUMENT (standing, sampled)
  Latency buffer L ............ CONTROL (declared constant, per profile)

Auditor: extend the I-1..I-14 sweep with C-1..C-3 and the oracle-authority
test; the historical sin to hunt for here is the η·KL pattern — any term,
regularizer, or schedule that lets the amortizer influence WHERE the
equilibrium is rather than how fast it is reached.
