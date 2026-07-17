# PREREG — the WEB FIELD surface (companion FE; replaces role pads + XY vector pad)

Pre-registered BEFORE build, house style (prereg before build; auditor PASS before
merge; walls surfaced, never patched). This ports the operator's FIELD directive —
already built and audited on the desktop instrument (`ui-v6/PREREG-uiv6-field.md`,
`ui-v6/ets/instrument/field.py`) — to the companion web front end. It is a FULL
REPLACEMENT of the web Play surface's ROLE PADS + REGION TILT · XY, mounted into the
`#steerSurface` slot reserved by `cloud/DESIGN-companion-tabs-v1.md` (§1 TAB A, §4
step 4). Not parallel: the pads grid and the XY pad are removed.

Base: branch `claude/field-surface-unified-clllba`, cloud suite 61/61 green at start.

## Governing invariant (stamped; auditor-enforced)

**You push → the engine re-settles → the display shows the ENGINE'S ANSWER.**

A square's fill brightness IS its live SETTLED weight, read from the read-only
`/api/telemetry` `roles` frame. No input path sets brightness. The ONE gesture is
hover-scroll BIAS: it accumulates an operator INPUT value per square (shown as a
RING on the square's edge, a channel DISTINCT from the fill) and routes the
composite through the panel's EXISTING region-tilt lane (`POST /api/steer` →
`StreamPlayer.set_region` → `clamp_region` → settlement). The machine re-settles
around the bias; it is never forced. Brightness moves ONLY when the next telemetry
frame carries the re-settlement — the FE's existing "settling" pending cue (design
§4A(c)) honors this and is wired to the field. Down-bias soft-saturates at
"strongly disfavored" (−1 × the safe envelope) and can never hard-mute (the region
lane is an exponential tilt; settled weight stays > 0). Membership (hard
include/exclude) remains the SEPARATE library/show-hide surface, untouched.

## Honest data-grain statement (inspected, not assumed)

The web telemetry carries only what `/api/telemetry` and `/api/world` actually emit,
inspected in `cloud/companion/engine_bridge.py`:

- `/api/telemetry` → `{"roles": [float]*M, "bar": int, "t": float}` (`StreamPlayer.
  telemetry`, produced by `bar_role_activity`). The ONLY settled grain is **per-role
  settled activity** (length M, 0..1).
- `/api/world` → `{ready, M, sr, world, is_trained, armed, disarmed, region_armed,
  bar_seconds, public, opened_set_id}` (`StreamPlayer.world_info`). It names M and
  whether region is armed. No profiles, no per-track settled activity, no unit pool.

Therefore, over the web API there is **exactly one telemetry grain: ROLE.** The
desktop field's TRACK and UNIT layers (`ui-v6` reads `/ets/profiles`,
`/ets/nowplaying`, `/ets/unitpool` over OSC) have **no web analog** — the bridge
emits none of those feeds. This is the honest reduction, disclosed up front:

- **Squares exist ONLY at role grain** — one square per role the telemetry names.
  Empty telemetry (no `roles`, e.g. before Play) → **empty field**, never
  placeholders (WEB-FIELD-E).
- **Squares are ATOMIC.** Drill self-sizing (WEB-FIELD-C on desktop) is implemented
  by the SAME criterion, but the web telemetry provides no per-role sub-structure
  vector, so every role square's sub-vector is empty → the participation-ratio floor
  correctly refuses to drill. **Depth honestly ends at role grain.** Faking deeper
  squares would violate WEB-FIELD-E and is NOT done. If the bridge ever grows a
  per-role sub-feed, drilling arms automatically by the same floor test.

**No new API surface is added.** The field consumes exactly the existing
`/api/telemetry` `roles` and `/api/world` `M`/`region_armed`, and steers via the
existing `POST /api/steer`. No read-only payload extension was needed (the required
data is already emitted), so none is added — the minimal, cleanest outcome.

## The participation-ratio noise-floor criterion (restated in JS)

