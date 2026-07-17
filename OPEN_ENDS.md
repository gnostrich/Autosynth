# ETS — open-ends register

A living tracker so nothing falls through. Each item: what it is, status, and the
single next action. Close top-down; don't start a new build while a diagnosis is open.

Legend: 🔴 blocking play · 🟡 decision needed · 🟢 ready to build · ⚪ background/cleanup

## 1. Grating / sudden-loud live audio  ✅ SAFE (cap shipped) · divergence deferred
- **RESOLVED for safety.** Loudness audit (scratch/loudness_audit.py) reproduced it: under a
  decisive MULTI-lane steer the engine DIVERGES (phi_density → 3.77e15; arrangement audio
  pre-cap rms ~1.7M, peak ~6.6M). The live output limiter/loudness-cap (`_playback_soft_limit`,
  live-only, engine-fork playback layer) bounds this to rms 0.10 / peak ≤0.60 on EVERY bar →
  eardrum-safe verified. Committed. render_offline + root engine untouched.
- Root cause = the v1 engine's steering divergence (the sealed-v3 subject). It is JOINT/
  combinatorial (continuity 3.0 alone is fine — the good music uses it; many lanes together
  diverge), so a per-lane UI clamp would break good settings. Bounding the joint envelope, or
  guarding phi_density engine-side, is a DEFERRED ENGINE DECISION (sealed-v3 / parked sampler),
  NOT an autonomous change. The cap makes decisive steers SAFE (bounded) but not yet musical.
- **Next (user decision):** either bound the joint steering envelope in the UI, or add an
  engine-side phi_density guard (StreamHalt), or revive the parked variance-corrected sampler.

### (historical lead, superseded by the audit above)
- Symptom: sound grates / tears in the live app; offline renders sound clean.
- **VERIFIED LEAD (d) — unlimited live output.** `master.py` (compressor→R128→peak
  limiter −1 dB) is applied to OFFLINE renders only; the LIVE engine path streams RAW —
  no limiter, no sub control. Unlimited peaks + sub-bass tear on laptop speakers. This
  explains offline-clean / live-grates directly.
