# PREREG — durable per-key session identity, orphan recovery, async train, warm-on-open

**Date:** 2026-07-24 · **Scope:** `cloud/companion/app.py` + `static/index.html` + tests.
**NO engine tree edit** (root `ets/`, `architecture-v6/ets/` untouched); no settlement/render/
steering path touched — audio + grid remain byte-identical.

## Live failures this remediates (all observed on ets-web, 2026-07-23/24)
1. **"My trained set is gone."** `/api/auth` minted a FRESH session dir per token
   (`visitor_<sha256(token)[:16]>`), so every re-login (new browser session, lost cookie,
   re-entered key) stranded the previous dir — corpus, trained world and all — orphaned on
   the volume. The operator's 10-track trained set was lost this way (it is still on disk).
2. **Train wedged / double-trained.** `/api/train` ran the full multi-minute train inside ONE
   HTTP request; the edge gateway killed the response (~60 s) while the server kept training;
   the FE showed "upstream error", the operator re-clicked, and a second train started.
3. **Silent cold Play.** Opening/recovering a trained set built its bank lazily at first
   stream — minutes of silence that read as "not playing".

## The fix (contract)
- **One key = one session, durably.** `sha256(KEY)` → `owners.json` record + one resident
  session. Every login re-lands on the same dir. Only hashes touch the volume (same privacy
  class as the existing token-hash store; the raw key/token never lands on disk).
- **Adoption.** First-ever login for a key adopts the most recent orphaned `visitor_*`/`anon_*`
  dir holding a trained world (else ingested audio) — pointers only, nothing moved/deleted.
  **SINGLE-key deploys only** (auditor finding B1): with one key the orphan's owner is
  unambiguous; with several it is unknowable and adoption would alias two owners onto one
  dir. Multi-key first logins start fresh. Dirs already claimed by an owner record are never
  adoptable (no aliasing even in pathological states).
- **Legacy migration.** A pre-fix token (record without owner tag) migrates onto the key's
  owner identity **only on single-key deploys** (unambiguous) — the already-open browser
  recovers without a re-login.
- **`/api/recover`** (key-gated by the same training secret): read-only inventory of every
  on-volume dir holding a trained world/audio; `{key, dir}` repoints the owner session.
  Refuses: dirs outside the session base, infrastructure dirs (`_store` — else a later
  reset() could unlink the durable store, auditor finding B3), dirs claimed by a different
  owner, and — the whole route — **multi-key deploys** (auditor finding B2: volume-wide
  inventory/rebind would let any key holder enumerate and seize another owner's corpus;
  per-owner scoping is a disclosed follow-up). A corpus can never silently disappear again.
- **Async train (keyed deploys).** `/api/train` returns `{training:true}` immediately;
  the truth lives in `/api/status` (`training` / `train_result` / `train_error`); a re-click
  ATTACHES to the running train (lock-guarded — exactly one). Keyless/local path unchanged
  (synchronous, tests' contract intact). FE reconciles from `/api/status` after dropped
  requests AND page reloads; a dropped request is never reported as failure.
- **Warm-on-open/restore.** `_warm_async` builds the bank in a daemon thread via the SAME
  LRU-capped `WorldRegistry` (memory bound holds; warm failure logged, never raised).

## Honest walls / disclosed tradeoffs
- Adoption picks the **newest** trained dir; on this deploy only the keyed operator can train,
  so the newest trained orphan is theirs. If it ever picks wrong, `/api/recover` lists all
  candidates and repoints explicitly — surfaced lever, not a silent guess.
- Warm spends CPU on a world nobody may play (same operator-accepted tradeoff as share-time
  pre-warm, OPEN_ENDS #21d).
- Test semantic update, deliberate: tests that fabricated "distinct strangers" by reusing ONE
  access key now use distinct keys — under per-key identity, same key IS same person (that is
  the fix). Cross-KEY and anon-visitor isolation is preserved by gating adoption and
  /api/recover to single-key deploys (auditor findings B1/B2, fixed pre-merge and pinned by
  tests); on multi-key deploys recovery is deliberately unavailable until per-owner scoping.
- `owners.json` stores unsalted `sha256(KEY)` (auditor note N1): a human-chosen low-entropy
  key is offline-brute-forceable if the volume itself is compromised. Same storage class as
  the existing token-hash store; operators should use high-entropy keys.
- A train that completes while the page is closed shows on reload as the trained world being
  live (Play repoints), not as the result banner (auditor note N2 — banner is per-page-load).

## Gate
`cloud/tests/test_owner_identity_recover.py` (15 tests: re-login identity, redeploy survival,
distinct keys, adoption preference, recover inventory + rebind + traversal refusal, async
attach-not-double-train, error surfacing, legacy migration, and the five auditor-finding
pins — multikey-no-adoption/no-aliasing (B1), adoption-skips-claimed-dirs (B1),
rebind-refuses-`_store` (B3), rebind-refuses-other-owner (B2), HTTP 403 on multi-key
/api/recover (B2)) + full cloud suite green.
ets-auditor: FAIL (B1/B2/B3) → fixed → **PASS-WITH-NOTES**, notes fixed pre-merge.
