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

## 3. Pad navigation stickiness  🟢  (ready; independent of #1)
- Bug: `w=1/dist` weighting pins you to the nearest region — can't roam across terrains.
- Fix designed: soft (Gaussian/softmax) kernel. ui-v5 forked (`architecture-v6/`), prereg
  written (`PREREG-uiv5-padfeel.md`), builder NOT started (paused for triage).
- **Next action (me):** spawn builder for the roam fix (+ emit-throttle IF #1 = emit flood).

## 4. MPC pad grid — not wired live  🟡  (decision)
- The grid exists but is a disconnected display; live light-up needs the engine→UI
  provenance feed, which is a WALLED item (new OSC address breaks the closed message
  space H-6). By design the pads are a VIEW + region-bias, NOT a sample-trigger keyboard.
- **Decision needed:** (a) leave as-is (dot pad is the instrument); (b) build the live
  provenance feed via a pre-registered H-6 revision (light-up + connected grid); (c) drop
  the grid. Recommend deciding AFTER #1/#3 so play works first.

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
- **train→YOUR-corpus seam — BUILD ✅ WIRED, PLAY 🔴 blocked on σ_φ (2026-07-17):**
  `/api/train` on raw audio runs the full LOCAL BUILD seam
  (`cloud/companion/train_local.py`: local ingest → stage-3 → CLOUD anchor-fit →
  verify → local `build_index` → `save_world` .etsworld referencing the user's local
  audio). CS-1 intact: only stage-3 crosses (`encode_job`→`post_job`; verified by
  `cloud/tools/seam_verify.py`). A `.npz` bundle keeps the geometry-only verify
  (offline/test path); `reset()` reverts to the founding demo world. **PLAY is
  blocked by a real σ_φ wall:** a freshly-trained world has a new content hash, so
  the registered σ_φ artifact (bound to the demo world) is REFUSED by
  `engine.resolve_sigma` (STALE) rather than reused — the trained world will not even
  load to play untilted. `run_train` reports `{"built":true,"playback":"blocked"}`
  and keeps the calibrated demo live; it does NOT invent a scale or fake an artifact
  (rejected non-solutions listed in PREREG-cloud-mvp2). **Proposed fix (needs
  sign-off):** revise `resolve_sigma` precedence so a foreign-hash artifact is treated
  as absent (→ untilted-only, loud refusal on lean) instead of a hard STALE raise;
  then per-corpus σ_φ calibration (settlement-only `scripts/run_sigma_phi.py` at
  world-freeze) unlocks live steering — a heavier, deferred item.
- **Next action (operator):** Railway is deployed (see above); run the companion
  locally to play/steer the demo world and iterate.
- **TBD — multi-user expansion:** deferred by operator. Sequence = single-user MVP-2 →
  **one more upgrade (TBD, to be named)** → multi-user. Needs key issuance/revocation/
  quotas + a store, and single-tenant-per-deploy vs. shared-multi-tenant call. Parked.

## Recommended order
1 + 2 (diagnose grating & build currency, operator-side, ~5 min) → 3 (roam fix, me) →
4 (grid decision) → 5/6/7 (background). Freeze ui-v5 only after live-test confirms feel.
