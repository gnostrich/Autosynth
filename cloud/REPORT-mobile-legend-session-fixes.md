# Build report — mobile bias, legend colours, dark-only, per-visitor sessions

Branch: `claude/field-surface-unified-clllba`. Four operator-directed fixes to the
hosted companion, plus one adjacent latent bug disclosed below. Full suite:
**135 passed** (was 119; +16 new/adapted, 0 removed, 0 loosened). Engine trees
(root `ets/`, `architecture-v6/ets/`) and `ui-v6/` untouched. COMPANION_INVARIANTS
R1–R5: no regression (R1 attribution improved by opt-in shared names;
keyless-local behaviour byte-identical).

## FIX 1 — Mobile: tap never zooms; one-finger vertical drag = bias
`cloud/companion/static/index.html`
- Pure block: `FIELD_TOUCH_BIAS_PX = 30`, `FIELD_TAP_SLOP_PX = 10`,
  `fieldDragSteps(accPx)`: accumulated vertical drag px → whole bias steps +
  remainder; one step per ~30px, drag up = favour (wheel-up analog).
- `fieldTouchStart`: records the square where the one-finger gesture STARTED
  (bias target for the whole drag); two fingers = pinch state (pinch zoom kept).
- `fieldTouchMove`: one finger `preventDefault()` (no page scroll), feeds whole
  steps into **the same lane the wheel uses**: `fieldAddBias` (same clamp/
  soft-saturation) → `sendSteerNow()` → the single `/api/steer` wire. No second
  channel.
- `fieldTouchEnd` (new): movement <10px = TAP: **no zoom, no emit** — hover
  highlight + tooltip only. Header tap = zoom out (kept). Arms
  `fieldLastTouchEnd` + `preventDefault()`; `fieldOnClick` ignores clicks within
  700ms of touchend (synthetic-click suppression). Desktop unchanged.

Tests (`cloud/tests/test_web_field.py`): `INPUT_HANDLERS` extended with
`fieldTouchEnd` (WEB-FIELD-INV transitive checker covers it);
`test_field_inv_touch_drag_reaches_the_steer_post_not_the_fill`;
`test_touch_tap_never_zooms_in_and_synthetic_click_is_suppressed`;
`test_touch_drag_steps_pure` (node: 30px = one `FIELD_BIAS_STEP` through the
same saturating clamp; 90px incremental drag = exactly 3 steps).

## FIX 2 — Role/unit colours stay in the parent track's family
`cloud/companion/static/index.html`
- `fieldRoleColor` (invented hues `i*47 % 360` — the collision the operator hit)
  **deleted**.
- Pure block gains `fieldHexToHsl`, `fieldParentTrack(stack)` (innermost drilled
  track), `fieldFamilyShade(baseHex, i)`: SAME hue as the parent track's legend
  colour, lightness (34/45/56/67%) + saturation stepped by role index;
  `baseHex == null` (no track parent = degraded role-grain-only view, the
  `info.field_degraded` path) = NEUTRAL grey ramp `hsl(0,0%,…)` — no false track
  attribution.
