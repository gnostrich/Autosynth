# PREREG — AUTOSYNTH LIVE MODE (deck playback + landscape bridges)

Registered **BEFORE** any code change, per the operator's sequencing ruling.
Kill conditions are stated below: **LM-1 / LM-2 failing ⇒ carrier redesign, no
mode work.** Nothing in Part B may be built until Part A's checks are green and
committed.

Companion REGISTRY entry: `live-mode-2026-08-13` (root `REGISTRY.jsonl`).

---

## 1. THE DIRECTIVE (operator, 2026-08-13, verbatim)

> AUTOSYNTH — LIVE MODE (deck playback + landscape bridges) — NEW THIRD TAB
> Engine-adjacent prereg + UI build. Additive only: GRID and TRACKS retained
> untouched (regression-fixtured). Log to LEDGER; REGISTRY entry before build.
>
> PLACEMENT (operator ruling: incremental, version-controlled)
> Tab trio: [ GRID ] [ TRACKS ] [ LIVE ]. Existing views byte-untouched. V-1
> switch-reset law extends to LIVE (all its walls + leans drop to the neutral
> state on any switch; entering LIVE starts clean). Default = GRID. All work
> lands as its own commits/train with REGISTRY + VERSION_LEDGER entries; no
> edits inside GRID/TRACKS code paths (guard fixture LM-0).
>
> CONCEPT
> A music player with a landscape bridge. STRAIGHT: the chosen track plays
> linearly, start-to-finish, like a normal player — realized as the engine tape
> under a FULL FENCE (bars pinned to that track's consecutive slices). CLICK a
> spot in any lane: the fence OPENS on a schedule while a character lean toward
> the clicked moment switches on; the engine mixes its way across the corpus
> (settlement + casting untouched, restricted candidate sets only). ARRIVAL: the
> fence CLOSES onto the destination track at the clicked spot; straight play
> resumes there. One engine, one audio path, always.
>
> PART A — THE CLAMP CARRIER (engine-adjacent; prereg first)
> A-1 SANCTIONED SECOND CARRIER: ClampTerms — feasible-set restriction (T4)
> delivered to the writer alongside TiltTerms. ONE construction point; anything
> else is a TypeError (mirror of I-1).
> A-2 NEUTRAL LAW: absent/neutral ClampTerms => output byte-identical to no
> carrier (mirror of the tilt neutral law). Prove before any mode work proceeds.
> A-3 CONTENT: per-bar candidate-set restriction, expressible at least as
> (track, slice-range) pins and per-track masks with a scalar openness in [0,1]
> (1 = fully fenced to the pin, 0 = no restriction). Openness schedule is DATA
> on the carrier, not engine logic.
> A-4 TYPING: unit/time targets are LEGAL on this carrier (walls are human
> content by census). They remain FORBIDDEN on the tilt carrier — WS-8 / JV-4
> stand absolute on the tilt path. State this split in the carrier docstring.
> A-5 SAMPLER PROTECTED: casting runs unchanged over the restricted set;
> settlement solver unchanged. No new energies, no new dynamics.
>
> PART B — THE LIVE MODE (UI + schedule, on the carrier)
> B-1 STRAIGHT PHASE: full fence to (track i, consecutive slices from position
> p). The lane shows a REAL playhead (real here because the clamp makes linear
> position true), moving glow. All other steering disabled in-view (hint:
> "straight play — click anywhere to travel").
> B-2 CLICK = BRIDGE: destination (track j, time t). Two ramps, both data: fence
> openness 1 -> 0 -> 1 (source fence opens; destination fence closes) on a
> TEMPO-SCALED schedule (N bars; N pre-registered once, never per-corpus tuned)
> + the existing w_r COLUMN lean toward the clicked moment's stored character
> (tilt carrier, sigma-clamped). Mid-bridge click: re-anchor exactly as JOURNEY
> law (last click wins, from current achieved state; momentum honest).
> B-3 ARRIVAL: destination fence fully closed at (j, t-onward slices); straight
> play from there. Arrival is the SCHEDULE completing; display must ALSO show
> achieved character convergence separately (see B-5) — never conflate the two.
> B-4 DISPLAYS: lanes read-only glow (placement telemetry, existing feed);
> straight phase = single-lane playhead; bridge = glow scattering and
> regathering. Journey bar = TWO stacked indicators, labeled:
>   schedule (the wall closing — human timetable)
>   achieved (character gap closing — telemetry)
> Divergence between them is honest information (corpus resisting the
> timetable), rendered, never smoothed.
> B-5 RECONSTRUCTION FIDELITY (honesty debt): measure straight-phase tape vs
> source audio once per world (byte-close metric, pre-registered threshold). If
> not exact: label "near-original playback" in-view. Never silently claim
> exactness.
> B-6 COPY: "a player with a landscape bridge — click anywhere to travel."
>
> CHECKS (each must bite)
> LM-0 additive-guard: GRID/TRACKS code paths byte-identical to current HEAD
> (regression fixture); LIVE ships as separate module(s).
> LM-1 carrier-neutral: neutral ClampTerms => byte-identical output.
> LM-2 carrier-typing: unit targets via TiltTerms FAIL TypeError; via
> ClampTerms PASS; single construction point enforced.
> LM-3 straight-truth: under full fence, emitted slices == the track's
> consecutive slices (fixture); playhead position derives from placements
> (telemetry), not a timer.
> LM-4 bridge-schedule-as-data: openness schedule arrives on the carrier; no
> schedule logic inside engine modules (static check).
> LM-5 dual-bar honesty: schedule bar from schedule data; achieved bar from
> profile telemetry only; frozen telemetry -> frozen achieved bar while schedule
> may advance (the divergence case renders).
> LM-6 fidelity-measured: reconstruction metric computed and stored per world;
> UI label matches the stored verdict (no hardcoded claim).
> LM-7 reset: view switch drops fences + leans to neutral (V-1 extended);
> re-enter LIVE = clean STRAIGHT-idle state (no resurrected walls).
> LM-8 tilt-path purity: WS-7/WS-8 rerun scoped to LIVE — no unit IDs, no
> audio/transport calls on the tilt path; the ONLY unit content rides
> ClampTerms.
>
> SEQUENCING (forcing proper version control — operator ruling)
> 1. PREREG commit: this file + REGISTRY entry (kill conditions: LM-1/LM-2
>    failing = carrier redesign, no mode work).
> 2. Train A (carrier) -> checks LM-1/2 green -> commit + ledger.
> 3. Train B (mode/UI) -> LM-0,3..8 green -> commit + ledger.
> 4. Deploy; report one page: checks table + fidelity verdict + what is NOT
>    claimed. Worktree closed.
>
> OUT OF SCOPE
> No crossfades/summing of two sources (never exists). No raw playback path. No
> per-corpus schedule tuning. No queued destinations. No changes to
> GRID/TRACKS/JOURNEY specs, sampler, F, world format (fidelity metric stored
> alongside, not inside, unless format already has a stats slot).

---

## 2. WHERE THE RESTRICTION LANDS (read from the code, before building)

The fiber choice is made in exactly one place:
`architecture-v6/ets/writer/realize.py::Realizer._choose(k, b, psi, bar)`
(dispatching to `_choose_original` / `_choose_fast`, bit-identical by
construction). It builds ONE list:

```
choices = [successor continuation (if any)] + index.candidates[(k, b)]
```

and then evaluates F's fiber energies + the tilt's soft field bias over that
list, drawing with the seeded rng.

**ClampTerms restricts `choices` — and nothing else.** The measure, the
energies, the gumbel draw, `place_slot`, the settlement solver and F are
untouched (A-5). This is the whole engine-side surface of Part A.

**Explicitly NOT the I-7 path.** `place_slot(clamp_unit=…)` already exists as a
HARD unit-demand clamp: it bypasses `_choose` entirely and emits one row at
neutral mass 1.0. Using it for LIVE would delete casting from the audio path —
exactly what A-5 forbids. LIVE never touches `clamp_unit`. Under a full fence
the candidate set is narrowed to one and **the unchanged casting measure still
runs over it** (argmax/draw over a 1-element set). One engine, one path.

### 2.1 The restriction rule (the only engine logic added)

Per bar, the carrier supplies `track_mask: {track_id -> m in [0,1]}` and a
scalar `openness in [0,1]`. A candidate survives iff

```
track_mask.get(track_of(candidate), 0.0) >= openness
```

plus, when a slice-range pin is present, its unit must lie in the pinned range.
This is one comparison — monotone in `openness`, with **no schedule logic in the
engine**: the ramp is a sequence of (mask, openness) values authored upstream
(LM-4 static check).

- `openness = 0` ⇒ every mask value ≥ 0 ⇒ **no restriction** (the neutral law).
- `openness = 1` ⇒ only mask-1.0 tracks survive ⇒ **full fence**.
- Intermediate ⇒ a widening ring of tracks, admitted in mask order.

**Polarity note (naming, stated so nobody misreads it):** the directive's word
is `openness` and the directive's definition is `1 = fully fenced, 0 = no
restriction`. That reads inverted against the English word. The carrier keeps
the operator's name **and** the operator's polarity verbatim, and the docstring
states both, so the ramp `1 -> 0 -> 1` means *fenced → free → fenced* exactly as
the directive describes it.

**The continuation entry is fenced too.** The successor candidate is inside
`choices`; if it were exempt, straight-truth (LM-3) would leak across tracks.

**Starvation is disclosed, never silent.** If the fence would empty the choice
set, the bar's fence is recorded as `STARVED` in telemetry and the unrestricted
set is used for that bar. No fabricated unit, no silent no-op, and the UI can
render the starve. (Wall candidate; if it fires on real corpora it gets
surfaced, not tuned away.)

## 3. PRE-REGISTERED CONSTANTS (fixed here, never per-corpus tuned)

| constant | value | meaning |
|---|---|---|
| `N_BRIDGE_BARS` | **8** | total bridge length in bars; tempo-scaled by construction (bars, not seconds) |
| ramp shape | **linear in bars**, `1 → 0` over bars 1–4, `0 → 1` over bars 5–8 | source fence opens, destination fence closes |
| mask handover | at the **midpoint** (start of bar 5) the mask swaps source→destination | the one discontinuity, in DATA |
| `FIDELITY_EXACT` | rel-L2 **== 0.0** | straight-phase tape is bit-exact to the source span |
| `FIDELITY_NEAR` | rel-L2 **≤ 0.05** | label "near-original playback" |
| above `FIDELITY_NEAR` | — | label "reconstruction (not original playback)" |

Any later change to these is a new prereg amendment, signed by the operator —
never a per-corpus adjustment.

## 4. INTERPRETATION FLAGGED FOR THE OPERATOR (not silently resolved)

A-4 says unit targets "remain FORBIDDEN on the tilt carrier". Taken globally
that would break a **shipped, operator-ratified feature**: the GRID field-bias
UNIT grain (`TiltTerms.channel_logbias {"unit": …}`, PREREG-field-bias-REV3),
which is how the field's unit squares steer today. LM-8 scopes the rule
explicitly — "WS-7/WS-8 rerun **scoped to LIVE**" — so this build reads A-4 as:

> **No unit or time target may leave the LIVE path on the tilt carrier.** LIVE's
> tilt payload carries `["col", r]` column leans and nothing else; a unit/time
> target offered to the tilt carrier *from the LIVE path* raises TypeError. The
> pre-existing GRID unit grain is untouched (that is LM-0).

If the operator intends the stronger, global reading (remove the ratified GRID
unit grain from TiltTerms entirely), that is a separate directive and a
regression of a live feature — it is **not** assumed here.

## 5. SCOPE GUARD

- **Touched:** `architecture-v6/ets/writer/` (new `clamp.py`; a restriction hook
  inside `_choose` only), `cloud/companion/` (LIVE routes/bridge schedule as
  data), `cloud/companion/static/` (LIVE view module), `cloud/tests/`, papers,
  ledgers, REGISTRY.
- **Never touched:** root `ets/` (byte-verified immutable), `ui-v6/` and other
  archival trees, F / `f.py` / LAMBDA, the settlement solver, `render/`, the
  world format, GRID/TRACKS code paths (LM-0), `place_slot`'s I-7 clamp.
- COMPANION_INVARIANTS R1–R5 unaffected: no new audio origin, no cloud decoder,
  privacy boundary unchanged, reset unchanged, fresh clone still self-contained.

## 6. KILL CONDITIONS

1. **LM-1 red** (neutral ClampTerms is not byte-identical) ⇒ carrier redesign.
   No Part B work. Disclosed, not patched.
2. **LM-2 red** (typing split not enforced at a single construction point) ⇒
   carrier redesign.
3. **LM-0 red** at any point (GRID/TRACKS bytes moved) ⇒ revert, the build is
   not additive.
4. If straight-phase reconstruction is not exact, the UI **says so** (B-5/LM-6).
   Claiming exactness on a measured non-exact reconstruction is a fabrication
   and fails the build outright.

## 7. STATUS

- **Step 1 (this commit): registered.**
- Step 2 Train A (carrier + LM-1/LM-2): pending.
- Step 3 Train B (mode/UI + LM-0, LM-3..LM-8): pending.
- Step 4 deploy + one-page report (checks table, fidelity verdict, what is NOT
  claimed): pending.

---

# AMENDMENT 1 — NATIVE PACE (v0)

Operator, 2026-08-13. Supersedes the B-2/B-3 schedule mechanics registered
above, and retires §3's `N_BRIDGE_BARS` / ramp-shape constants with them.

## A1.1 The amendment (verbatim)

> AMENDMENT to ets-directive-live-deck-mode — NATIVE PACE (v0)
> Incremental; supersedes B-2/B-3 schedule mechanics. Log to LEDGER.
>
> 1. B-2 REVISED — NO TIMETABLE: on click, source fence RELEASES (openness
>    -> 0 by the existing global slew, no N-bar schedule) + w_r column lean
>    latches (unchanged). Bridge duration is EMERGENT: the corpus's own
>    inertia under the committed tape. No new constants anywhere.
> 2. B-3 REVISED — ARRIVAL BY CONVERGENCE: destination fence closes when
>    the achieved-vs-target character gap falls under the MEASURED NOISE
>    FLOOR (the existing pre-registered floor convention; no new threshold).
>    Stall/plateau renders honestly (corpus has no road); no timeout that
>    fakes arrival.
> 3. B-4 REVISED — SINGLE journey bar (achieved gap only); the dual bar is
>    retired with the schedule. LM-5 replaced: bar derives from profile
>    telemetry only; frozen telemetry -> frozen bar; stall renders as stall.
> 4. LM-4 re-scoped: openness transitions ride the carrier as data (release
>    + convergence-close events); still no schedule logic in engine modules.
> 5. FUTURE (not built): optional fixed-length transition (N bars, one
>    registered knob) as a separate amendment if performers want it.
> Fidelity label (B-5/LM-6) unchanged. Everything else stands.

## A1.2 What this retires

- **`N_BRIDGE_BARS = 8`, the linear ramp shape, and the midpoint mask swap
  are RETIRED.** They are struck from §3 and must not appear in any module.
- **The dual journey bar is RETIRED.** One bar: achieved gap only.
- **LM-5 is REPLACED** by: the bar derives from profile telemetry only; frozen
  telemetry ⇒ frozen bar; a stall renders **as a stall**, never as progress.
- **LM-4 is RE-SCOPED**: the carrier now carries *events* (release,
  convergence-close) rather than a ramp table. Engine modules still contain no
  schedule logic — the static check stands, now against event data.

The carrier itself (Part A / Train A) is **unchanged**: it still carries
per-track masks + `openness` + pins as data. Only who moves `openness`, and
when, changes — and that mover is upstream of the engine either way.

## A1.3 WALL SURFACED — "the existing global slew" is not running in the web path

Read from the code, not assumed:

- `architecture-v6/ets/panel/envelope.py::RegionSlew` **exists** and is the
  registered slew law (bounded-rate follower, `SLEW_MAX_STEP = 0.20` per emit,
  registered under PREREG-uiv5-padfeel BUG-1).
- It lives in the **panel** package. `cloud/companion/` — the web instrument
  this build ships — **does not import or run it**. Grep for `slew` across
  `cloud/` returns nothing. The web path has no live slew law today.

So "the existing global slew" cannot be *referenced*; it can only be
**adopted**. This build adopts it, which honors "no new constants anywhere"
(the constant is pre-existing and registered) — it does **not** invent a rate:

> LIVE's `openness` release follows `RegionSlew`'s registered law and its
> registered `SLEW_MAX_STEP = 0.20`, applied at the LIVE path's own emit
> cadence (per bar, the cadence at which the carrier is rebuilt), not the
> panel's 30 Hz timer.

**Honest consequence, disclosed not tuned:** because the cadence differs, the
wall-clock release time differs from the panel's ~80–150 ms feel. At one emit
per bar, a full release (1.0 → 0.0 at 0.20/emit) takes 5 bars of *release*, and
the bridge's total duration remains emergent (the corpus's inertia dominates).
This is **measured and reported** in the Train B report, never adjusted to hit a
target feel. If the operator wants a different cadence or rate, that is a new
amendment with a registered knob (their item 5), not a silent tune.

## A1.4 The convergence criterion (B-3) — which existing floor, stated

The repo holds two pre-registered floor conventions. The amendment says
"the MEASURED NOISE FLOOR (the existing pre-registered floor convention)":

- the **participation-ratio floor** `(Σw)²/Σw² ≥ 2` (`anchors.py::effective_rank`,
  live as `fieldClearsFloor`) — a floor on a *weight vector's* effective support;
- the **measured-fluctuation floor** σ (the σ_φ calibration convention) — a floor
  on a *scalar quantity's* own untilted fluctuation.

The arrival criterion compares a **scalar gap** (achieved character vs target
character), so the fluctuation convention is the one that types:

> **ARRIVAL** iff the achieved-vs-target gap on the column-share telemetry
> (`fieldColShares`, the same reduction the D-1 role strip already reads) falls
> **below that telemetry's own measured bar-to-bar fluctuation**, measured on
> this world under no lean. Measured first, compared second. No new threshold
> constant is introduced; the floor is a measurement.
> **STALL** = the gap plateaus above its own floor. It renders as a stall
> ("corpus has no road"). There is **no timeout and no fake arrival**.

Flagged for the operator: if they meant the participation-ratio floor instead,
say so — it is a one-line change to the criterion, and it is not assumed here.

## A1.5 Amended check list

| check | status after Amendment 1 |
|---|---|
| LM-0, LM-1, LM-2, LM-3 | unchanged |
| **LM-4** | re-scoped: release + convergence-close arrive as carrier **events**; static check still forbids schedule logic in engine modules |
| **LM-5** | **replaced**: single bar from profile telemetry only; frozen telemetry ⇒ frozen bar; stall renders as stall (deliberate-violation fixture must bite) |
| LM-6, LM-7, LM-8 | unchanged |
| **new LM-9** | **no-timetable check**: no `N_BRIDGE_BARS`, no ramp table, no timeout anywhere in the LIVE path; a planted timeout-to-arrival must FAIL the check |

## A1.6 Operator rulings on the two flags (2026-08-13) — both CONFIRMED

**Ruling 1 — slew adoption: approved as built.** Adopting the registered law and
its registered constant at LIVE's cadence, then *measuring* the resulting feel,
is the correct procedure; inventing a new rate because the panel's is not wired
into the web path would have been the hand-set-constant class. The feel
divergence is **a measurement to report, not a defect to fix**. If the measured
feel is too slow for the deck, the item-5 fixed-length knob arrives through the
front door as its own registered amendment — *later, based on the number*.

**Ruling 2 — floor: fluctuation reading confirmed, no switch.** The type-check
settles it: the participation-ratio floor answers a *rank* question ("how many
directions are real in a vector's spread" — it sizes M and k). Arrival is a
*scalar convergence* question. The fluctuation floor is definitionally the one
that types; participation-ratio would have been a category error on a scalar.

> **"Arrived" = "the remaining distance is smaller than the breathing."** You are
> there when the difference between here and the destination is no more than the
> music's own natural wander.

Consistency argument recorded with it: at arrival the fence closes and straight
play resumes, and that transition is seamless **precisely because** the residual
gap is sub-wobble.

### A1.6.1 STANDING REQUIREMENT FOR TRAIN B (operator)

With the timetable retired, **the plateau is now the only failure mode the user
ever sees.** Native pace means *the corpus is allowed to say no*. Therefore the
stall rendering — and the "corpus has no road" note — is built with **the same
care as the happy path**: it is a first-class state, not an error branch. It
gets its own must-bite fixture (LM-5), its own copy, and its own visual
treatment. A stall that renders as vague progress, or as a bug, fails the train.

### A1.6.2 INCIDENTAL FINDING BANKED (separate from LIVE)

The panel-package slew never having been imported in `cloud/` implies **the web
sliders may not be slew-limited at all** — a spec-vs-web divergence. Banked here
for the next deadweight/faithfulness sweep; **explicitly out of scope for LIVE**
and not to be fixed opportunistically inside this build.

---

# AMENDMENT 2 — LIVE IDLES SILENT

Operator, 2026-08-13. Incremental; adds B-0 and amends B-1.

## A2.1 The amendment (verbatim)

> AMENDMENT 2 to ets-directive-live-deck-mode — LIVE IDLES SILENT
> Incremental. Log to LEDGER.
>
> 1. B-0 (new) IDLE STATE: entering LIVE = SILENT. No fence set => no play
>    (transport-gated hold), NOT free settlement — the unfenced blend must
>    never sound in LIVE. Lanes render (given audio waveforms), glow dark,
>    hint: "click a spot to start playing from there."
> 2. B-1 amended — FIRST CLICK = IMMEDIATE START, NO BRIDGE: from idle
>    silence there is no source state to travel from; the fence closes at
>    (track i, spot t) and straight play begins there at once. Bridges
>    apply only from the second click onward (a playing state exists).
> 3. Check LM-9 idle-silence: in LIVE with no fence, zero slices are cast
>    and the tape does not advance (fixture); any unfenced settlement
>    audible in LIVE FAILS.
> 4. Check LM-10 first-click-immediacy: from idle, click => straight play
>    begins within one bar at the clicked spot; no bridge machinery, no
>    lean emitted (fixture asserts tilt payload neutral on first click).
> V-1 reset unchanged: leaving LIVE drops the fence; re-entering = idle
> silence again. Everything else stands.

## A2.2 CHECK-NUMBER COLLISION — resolved by renumbering MINE, not the operator's

Amendment 1's register (§A1.5) introduced a check I numbered **LM-9**
(no-timetable check). The operator's Amendment 2 assigns **LM-9 = idle-silence**
and **LM-10 = first-click-immediacy**. The operator's numbering is authoritative.

- **LM-9** = idle-silence (operator)
- **LM-10** = first-click-immediacy (operator)
- **LM-11** = the no-timetable check (renumbered from my LM-9; content unchanged:
  no bridge-length constant, no ramp table, no timeout anywhere in the LIVE
  path; a planted timeout-to-arrival must FAIL)

## A2.3 DESIGN CONSEQUENCE — idle is TRANSPORT, not a carrier state

This is the substantive point in B-0 and it must not be misbuilt:

Under the registered fence rule (`track_mask.get(track, 0.0) >= openness`), a
**neutral / absent carrier means NO restriction** — i.e. the *free unfenced
blend*, which is exactly what B-0 forbids from sounding in LIVE. So:

> **Idle silence CANNOT be expressed as an empty or neutral ClampTerms.** It is a
> **transport-gated hold**: in LIVE with no fence, the produce loop does not cast
> slices and the tape does not advance. Nothing is rendered, so nothing can
> sound.

Two things this protects:

1. **LM-1 stays intact.** The neutral-carrier law ("neutral ⇒ byte-identical to
   no carrier") remains a statement about the *engine*, untouched by LIVE's idle.
   Had idle been built as "empty fence = silence", the carrier's neutral meaning
   would have been overloaded with a second, contradictory sense.
2. **No new muting path.** Silence comes from *not producing*, not from a gain of
   zero, not from a mute, not from a fabricated empty buffer. The existing
   transport hold is the mechanism.

## A2.4 FIRST CLICK EMITS NO LEAN

B-1-amended plus LM-10: from idle there is no source character to travel *from*,
so the first click closes the fence and starts straight play — **and emits no
tilt payload at all** (the fixture asserts the tilt payload is neutral on first
click). The w_r column lean latches only from the **second** click onward, when a
playing state exists to bridge from. The bridge machinery is not merely skipped
visually on the first click; it is not engaged.

## A2.5 Amended check list (current, after both amendments)

| check | meaning |
|---|---|
| LM-0 | additive-guard: GRID/TRACKS byte-identical; LIVE in separate modules |
| LM-1 | carrier-neutral: neutral ClampTerms ⇒ byte-identical output **(kill)** |
| LM-2 | carrier-typing + single construction point **(kill)** |
| LM-3 | straight-truth: full fence emits the track's consecutive slices; playhead from placements, not a timer |
| LM-4 | schedule-as-data, re-scoped to release/convergence **events**; no schedule logic in engine modules |
| LM-5 | single journey bar from profile telemetry only; frozen telemetry ⇒ frozen bar; **stall renders as stall** |
| LM-6 | fidelity measured + stored per world; UI label matches the stored verdict |
| LM-7 | V-1 reset extended to LIVE; leaving drops the fence; re-entering = idle silence |
| LM-8 | tilt-path purity scoped to LIVE (WS-7/WS-8) |
| **LM-9** | **idle-silence: no fence ⇒ zero slices cast, tape does not advance; any unfenced settlement audible in LIVE FAILS** |
| **LM-10** | **first-click-immediacy: idle ⇒ straight play within one bar at the clicked spot; no bridge machinery, tilt payload neutral** |
| **LM-11** | no-timetable (renumbered from Amendment 1's LM-9) |

---

# AMENDMENT 3 — RATCHET GLIDE (default bridge)

Operator, 2026-08-13. Applies on top of Amendments 1 (native pace) and 2 (idle
silent). Sampler / F / world untouched; engine modules untouched.

## A3.1 The amendment (verbatim)

> ## THE LAW (operator ruling)
> Bridges may wander sideways, never backwards. As a journey runs, track
> best_gap = the smallest achieved-vs-target character gap reached so far.
> The admissible region for subsequent bars is a CORRIDOR:
>     gap(bar) <= best_gap + slack,   slack = the registered fluctuation
>     noise floor for this world (the wobble) — NO new constant.
> Progress locks in; roaming, texture, and breathing continue INSIDE the
> corridor (slack >= natural bar-to-bar wobble by construction, so idle
> breathing never triggers the ratchet). Cadence = the settle tick / bar,
> NEVER beat-level; the ratchet lives in character space and never clips,
> snaps, or edits audio.
>
> ## MECHANISM (mode-level policy, carrier as the only mechanism)
> R-1 Per bar, the LIVE mode computes a candidate mask admitting material
>     whose settled character keeps gap <= best_gap + slack, and ships it
>     as ClampTerms data (the existing carrier; walls as mechanism). No
>     ratchet logic inside engine modules — the mode computes, the carrier
>     carries (mirror of LM-4).
> R-2 best_gap updates ONLY from achieved-profile telemetry (monotone
>     non-increasing); never from a clock, schedule, or easing.
> R-3 Stall honesty preserved: no road within the corridor at the current
>     best_gap => the corridor simply stops tightening; the existing stall
>     rendering applies. The ratchet NEVER force-splices (that remains
>     timed mode's explicit, separate, future business).
> R-4 Scope: bridges only. Straight phase, first-click start, idle
>     silence, arrival rule (gap under floor), V-1 reset — all unchanged.
>     On re-click mid-bridge, best_gap RESETS to the new journey's start
>     gap (fresh corridor; no carried ratchet across destinations).
> R-5 Default: ratcheted glide is the bridge default. Pure native glide
>     (no ratchet) remains available as a registered mode flag for
>     comparison/measurement, not exposed in UI v0.
>
> ## CHECKS (each must bite)
> RG-1 telemetry-only tightening: corridor bound derives from best-achieved
>      gap + registered floor ONLY; a fixture advancing a clock with frozen
>      telemetry must show a frozen corridor; any time-driven tightening
>      FAILS.
> RG-2 breathing preserved: with a stationary target and converged state,
>      natural wobble must never trigger mask churn (fixture: idle at
>      arrival; corridor stable; no candidate flapping).
> RG-3 no-backwards: a fixture forcing a would-be regression beyond
>      best_gap + slack must show those candidates masked; sideways motion
>      within the corridor must remain admissible (both directions of the
>      assertion bite).
> RG-4 no-splice: ratchet active + no admissible road => stall renders;
>      fence does NOT close; no timeout arrival.
> RG-5 reset: mid-bridge re-click resets best_gap (fixture); view switch
>      drops everything per V-1/LM-7 (extended to ratchet state).
> RG-6 engine-purity: static check — no ratchet/corridor logic in engine
>      modules; carrier data only.
>
> ## OUT OF SCOPE
> Alternation/pins (composition, step 2 — parked). Timed glide (separate
> future amendment; allowed to splice out loud when it comes). Cut-hardness
> dial. Any UI knob for slack (it IS the registered floor; not tunable).

## A3.2 Register — what this does and does not disturb

**The mechanism is already built.** Train A's carrier takes exactly the data
this needs: `clamp0(track_mask={tid: m}, openness=…, unit_pin=…)`. The corridor
is a per-bar `track_mask` computed by the MODE and shipped as carrier data. The
engine's `_admits` rule (`track_mask.get(track, 0.0) >= openness`) is untouched,
so RG-6 is satisfied by construction rather than by a new guard — the same way
LM-4 is.

**One floor, two uses, no new constant.** The registered fluctuation floor (the
wobble, confirmed over participation-ratio in §A1.6) now serves both:

| use | rule |
|---|---|
| arrival (B-3, Amendment 1) | `gap < floor` — the remaining distance is smaller than the breathing |
| corridor slack (Amendment 3) | `gap(bar) <= best_gap + floor` |

The second is why breathing can never trip the ratchet: slack **is** the
measured wobble, so a bar that only breathes is inside the corridor by
definition. RG-2 is the fixture that proves this rather than assuming it.

**Monotone by telemetry only.** `best_gap` is non-increasing and moves only when
achieved-profile telemetry says so (R-2). No clock, no schedule, no easing — the
same discipline that killed the timetable in Amendment 1. RG-1 is its must-bite.

**Ratchet ≠ splice.** R-3/RG-4: when the corridor has no road, the corridor
stops tightening and the **existing stall rendering** applies. The fence does
not close, and there is no timeout arrival. Force-splicing is explicitly the
future timed mode's business, "allowed to splice out loud when it comes".

**Scope is bridges only (R-4).** Straight phase, first-click start, idle silence,
the arrival rule and V-1 reset are all unchanged — so this amendment does **not**
disturb the playable milestone currently in flight (idle → click → straight
play). Mid-bridge re-click resets `best_gap` to the new journey's start gap: a
fresh corridor, no ratchet carried across destinations.

**Check namespace:** `RG-1..RG-6` is a new namespace and collides with nothing
in `LM-*`. No renumbering needed this time.

**R-5 flag:** pure native glide (no ratchet) stays available as a *registered
mode flag* for comparison and measurement, not exposed in UI v0 — a measurement
instrument, not a user knob. Slack itself is never a UI knob: it IS the
registered floor.

---

# AMENDMENT 4 — HARD FENCE (riders on the per-role widening fix)

Operator, 2026-08-13, approving the pure-fence fix (per-role widening WITHIN the
track) with three riders.

## A4.1 The riders (verbatim)

> Fix approved as pure fence (per-role widening within-track). Three riders:
> R1 HARD FENCE (must land with this fix): "reaches outside" = fence is
>    currently soft = the real breach. Assert: no cast outside ClampTerms
>    ever; starvation surfaces as fence-definition change or honest error,
>    never silent escape. New check LM-11: fixture with deliberately
>    starving fence must show in-fence handling or explicit error; any
>    out-of-fence cast FAILS.
> R2 LM-3 REVISED (honest, not deleted): STRAIGHT = forward-walking time
>    core + per-role admits. Assert (a) core window walks forward
>    monotonically and dominates; (b) off-window cast fraction measured +
>    logged per world, folded into the B-5 fidelity verdict and label.
> R3 FUTURE AMENDMENT LOGGED (not this train): STRAIGHT-EXACT — pin the
>    settlement occupancy to the window's stored role masses (Pi-clamp,
>    T4, A-3 carrier extension). Removes starvation at cause; restores
>    consecutive-slice exactness by construction. Prereg when Train B lands.
> B-5 labeling stance confirmed: measured, never sold as the original.

## A4.2 R1 REVERSES A CLAUSE I REGISTERED — recorded, not quietly swapped

Prereg §2.1 registered: *"if the fence would empty the choice set, the bar's
fence is recorded as STARVED in telemetry and the unrestricted set is used for
that bar."* That clause is **struck**. The operator is right that it made the
fence SOFT: a fence you can fall out of is not a wall, and recording the escape
does not make the escape legitimate. Disclosure is not permission.

**The new law:** no cast outside ClampTerms, ever. Starvation resolves as
either

1. a **fence-definition change** — the fence widens *explicitly, within its own
   terms* (the approved per-role widening within the track), or
2. an **honest error** — the bar refuses rather than escaping.

Casting nothing into a slot the fence cannot fill is *in-fence handling*
(silence is inside every fence). Reaching to another track is not.

## A4.3 CHECK-NUMBER COLLISION (second occurrence) — mine moves again

`LM-11` was my renumbered no-timetable check (Amendment 2 §A2.2, itself
renumbered from my original LM-9). The operator now assigns **LM-11 = hard
fence**. Operator numbering is authoritative, so mine moves again:

- **LM-11** = hard fence (operator, this amendment)
- **LM-12** = no-timetable check (mine, content unchanged since Amendment 1)

## A4.4 R2 — LM-3 revised, and why the fix is NOT a TRACKS duplicate

The operator caught the trap in my first proposal: fixing starvation with a
settlement lean would have rebuilt the TRACKS click inside LIVE — LIVE would
become "TRACKS plus a fence that mostly starves". Rejected.

The measured cause was narrower: the window was cut by **time only**. A bar's
settlement demands material by (role, band); eight consecutive slices often
contain no unit of a demanded role, so the fence emptied. The fix widens the
fence **within the same track** — for each demanded role, admit that track's own
nearest material of that role. Still one track, still walking forward, still a
pure fence, no lean, no settlement steer.

**LM-3 revised** (honest, not deleted):

| part | assertion |
|---|---|
| (a) | the core time window walks forward **monotonically** and **dominates** the bar's casts |
| (b) | the **off-window cast fraction** is measured and logged per world, and folded into the B-5 fidelity verdict and label |

Off-window here means *within the fenced track but outside the forward time
window* — never another track, which R1 forbids outright.

## A4.5 R3 — future amendment logged, NOT built in this train

**STRAIGHT-EXACT**: pin the settlement occupancy itself to the window's stored
role masses (a Π-clamp, T4, as an A-3 carrier extension). That removes
starvation *at cause* rather than absorbing it, and restores consecutive-slice
exactness by construction. To be pre-registered when Train B lands. Explicitly
not this train.

## A4.6 B-5 stance confirmed

Measured, never sold as the original. The off-window fraction from R2(b) feeds
the same verdict, so the label reflects what the reconstruction actually did.

---

# AMENDMENT 5 — THE BRIDGE IS THE POINT (operator, 2026-08-14, verbatim)

> To be unambiguous: the bridge is not an enhancement, it is the point of
> LIVE. Straight play with hard cuts is a music player; the landscape
> traversal is the instrument. LIVE is not shippable or demoable without it.
>
> Next train = the bridge, top priority, nothing else in it:
> - fence release on the adopted slew (no timetable, Amendment 1),
> - ratchet corridor (Amendment 3: best_gap + registered floor slack,
>   telemetry-only tightening),
> - arrival = in-metric gap under the fluctuation floor -> fence closes at
>   the destination; stall renders honestly when the corpus has no road.
>
> Two blockers to clear first, both cheap:
> 1. Hard fence green (LM-11): no cast outside ClampTerms under starvation.
>    Release/close mechanics sit on the wall holding.
> 2. Settle the in-metric floor (jump-immediate D2): the arrival gap and the
>    floor must be measured in the SAME metric — idle bar-to-bar wobble of
>    the journey's own distance. Otherwise the bridge will "arrive"
>    instantly and look abrupt for a second, unrelated reason.
>
> Current hard-cut behaviour stays as the honest jump end of the dial;
> label it in-view so nothing implies a transition is occurring yet.

## A5.1 Standing correction this amendment makes to my framing

I had been reporting the missing bridge as a later train alongside polish items.
It is not: without it LIVE is a player with cuts, and the traversal — the thing
the whole carrier was built to carry — does not exist. Recorded so the priority
is not re-litigated.

## A5.2 BLOCKER RESULTS (both cleared, measured)

**1. Hard fence (LM-11): GREEN.** Six checks pass — no cast ever leaves the
fence; starvation is surfaced not swallowed; the admitted (role, band) still
casts normally; fast and original stay bit-identical under a starving fence.
The wall holds, so release/close mechanics have something to sit on.

**2. In-metric floor (D2): MEASURED, and the operator's concern is confirmed.**
The journey's own distance is the L2 distance between achieved column-share
vectors. Measured bar-to-bar on an idle engine (23 bars):

| statistic | value |
|---|---|
| mean | 0.1591 |
| median | 0.1191 |
| sd | 0.0933 |
| p90 | 0.2860 |
| **floor = mean + sd** | **0.2524** |

The metric's diameter is √2 ≈ 1.41, so the idle wobble alone spans ~18% of the
whole space. **Any destination within 0.25 of the current character would read as
"arrived" on the very first bar** — an instant completion that looks like a cut
for a reason unrelated to the fence. Exactly the jump-immediate failure D2
predicted.

**Consequences fixed by this measurement, binding on the bridge train:**
- the floor is **measured per world at runtime**, in this metric, never a constant;
- the arrival test is `‖achieved − target‖ < floor` with **both sides in that one
  metric** — no mixing a gap in one space with a floor from another;
- a journey whose start gap is already below the floor is **not a journey**: it
  must render as an immediate jump and say so, rather than animating a bridge
  that was over before it began.
