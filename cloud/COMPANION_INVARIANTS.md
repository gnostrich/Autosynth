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

- **R3 — Privacy boundary — [OPERATOR TO CONFIRM, then LOCKED].**
  Exactly one of these is the rule; the operator picks it and it is locked:
  - **(a) Private:** raw audio stays on the device; only derived, gauge-invariant
    **stage-3** data crosses to the cloud (the sealed design already built,
    CS-1..CS-5). Raw audio + recipes NEVER uploaded.
  - **(b) Simple:** the raw audio itself is uploaded to the cloud for training.
  *(Currently built = (a). Awaiting operator confirmation before locking.)*

- **R4 — RESET / change corpus.** The user can clear the current corpus and load a
  new one at any time ("New corpus" reset) — account-free, one corpus at a time,
  full revert.

- **R5 — Fresh clone PLAYS out of the box.** A committed, self-contained demo world
  (`demo.etsworld` — embedded audio, no external files, no copyright) ships so
  anyone who clones can hear + steer immediately, without supplying audio first.

## Enforcement (the "never repeat this again" mechanism)

1. Every change touching `cloud/` or `cloud/companion/` gets an **ets-auditor pass
   against this file** before it merges. No merge without it.
2. The auditor explicitly re-checks R1–R5 each time and reports any regression.
3. CS-1..CS-5 (the stage-3 boundary) remain in force per R3(a) unless/until the
   operator locks R3(b).
4. This file is the source of truth for "what the companion must always do." If a
   requirement changes, it changes HERE first, on the record.