- Other candidates (test only if (d) doesn't fully fix it): (a) laptop real-time
  underrun; (b) fast-pad emit flood; (c) engine divergence/settle-budget.
- **30-sec confirm (operator):** does it grate when you just let it PLAY without touching
  any control? If yes → it's output-level (d) [or underrun (a)], not the pad. Also glance
  at the engine terminal: φ_density/settle spiking → divergence (c); normal → (d)/(a).
- **Fix for (d):** a live PLAYBACK limiter (+ gentle sub high-pass) — the same
  "outside the trained object" playback stage as `master()`. Design note: it lives in the
  render/playback layer (I-11), not the trained object (F/settlement/writer/provenance),
  so the ARRANGEMENT is provably unchanged — but it touches the engine tree, so it's a
  **playback-layer revision** (engine-v1 → v1.1 playback), re-bless the verifier. Small.

## 2. Local build currency  🔴  (cheap, do alongside #1)
- Unknown whether the desktop is running the CURRENT engine-v1 or an older checkout — an
  old build could explain grating/divergence on its own.
- **Next action (operator):** confirm `git log -1` on the running checkout matches origin
  HEAD of the branch; if not, pull and re-run.

## 3. Pad navigation stickiness  ✅ CLOSED by ui-v6 (2026-07-17)
- The soft-kernel roam fix shipped in ui-v5; ui-v6 then REMOVED the XY pad entirely —
  the FIELD surface (`ui-v6/`, PREREG-uiv6-field.md) subsumes it (biasing toward
  material IS the blend). No further action.

## 4. MPC pad grid — not wired live  ✅ RESOLVED by the FIELD directive (2026-07-17)
- The operator's FIELD directive replaced the pad grid (and XY + drill) with ONE
  unified field of squares (`ui-v6/`), lit from the existing read-only telemetry —
  no new OSC address, H-6 intact. The old surface is preserved immutable in
  `architecture-v6/` as the rollback/A-B point.

## 5. Thin-UI packaging refactor  ⚪  (deferred, disclosed)
- "Thin ui-vN" is blocked by the shared `ets` namespace (engine+UI same package). Needs a
  namespace-package refactor. ui-v5 is a full fork for now.
- **Next action (me, later):** design the namespace split; one-time refactor.

## 6. External smart-EQ / mastering layer  ⚪  (parked)
- Earlier thread: optional de-tilt "smart EQ" on finished audio; upscale dropped. Never
  finalized into the mastering path.
- **Next action:** decide if it belongs in the render/master stage; low priority.

## 7. futuregarage instance  ⚪  (status check)
- Trained instance exists; the 30-min set was psytech only. Unclear if a futuregarage set
  is wanted.
- **Next action (operator):** say whether you want a futuregarage set; else close.

## 8. Cloud deployment (Railway + Vercel web instrument)  🟢 → building path set
- **MVP-1 (anchor-fit offload, Railway):** ✅ **DEPLOYED LIVE** at
  `https://geodesic-mixing-production.up.railway.app` (project `thorough-serenity`,
  service `Geodesic-Mixing`). Deployed from a **code-only context** (ets/ + cloud/;
  NO corpus/worlds/samples uploaded — CS-1 respected at deploy time too). Single-user
  bearer gate ACTIVE: unauth `/train` → 401, authorized real job → 200 + verifiable
  receipt (end-to-end confirmed 2026-07-17). `$PORT`-ready + `railway.json` committed.
- **MVP-2 (browser instrument):** prereg complete (`cloud/PREREG-cloud-mvp2.md`) +
  design-direction mockup signed-off-pending. Topology: Vercel serves the UI code; a
  sealed local Docker container renders + holds data + couriers stage-3 to Railway.
  Decisions locked: keep Vercel web UI mirroring the ui-v5 layout; GUI surfaces via the
  browser (no X11 passthrough); in-browser drag-drop ingest (folder-drop fallback);
  **single-user auth** (one shared bearer secret).
- **MVP-2 phase 2 (web instrument):** built — local render bridge (reuses the engine's
  produce_one pipeline + eardrum cap), region-tilt as the only control (door held),
  streaming audio + SSE telemetry, functional FE. Auditor FAIL→fixed: (a) sys.path pin
  bug that let root ets shadow the arch-v6 engine — fixed (app.py appends repo-root;
  bridge forces arch-v6 front + fails loud); (b) namespace + clamp reuse. Re-audit pending.
- **train→YOUR-corpus seam — ✅ FULLY WIRED: build + play + steer (2026-07-17):**
  `/api/train` on raw audio runs the full LOCAL seam
  (`cloud/companion/train_local.py`: local ingest → stage-3 → CLOUD anchor-fit →
  verify → local `build_index` → **measure this corpus's own σ_φ** (untilted
  settlement, mirroring `scripts/run_sigma_phi.py` in-process; registered artifact NOT
  touched) → `save_world` .etsworld with the σ_φ EMBEDDED, referencing the user's
  local audio) and REPOINTS the instrument at the trained world (`is_trained:true`).
  Because `resolve_sigma` precedence is `--sigma-phi > embedded > registered`, the
  embedded σ_φ is used and the demo world's registered artifact is never consulted —
  the earlier STALE wall is resolved by measuring, not faking. Region/continuity/
  novelty are armed; density/gauge are non-identifiable at u=0 → disarmed (measured,
  same as the founding world). CS-1 intact: only stage-3 crosses (`encode_job`→
  `post_job`); σ_φ calibration is fully local. A `.npz` bundle keeps the geometry-only
  verify; `reset()` reverts to the demo world. Verified end-to-end against LIVE
  Railway by `cloud/tools/seam_verify.py` (steered bar ≠ u=0 bar; both eardrum-capped).
  Cost: one untilted settlement added at train time (disclosed).
- **Next action (operator):** Railway is deployed (see above); run the companion
  locally to play/steer the demo world and iterate.
- **TBD — multi-user expansion:** deferred by operator. Sequence = single-user MVP-2 →
  **one more upgrade (TBD, to be named)** → multi-user. Needs key issuance/revocation/
  quotas + a store, and single-tenant-per-deploy vs. shared-multi-tenant call. Parked.

## 9. ets-web Railway crash  ✅ DIAGNOSED (OOM) + FIXED + REDEPLOYED (2026-07-17)
- A second Railway service `ets-web` (ets-web-production.up.railway.app, deploy
  `ddcadfb0`) is in **Crashed** state. Its deploy log spams the region-DISARM
  warning (`DISARMED lane leaned: region[0], region[1]` — the HONEST disarm: the
  σ_φ instrument measured zero untilted region fluctuation on that corpus/world;
  u transmits, no tilt). That warning is expected behavior, per-steer, NOT a
  crash cause. The visible log contains no traceback; neither `ddcadfb0` nor the
  healthy `Geodesic-Mixing` service's `43c3e43a` matches any commit in this repo
  (likely Railway deployment IDs). The repo has no `ets-web` config.
- RESOLVED: with Railway API access the cause was measured — 7.997GB against the
  8GB cap, six silent OOM kills (per-visitor engines + in-proc training in the
  lost snapshot code). Fixed by the demo-phase rebuild (shared demo engine +
  LRU-capped trained worlds + single-training lock), auditor-passed, and
  redeployed from GitHub main (the service now sources the repo — the lost-code
  era is over; snapshot ddcadfb0 retained in Railway history for archaeology).
  Still worth doing sometime: rate-limit the per-steer DISARM warning (log noise).

