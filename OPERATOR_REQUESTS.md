# ETS — Operator request ledger (single source of truth)

**Purpose.** So the operator NEVER has to repeat a request. Every distinct ask from
the operator (across sessions) is captured here with a status. Any agent working in
this repo READS THIS FIRST and updates it. If the operator asks for something, it
goes HERE before it's actioned, and its status is kept current.

Status key: ✅ DONE/LIVE · 🧩 BUILT — HELD (done, awaiting the batched deploy) ·
🚧 IN-PROGRESS · 🅿️ QUEUED · ♻️ STANDING (a rule, always on).

---

## 0. STANDING META-DIRECTIVES (asked many times — these are always-on rules)
These are the recurring demands. They live in CLAUDE.md / COMPANION_INVARIANTS.md /
FAITHFULNESS_REGRESSION_SPEC.md and are enforced mechanically where possible.

- ♻️ **No fabrication. Ever.** Real data or disarmed-and-labeled — never decorative-
  captioned-as-real. Enforced by `cloud/tools/faithfulness_verify.py` CHECK-NO-FABRICATION
  + CHECK-AUDIO-BOUNDARY-HONEST. Incident log in FAITHFULNESS_REGRESSION_SPEC.md (INC-1..4).
- ♻️ **Verify by RUNNING, not asserting — and for a BROWSER feature, drive a real
  browser.** (INC-4: I once declared "ready" off curl/API without driving the UI.)
  No "works"/"ready" claim for a UI feature without a Playwright/Chromium drive.
- ♻️ **Faithfulness harness runs at every edit/commit/merge** (tiered; git hooks +
  CLAUDE.md rule). Auditor runs it FIRST, then judges. No merge on a red harness.
- ♻️ **Builder + separate auditor on every non-trivial change. Auditor PASS before
  merge.** Walls are surfaced (disclosed), never patched/faked/no-op'd.
- ♻️ **Keep `main` current; operator never chases branches/repo updates.**
- ♻️ **No engine/theory edits** (`ets/`, `architecture-v6/ets/` immutable) without a
  prereg + operator sign-off. Prereg BEFORE build for new theory-touching features.
- ♻️ **Parallelize with agents; be fast; give honest ETAs.**
- ♻️ **"Tell me when it's actually working" gate** — a defined acceptance set (not
  "nothing's lying" but "everything works end-to-end, browser-driven"). See §4 / task #22.

---

## 1. HOSTING / ACCESS
- ✅ Host on the cloud (Railway) for performance; browser front-end (no Vercel needed —
  Railway serves the UI). Live: https://ets-web-production.up.railway.app
- ✅ Interface talks DIRECTLY to Railway for everything — no GitHub-repo dependency, no
  clone needed to use it (R6).
- ✅ Access-key gate — only the operator has a key; more keys mint by adding to
  `ETS_ACCESS_KEYS` (env, no code change). Single-user now; multi-user = later.
- ✅ Deployed by me end-to-end with the operator's Railway token (kept, not shredded).
- ✅ **Hobby plan / memory** — training OOM-killed the container on the old tier;
  operator upgraded to Hobby (≥4 GB, 8 GB bulletproof). Verified live: train survives,
  no restart, ~14 s. THE core "it cans me when I train" blocker — RESOLVED.

