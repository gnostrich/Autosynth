# PREREG — WAVEFORM SCRUB-TO-STEER as switchable second view (TRACKS)

**Date:** 2026-07-25 · **Status:** RATIFIED BY OPERATOR DIRECTIVE (the directive below is
the operator's own ruling, quoted verbatim; this prereg adds only the technical annex and
honest walls). Display + input-mapping layer ONLY; same two jacks; sampler/F/world/output
untouched.

## Operator directive (verbatim)

> AUTOSYNTH — WAVEFORM SCRUB-TO-STEER as SWITCHABLE SECOND VIEW
> Display + input-mapping layer ONLY. Same two jacks, no new engine entries.
> Sampler/F/world/output untouched. Log to LEDGER.
> PLACEMENT (operator ruling)
> The material surface gets TWO VIEWS in the SAME PLACE, switched by a small tab control:
> [ GRID ] [ TRACKS ]
> * GRID = the existing track x role cells view. NOT removed, NOT altered — it is the
>   machine-native view, the paper's deployed surface, and the faithfulness demonstration.
>   Untouched.
> * TRACKS = the new waveform-lane view (this directive). Both are front-ends to the SAME
>   two jacks; only one is visible at a time.
> VIEW-SWITCH LAW (operator ruling: reset for simplicity)
> V-1 On ANY view switch (either direction), ALL material-surface biases reset to neutral:
>   row/column/cell leans zeroed, scrub leans zeroed, payload = neutral carrier
>   (bit-identical to no carrier). No mapping, no carry-over, no attempted translation
>   between views. Clean slate.
> V-2 Reset applies to the material-surface jacks ONLY. Outboard (TEMP, etc.), eigen
>   strips, crate, transport are UNTOUCHED by view switches.
> V-3 The reset is instant and honest: no fade-out theater on the leans; the
>   decay-to-neutral follows the existing release/slew law, nothing else.
> V-4 Switch control is a small tab pair in the surface header. Persist last selected view
>   per session; default = GRID (paper-faithful default).
> TRACKS VIEW BUILD
> W-1 WAVEFORM LANES: one lane per track rendering the GIVEN audio's waveform (derived
>   from the user's file; given material, not engine telemetry — no fabrication class).
>   Row header keeps the existing row-lean gesture (scroll/drag up = amplify, down =
>   de-amplify, soft, saturating).
> W-2 SCRUB MAPPING: pointing/holding at time t on track i selects the beat-slice unit(s)
>   under the window at t (window = the slice grid, pre-registered). Compute w_r =
>   normalized soft role mass q(r | selected units) from the trained world's STORED
>   assignment (real values only). Emit through the EXISTING sanctioned casting-jack
>   entries: row bias (i) + cell biases (i,r) weighted by w_r. Sigma-clamped +
>   slew-limited per existing law. Soft, saturating, never a mute. Held = sustained lean;
>   release = existing decay law. NO unit-pinning (that would be a clamp; not exposed).
> W-3 ACHIEVED HEATMAP: read-only overlay per lane showing where the engine is ACTUALLY
>   drawing material from (real placement telemetry, same feed as grid glows). Scrub
>   point = force mark; heatmap = achieved mark. Two-marks law on the waveform.
> W-4 SAME-JACK EQUIVALENCE: scrub(i,t) payload must equal the equivalent manual row+cell
>   gesture payload in GRID view (fixture-asserted).
> W-5 COPY: "point at a part you love — the instrument leans toward what that part is
>   made of."
> NOT-A-PLAYHEAD LAW (safeguard — operator ruling)
> The scrub is a STEERING gesture, not a transport/playback gesture. Pointing at a moment
> does NOT play it, seek to it, audition it, queue it, or inject its units into the tape.
> The ONLY effect of the pointer is the bias payload of W-2. The only audio path in the
> app remains the engine's output tape (settlement + casting under the current leans).
> Explicitly forbidden:
> * any audio preview/monitor of the pointed region;
> * any transport seek keyed to the pointer;
> * any direct unit injection / queueing / pinning from pointer position (unit IDs must
>   NOT travel from pointer to writer; only the q-weighted row/cell biases do);
> * any "play from here" affordance on the lanes. If a preview feature is ever wanted,
>   it is a SEPARATE future directive with its own typing; it is out of scope here and
>   must not be improvised.
> CHECKS (each must bite)
> WS-1 mapping-honesty: emitted cell weights == stored q(role|unit) of the selected
>   slices (fixture with known assignment); invented/smoothed weights FAIL.
> WS-2 heatmap-honesty: heatmap derives from placement telemetry only; frozen telemetry
>   -> frozen heatmap; deleting heatmap leaves audio byte-identical.
> WS-3 same-jack: instrument the steer entry; scrub emits through existing casting-jack
>   lanes only; any new entry point FAILS type-check.
> WS-4 wall-respect: disarmed/degenerate lanes absent from scrub payload.
> WS-5 switch-reset: fixture applies biases in one view, switches view, asserts payload
>   == neutral carrier (bit-identical); switches back, asserts still neutral (no
>   resurrection of old biases).
> WS-7 not-a-playhead: replay a recorded bias-payload sequence with and without the
>   waveform-view pointer events attached; output tape must be byte-identical (pointer
>   affects audio ONLY via the payload). Static + runtime check: no audio API calls, no
>   transport calls, and no unit-ID arguments originate from the scrub path.
> WS-8 no-injection: instrument the writer inputs; assert no unit identifiers reach the
>   writer from the TRACKS view; a fixture attempting direct unit injection from pointer
>   position must FAIL type-check.
> WS-6 grid-untouched: GRID view behavior byte-identical to pre-directive build
>   (regression fixture).
> OUT OF SCOPE
> No settlement-lane changes (column-lean from a moment's profile = separate future
> directive). No crate changes. Eigen strips / outboard / transport untouched. No
> cross-view bias mapping (explicitly ruled out for now).

