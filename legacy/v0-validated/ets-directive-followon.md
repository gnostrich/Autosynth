# ETS follow-on directive — connector authority + retro-audit

Context: the build was started from ets-spec-v0.md + agent files. Since then a
companion authority was issued: ets-connector-v0.md (attached). It governs the
panel-writer-tape interface and SUPERSEDES ets-spec-v0 §8 where they differ.
Read it in full before writing another line of code.

## 1. New normative typings now in force (summary; the file is authoritative)

- ONE CONNECTOR SPECIES system-wide: clamped-measure boundary nodes coupled
  through the anchor star. Input tracks = fully clamped; the OUTPUT TAPE is
  the (N+1)-th track-typed node, progressively clamped (writing = the
  settlement clamping its own frontier cells; the MZ writer is this node's
  causal evaluation order, not a separate mode); the PANEL is a clamped
  measure on role space (knob leans = hand-set mass; the h-transform tilt is
  the induced Doob conditioning, not an added mechanism). Generalized I-7:
  no other intervention species may exist.
- NO DECODER: no readout head, render-policy net, or world-to-audio
  translation layer. The tape-node's coupling IS the output; render executes
  its schedule; the coupling is the provenance record (discharges I-12).
- NO SELF-INGESTION: the tape-node has read/write traffic but zero structural
  authority — it may never spawn anchors. Anchor growth from input material
  only, frozen at world-freeze.
- NO STATIC KEYMAP: unit-to-slot selection is decided per slot by the
  settlement. Any fixed unit->slot table is a second authority.
- KNOB SCALING derived, not hand-set: lambda_i = u_i / sigma_phi_i with
  sigma from the untilted-writer calibration pass (registered instrument;
  re-run on anchor spawn/prune). Any hand-set lambda constant dies.
- AMORTIZER = ORACLE ONLY (EBR FIX-1 conventions inherited by reference):
  DeepSets-equivariant over anchors, amortization-gap trained from replay,
  dual-estimator standing check, auto-quarantine on divergence. Deleting it
  changes wall-clock only, never the settled schedule.
- LATENCY typed honestly: writer runs L bars ahead of playhead (declared,
  pre-registered per hardware profile). Cold-solve deadline miss = WALL.
  Shipping unverified oracle guesses / reducing frontier resolution under
  load = named patch signatures.
- New CI tests required: C-1 (same schedule + different knob values =>
  bit-identical audio), C-2 (machine-precision gauge invariance of every
  phi statistic), C-3 (static check: panel reaches the writer only via the
  Layer-0 map).

## 2. RETRO-AUDIT (do this FIRST, before any new build work)

Inventory everything built in this session so far. Classify every existing
module/decision as mechanism / instrument / oracle / control under the new
typings. Then hunt specifically for these, which the pre-connector spec left
underdetermined and a reasonable builder may have improvised:

  a. any decoder/readout/render-policy structure between world and audio
  b. any control path into the writer other than the Layer-0 tilt map
  c. any hand-set knob-scaling constants
  d. any fixed unit-to-slot mapping table
  e. any pathway by which output/tape data could reach anchor growth
  f. any deadline-pressure shortcut (iteration caps, resolution reduction)

For each finding: WIPE or RE-DERIVE under the new authority. Sunk cost is
explicitly not a consideration — an hour of work embodying (a)-(f) is an
hour of gambiarra and is treated per the manifest. Report the audit as a
table (component, classification, verdict, action) BEFORE resuming.

Hand the audit table to ets-auditor for a verdict. Resume building only on
PASS.

## 3. Then resume build order

Continue ets-builder step sequence with the connector layer slotted at
steps (f)/(g): Layer-0 tilt map + C-1..C-3 tests land WITH the streaming
writer; calibration pass (sigma_phi) lands at world-freeze; amortizer +
dual-estimator land only after the cold path is correct and gated (oracle
after truth, never before). Panel work (PySide6, six lanes exhaustive, MIDI
CC learn, meter jacks) remains at step (g) and must consume the panel-as-
boundary-measure typing, not a bespoke control API.

## 4. Standing expectations (unchanged, restated once)

Walls are information: STOP, re-derive from first principles, present
divergence as a proposed spec revision. Anticipated WALL: the Hankel
construction for anchor growth (known load-bearing ambiguity inherited from
the EBR program) — hitting it and reporting it is a GOOD outcome; papering
over it is not. Prereg before any gate run; registry append-only,
commit-before-run; every session report ends with coverage honesty (what
exists vs what the spec describes), invariants touched, and what the auditor
should scrutinize. No green dashboards built on shims; deliver the truth.
