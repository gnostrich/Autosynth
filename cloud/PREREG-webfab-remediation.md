# PREREG — web fabrication-class remediation (2026-07-18)

Status: **pre-registered before build**, per standing law ("prereg before build,
auditor PASS before merge, walls surfaced not patched"). This entry is committed
before the code changes it governs.

## Governing rule (operator directive, quoted verbatim, the sign-off for this prereg)

> "Every surface either shows REAL data (backed by the engine) or is disarmed/blank
> and honestly labeled. No decorative content under a caption that asserts a data
> source. Real-or-absent, per surface."

Rollback surface: git tag `pre-webfab-remediation-2026-07-18` at HEAD `b054411`
(created before any edit). Core (`ets/`, `architecture-v6/ets/`) stays ZERO-DIFF —
this is a web/display-layer fix only; every engine quantity is READ via the bridge,
never by editing an engine `.py`.

## Scope

Three read-only-audited surfaces in `cloud/companion/static/index.html` assert more
than their data supports (fabrication class; the tape is a REPEAT of the prior
sine-art scar). Editable surfaces only: `cloud/companion/*`, `cloud/tests/*`,
`scripts/build_ledger.py` + `LEDGER_DATA.json` (doc generator). Transport uses the
existing telemetry frame (`StreamPlayer.telemetry` → `/api/telemetry` SSE, already
`json.dumps(p.telemetry)`) — NO new endpoint, NO new engine call.

## The three fixes

### Fix 1 — Output Tape waveform (F1, repeat scar): REMOVE, honest-empty
- `buildWave()` (the `Math.sin` cosmetic fill of `#wav`) is DELETED entirely.
- The tape shows an HONEST-EMPTY state ("waveform not wired"); no replacement art.
- The "settled render" clause is STRIPPED from the caption. Playhead/clock stay
  (they are real: `applyTelemetry → updateTape(d.t)`), correctly labeled
  ("playhead from telemetry").

### Fix 2 — Lane Console: real-or-absent, sliders were inert + hardcoded
Investigation (verified by running the bridge on `demo.etsworld`): the engine's
per-bar Layer-0 statistics `r.phi` (`ets/writer/phi.py`) are REAL and live —
`region` (M-vector), `cont`, `novelty` (∈[0,1]), `density`. The bridge already
holds `r` (the `BarResult`). All four console lanes are therefore WIRED to real,
intrinsically-bounded [0,1] reductions of produced state (same read-only pattern
as `roles`/`nowplaying`), transmitted in the telemetry frame:
- **region** → occupancy concentration `(peakshare − 1/M)/(1 − 1/M)` of `phi.region`.
- **continuity** → `phi.cont / n_placements` (share of the bar's content continuing
  a real source run).
- **novelty** → `phi.novelty` (already recency-weighted reuse ∈[0,1]).
- **density** → filled-slot fraction `#filled_slots / s_phase`.

The inert `<input type=range>` control affordance is REMOVED (the web has exactly
ONE control — the field/region-tilt; a per-lane "weight" control never existed).
Lanes become read-only bars. The section caption "display · tolerances & weights"
(the false control claim) → "display · live arrangement statistics (read-only)".
No hardcoded number remains; the `62/74/33/55` literals are deleted. A lane with no
telemetry value yet reads "—" (honest-absent), never a placeholder number.

### Fix 3 — "drift" meter (E1): WIRE real LOOP, honestly DISARM SLIDE
The mislabeled proxy `(max−min of roles)*1.4` is DELETED. The real gauge-drift split
lives in `architecture-v6/ets/meters/` (`gauge_slide`, `gauge_loop`, `holonomy`).
Investigation (verified by running):
- **LOOP[g]** — `ets.meters.gauge_loop.loop_g(O, s_phase)` is a read-only functional
  of the committed settled occupancy `r.O` the bridge already holds. Fed a BOUNDED
  trailing window of committed `O` (deque maxlen=W=16; respects I-8 — bounded state,
  bounded cost ~1.7ms/bar), it returns a REAL, live, nonzero antisymmetrized cycle
  holonomy (≈±0.004 on the demo world; moves with steering). WIRED, displayed as the
  engine's own signed reading. loop = the incorruptible holonomy quantity.
- **SLIDE[g]** — `ets.meters.gauge_slide` reads the per-bar GAUGE FRAME (transpose,
  phase). On any v0 world the writer holds the frame at the IDENTITY every bar
  (`stream.py`: "v0: frozen identity frame"; `realize.py`: "emitted gauge is
  IDENTITY"). Verified: `writer.frame.transpose/phase` set = {0.0} for all bars, so
  slide is STRUCTURALLY, PERMANENTLY ZERO. This is a documented ENGINE construction
  WALL (see `gauge_slide.py`: "absent-by-construction on any v0 world"), NOT a
  transmission wall. Honest outcome: SLIDE is DISARMED ("—", labeled "gauge frame
  identity (v0)"). The bridge computes slide honestly and auto-arms ONLY if the
  frame ever moves — so this disarm is measured, not hardcoded.

SLIDE and LOOP are shown as a read-only pair, NEVER collapsed into one "drift"
number. Both read engine state; neither enters settlement (I-5/I-14).

**Divergence disclosure (one sentence):** the directive's PREFERRED path was
"transmit real SLIDE and LOOP"; SLIDE is transmitted but reads honest-disarm because
the shipped v0 world's gauge frame never slides (a real engine construction wall,
surfaced not patched), while LOOP is fully wired and live.

## Guard design (WEB-FAB-1 / WEB-FAB-2), standing, both must BITE

`cloud/tests/test_web_fab_guard.py`, in the style of the WEB-FIELD-INV transitive
checker: a caption→data-source map over `index.html` (static analysis).
- **WEB-FAB-1** — a caption asserting a live data source that is backed by a
  synthetic/hardcoded/placeholder value FAILS. Mechanism: (a) a HARD-BAN of the three
  remediated scar phrases ("settled render", "tolerances & weights", the "drift"
  meter label) — they may never reappear; (b) every data-claim caption that legitimately
  remains must be in an ALLOWLIST map naming its real telemetry/world backing symbol,
  and that symbol must exist in the telemetry/world apply path (unregistered new
  data-claim caption → FAIL). Biting fixtures: a synthetic-literal value under a data
  caption → FAIL; an unregistered data caption → FAIL.
- **WEB-FAB-2** — no `Math.sin/cos/random` may feed a surface captioned as engine
  output. Mechanism: a function that WRITES a data surface (e.g. `#wav`, a meter/lane
  value) may not contain procedural-art math. Biting fixtures: `Math.sin` feeding a
  data-captioned `#wav` writer → FAIL; layout-geometry `Math.sin` positioning dots on
  a caption-less chrome canvas (`#ambient`) → ALLOWED.

## Invariants touched / how tested
- I-5 / I-14 (read-only meters, no F dependency): loop/slide/φ are read-only reductions
  of produced state; audio stays byte-identical (existing `test_stream_decode`), and
  the single settlement lane stays one `set_region` call site (existing WEB-FIELD-D).
- I-8 (bounded state): the loop/frame windows are `deque(maxlen=16)` — bounded by
  material, not time.
- WEB-FIELD-INV: no field input handler is added/changed; `node --check` + the
  transitive checker stay green. The render smoke gate is extended for the three
  remediated surfaces.

## Walls anticipated
1. SLIDE structurally zero on v0 (CONFIRMED wall) → honest-disarm + this report.
2. If `loop_g` were too costly for the realtime path → would fall back to a coarser
   cadence. (NOT hit: measured ~1.7ms/bar at W=16.)

## Kill / acceptance
Full `cloud/tests` suite green (145 baseline + new guard + extended smoke); both
WEB-FAB guards proven to bite; caption sweep shows zero surfaces asserting more than
their data; core `ets/` + `architecture-v6/ets/` zero-diff. Auditor PASS required
before any commit (orchestrator commits after audit).
