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
