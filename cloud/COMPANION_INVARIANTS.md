# ETS companion — NON-NEGOTIABLE product invariants

These are permanent, operator-set requirements. **Every change to the companion /
cloud path must be checked against them (ets-auditor pass required before merge).**
Do not drop, weaken, or regress any of these. If a change appears to require
breaking one, STOP and surface it — never silently.

- **R1 — Audio originates on the USER'S DEVICE.** The user supplies their own
  audio (drag-drop / file pick in the browser). There is no server-side audio
  library; the app never plays "someone else's" audio as if it were the user's.

- **R2 — Training runs via the CLOUD.** The user's own audio drives a cloud
  training step (Railway) that produces THAT user's world. "Upload my audio, train
  in the cloud, get my world."

- **R3 — Audio flow (operator's model, 2026-07-17). LOCKED to R3(b).** The ONLY
  local step is **fetching the user's music from their device** (browser file-pick /
  drag-drop — the "device-origin" of R1). After that first local fetch, the **raw
  audio is uploaded to the Railway server**, which does the training/processing; the
  interface talks to Railway for everything else (R6). **The raw audio DOES leave the
  device and is processed in the cloud.** This is the operator's explicit, current
  decision (confirmed 2026-07-17: "allow this for the time being … so this works with
  drag and drop") — the earlier "stage-3-only / audio never leaves" sealed design is
  **superseded** for the hosted app.
  - **HONESTY REQUIREMENT (load-bearing):** while R3(b) is active, NO surface, label,
    caption, comment, or doc may state or imply the audio stays on the device / is
    private / is sealed / "only a summary is uploaded". The UI must be unambiguous
    that **tracks are uploaded to the cloud and processed there** ("Train on cloud").
    A privacy claim while R3(b) is live would itself be a fabrication.
  - **PLANNED UPGRADE — R3(a) "private mode" (raw never leaves device).** Recorded as
    a future build, not yet done. Two routes: **(i) local companion** — a small
    on-device install runs stage-3 ingest locally and uploads ONLY the stage-3
    whitelist (reuses the existing sealed companion + the `encode_job` wire that
    already passes MVP-A); or **(ii) browser WASM** — port stage-3 ingest to
    WebAssembly so audio stays on device with zero install (large engine→WASM
    rebuild). When either lands, R3 flips to R3(a) HERE first, on the record.

- **R4 — RESET / change corpus.** The user can clear the current corpus and load a
  new one at any time ("New corpus" reset) — account-free, one corpus at a time,
  full revert.

- **R5 — Fresh clone PLAYS out of the box.** A committed, self-contained demo world
  (`demo.etsworld` — embedded audio, no external files, no copyright) ships so
  anyone can hear + steer immediately, without supplying audio first.

- **R6 — Interface is served by the CLOUD, not a repo clone [TARGET].** An end user
  must NOT need to clone the GitHub repo to use the instrument. The interface gets
  everything it needs (UI, worlds/assets, engine services) directly from the
  **Railway** server; we keep the server updated with whatever it needs.
  **Status: NOT yet met** — today's companion is local Python and still needs a
  clone. This is the next major build (a Railway-served web app).
  **Forced decision (this IS the R3 lock):** with no local install, the engine can't
  run locally, so audio must render EITHER (a) on Railway — server-side, meaning the
  audio is processed in the cloud [= R3(b)], OR (b) in the browser via WASM — audio
  stays on device [= R3(a)], but that's a large engine-to-WebAssembly rebuild.

## Enforcement (the "never repeat this again" mechanism)

1. Every change touching `cloud/` or `cloud/companion/` gets an **ets-auditor pass
   against this file** before it merges. No merge without it.
2. The auditor explicitly re-checks R1–R5 each time and reports any regression.
3. **R3(b) is LOCKED (operator, 2026-07-17).** The CS-1..CS-5 "raw never leaves the
   device" wall is therefore **superseded for the hosted app**: raw audio uploads to
   Railway by design. What CS-1..CS-5 still guard is the **internal** encoder hop —
   `cloud.common.encode_job` (companion → anchor-fit) stays whitelist-closed to
   stage-3 (`cost/mass/slot_hist/band_profile`), which `test_mvp_a_raw_never_uploaded`
   verifies. NOTE (honesty): that test guards the encoder wire, NOT the browser→Railway
   upload — it is NOT evidence that raw audio stays on device in the hosted app; it
   does not, and that is the declared R3(b) behavior. When R3(a) "private mode" is
   built, CS-1 returns to full force at the device boundary and this line flips.
4. This file is the source of truth for "what the companion must always do." If a
   requirement changes, it changes HERE first, on the record.
5. MECHANICAL floor before the judgement pass: `cloud/tools/faithfulness_verify.py`
   (spec: `cloud/FAITHFULNESS_REGRESSION_SPEC.md`) re-asserts these invariants on
   every edit/commit/merge and fails loud. `CHECK-INVARIANTS-DOC` asserts R1–R6 are
   still present here; `CHECK-NO-FABRICATION` enforces REAL-DATA-or-DISARMED for
   every UI surface; `CHECK-CS-DECODER-FREE` guards CS-4. The auditor runs the
   harness first and pastes its output; no merge on a red harness.
