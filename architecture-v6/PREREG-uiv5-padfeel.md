# PREREG — ui-v5: pad feel (fix grating on fast move + navigation stickiness)

**Version:** ui-v5 (physical folder `architecture-v6/`, fork of ui-v4/`architecture-v5`;
pre-change tag `pre-uiv5-padfeel`). UX/FE line, runs on `engine-v1`. Engine status quo.
(Thin-UI packaging is deferred to its own refactor — the `ets` namespace is shared with
the engine; this fork keeps velocity on the feel fix. Disclosed, not forgotten.)

**Nature:** UI-only feel fixes to the REGION XY pad. ZERO engine diffs; inherits the
outboard byte-identical guarantee (deleting the v5+v6 UI ⇒ main-out byte-identical). The
one engine-bound path stays the region-tilt lane via the existing emitter.

## Two reported live bugs (from local play)

**BUG-1 "grates when I move fast".** The armed pad emits `self._vector()` on EVERY
`mouseMoveEvent` (widget.py ~L381) — fast cursor motion floods the engine with rapid
region jumps; the live streaming writer can't settle per bar → grating. Fix (UI only):
- Armed move updates only the **target**; it does NOT emit directly.
- A single timer emits the **slewed** value toward that target at a controlled rate
  (coalesce moves; cap emit rate ~30–60 Hz) with a slew tuned to glide over ~80–150 ms.
- Tune `SLEW_MAX_STEP` / make the slew critically-damped so the emitted stream is smooth
  (no per-tick audible step) even when the target jumps far.
- Result: dragging fast produces one smooth glide of region values, not a burst.
- (Diagnosis aid, NO engine change: the engine already logs per-bar settle iters /
  φ_density; if grating persists after this, watching that log tells us it's the live
  settle budget — an engine decision for later, not this UI change.)

**BUG-2 "can't navigate out of one terrain".** The pad weights anchors by
`w[i] = 1/(dist+eps)` (widget.py ~L367), which spikes near an anchor and pins you to the
nearest region. Fix (UI only): replace with a **soft kernel** — a Gaussian/softmax over
distance with a width ~ the anchor-ring spacing (e.g. `w[i] = exp(-(dist_i/σ)²)`,
normalized) — so intermediate positions genuinely blend neighbouring regions and you can
roam smoothly across the whole pad. Center still = even/neutral; distance-from-center
still = magnitude (clamped to the ring). No new lane, no new path.

## Hard lines (unchanged)

- Region tap/emit reaches the engine ONLY via the existing region-tilt lane + emitter.
- No new write path into settlement/F/render/provenance. Clamp/slew act on the outbound
  copy only, read nothing from the trained object.
- Any change to how F scores / the writer settles / the render emits ⇒ out of scope,
  stop and report.

## Harness (each bites)

- **UV5-A outboard** — delete/stub the UI ⇒ main-out byte-identical, fixed seed
  (inherited; run at merge).
- **UV5-B emit-throttle** — a fast synthetic move burst (N mouseMove events in one tick)
  produces at most one target update per emit tick and a MONOTONE bounded slew ramp on
  the wire — assert the emitted count is bounded and no raw target is pushed directly.
- **UV5-C roam** — with the soft kernel, a dot placed between two anchors emits a vector
  with BOTH meaningfully weighted (not ~all mass on the nearest); sweeping across the pad
  changes the dominant anchor smoothly (no hard pin). Assert the old 1/dist pin is gone.
- **UV5-D clamp still binds** — no reachable position emits magnitude above the cap
  (inherited).
- **UV5-E door** — no new engine path; region-tilt emitter is the sole gesture wire.

## Discipline

Prereg before build; auditor PASS before merge; walls surfaced not patched; coverage
honesty. This is a FEEL fix — expect a live-test iteration loop with the operator before
the version is frozen. Update the ledger at every edit.