## 10. ui-v5 stale hover-inert static assertion on main  ⚪  (disclosed, mooted in ui-v6)
- `architecture-v6/tests/v5/test_v5b_hover_inert.py::test_tap_surface_has_no_hover_move_channel`
  fails on main: `RegionTapPads` gained a `mouseMoveEvent` in the merged drill
  sprint (it only cancels the hold-timer and emits nothing — the INVARIANT holds;
  the static check is stale). architecture-v6 is immutable history now, so it is
  disclosed rather than patched; ui-v6 deletes the widget and carries the
  invariant on the field (`tests/v5/test_v5b_hover_inert.py`, field edition).

## 11. EXPLORE page + shared sets (+ tab-planning design)  🟡  (recovered from crashed session, 2026-07-17)
- **Recovered by operator recall — the crashed session's artifacts were never
  committed; nothing of this survived in the repo (verified by search).**
- **The feature:** a sharing layer for the web companion:
  (a) OPT-IN publishing — open one of your sets (trained worlds) so others can
  play and STEER it; (b) an EXPLORE page listing others' shared sets to browse
  and play. This is very likely the roadmap's unnamed slot in #8's sequence
  (single-user MVP-2 → **one more upgrade** → multi-user) — operator to confirm
  the naming.
- **Invariant homework BEFORE any prereg** (R1–R6 / CS-1..CS-5 pressure):
  playing someone else's set requires render somewhere — a shared set's world
  references the OWNER's local audio (CS-1: raw audio never uploaded), so
  listing a set either (i) embeds/uploads the owner's audio bank WITH EXPLICIT
  CONSENT at publish time (a deliberate, disclosed privacy-boundary crossing —
  needs operator sign-off + prereg), (ii) renders on the owner's device/
  companion (owner-online-only sharing), or (iii) shares only self-contained
  demo-style worlds. Steering-by-others also needs per-set rate/authority
  limits (still only the region-tilt lane). None of this is decided.
- **Tab planning / FE information architecture:** a DESIGN AGENT was spun up in
  the crashed session to lay out the companion's tab structure (Play /
  Explore / Train, etc.); its output is LOST. Needs re-spinning against the
  current state — which now includes the FIELD (ui-v6) as the play surface,
  per the sequencing rule (field first, then re-point crate/library UX at it).
- **Next action:** operator green-light → re-spin the design agent for the tab
  IA + write PREREG for the explore/sharing layer (privacy decision (i)/(ii)/
  (iii) is the first fork in that prereg).

