# DESIGN — companion web app tab structure / information architecture (v1)

Status: DESIGN DOC ONLY (no code, no engine authority). Re-spin of the crashed
design agent's lost output, now with the FIELD (ui-v6) and the Explore/shared-sets
open-end (#11) in view.

Scope: how the companion web FE (`cloud/companion/static/index.html`, served by
`cloud/companion/app.py`) should be organized into tabs, how PUBLIC mode (R6)
degrades it, where the Explore/publish affordances live, and the migration order
from today's single scrolling page. Keyed to existing controls only; the
FIELD-style web steer surface is a *future* build — this doc designs its slot, not
its internals.

Governing law this IA must never bend: `cloud/COMPANION_INVARIANTS.md` R1–R6 and
the CS-1..CS-5 stage-3 boundary. See §5 for the explicit guardrails.

---

## 0. Where we are today (the thing being re-organized)

Today `index.html` is ONE scrolling page, top to bottom:

1. **Source Audio** — drop/pick ingest + "New corpus" reset + the stage-3 seal note.
2. **Train (cloud anchor-fit)** — "Train on cloud" button + receipt/result panel.
3. **Instrument** (locked until a world is ready):
   - Role Pads (tap = region tilt, hold = drill)
   - Region Tilt · XY vector pad
   - Lane Console (display-only tolerances/weights) + meters (settle/drift/output)
   - Source Library (ingested tracks, display-only show/hide eye)
   - Output Tape (settled render, playhead from telemetry)
4. **Transport** — fixed footer (play/pause/stop + time).
5. **Drill overlay** — modal, display-only role makeup.

Two axes are tangled on one page: **build my world** (ingest → train → reset) and
**play/steer a world** (instrument + transport). PUBLIC mode already amputates the
build axis by `display:none`-ing the Source + Train sections (app.py 503s those
routes; FE hides them on `world.public`). The Explore feature (#11) adds a THIRD
axis — *other people's worlds* — with nowhere to live today. Tabs resolve all three.

---

## 1. Proposed tab set — **PLAY / TRAIN / EXPLORE** (three tabs)

Fewer is better; three is the floor that keeps the three axes from colliding. The
tab bar lives in the existing header (`header.hd`), left of the cloud/conn pills.
Transport stays a **global fixed footer across all tabs** — it binds to whatever
world is currently loaded in the player, so playback survives tab switches.

Rejected alternatives: a 4th "Library/Sets" tab (membership + set-listing fold
into Play and Explore respectively — see below); a "Settings" tab (theme toggle is
one button, keep it in the header). A 2-tab Play/Build collapse was rejected
because Explore is a genuinely different actor-context (visitor vs owner) and
merging it into Play muddies R6 gating.

### TAB A — **PLAY** (the instrument; the default tab)
The live surface for the world currently loaded in the player — demo world on a
fresh clone (R5), or your trained world after Train goes live, or someone's shared
set opened from Explore. Contents (all existing controls, re-homed):

- **Steer surface** — TODAY: Role Pads + Region Tilt · XY. FUTURE: a single
  **FIELD slot** (the ui-v6 design language: squares you push via hover-scroll
  bias + zoom-drill; brightness = live settled telemetry; bias only via the
  region-tilt lane). Design the Play tab's main column as ONE surface container
  (`#steerSurface`) that today mounts pads+XY and later mounts the field, so the
  swap is contained. The drill overlay collapses into the field's zoom gesture
  when that lands; until then it stays as-is inside Play.
- **Lane Console** (display-only tolerances/weights) + the six-lane scalar strips
  that stay unchanged per the ui-v6 prereg ("What stays UNCHANGED").
- **Meters** (settle / drift / output) — read-only telemetry.
- **Source Library** — ingested-track list with display-only show/hide eye. This
  is the "membership-adjacent surface" the ui-v6 prereg keeps; it is NOT steer.
  Re-pointing crate/library UX at the field is explicitly sequenced AFTER the field
  lands, so Play keeps the current library list for now.
- **Output Tape** — settled render + telemetry playhead.
- **Transport** — global footer (shared; see above).
- **Honest-disarm state** — the existing `region-disarmed` dimming/tag and the
  "steer inactive" instHint live here unchanged (never fake a live steer).

### TAB B — **TRAIN** (build MY world; owner-only)
The build axis, lifted out of the scroll into its own tab:

- **Source Audio** — drop/pick ingest, file list, the stage-3 seal note ("only
  gauge-invariant stage-3 leaves this box").
- **New corpus** reset (R4) — clears corpus + world, reverts Play to the demo.
- **Train on cloud** (R2) — the button, the σ_φ calibration note, and the
  receipt/result panel (world verified / disarmed-lane report / errors).
- On success: a clear "→ your world is LIVE in **Play**" affordance that switches
  the active tab to Play. Training repoints the player (`is_trained:true`); the tab
  switch just follows the player.
- **Publish control lives here too** (owner side of Explore) — see §3.

### TAB C — **EXPLORE** (other people's shared sets; browse + play + steer)
The sharing layer from OPEN_ENDS #11. Contents:

- **Browse list** of published sets (title, owner handle, role count, a "disarmed"
  badge if that set can't be steered). Card → "Open in Play".
- **Open a shared set** = load it into the same player the Play tab renders, then
  switch to Play. A visitor plays and STEERS it via the SAME region-tilt lane —
  no elevated authority (§5). Per-set rate/authority limits (still region-tilt
  only) are enforced server-side; the FE just exposes the one lane.
- **Your published sets** — a section listing sets YOU'VE opened up, with an
  unpublish/close control. The publish ACTION originates in Train (§3), but its
  管理 (management/listing) surfaces here.

Explore is intentionally a thin "list → load into Play" router: it does not
duplicate the instrument. One instrument (Play), many sources of the loaded world
(demo / trained / shared).

---

## 2. PUBLIC mode (R6) degradation per tab

R6/public mode = the hosted Railway deploy: `app.py` 503s `/api/ingest`,
`/api/train`, `/api/reset`, and `/api/world` returns `public:true`. It is a
**play/steer-the-demo** deployment. Visitor ≠ owner.

| Tab | LOCAL (owner) | PUBLIC (visitor) |
|---|---|---|
| **PLAY** | Full instrument on demo/trained/shared world. | Full instrument, but on the demo world (or a shared set) only. No behavioral change — Play never calls the gated routes. This is the tab a visitor lands on. |
| **TRAIN** | Full ingest/train/reset. | **Hidden entirely** (tab removed from the bar, not just disabled). The gated routes 503; showing a dead tab would violate the "never show something broken" stance already coded (`if(w.public){ hide source/train }`). Replace with a one-line inline note in Play: "Training your own audio runs in the local companion — [how]." |
| **EXPLORE** | Browse + open shared sets. Publish (from Train) available. | Browse + open + play/steer shared sets (read/consume side). **Publish is hidden** for visitors (publishing requires an owner with a trained world, which requires Train, which is gone in public). Explore in public is consume-only. |

Visitor flow: land on **Play** (demo world, hearable + steerable immediately — R5)
→ optionally **Explore** to open someone's shared set → back to Play to steer it.
Never sees Train. Never sees a publish button. Never hits a 503.

Owner flow (local): **Train** (ingest → train → live) → **Play** (steer own world)
→ optionally **publish** from Train → manage the publication in **Explore**.

Implementation note (no new authority): the tab bar reads the SAME `world.public`
signal the FE already uses; public just filters the tab set to `[Play, Explore]`
and drops publish affordances. One gate, reused.

---

## 3. Explore publish/list/play/steer — and the privacy fork (i)/(ii)/(iii)

The publish/consume affordances split cleanly so the IA is **agnostic to the
undecided privacy fork** (OPEN_ENDS #11 (i) embed-with-consent / (ii) owner-online
render / (iii) self-contained-only). None of the tab structure above changes per
fork; only ONE surface (the publish confirm step) and ONE list-state (set
availability) change. Everything below is what WOULD differ, called out explicitly.

**Publish (owner, originates in Train):**
- A "Publish this set" control appears next to a live trained world in Train.
- It opens a **publish confirm dialog** that MUST state the privacy boundary
  explicitly (R1/R3/CS-1 language: what leaves the device). This dialog is the
  ONE place the fork is visible:
  - **Fork (i) embed-with-consent:** the dialog is a deliberate, disclosed
    consent gate — "publishing uploads your world AND the audio bank it references
    so others can play it. Your raw audio leaves your device." Requires an explicit
    checkbox. This crossing needs operator sign-off + its own prereg before build
    (per #11) — the IA just reserves the dialog slot.
  - **Fork (ii) owner-online render:** the dialog says "your set is playable by
    others only while your companion is online; audio never leaves your device."
    Adds an online/offline availability concept (below). No audio upload.
  - **Fork (iii) self-contained-only:** publish is **only enabled for
    demo-style self-contained worlds** (embedded audio, no external refs — the
    `demo.etsworld` shape). A trained world referencing local audio shows the
    control **disabled** with "this set references local audio; only self-contained
    sets can be shared." No audio-bank upload, no online requirement.

**List (Explore browse):**
- Cards are identical across forks EXCEPT an **availability state** that only forks
  (i)/(iii) make always-on:
  - (i)/(iii): every listed set is always playable (audio travels / is
    self-contained). Card = "Open in Play".
  - (ii): a set carries an **online/offline** indicator (owner's companion reachable
    or not). Offline sets list but "Open" is disabled with "owner offline." This is
    the ONE list-level element that appears/disappears by fork.

**Play/steer a shared set (consume):**
- Identical across all three forks: the set loads into the Play instrument, steered
  by the region-tilt lane only. Fork (ii) additionally proxies render through the
  owner's companion, but that is a TRANSPORT detail invisible to the Play IA — the
  player loads a world; where the samples resolve is below the FE.

So the fork touches exactly: (a) the publish-dialog copy + enable/disable rule, and
(b) an availability badge on Explore cards. The three-tab structure, the "Explore =
list → load into Play" router, and the publish-originates-in-Train placement hold
under any outcome. **Design the publish dialog and the card's availability slot now;
wire their fork-specific behavior when the operator picks a fork.**

---

## 4. Migration notes — small steps from today's single page

The field-style web steer surface is a SEPARATE future build; these steps do NOT
build it. They reshape the current single page into the tab shell and pre-cut the
seams. Order chosen so each step is independently shippable and auditable.

1. **Introduce a tab shell around existing sections; zero behavioral change.**
   Wrap today's DOM in three panes: Play = Instrument block + its sub-panels +
   Source Library + Output Tape; Train = Source Audio + Train sections; Explore =
   empty placeholder ("shared sets — coming"). Add a tab bar in `header.hd`.
   Transport stays the global footer. Default tab = Play. Nothing new calls the
   backend. (Auditor: pure re-parenting; R1–R6 untouched.)
2. **Wire `world.public` to the tab set.** In public, render `[Play, Explore]`
   only and drop the Train tab (replaces today's `display:none` on the sections).
   Reuses the existing `w.public` branch — no new signal.
3. **Move reset ("New corpus") fully into Train** and make Train's success switch
   to Play. Cosmetic re-home of existing buttons/handlers.
4. **Carve the Play main column into one `#steerSurface` container** that today
   mounts Role Pads + XY exactly as now. This is the FIELD SLOT — a contained mount
   point so the future field swap touches one container, not the whole page. No
   field code in this step; the slot just exists and holds the current controls.
5. **Explore consume-only skeleton** (behind the operator's green-light + the
   sharing prereg): a browse list that loads a chosen set into the Play player and
   switches tabs. Publish control + dialog slot added to Train, disabled until the
   fork is chosen. No audio-boundary crossing is coded until the fork prereg lands.
6. **(Future, separate build)** the FIELD web steer surface mounts into
   `#steerSurface`; drill overlay folds into its zoom gesture; crate/library UX
   re-points at the field per the ui-v6 sequencing rule. Out of scope here.

Steps 1–4 are safe re-organization of what exists and can ship without touching
the sharing/privacy question. Step 5 is gated on operator sign-off + prereg.

---

## 4A. Progress / feedback states (the app must never look stalled — honestly)

Same honesty rule as the whole repo: **a progress indicator must reflect REAL
backend state, never decorative animation pretending at progress that isn't
happening.** The failure this prevents: a live deployment whose backend had died
sat on the static "Loading the founding demo world…" lock with no way to tell
*loading* from *dead*. Every state below is driven by a real signal the backend
already emits (or a named signal it must start emitting — flagged as such, not
faked in the FE).

### (a) PLAY — world-loading overlay (the frozen-lock fix)
Today `#instLock` shows a static padlock + "Loading the founding demo world…" with
no liveness. Replace with three DISTINGUISHABLE states, keyed to real signals:

- **Loading (backend alive, world not ready yet):** `/api/health` returns ok AND
  `/api/world` not yet `ready`. Show a live **heartbeat** tied to the existing
  `conn.dot` breathing (already animates only while health polls succeed) plus
  "loading the demo world…". The heartbeat is real: it stops the instant a poll
  fails, so a frozen page is impossible to mistake for a live one.
- **Backend dead / unreachable:** `/api/health` fails or the telemetry SSE drops
  (the FE already flips `connDot` to `.bad` + "no companion" on health failure).
  Overlay must switch to an **honest error**: "lost the companion backend —
  it may have crashed or restarted. Retrying…" with a visible retry countdown and
  a manual "retry now". This is the state that was invisible before; make it loud.
- **Timeout (loading too long):** if `ready` hasn't arrived within a bounded wall
  (generous — the sandbox renders ~100x slower than hardware, so pick a corpus-size-
  aware ceiling, not a tight one), show "still loading — this is taking longer than
  expected" WITHOUT declaring failure (the render may genuinely be slow). Only the
  health-fail signal declares death; slowness never fakes a crash and a crash never
  hides behind "still loading".

Distinguishability rule: **loading**, **slow**, and **dead** are three different
messages driven by three different real signals (health-ok+not-ready /
health-ok+not-ready+over-ceiling / health-fail). Never collapse them into one spinner.

### (b) TRAIN — staged cloud-train progress
`Companion.run_train` walks REAL sequential stages: local ingest → stage-3 encode →
cloud anchor-fit (the wire round-trip) → receipt verify → local `build_index` →
per-corpus σ_φ measurement → `save_world`. These are honest, nameable stages.

- **The honest constraint:** today `/api/train` is a single blocking POST that
  returns one JSON at the end — there is **no per-stage progress channel**. So a
  staged indicator showing "stage-3… ✓ cloud fit… ✓" faithfully requires the
  backend to EMIT stage events (an SSE/chunked progress stream from `run_train`, or
  a polled job-status endpoint). Design the staged UI now; **flag the backend
  progress stream as a prerequisite** — do NOT fake stage advancement on a timer in
  the FE (that would be decorative progress, banned).
- **UI (once the stream exists):** a fixed vertical stage list (Ingest → Stage-3 →
  Cloud fit → Verify → Build → σ_φ calibrate → Save) where each row lights from the
  real event. No numeric percentages inside a stage (the backend emits stage
  boundaries, not sub-progress — inventing a percent would be fake). The active
  stage gets an indeterminate pulse; completed stages get a check; the cloud-fit
  stage additionally shows the same `conn.dot` heartbeat so a dead round-trip is
  visible mid-train.
- **Until the stream is built (interim, honest):** keep today's single "training…"
  indeterminate state, but label it with the KNOWN stage list as static text
  ("training walks: ingest → stage-3 → cloud fit → verify → build → σ_φ → save")
  and a live heartbeat, so the user sees the real shape and that the backend is
  alive — without claiming to know which stage is active. Honest ignorance beats a
  fake stepper.
- **Terminal states are already honest in the receipt panel** (world verified /
  disarmed-lane report / `playback:"error"` / failure) — keep those; they are real
  backend truth.

### (c) PLAY — steer feedback (gesture → engine answer latency)
The steer loop is: gesture → `/api/steer` (region-tilt lane) → engine RE-SETTLES →
`/api/telemetry` SSE (0.1s frames) carries the new settled state → surfaces update.
There is REAL latency here (the settle loop; ~100x slower in the sandbox), and the
ui-v6 governing invariant demands the display show the ENGINE'S answer, never the
raw input echoed. So:

- On gesture, the pushed control enters a **pending "settling" state** (a subtle
  indeterminate cue on the pushed square/pad — NOT a moved brightness). Brightness
  must not move until a telemetry frame reflects the re-settlement (echoing the
  input as instant feedback would violate FIELD-INV / the "engine's answer" law).
- When the next telemetry frame arrives showing the re-settled weights, the pending
  cue clears and brightness updates — INCLUDING co-movement on untouched related
  squares (the proof-of-realness the field requires). The latency between push and
  brightness-change IS the honest settle time; showing a fake instant response would
  lie about what the engine did.
- If telemetry STALLS after a gesture (SSE dropped / backend died mid-settle),
  reuse the (a) backend-dead treatment: the steer surface shows "lost telemetry —
  reconnecting", never a frozen pending cue that looks like a slow settle forever.
- Honest-disarm interplay: on a `region-disarmed` set the gesture legitimately
  produces NO settled change — the existing dim/tag already says "steer inactive",
  so the pending cue must NOT appear there (it would imply a change is coming that
  never will).

### (d) EXPLORE — list / loading / open states
- **List loading:** skeleton rows while the shared-set list fetch is in flight,
  driven by the real fetch promise (not a timed placeholder). On fetch failure:
  "couldn't load shared sets — retry", same honesty as (a).
- **Empty:** "no shared sets published yet" (distinct from a failed load — an empty
  list is a real 200, a failed load is an error; never show empty on error).
- **Per-card availability (fork-dependent, see §3):** under fork (ii) an
  owner-offline card shows a real offline state with "Open" disabled ("owner
  offline — set unavailable"); this reflects a real reachability check, not a guess.
- **Opening a set → Play:** the set loads into the Play player via the SAME
  world-loading states as (a) — including the backend-dead/timeout distinctions —
  because "open a shared set" IS "load a world into the instrument". Under fork (ii)
  the render proxies through the owner's companion, so the loading overlay's
  dead-vs-slow distinction matters doubly (the OWNER's backend can be the thing
  that's slow or dead); surface which side is unreachable when the transport can
  tell them apart.

**Cross-cutting rule:** every spinner/pulse in the app is bound to a live signal
(health poll, SSE frame, or fetch promise) whose STOPPING is itself visible.
Nothing animates on a bare timer. If a signal isn't available yet (e.g. train
stages), the UI states its ignorance honestly rather than animating fake progress.

---

## 5. Non-goals + invariant guardrails

Non-goals (explicitly NOT in this IA):
- **No new engine authority.** Tabs re-organize existing surfaces; they add no
  control that reaches settlement. The only engine-bound gesture stays
  `/api/steer` = the region-tilt lane.
- **No spec of the FIELD web surface internals.** We design its *slot*
  (`#steerSurface`) only; its build is the ui-v6-derived future work.
- **No multi-user/account system.** MVP stays account-free, one corpus at a time
  (R4). Explore's per-set authority/rate limits are server-side and are NOT an
  account model.
- **No decision on the privacy fork.** This doc is fork-agnostic by construction
  (§3); it does not pick (i)/(ii)/(iii).

Invariant guardrails (the IA must uphold these; auditor-checkable):
- **R1/R3/CS-1..CS-5 (audio boundary).** Play/Explore consume worlds; no tab adds a
  raw-audio wire path. Ingest stays local-only in Train. Publishing raw audio
  (fork (i)) is the ONE disclosed crossing and requires its own prereg + operator
  sign-off + an explicit consent dialog — never silent, never a default.
- **R2 (train via cloud).** Train tab preserves the existing ingest → stage-3 →
  cloud fit → verify seam; the tab move changes placement, not the seam.
- **R4 (reset/change corpus).** "New corpus" full-revert stays reachable (in Train)
  and still reverts Play to the demo world.
- **R5 (fresh clone plays).** Play defaults to the demo world with no prerequisites;
  the tab shell must not gate Play behind Train.
- **R6 (public gating).** Public mode hides Train + publish and 503s stay authoritative
  server-side; the FE gate is convenience, not the enforcement boundary.
- **Steer = region-tilt lane only, for owners AND visitors.** A visitor steering a
  shared set gets no elevated authority; same single lane, same clamp/slew, same
  honest-disarm behavior.
- **Honest disarm.** The `region-disarmed` dim/tag stays; a set that measured σ=0
  discloses "steer inactive" in Play and carries a "disarmed" badge in Explore —
  never a faked live steer.

---

## Key IA decisions (summary)

1. **Three tabs: PLAY / TRAIN / EXPLORE**, splitting the three tangled axes
   (play a world / build my world / other people's worlds). Transport is a global
   footer bound to the loaded world, shared across tabs.
2. **One instrument, many sources.** Play renders whatever world is loaded (demo /
   trained / shared); Explore is a thin "list → load into Play" router, not a
   second instrument.
3. **Public mode filters to `[Play, Explore]`**, drops Train and all publish
   affordances, reusing the existing `world.public` signal — visitors never see a
   gated route or a 503.
4. **Fork-agnostic sharing.** The privacy fork (i)/(ii)/(iii) touches exactly two
   FE elements — the publish-confirm dialog copy/enable-rule and an Explore card
   availability badge; the tab structure holds under any fork.
5. **Publish originates in Train, is managed in Explore.** Keeps publishing tied to
   owning a trained world (so it's inherently absent in public).
6. **Migration is 5 safe re-org steps + 1 future field build.** A contained
   `#steerSurface` slot is cut now so the future FIELD swap touches one container;
   no engine authority, no audio-boundary crossing is added by the re-org.
7. **Progress states are signal-bound, never decorative.** Loading vs slow vs
   dead are three distinct messages from three real signals (fixing the frozen-lock
   failure); train shows honest stages ONLY once the backend emits them (interim:
   heartbeat + static stage list, never a fake stepper); steer shows a pending
   "settling" cue until the telemetry frame carries the engine's answer (never an
   echoed input); Explore's list/open states reuse the same honest loading/dead
   treatment. Every spinner is bound to a signal whose stopping is visible.