- `fieldSquareColor`: track/unit squares keep their OWN track's legend colour
  (honest — a role's unit pool spans tracks); role squares take the parent-track
  family shade or grey. Legend stays track-root-only.

Tests: `test_role_hue_inventor_is_gone`;
`test_role_shades_stay_in_the_parent_tracks_family` (node: hue equality pinned,
shades distinguishable); `test_degraded_role_view_is_neutral_grey_not_track_like`
(node: zero saturation).

## FIX 3 — Dark only
`cloud/companion/static/index.html`
- Removed: the `prefers-color-scheme: light` variable block, both
  `:root[data-theme=…]` blocks, light `.inst-lock` overrides, the `#themeBtn`
  header button, and the THEME JS block. Unused `--bg-grad-a/b` dropped.
- Permanent dark: `html,body{background:#05060B}`, `#ets{background:transparent}`,
  `#ambient` always `display:block` (was theme-gated); reduced-motion freeze
  untouched.

Tests: new `cloud/tests/test_dark_only.py` (no themeBtn/data-theme/
prefers-color-scheme; ambient ungated; reduced-motion kept);
`cloud/tests/test_fe_render_smoke.py` extended (headless chromium, really
rendered: `#themeBtn` gone, computed body bg `rgb(5, 6, 11)`, `#ambient`
display `block`). No existing test asserted the toggle — checked; nothing
deleted.

## FIX 4 — Per-visitor sessions + honest shared track names
`cloud/companion/app.py`
- One rule (Hub docstring): whoever is NOT the machine's owner gets their OWN
  session. Keyless-LOCAL → single default session (unchanged; R4, on-disk
  layout, `httpd.companion` back-compat). KEYED + valid token → that owner's
  session (**auth flow untouched**: `ETS_ACCESS_KEYS`, `/api/auth`,
  `_can_train`). Otherwise (keyless on a keyed or public deploy) → PER-VISITOR
  anonymous session via the existing `ets_session` cookie transport, minted on
  first API contact (`Hub.anon_session`/`new_anon_session`; `_Handler._session`;
  mint rides out through `_json`'s existing cookie header; `_mint` reset per
  request in do_GET/do_POST). Two anonymous visitors can never share a session —
  the exact leak the operator hit.
- Engines stay pooled in the ONE `WorldRegistry` LRU (`ETS_MAX_LOADED_WORLDS=2`);
  anon sessions are pointers in a capped in-memory LRU (`ETS_MAX_ANON_SESSIONS`,
  default 1024). In-memory per known #17; no durable store built.
- Shared names: `Companion.ingested_track_names()` (single source: index i =
  track id i, train-seam order); `Hub.share` snapshots into
  `CatalogEntry.track_names`; `/api/world` overrides generics from the session's
  own names (owner, as before) or the opened set's published names; generics
  kept where no real names exist. Public Explore card unchanged (EXP-D key-set
  pin still passes).

Tests: `cloud/tests/test_visitor_tier.py` — docstring adapted; 6-cell owner-gate
matrix UNCHANGED and passing (keyed anon still 401, keyless-public still 503);
new `test_anon_cookie_minted_once_and_session_sticky` (both public modes),
`test_two_anonymous_visitors_are_isolated` (the operator's scenario),
`test_engines_stay_pooled_not_per_visitor` (5 sessions, 0 loaded engines, one
registry). `cloud/tests/test_explore_shared_sets.py` —
`test_share_snapshots_the_real_ingested_track_names`,
`test_share_with_no_ingested_audio_keeps_generic_labels`,
`test_opened_shared_set_serves_owner_published_names_end_to_end`.
`test_public_keyed_gate.py`, `test_access_gate.py`, `test_no_demo_surface.py`
pass **unadapted** — mode-matrix behaviour genuinely unchanged.

## Adjacent latent bug (disclosed, fixed)
`app.py` used `log.warning(...)` in the `/api/world` static_field degradation
handler with no `log` defined — the honest degraded-field path would have 500'd
with `NameError` instead of serving the disclosed role-grain-only payload.
Fixed: `log = logging.getLogger("ets.companion")` (line 47).

## Walls (disclosed)
- **Touch behaviour verified statically + in node, not by a touch DOM**:
  reachability checker + pure node tests + `node --check` + render smoke cover
  it; a playwright touchscreen run against a READY world wasn't added (field
  initialises only with a live world; demo engine load is ~100x slower in this
  sandbox). Worth a device pass on the deployed site.
- **Anon sessions in-memory + capped** (known #17): redeploy/eviction re-mints
  an empty session; cookie-less clients get a fresh session per request —
  stateless, never shared.
- **Track-id ↔ filename mapping** reuses the already-load-bearing assumption
  (i-th sorted ingested audio file = track id i), now factored into ONE helper
  shared by both readers.

## Final pytest tail
```
$ python -m pytest cloud/tests -q
135 passed in 46.66s
```