## 12. Progress/feedback states — nothing may LOOK stalled  🟢  (recovered from crashed session, 2026-07-17)
- Loading bars / staged progress everywhere the app currently sits silent: the
  world-loading overlay (static lock icon today — a dead backend is visually
  identical to a slow load; see the ets-web crash screenshot, #9), train-on-
  cloud (real stages exist: ingest → stage-3 → cloud fit → σ_φ → world build),
  steer round-trip feedback, and (future) Explore list loading.
- HONESTY RULE inherits: indicators reflect REAL backend state — staged
  progress from actual stage transitions, heartbeat + timeout + honest error
  for backend-dead; never decorative animation faking progress.
- Folded into the tab-IA design doc (design agent re-spin, in progress);
  implementation is FE-only, no engine surface.

## 13. Recovered fragment: additional theory-faithfulness checklist/hooks  🟡  (operator to re-state)
- The crashed session also discussed further faithfulness checklist items /
  hooks ("theory checklist, faithfulness hooks") beyond what is committed.
  SPECIFICS LOST — nothing recoverable in the repo. What already exists and is
  enforced: CLAUDE.md standing discipline, ets-auditor pass before merge,
  builder/auditor pairing, per-edit ledger hook (build_ledger.py), FIELD-INV +
  FIELD-A..E harness, door/outboard/byte-identical test patterns, verify-by-
  running (cloud/tools/*_verify.py). If the discussed items exceeded this list,
  the operator should re-state them; they will be registered and, where
  hook-shaped, wired into the same enforcement layer.

## 14. IN-FLIGHT: fixed demo build v2 (audio + keyed-Train + web FIELD)  🔴  (live tracker, 2026-07-17 evening)
- **Live site state:** STOPGAP deployed (pre-demo commit e174b60 via pinned
  deploy): play/steer the demo works, keyless, NO upload/train on the site
  (old R6 public rule hides it — not a new break). The demo build v1 was pulled
  after two live defects.
- **Defects being fixed (builder in flight, expedited):**
  (a) WHITE NOISE playback — RESOLVED AS A WALL, not a stream bug: two
      independent measurements (builder 9b263a1 + read-only diagnosis) prove
      the stream/fan-out is BYTE-FAITHFUL; the DEMO WORLD'S OWN ENGINE RENDER
      is white-noise-like (flatness ~0.844 live AND offline, autocorr ~0).
      The committed self-contained demo world likely always sounded like this
      (old checks measured only peak level). Fixing the demo's SOUND = new
      demo-world content build (engine/world territory: prereg + operator
      sign-off, registered as its own item). User-trained worlds are the
      real-music path — the pipeline is faithful.
  (b) TRAIN hidden/blocked for KEYED users — both layers gate on
      session.public alone; diagnosed patch: can_train = hub.keyed or not
      session.public on /api/status + /api/world + the POST gate, FE honors
      can_train. Regression matrix for all four public×keyed combos required.
  (c) WEB FIELD surface (the operator's directive, web half) — prereg
      committed (cloud/PREREG-web-field.md); replaces role pads + XY on the
      web Play tab.
- **New merge/deploy GATES (standing, learned today the hard way):**
  render gate (Playwright: no CSS-as-text, tabs switch panes), served-bytes
  check on the LIVE app page post-deploy (not just the access page), decoded-
  audio check (stream must decode to non-flat spectrum), deploys pinned to an
  explicit commit SHA (no branch-tip trust — no webhook exists).
- **Design question for operator (from the gate diagnosis, unresolved):** in
  public+keyed mode, anonymous visitors currently hit the access wall instead
  of a Play+Explore demo view. Decide: access-wall-only, or keyless demo play
  alongside keyed full powers.
- **Also pending:** operator interested in CO-PLAY as a first-class feature
  (composed multi-player biases, presence indicators) — offered, not yet
  confirmed as registered work. Railway token rotation after infra work ends.
  ddcadfb0 snapshot download (crashed-session archaeology) still optional.

## 15. Session/world persistence on Railway  ✅ VOLUME ATTACHED (2026-07-18)
- The ets-web service has NO volume ("volumeMounts": []): visitor sessions,
  uploaded audio, and TRAINED WORLDS live in the container filesystem and are
  WIPED on every deploy/restart. Tonight: operator re-drops files after the
  beat_this image deploy; the deep-field swap will wipe again.
- FIXED: volume `ets-web-volume` (id 9dd79d5d) created via API and mounted at
  /app/cache (covers companion_sessions + worlds). ACTIVATES on the next
  deploy (the front-door swap); persistence across a subsequent redeploy to be
  verified once two deploys have occurred post-attach. Until that verify, the
  next single swap still starts empty (nothing pre-volume can be preserved).

## 16. FRONT DOOR redesign — keyless Explore-driven flow  🟢 (operator-specified 2026-07-17/18, awaiting "build" word; freeze in effect)
- Operator decisions from live testing, superseding the parked #8 "P+K anonymous
  view" question:
  (a) KEYLESS visitors: NO access wall. Land on PLAY in an EMPTY STATE (no world
      auto-loaded, no noise; honest "pick a set from Explore" pointer). Explore
      lists opted-in shared sets; opening one loads it into Play (listen+steer).
      Key unlocks ONLY Train/publish (can_train machinery already does the split).
  (b) Sharing stays STRICTLY OPT-IN (already implemented + audit-pinned: default
      OFF, owner-only toggle, unshare revokes). Training never auto-publishes.
  (c) Demo world: DECIDED (operator, 2026-07-18): NO founding demo surfaced on
      the site for now — hidden from keyless Explore AND not auto-loaded for
      keyed users' empty state either; "we'll zero in on the right one later."
      #14a's content rebuild is PARKED until the operator picks the material
      (it remains committed in the repo for R5's fresh-clone/local path).
  (d) Build-time consideration: per-set steer RATE caps (deferred in the demo
      prereg) become relevant once strangers can steer shared sets; envelope
      bounds magnitude already, caps would bound frequency.
- Status: specified, registered, NOT building (operator freeze). Trigger phrase:
  "build the front door".

## 17. Hardened multi-user fork — collected deferrals  🟡  (register, 2026-07-18)
- From the front-door audit (PASS-WITH-NOTES): (a) SHARED VISITOR SESSION —
  all keyless visitors share one session, so concurrent strangers collide on
  opened set + steer (accidental co-play). No privacy/R1 leak (owner routes
  gated; only opt-in attributed sets reachable). Acceptable demo-phase UX;
  per-visitor sessions belong to the multi-user fork. (b) Per-set visitor
  steer RATE caps (magnitude already enveloped). Plus the earlier multi-user
  parking (#8): key issuance/quotas/store, deliberate co-play as a feature.

## Recommended order
1 + 2 (diagnose grating & build currency, operator-side, ~5 min) → 3 (roam fix, me) →
4 (grid decision) → 5/6/7 (background). Freeze ui-v5 only after live-test confirms feel.