## 2. AUDIO IN → TRAIN → PLAY YOUR CORPUS
- ✅ Upload YOUR OWN tracks from YOUR device (drag-drop / file pick).
- ✅ Audio goes device → cloud and is trained on Railway (R3(b), operator-locked).
  Private/on-device mode (raw never leaves device) = 🅿️ planned upgrade (task #20).
- ✅ Train → play YOUR corpus (the seam), reset to change corpus.
- ✅ **Reset clears ALL audio** (files + subdirs + trained world) so nothing piles up.
- ✅ Parallel uploads + live "uploading X/N" progress (was one-at-a-time, felt stuck).
- ✅ Session recovery — an evicted session (restart/TTL) sends you back to the key gate
  instead of failing silently.
- ✅ Upload caps documented/measured (100 MB + 12 files/session).
- 🅿️ **Corpus persistence** — trained world should survive a container restart (queued
  for the batched deploy; less critical now that OOM restarts are gone).

## 3. THE INSTRUMENT UX
- ✅ Browser UX mirrors the desktop layout (role pads + XY + tape + transport + library).
- ✅ Fresh clone plays a self-contained demo (`demo.etsworld`) out of the box (R5).
- ✅ **Real drill-in** — tap-hold a pad / press `d` / (now) a visible "⋯ drill" button;
  shows REAL per-bar units colored by REAL source track (via read-only /api/units).
- 🧩 **Visible drill affordance** (the "where's the drill" fix) — BUILT, browser-verified,
  HELD for the batched deploy.
- 🧩 **Control interaction model** — hover never moves a value; CLICK-then-drag-then-DROP
  to grab/move/commit; NO inadvertent jumps (removed click-to-teleport on the XY pad);
  no extra friction (big grab target, wheel-nudge). BUILT, browser-verified, HELD.
- ✅ Waveform = real decoded PCM (not sine-art); tracklist = plain real filenames (not
  fake lit buttons); captions honest ("uploaded to the cloud", not "on-device").
- ✅ Loudness / eardrum cap applied on EVERY produced bar; verified non-regressed.
- ✅ Honest disarmed-region labeling (small/degenerate corpus → says steering is inactive).
- 🅿️ **Relabel "founding demo world"** — confusing jargon. It's the built-in starter demo
  that plays before you train; switches to your world after training. Reword to plain
  "demo world — train your tracks to replace it". Fold into the batched UX deploy.
- 📝 KNOWN (world/theory, disclosed): shipped worlds have a uniform band→role matrix, so
  units collapse under one role (others honestly empty). Not a UI bug; surfaced not faked.

## 4. FEATURES REQUESTED
- 🚧 **Master BPM / tempo control** (output-layer only; pitch-preserving time-stretch;
  optional tap-tempo / MIDI clock) — BUILDING now with prereg + TMP-1..TMP-4 faithfulness
  proofs + real-browser drive + auditor. No engine/settlement changes.
- 🅿️ **READY-TO-TRY acceptance gate** in the harness (task #22) — a `--ready` mode that
  drives the full loop in a real browser and emits GO / NOT-READY, so "ready" = your bar.

## 5. FAITHFULNESS / PROCESS (asked repeatedly)
- ✅ Deterministic faithfulness-regression harness (`cloud/tools/faithfulness_verify.py`)
  — 15 checks, tiered, `--self-test` proves each can fail; git hooks + CLAUDE.md rule.
- ✅ Persistent auditor discipline (ets-auditor on every diff; harness-first).
- ✅ Fabrication incidents LOGGED not quiet-patched (INC-1 green-dashboard drill/waveform;
  INC-2 image-incompleteness σ_φ; INC-3 stale privacy captions; INC-4 API-green-as-ready).
- ✅ Holonomy/circulation meter diagnostic (read-only) — VERDICT: COVERED (loop meter is
  clean antisymmetric circulation; forced-order part annihilated). Repo byte-identical.
- ✅ Torch/beat_this faithfulness explained (INGEST-only beat clock; theory stays classical).
- ✅ Engine-version faithfulness / hash verify (byte-identical engine trees; CHECK-ENGINE-IMMUTABLE).

## 6. DECISIONS ON RECORD (so they're not re-litigated)
- R3(b) LOCKED: raw audio uploads to the cloud (the only way a zero-install browser can
  train); private-mode is a future upgrade. No surface may claim on-device/private.
- Sound tearing: operator decided it's covered by the volume cap for now — not pursuing a
  separate buffering fix (can revisit).
- Memory sizing: 4 GB sufficient, 8 GB bulletproof; 16 GB unnecessary (RAM ≠ tearing fix).

---

### The one deploy still pending (ships at operator "go")
Batched: BPM/tempo (+audit) · visible drill button · click-drag interaction ·
leaner training · corpus persistence. Held because `railway up` restarts the container;
commits/pushes are safe and happen continuously.