## Technical annex (implementation mapping — no new authority)
- **Jacks:** row lean → existing `channel_bias` (set_channel_bias); cell leans → existing
  `track_role_bias` (set_track_role_bias). Both already ride the ONE `/api/steer` route
  and the single TiltTerms carrier. The TRACKS view emits ONLY these.
- **Waveform + slice grid + q(r|unit):** a new READ-ONLY endpoint (`/api/wavemap`) serves,
  per track of the loaded world: (a) a downsampled peak envelope of the user's own audio
  file (given material), (b) the unit slice boundaries in track time (from the world's
  stored provenance/index — real spans only), (c) per-unit q(role) from the trained
  world's STORED soft assignment. Pure read; no engine state touched; cached per world.
- **Heatmap feed:** the existing nowplaying/track-role telemetry (`nowplaying`,
  `nowplaying_track_role`) mapped onto lane time via the same stored unit spans — the
  same feed the grid glows use, re-projected. Read-only.
- **View switch + reset:** FE-only state; on switch, the FE publishes the neutral payload
  (all four keys neutral — the existing byte-identical neutral carrier) before rendering
  the other view.
- **Privacy note:** the wavemap envelope derives from the session owner's own audio and is
  served under the same access as playing the set (a shared set's openers can already
  hear the audio; the envelope is a strictly weaker disclosure). Raw audio still never
  leaves the box except as the engine's output stream.

## Honest walls (disclosed up front)
- **q(role|unit) sourcing:** the directive requires the trained world's STORED soft
  assignment. If the stored provenance carries only a coarser assignment than per-unit
  (e.g. per-prototype), the mapping uses the finest STORED level and the gate fixture
  (WS-1) asserts equality against exactly that stored object — never an invented
  refinement. If NO stored soft assignment exists at any usable level, the build STOPS
  and reports the wall (no fabricated weights).
- **Slice window:** the "window at t" is the stored unit span(s) containing t — the
  pre-registered slice grid is the world's own unit segmentation, not a new grid.

## Gates
WS-1..WS-8 as fixtures/tests (each must bite — a deliberate violation fixture must FAIL);
full cloud suite green; ets-auditor adversarial PASS; live verification on ets-web
(view switch, scrub steers audibly via the existing lanes, GRID regression) before "done".

## Rollback
FE view is flag-gated (`FIELD_TRACKS_VIEW`, default on; off = GRID-only, pre-directive
surface). Backend endpoint is additive/read-only. Single revert restores prior state.