Drill (Ctrl+scroll / pinch) is gated by the SAME criterion that self-sized the
anchor count M — the balanced-truncation effective mode count
`PR(w) = (Σw)² / Σw²` over a non-negative weight vector
(`architecture-v6/ets/functional/anchors.py::effective_rank`, which computes exactly
this on the traffic operator's spectrum). It is RESTATED as pure JS arithmetic on
telemetry vectors (`fieldParticipationRatio` / `fieldClearsFloor`); the instrument
does not import the engine. A square may drill only while `round(PR) ≥ 2` (≥ 2
distinct effective sub-modes). Pinned to `effective_rank` by value in the harness.

## What is built (all in `cloud/companion/static/index.html`)

- A `<canvas id="fieldCanvas">` field inside `<section id="steerSurface">`: a grid of
  role squares. FILL brightness = settled telemetry only (written solely by
  `fieldApplySettled`, the telemetry applier). Per-square BIAS via hover-scroll
  (wheel), accumulating in [−1,+1], soft-saturating, NEVER a mute path. A visible
  RING on the square's edge (color = bias sign, width = magnitude) distinct from the
  fill. The composite bias vector maps to the region vector
  (`region[r] = bias[r]·SAFE_MAG`, each square leaning along its own axis e_r) and is
  sent ONLY via the existing `POST /api/steer` region path (same payload shape the XY
  pad used: `{region:[...]}`). Zoom drill wired for Ctrl+scroll and touch pinch,
  gated by the PR floor (atomic over the web → honest refusal).
- REMOVED: the Role Pads grid (`section.pads`), the XY vector pad (`section.xy`), and
  the pad-driven drill overlay (which fabricated 36 cosmetic units — its removal also
  removes a fabrication). Their now-dead CSS/JS is deleted.
- KEPT UNCHANGED: the six-lane scalar sliders / Lane Console, meters (read-only,
  telemetry-driven), Source Library (display-only show/hide), Output Tape, transport
  footer, Train/Explore tabs and all their logic, the loading/slow/dead overlay, the
  honest-disarm dimming (re-pointed at `#steerSurface`).
- The "settling" pending cue is wired to the field (gesture → cue on the field →
  cleared by the next telemetry frame; suppressed when region is disarmed).
- Mobile/trackpad: `wheel` (bias) + `pinch` / `Ctrl+scroll` (zoom). No hover-move
  channel; passive hover is inert (targets the wheel only, writes no state).

## Harness (all must bite; extend `cloud/tests` + a `node --check` pass)

- **WEB-FIELD-INV** (`test_web_field.py`): static/structural check on the inline JS —
  no input handler (`fieldOnWheel`, `fieldOnMove`, `fieldZoom`, `fieldTouchStart`,
  `fieldTouchMove`) writes the brightness store (`fieldApplySettled` or a direct
  `fieldSettled` assignment), TRANSITIVELY through same-source helpers. Mirrors the
  AST/structure of `ui-v6/tests/field/test_field_inv.py`. Proven to BITE: an inline
  echo-handler fixture string (and a laundered handler→helper→writer fixture) MUST be
  flagged by the same checker. Also asserts the real handlers reach the steer POST.
- **WEB-FIELD-B** (`node` runtime): bias soft-saturates at ±1 (drive the wheel step
  past the stop → clamps to exactly ±FIELD_BIAS_LIMIT); the emitted region components
  never exceed the safe envelope (`|region[r]| ≤ FIELD_SAFE_MAG`), and
  `FIELD_SAFE_MAG` is pinned by value to `envelope.SAFE_REGION_MAGNITUDE`. Full
  down-bias is a re-weight, not a mute (bias stays a finite lean, never −∞).
- **WEB-FIELD-C pin**: `fieldParticipationRatio` equals `anchors.effective_rank` on
  diagonal fixtures (value pin); `fieldClearsFloor` is `round(PR) ≥ 2` (2 modes clear,
  1 mode atomic, empty atomic) — so the web's atomic role squares refuse to drill by
  the same law that would arm it if sub-structure existed.
- **WEB-FIELD-D** (single-lane): `app.py` `.set_region(` remains a single call site
  (unchanged); the FE emits exactly one `POST /api/steer` and introduces no new
  `/api/` endpoint (target set unchanged).
- **WEB-FIELD-E** (no fabrication): squares derive from telemetry roles
  (`fieldSettled` starts `[]`, count == `fieldSettled.length`, written only by
  `fieldApplySettled(roles)`); empty telemetry → empty field; the fabricated cosmetic
  unit grid is gone; `fieldSubVector` is empty by construction (no fabricated depth).
- **RENDER SMOKE** (`test_fe_render_smoke.py`, Playwright/headless chromium; standing
  requirement after the CSS-outside-`</style>` regression): starts the companion on a
  loopback port (keyless), loads `/`, asserts (a) no CSS leaks into `body.innerText`
  (no `display:` / `::after` style signatures), (b) the tab bar exists and each tab
  shows exactly one active pane (others `display:none`), (c) the FIELD canvas is
  present and role-pads / XY elements are GONE; screenshots to the pytest tmp dir.
  Skips loudly if chromium is genuinely unavailable.

Target: full cloud suite stays 61+ green; new tests added on top.

## Anticipated walls (disclosed up front)

1. **Web grain is ROLE-level; depth ends at role.** The bridge emits no per-track,
   per-unit, or profile telemetry over the web API, so the desktop field's TRACK→
   ROLE→UNIT drill collapses to a flat, atomic role field. This is the honest
   reduction, not a bug; the PR drill machinery is present and correctly disarmed. If
   deeper web telemetry is ever wanted, it is a pre-registered read-only bridge
   extension, out of scope here.
2. **Touch bias is scroll-only.** Bias is a wheel/scroll gesture; a pure-touch device
   with no scroll wheel can pinch (zoom, which is atomic here) but has no bias
   channel, because inventing a touch-drag bias would add a second input channel and
   risk a hover-move path the invariant forbids. Disclosed, not worked around.
3. **The field is populated only while telemetry flows** (i.e. while playing), by
   design: fill = settled telemetry only, and there is no settled state when the
   engine is not producing. Idle → honest "no settled telemetry yet — press Play".
</content>
</invoke>
