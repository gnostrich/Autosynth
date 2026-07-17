# ETS — standing instructions for any agent working in this repo

Read this first, every session. These are enforcement rules, not suggestions.

## Non-negotiable product invariants
`cloud/COMPANION_INVARIANTS.md` lists R1–R5 (device-origin audio; cloud training;
privacy boundary; reset/change-corpus; fresh-clone-plays-a-self-contained-demo).
**Never drop, weaken, or regress any of them.** If a change seems to require
breaking one, STOP and surface it to the operator — never silently.

## Faithfulness discipline (the "check everything" process)
1. **Auditor pass before every merge.** Any change touching `cloud/`, `ets/`, or
   `architecture-v6/ets/` gets an **ets-auditor** pass (Opus-class model) that
   verifies it against `cloud/COMPANION_INVARIANTS.md` AND the ETS faithfulness
   manifest / CS-1..CS-5. The auditor is read-only and adversarial. No merge
   without its PASS (or PASS-WITH-NOTES with the notes fixed).
2. **Builder/auditor pairing.** Non-trivial builds are done by a builder agent and
   reviewed by a separate auditor agent — never self-certified.
3. **Walls are surfaced, not patched.** If you hit a real limit (a wall), disclose
   it in the prereg + code + to the operator. Never fake, forge, or paper over
   (no fabricated measurements, no hash re-stamps, no silent no-ops). Prior real
   walls that MUST stay honest: σ_φ is measured not fabricated; only stage-3
   crosses the wire; no cloud decoder; region steering honestly disarms on a
   degenerate corpus.
4. **No engine/theory edits without a prereg + operator sign-off.** `ets/` (root
   engine-v1) is byte-verified and immutable; `architecture-v6/ets` is the ui-v5
   engine. Changes to F / settlement / render / world definition are out of scope
   unless explicitly pre-registered and approved.
5. **Verify by running, not asserting.** Prove behavior end-to-end (the standalone
   `cloud/tools/*_verify.py` pattern) before claiming it works. Note that this
   sandbox renders ~100x slower than real hardware — build/verify accordingly.

## Repo hygiene
- **Keep `main` current.** After work is committed to the working branch, merge it
  to `main` (PR + merge) so the operator only ever needs `main`. Don't make them
  chase branches.
- **A fresh clone must work.** Anything required to run (worlds, demo assets) must
  be committed and self-contained — never reference absolute paths or uncommitted/
  copyrighted files. `demo.etsworld` is the committed, self-contained demo.
- Ledgers (`LEDGER.md`, `VERSION_LEDGER.jsonl`) and `release-manifest.json` are the
  provenance record; keep them updated.
