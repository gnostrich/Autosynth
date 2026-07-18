# REPORT — OPEN_ENDS #21 batch: wheel storm · prism perf · legend at depth ·
# loop honesty · cold start (+ lane-meter addendum)

Branch `claude/field-surface-unified-clllba` at `36b4f40`. Suite 156 → 191.
Engine trees + ui-v6 byte-clean.

## (a) Desktop wheel storm — one deliberate gesture = one action
Named constants: `FIELD_WHEEL_BIAS_PX=40`, `FIELD_ZOOM_STEP_DELTA=120`,
`FIELD_ZOOM_COOLDOWN_MS=350`, `FIELD_WHEEL_LINE_PX=40`, `FIELD_WHEEL_PAGE_PX=800`.
`fieldWheelPx` normalizes deltaModes (latent bug found: line-mode mice —
Firefox — previously got ~1/40th the intended bias per notch). ZOOM gated by
`fieldZoomGate`: one layer per 120px same-direction travel AND 350ms cooldown;
absorbed storm travel never banks; direction change resets. BIAS: one
`FIELD_BIAS_STEP` per 40px through the existing `fieldAddBias` lane, remainder
kept; touch + wheel share ONE quantizer (`fieldStepQuant`). PINCH runs through
the same gate (was also once-per-event).
Near-wall disclosed: a long momentum flick (>320px) still reaches the soft ±1
stop (the intended saturation, a re-weight never a mute); a bias-side cooldown
would be an operator decision, not silently invented.
Tests: cloud/tests/test_wheel_storm.py (12).

## (a2) Prism perf
#ambient IIFE only: half-res backing store (AMB_SCALE=0.5), RAF capped ~30fps,
paused on document.hidden, one-time software-GL probe → single static frame
(no loop); reduced-motion freeze kept; ambFirePulse no-ops in static mode.
No caption changes (stays caption-less decor).

## (b) Legend at depth
Pure `fieldLegendSpec(st, stack)` → root|track|unit|none. Track depth: parent
chip + role-shade key from the SAME `fieldFamilyShade` the squares use (one
palette, no renderer colour literals — asserted). Unit depth: parent chip +
role label. Degraded role-only field: legend hidden.
Tests: cloud/tests/test_legend_depth.py (5).

## (c) Produce-loop honesty
`StreamPlayer._loop`: bare except → `logging.exception` on
`ets.companion.bridge` + timestamped `self.last_error` mirrored into telemetry
and `world_info()` (/api/world reports "engine failed: <type>"); still breaks
(no retry spin; produce called exactly once — asserted). Tripwire test that
the silent scar cannot return. Tests: cloud/tests/test_bridge_loop_honesty.py (4).

## (d) Cold start
Bridge `_warmed` flips on the FIRST produced bar (failed first bar never
claims warm); exposed via world_info. `app.py::_prewarm_engine` on
train-complete (both branches) and on share: `player.start()` pays bank build
+ first bars before any listener; guarded to the one world involved within the
registry LRU; CPU-on-unlistened-world tradeoff disclosed in-code; pre-warm
failure logs loudly, never fails the train/share. FE `#warmNote` "engine
warming up — first sound can take a few minutes" gated on real
`ready && !warmed`; cleared by first bar / warmed flag via a slim /api/world
re-read (`refreshEngineState`, deliberately never re-runs enableInstrument);
a recorded last_error replaces it with "engine failed: …" — never eternal
warming. Tests: cloud/tests/test_cold_start.py (13).

## Addendum — lane readouts must not look draggable
Read-only lane bars restyled as flat meters: no thumb/pill/glow,
cursor:default + pointer-events:none; dead .slider CSS deleted. Guard extended
(test_web_fab_guard.py::test_lane_console_has_no_slider_affordance).

## Interface growth disclosed
Three test fakes grew a recording no-op `start()` (pre-warm exercises it).
No assertion weakened.

## Invariants
WEB-FIELD-INV covers all new helpers; WEB-FIELD-D untouched (one set_region
call site, no new endpoint); WEB-FAB posture unchanged; H-8 untouched —
nothing changes rendered content.

## Final pytest tail
```
191 passed in 41.87s
```
