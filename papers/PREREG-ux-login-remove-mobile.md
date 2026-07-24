# PREREG — Header Unlock (login discoverable) + owner Remove flow + tab/mobile consistency

Status: pre-registered before the change. Class: **DISPLAY / ADDITIVE ONLY**
(affordance surfacing, CSS consistency, responsive layout). No mechanism, no
engine, no bias-routing change, no new auth path.

Scope: `cloud/companion/static/index.html` (front-end) only. NO root `ets/` edit,
NO `architecture-v6/ets` engine edit, NO `channel_bias.py` / bridge routing edit,
NO `app.py` behavior change (all auth/owner gates reused unchanged). `git diff
--name-only -- ets/ architecture-v6/ets/` MUST be clean. The render-smoke gate
(`test_fe_render_smoke.py`) is updated ONLY to describe the header Unlock control's
new placement — the auth flow it drives (`/api/auth`) is byte-for-byte the same.

## Motivation

Today the Unlock affordance (`#unlockBtn`) is gated to `currentTab === "train"`, so
a keyed visitor cannot find how to log in from Play/Explore. The Explore "Remove my
set" control only renders on `mine === true` cards, which requires being the
authenticated owner — reachable only after login. The two must connect: login must
be discoverable, and unlocking must make the owner controls (Set-tab Train controls
and Explore Remove) appear without a manual reload.

## Changes (all display/additive)

1. **Header Unlock, discoverable on every tab.** `#unlockBtn` (already in the
   header) is regated: `refreshUnlock()` shows it whenever `world.keyed &&
   !world.canTrain`, independent of the current tab. When unlocked (`world.keyed
   && world.canTrain`) it is replaced by an owner chip `#ownerPill` ("unlocked").
   Keyless deploys (`!world.keyed`, nothing to unlock) show neither. It opens the
   EXISTING `#keyModal` and posts the EXISTING `/api/auth` — no new auth path, no
   secret in page source.

2. **Owner controls appear on unlock, no reload.** On `/api/auth` success the code
   already re-reads state (`loadStatus(); loadWorld()`), which flips `world.canTrain`
   and runs `applyTrainGating()` (Set-tab Train controls) + `refreshUnlock()`. Added:
   after `loadWorld()` resolves, if the Explore tab is active, re-run `loadExplore()`
   so owned sets (`mine === true`, now recognized server-side) render their Remove
   button in place. Remove still calls the EXISTING owner-gated `POST /api/share
   {on:false, set_id}` behind a confirm — no new route.

3. **Tab + chip + panel consistency.** Play/Set/Explore become one segmented control
   (uniform padding/font/radius, translucent glass container). Inactive tabs read at
   `--ink-2` (legible), active tabs stay the accent fill — a deliberate filled-vs-
   outline treatment instead of the accidental half-fade. Status chips pick up the
   same glass tokens so the header reads as one system with the `.glass` panels.

4. **Mobile parity (~390px).** `.pad-head` wraps so the field Expand button never
   clips; the Explore card `.foot` wraps so Open + Remove stay visible/tappable; the
   tabs drop their left margin on narrow widths. Field grid scroll + full-name
   marquee are the existing display-only behavior, unaffected.

## Hypothesis / null we refuse to break (H0)

Every change here is display-only, so with an **empty field** the steer payload is
**byte-identical** to before: `channel_bias` all-zero, `unit_bias {}`,
`track_role_bias []`, `region_add` all-zero → each bridge grain `None` → produced
rows and settled `O` bit-identical → rendered audio byte-identical. The working
track×role grid keeps steering identically (draw and hit-test read the SAME canvas
`clientWidth/clientHeight`; nothing here touches `fieldBiasPayload`/`fieldGridPlace`).

## Kill conditions (any one FAILING rejects the change)

1. `test_channel_bias` (engine byte-identity) not green, or the FE neutral-field
   payload is not all-zero/empty on all four grains
   (`test_neutral_field_payload_is_byte_identical`).
2. `fieldBiasPayload` / `fieldGridPlace` altered in any byte, or the track×role grid
   steers differently (`track_role_grid_verify`).
3. Any new authentication surface, or the Unlock affordance stops reusing `/api/auth`;
   Remove/Train stop being owner/key-gated server-side (`app.py` unchanged).
4. `git diff --name-only -- ets/ architecture-v6/ets/` is non-empty.
5. The display-purity guard (`test_field_display_and_explore_fe.py`
   `test_display_logic_never_touches_the_bias_payload`) or WEB-FAB guard trips.

## Instruments (re-run with the change)

- `cloud/tests/test_channel_bias.py` — engine byte-identity + pull (unchanged).
- `cloud/tests/test_field_display_and_explore_fe.py` — NEUTRAL / MINE / display-purity.
- `cloud/tools/track_role_grid_verify.py` — grid steering identity.
- `cloud/tests/test_fe_render_smoke.py` — header Unlock discoverable on all tabs,
  owner chip hidden for a visitor, click opens the key prompt (smoke updated).
</content>
</invoke>
