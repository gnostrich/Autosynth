# REPORT — field fullscreen snap + one-time tutorial (mobile UX)

Date: 2026-07-18 · Branch: `claude/field-surface-unified-clllba`
Scope: `cloud/companion/static/index.html` only (plus tests). No engine tree,
no `app.py`, no `ui-v6/` touched. No new `/api/` calls, no new endpoints.

## Feature 1 — field fullscreen snap

A `⛶` affordance (`#fieldExpand`, 44×38 px touch target) in the field pane's
header row. Tapping it adds `.field-full` to `#steerSurface`: `position:fixed;
inset:0; 100dvw/100dvh` (vw/vh fallback), `z-index:150` (above transport/tabs
at 40), dark `#05060B` backdrop. Legend, breadcrumb header, canvas (flex-fill)
and field status stay visible inside. The same button becomes `✕` to collapse.

Where the platform allows: `steerSurface.requestFullscreen()` then
`screen.orientation.lock('landscape')` inside the resolved promise, each
guarded try/catch (Android Chrome supports both).

Exit paths: `✕` collapses + `exitFullscreen()`/`orientation.unlock()`; Esc /
system gesture fires `fullscreenchange` → `fieldOnFullscreenChange` collapses
whenever `document.fullscreenElement` is gone. No stuck overlay.

Hit-testing/redraw verified: all gesture handlers use getBoundingClientRect /
clientWidth-Height; `fieldDraw()` re-fits the DPR-aware backing store each
draw; `fieldExpandApply` redraws immediately; the window resize hook (fires on
rotation) redraws inside the expanded state.

**WALL (disclosed, not patched):** iPhone Safari supports neither element
`requestFullscreen` (video-only) nor `screen.orientation.lock`. There the snap
is viewport-fill only; physically rotating the phone gives landscape. Disclosed
in code comments. No UA sniffing, one implementation, honest degradation.

## Feature 2 — one-time tutorial

`#fieldTut`, static dark overlay confined to `.field-wrap`, ships `hidden`.
Shown by `tutShowIfFirst()`, single call site = `enableInstrument()` (the
`world.ready` transition) — never before a world exists; empty Play state
untouched. Exactly three lines, worded by `'ontouchstart' in window`:

- touch: `drag up/down on a square — more / less of it` /
  `pinch — zoom in/out (tap header to back out)` /
  `fill = the engine's answer · ring = your push`
- mouse: `scroll on a square — more / less of it` /
  `Ctrl+scroll or click — zoom (header backs out)` / same third line

"got it" sets `localStorage.ets_tut_v1="done"` forever; gated on that flag; no
animation (reduced-motion-safe by construction); no tour framework; overlay
never covers the transport. localStorage unavailable → never nags.
Display-only: no engine calls, no telemetry writes, no fetch.

## Invariant coverage

- WEB-FIELD-INV (transitive): five new input entry points (`fieldExpandToggle`,
  `fieldExpandOpen`, `fieldExpandClose`, `fieldOnFullscreenChange`,
  `tutDismiss`) registered in INPUT_HANDLERS; checker proves none reaches the
  fill writers or telemetry stores; echo fixtures still bite.
- Stronger in new tests: this chrome must not even reach
  `sendSteer`/`fieldAddBias`/`fetch` — display-only, no second channel.
- WEB-FIELD-D: no new endpoint; still exactly one `/api/steer` in the FE.
- New tests: `cloud/tests/test_web_mobile_ux.py` (9). Render smoke extended:
  `#fieldExpand` renders on load; `#fieldTut` hidden on the empty landing.

## Verified by running

Interactive playwright drive against a live local companion (demo world):
tutorial appears on world.ready (mouse wording); "got it" hides + persists
across reload; snap pins fixed with canvas filling the viewport, DPR backing
store re-fit exactly; `✕` restores; headless chromium granted real element
fullscreen and a real `document.exitFullscreen()` (Esc path) collapsed the
snap. (An earlier checker draft dispatched a synthetic `fullscreenchange`
while genuinely fullscreen and "failed" — instrument error, fixed the
instrument, not the threshold.)

## Auditor scrutiny pointers

- `fieldExpandApply → fieldDraw` as the snap's only side effect.
- `tutShowIfFirst` re-fires on later ready transitions until dismissed — by
  design ("never auto-reappears" is scoped to after dismissal).
- z-index 150 layering: above transport (40)/inst-lock (25), below key modal
  (200, reachable only from the hidden header) — no trap found.

## Final pytest tail

```
145 passed in 48.12s
```
(136 pre-existing + 9 new; includes both browser render-smoke tests and the
node --check syntax gate on the whole inline script.)
