# ETS companion — NON-NEGOTIABLE product invariants

These are permanent, operator-set requirements. **Every change to the companion /
cloud path must be checked against them (ets-auditor pass required before merge).**
Do not drop, weaken, or regress any of these. If a change appears to require
breaking one, STOP and surface it — never silently.

- **R1 — Audio originates on the USER'S DEVICE.** The user supplies their own
  audio (drag-drop / file pick in the browser). There is no server-side audio
  library; the app never plays "someone else's" audio as if it were the user's.

  *R1 amendment — OPT-IN SHARED SETS, demo phase (operator-signed 2026-07-17;
  recorded decision + scope in `cloud/PREREG-explore-shared-sets.md`).* On the
  ACCESS-KEYED hosted deploy, a user may explicitly SHARE a set they trained;
  the server then renders that set for other keyed users (audible + steerable
  via the Explore page). This narrowly relaxes the "no server-side audio
  library" clause for EXPLICITLY SHARED sets only: sharing is opt-in per set
  (default OFF), unshare/delete actually revokes (auditor-verified EXP-B), and
  a shared set is always ATTRIBUTED ("by <owner>" / "shared set") — the second
  clause, never passing someone else's audio off as the user's own, stays
  fully in force. Keyless/public visitors still get only the self-contained
  demo (R6 unchanged). The hardened privacy forks (owner-online rendering /
  self-contained-only) recorded in the prereg remain the path for any
  post-demo tightening.

- **R2 — Training runs via the CLOUD.** The user's own audio drives a cloud
  training step (Railway) that produces THAT user's world. "Upload my audio, train
  in the cloud, get my world."

- **R3 — Audio flow (operator's model, 2026-07-17).** The ONLY local step is
  **fetching the user's music from their device** (browser file-pick / drag-drop —
  the "device-origin" of R1). After that first local fetch, the audio goes to the
  **Railway** server, which does the training/processing; the interface talks to
  Railway for everything else (R6). So the raw audio DOES leave the device (it is
  processed on Railway) — the earlier "stage-3-only / audio never leaves" sealed
  design is superseded by this simpler model unless the operator says otherwise.
  *(If privacy-max is ever wanted again, that's the WASM-in-browser path in R6(b).)*

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
3. CS-1..CS-5 (the stage-3 boundary) remain in force per R3(a) unless/until the
   operator locks R3(b).
4. This file is the source of truth for "what the companion must always do." If a
   requirement changes, it changes HERE first, on the record.
