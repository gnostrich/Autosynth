# PREREG — Field fullscreen/scroll/full-names + Explore owner-only "Remove my set"

Status: pre-registered before the change. Class: **DISPLAY / ADDITIVE ONLY** (layout,
motion, catalog affordance). No mechanism, no engine, no bias-routing change.

Scope: `cloud/companion/static/index.html` (front-end) only. NO root `ets/` edit, NO
`architecture-v6/ets` engine edit, NO `channel_bias.py` / bridge routing edit, NO
`app.py` behavior change (the backend already enforces owner-only unshare — this reuses
it). `git diff --name-only -- ets/ architecture-v6/ets/` MUST be clean.

## Hypothesis (what must stay true — the null we refuse to break)

H0 (the invariant we defend): every change here is display-only, so with an **empty
field** (no bias on any grain) the steer payload is **byte-identical** to before —
`channel_bias` all-zero, `unit_bias {}`, `track_role_bias []`, `region_add` all-zero →
each bridge grain `None` → produced rows and settled `O` bit-identical → rendered audio
byte-identical (the `test_channel_bias` engine contract, unchanged). The `FIELD_GRID_ENABLED`
track×role grid keeps steering byte-identically because the draw AND the hit-test read the
SAME canvas `clientWidth/clientHeight` — resizing the canvas for scroll never changes which
square a gesture resolves to, only how large it is drawn.

## Change 1 — Field: fullscreen-expandable + full names + no legend + scroll

All four are display transforms of the existing canvas field; none reads or writes
`fieldBias`, `fieldBiasPayload`, `sendSteer`, or `/api/steer`.

- **Fullscreen (laptop AND mobile).** A pure branch function `fieldFsPlan(apiAvail, isActive)`
  picks the Fullscreen API where the element supports it (`Element.requestFullscreen`,
  works on laptop + most mobile) and a CSS viewport-fill fallback otherwise (e.g. iOS
  Safari): one `#padHero.field-fs` class (`position:fixed; inset:0; 100dvw/100dvh` with
  `env(safe-area-inset-*)` padding) styles BOTH paths, so native and fallback look the
  same; `fullscreenchange` + `Escape` keep the button/state synced. Collapse restores the
  embedded size. The non-expanded layout is untouched.
- **Full uncompressed track names.** Row (track) labels no longer middle-truncate. They
  render at FULL length; when a name overflows its header box it is shown with a gentle
  horizontal ping-pong **marquee** (`fieldMarqueeShift`, a pure function of elapsed ms —
  no trig, no timer, no easing lib; WEB-FAB clean), clipped to the header cell. Under
  `prefers-reduced-motion` the marquee is replaced by middle-truncation with the full name
  in the canvas tooltip (the stated acceptable fallback). Names are the REAL ingested
  `fieldTrackName` values — never padded or invented.
- **Legend removed in grid mode.** The `#fieldLegend` key is redundant once rows=tracks
  and columns=roles are labeled. `fieldRenderLegend` is now called ONLY on the non-grid
  path (retained, dormant under the flag); in grid mode the container is `display:none`
  (kept in the DOM so the non-grid code path and the existing render-smoke element check
  still hold — no dangling visible container).
- **Scroll when oversized.** The canvas is sized by `fieldGridMinSize(T, M, availW, availH)`
  so cells never shrink below a legible floor (≥34×30 px + row-header/column-header rail);
  when the grid needs more than the box, a `#fieldScroll` container (`overflow:auto`,
  `overscroll-behavior:contain`) pans both axes. The page body never scrolls horizontally
  — the scroll is contained in the field.

## Change 2 — Explore owner-only "Remove my set"

- `exploreRemovable(entry)` is true **iff** `entry.mine === true` (strict; a truthy-but-not
  -true value does not unlock it). The Remove button renders ONLY on owned sets.
- Removal reuses the EXISTING owner-gated unshare: `POST /api/share {on:false, set_id}`,
  behind a `confirm("Remove <name> from Explore?")` mis-tap guard, then refreshes the list.
  No new route, no new auth path.
- The backend already enforces owner-only: `app.py` (~1489) 403s when `set_id != session.set_id`
  (a session may unshare only its OWN set). A non-owner never sees the button AND the server
  refuses a foreign `set_id` regardless. Verified at the request layer by
  `test_share_unshare_foreign_set_is_403`.

## Kill conditions (any one FAILING rejects the change)

1. `test_channel_bias` (engine byte-identity) not green, or the FE neutral-field payload is
   not all-zero/empty on all four grains (`test_neutral_field_payload_is_byte_identical`).
2. `FIELD_GRID_ENABLED` steering behavior altered (the grid must keep working byte-identically).
3. Any DISPLAY pure-logic function references the steer path
   (`test_display_logic_never_touches_the_bias_payload`).
4. The marquee introduces trig/timer/easing (WEB-FAB regression) — `test_marquee_has_no_trig_timer_or_easing_in_code`.
5. A non-owner can remove someone else's set (the 403 does not fire).
6. `git diff --name-only -- ets/ architecture-v6/ets/` is non-empty.

## Instruments (committed with the change, run in CI)

- `cloud/tests/test_field_display_and_explore_fe.py` — node pure-logic teeth: FIT / MARQUEE
  / FS / MINE / NEUTRAL, plus the display-purity static guard.
- `cloud/tests/test_public_keyed_gate.py::test_share_unshare_foreign_set_is_403` — request-layer 403.
- `cloud/tests/test_fe_render_smoke.py` — the field-scroll container + expand control render,
  and the legend is display:none in grid mode.
- Unchanged regressions re-run: `test_channel_bias`, `test_web_fab_guard`, `test_web_scalar_lanes`,
  `test_explore_shared_sets`.
