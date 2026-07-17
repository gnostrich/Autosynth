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

## 9. ets-web Railway service CRASHED  🔴  (operator input needed, 2026-07-17)
- A second Railway service `ets-web` (ets-web-production.up.railway.app, deploy
  `ddcadfb0`) is in **Crashed** state. Its deploy log spams the region-DISARM
  warning (`DISARMED lane leaned: region[0], region[1]` — the HONEST disarm: the
  σ_φ instrument measured zero untilted region fluctuation on that corpus/world;
  u transmits, no tilt). That warning is expected behavior, per-steer, NOT a
  crash cause. The visible log contains no traceback; neither `ddcadfb0` nor the
  healthy `Geodesic-Mixing` service's `43c3e43a` matches any commit in this repo
  (likely Railway deployment IDs). The repo has no `ets-web` config.
- **Next action (operator):** paste the TAIL of the crashed deploy log (the
  exit/traceback lines) + the service's start command, or grant Railway access.
  Separately worth doing: rate-limit the per-steer DISARM warning (log-noise).

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

## Recommended order
1 + 2 (diagnose grating & build currency, operator-side, ~5 min) → 3 (roam fix, me) →
4 (grid decision) → 5/6/7 (background). Freeze ui-v5 only after live-test confirms feel.
