# PREREG — EXPLORE / shared-sets layer (companion sharing)

**Status:** PREREG ONLY (pre-staged 2026-07-17, from `OPEN_ENDS.md` #11). **No build.**
The first section is a PRIVACY FORK that is **explicitly the operator's to decide** —
this document analyzes the three branches fully and gives a recommendation, but does
**not** choose. Nothing is built until the operator signs the fork. This is the
registration of the plan, per the standing discipline (prereg → auditor PASS → merge;
walls surfaced, not patched; no engine/theory edits).

**Deployment version (proposed):** `cloud-mvp3` on the **deployment axis** (see
`VERSION_SCHEME.md` — "Cloud/topology work is a fourth, orthogonal axis… named
`cloud-mvpN`, pinned in `release-manifest.json` under `deployment`"). It changes *where
compute runs and who can reach it*, not the sound (engine-v1) or the surface (ui-v6).
It is very likely the roadmap's unnamed "one more upgrade" between single-user MVP-2 and
multi-user (`OPEN_ENDS.md` #8: single-user MVP-2 → **one more upgrade** → multi-user).
**Operator confirms the name/slot.** Engine, F, world definition, settlement, render are
byte-for-byte untouched; any diff altering a learned object or F is OUT OF SCOPE → stop
and report.

---

## The load-bearing fact (read this first — it forces the fork)

The feature is: (a) opt-in **publish** one of your trained sets so others can play and
STEER it; (b) an **Explore** page listing shared sets to browse and play. The whole
topology is decided by one wall we already own:

> **Playing a set requires rendering it, and rendering needs the unit slices —
> recipe/raw data. CS-1 says recipes never leave the device; CS-4 says there is no
> cloud decoder.** (`PREREG-cloud-mvp2.md`, "the load-bearing fact".)

A shared set's `.etsworld` references the **owner's LOCAL audio bank**. So the instant a
*second* person wants to hear it, the render has to happen *somewhere with the slices*.
There are exactly three somewheres, and each is a different privacy posture. That choice
is the fork — it cannot be deferred into the build, because it decides what crosses the
wire and what invariants get amended.

Visitor **steering** is the easy half and is common to all forks: it is the existing
region-tilt lane, nothing new (see the skeleton below). The hard half is **where the
audio comes from**.

---

## THE PRIVACY FORK — operator decides (analyzed, not chosen)

### Fork (i) — Embed/upload the owner's audio bank at publish (consented CS-1 crossing)

At publish, with an explicit consent step, the owner's realization index / source audio
bank is packaged into a self-contained, redistributable object and uploaded to a shared
store. Visitors download it and render **locally** (their own companion), so playback
stays CS-4-clean; but the owner's private slices have left the device.

- **What crosses the wire:** the owner's **raw/recipe audio bank** (unit slices +
  realization index), embedded into the published world. This is precisely the class
  CS-1 forbids. It would be a *deliberate, disclosed, consent-gated* crossing, **scoped
  to explicitly-listed sets only** (never the working corpus, never on train).
- **New server state:** a persistent **audio store** holding each published set's
  embedded bank + world + σ_φ; a **catalog** of published sets; a **consent record**
  per set (who consented, when, to what).
- **Abuse surface:** the store becomes a honeypot of users' private banks (one breach
  leaks everyone's audio); **copyright redistribution** — an uploaded bank is now
  distributed to strangers, so R5's "no copyright" concern graduates from a demo caveat
  to a live distribution-liability; consent dark-patterns; takedown obligations.
- **Invariants — AMEND vs UNTOUCHED:** **CS-1 must be AMENDED** (a new, narrow, consent-
  scoped exception: "listed-set banks may cross with explicit per-set consent"). **R1
  must be AMENDED** ("there is no server-side audio library" becomes false — the server
  now holds banks to serve others). CS-4 UNTOUCHED (visitor still renders locally).
  Receipts/CS-2/3/5 UNTOUCHED. Amending CS-1 and R1 is a heavy faithfulness decision and
  is exactly the kind of wall this repo does not paper over.

### Fork (ii) — Owner-online rendering (owner renders; visitors steer via relay)

The owner's own companion renders the set; a lightweight **relay** forwards the rendered
PCM out to visitors and forwards visitors' region-tilt gestures back in. When the owner
is offline, the set **goes dark** (honestly listed as offline).

- **What crosses the wire:** **rendered PCM** (owner→relay→visitor) and **region-tilt
  gestures + read-only telemetry** (visitor→relay→owner). **No raw audio, no recipes,
  no realization index ever cross.** PCM is *output* — already outside the trained
  object, the same class as the streamed WAV MVP-2 already sends to its own browser
  (`PREREG-cloud-mvp2.md`, audio path). The novelty is only that the listener is now a
  *different user*, not the owner's own browser.
- **New server state:** a **relay / rendezvous** (session routing + **presence**: which
  sets are live right now); a **catalog** (metadata only — name, description — **no
  audio**); ephemeral per-session steer/PCM forwarding. **No persistent audio store.**
- **Abuse surface:** the relay can observe/record the PCM in transit (mitigate: treat
  relay as untrusted, minimize/encrypt; it never sees slices regardless); a visitor
  **floods steer gestures** (bounded by the per-set rate/authority cap in the skeleton);
  presence leaks the owner's online status; the owner's machine now serves render to
  arbitrary visitors → **compute-exhaustion / DoS on the owner's device** (bound
  concurrent listeners per set).
- **Invariants — AMEND vs UNTOUCHED:** **CS-1 UNTOUCHED** (nothing recipe-class crosses).
  **CS-4 UNTOUCHED** — the decoder runs on the **owner's** device, local to the render;
  the relay decodes nothing, so there is still **no *cloud* decoder**. **R1 UNTOUCHED in
  substance** (owner plays their own device-origin audio; visitors hear it explicitly
  labeled as the owner's shared set, never presented as their own). The one genuinely
  new fact — *rendered output now crosses to another user* — needs a **disclosed new
  data-flow clause** (the same honesty move R3 made for raw→Railway at train time), but
  **breaks no CS wall.**

### Fork (iii) — Self-contained-only sharing (demo-class worlds only)

Only worlds that are **self-contained and redistributable by construction** — embedded
audio, no external files, no copyright, exactly the `demo.etsworld` / R5 contract — may
be listed. Visitors download the world and render locally.

- **What crosses the wire:** a **self-contained `.etsworld`** whose embedded audio the
  owner **attests is redistributable**. No *private* corpus crosses — only content that
  was already shareable by declaration (the same class the repo already ships as the
  committed demo).
- **New server state:** a **catalog** + a small **store of self-contained worlds**
  (these objects are *meant* to be shared); a per-set **redistributable-audio
  attestation**. No presence, no relay.
- **Abuse surface:** someone publishes a world with **copyrighted audio embedded** →
  needs a publish-time attestation gate + moderation/takedown; but **no private bank can
  leak**, because only redistributable content is admissible.
- **Invariants — AMEND vs UNTOUCHED:** **CS-1 UNTOUCHED in substance** — the bytes that
  cross are redistributable-by-declaration, not the user's private corpus; this is R5's
  contract generalized, not a new crossing of *private* data. **R1** needs a **narrow
  note** ("no server-side *user-private* audio library" — the store holds only
  demo-class, owner-attested-shareable worlds). CS-4 UNTOUCHED (visitor renders locally).
  The most conservative branch: it essentially ships "an Explore page of demo-class
  sets," and the repo already contains one such object.

### RECOMMENDATION (clearly marked — the operator still decides)

> **RECOMMENDATION:** Adopt **Fork (ii), owner-online rendering, as the mechanism for
> sharing a user's *real, private* trained set**, and stand up **Fork (iii),
> self-contained-only, as the zero-crossing bootstrap** so the Explore page has
> always-on content before any relay exists. **Reject Fork (i) as the default.**
>
> **Reasoning.** The feature's actual ask is "open one of *your* sets" — a private
> trained corpus. Only forks (i) and (ii) can share a *private* set at all; fork (iii)
> can only share demo-class content. Between (i) and (ii), **(ii) breaks no CS wall**:
> CS-1 and CS-4 stay intact, only rendered output (already-outside-the-object) and
> gestures cross, and it is the faithful multi-user analog of the MVP-2 topology
> (render local, only PCM + gesture on the wire). **(i) requires amending both CS-1 and
> R1** and turns the server into a honeypot of private banks with live copyright-
> redistribution liability — the heaviest possible privacy posture for a convenience
> ("always-on") that (ii) approximates without the crossing. The one honest cost of (ii)
> — **sets go dark when the owner is offline** — is a disclosed limitation, not an
> invariant break, and it is the *right* default for a system whose whole thesis is
> "your audio stays on your device." (iii) is cheap, always-on, and CS-clean, so it is
> the correct thing to ship *first* to prove the Explore page + publish/unpublish +
> catalog machinery with the lowest blast radius, before the relay lands.
>
> Fork (i) should be reached for **only if** always-on sharing of *private* sets becomes
> a hard product requirement, and then **only** behind an explicit CS-1 + R1 amendment
> recorded HERE first, per the enforcement rule in `COMPANION_INVARIANTS.md`.

---

## Invariant-preserving skeleton (common to ALL forks — this part is not forked)

Whichever branch the operator signs, the build MUST hold all of the following. None of
these depend on the fork; they are the non-negotiable frame the fork sits inside.

- **Steering is ONLY the region-tilt lane.** A visitor's sole engine-control path is the
  existing region-tilt tap (the ui-v5 f3b / ui-v6 FIELD door invariant, `single_region_
  tilt_authority`). **No new engine authority, no second control path** — a second path
  is a WALL. Telemetry to visitors is **read-only**.
- **Per-set rate + authority limits on visitor steer.** Each published set carries a
  visitor **steer-rate cap** and a **steer-authority cap** (max |u| a visitor may apply),
  enforced server/owner-side, so a stranger cannot drive the set past what the owner
  allows or flood it. (Bounds are also the abuse mitigation for fork (ii)'s relay.)
- **No cloud decoder (CS-4), ever.** Rendering happens on a *device* local to the slices
  — the owner (ii) or the visitor after local download (i)/(iii). No server renders
  audio. The catalog/relay/store import no renderer and emit no synthesized audio.
- **Publish is opt-in, per set, with an explicit consent step.** Nothing is ever listed
  by default. Publishing the working/private corpus is never automatic and never a
  side-effect of train. Consent is per set and recorded.
- **Unpublish / delete actually revokes.** Removing a set from Explore must make it
  **truly unreachable**: catalog entry gone, relay session refused (ii), stored object
  deleted and its URL 404 (i)/(iii). No soft-hide that still serves.
- **CS-1 unchanged by default.** Only fork (i), and only if the operator signs its
  amendment, may let recipe-class bytes cross — and then only for explicitly listed sets.
  Absent that signature, the whitelist encoder remains the sole wire exit and nothing
  recipe-class crosses.

---

## Harness sketch — the checks that MUST bite (`cloud/tests/`, extend the mvp1/2 suite)

Written now so the build cannot quietly skip them. Each must be shown to FAIL on a
violating fixture (bites), not merely pass.

- **EXP-A unlisted-is-unreachable:** a set that was never published (and one that was
  unpublished) is not enumerable in the catalog **and** cannot be played/steered by
  direct ID. A fixture that pokes an unpublished ID FAILS to get audio/telemetry.
- **EXP-B unpublish revokes:** after unpublish/delete, the catalog entry is gone, the
  relay refuses the session (ii) / the stored object 404s (i)/(iii). A fixture holding a
  pre-unpublish handle can no longer reach the set.
- **EXP-C visitor-steer-is-region-tilt-only:** the visitor→set control boundary exposes
  ONLY the region-tilt tap. Port the f3b/FIELD door test to this boundary; a fixture
  trying to reach **ingest / train / reset / a second lane** FAILS. Rate/authority caps
  are enforced (a flood/over-authority steer is clamped or refused).
- **EXP-D CS-1-shaped guard for the chosen fork:**
  - **(ii):** capture the exact bytes the relay forwards → assert **PCM + gesture +
    telemetry only**, **no** slice/recipe/realization-index/provenance key. A fixture
    attaching a slice FAILS. (Mirrors `seam_verify.py`'s post_job byte-capture.)
  - **(iii):** publish refuses a world that is **not self-contained** (external file
    refs / unattested audio) — the redistributable-audio attestation gate bites.
  - **(i) — only if signed:** the consent gate bites (no consent record → no upload);
    the crossing is scoped to the listed set only (the working corpus never crosses);
    and this is the ONE place the CS-1 amendment is exercised, logged loudly.
- **EXP-E no-cloud-decoder (all forks):** static check — the catalog/relay/store images
  import no renderer and ship no audio synthesis (mirror MVP2-B). Every sample a visitor
  hears was rendered on a device (owner or visitor), never on the sharing server.

---

## Open questions (questions, not answers — for the operator + the multi-user prereg)

- **Owner auth vs. visitor auth.** MVP-2 is single shared-bearer. Publishing implies an
  *owner identity* (whose set is this?) and *visitor identity* (or anonymous browse?).
  What is the minimum identity model, and how much of it is really the multi-user store
  from `OPEN_ENDS.md` #8 arriving early?
- **Quotas.** Per-owner published-set count / storage (i)/(iii); per-set concurrent
  listeners and relay bandwidth (ii). Where do these live, and who pays?
- **Moderation / takedown.** Copyright and abuse reporting — most acute for (i), present
  for (iii), minimal for (ii). What is the takedown SLA and mechanism, and does unpublish
  (EXP-B) satisfy it?
- **Relation to multi-user (#8).** #8 parks "key issuance / revocation / per-key quotas +
  a store, and single-tenant-per-deploy vs. shared-multi-tenant." Explore needs a catalog
  (a store) and identities — **how much of #8 does this pull forward**, and does building
  Explore effectively *start* multi-user rather than precede it? Is the "one more upgrade"
  slot in #8 exactly this, or a strict subset?
- **Presence & privacy (ii).** Is broadcasting "owner X is online now" acceptable, and
  can a set be listed-but-dark without leaking a schedule?
- **Catalog trust.** Set names/descriptions are user-authored untrusted text — where is
  the moderation/escaping boundary for the Explore listing itself?

---

## Environment honesty & sequencing

Real hosting (a relay, a catalog service, a store) needs the operator's cloud account —
not provisionable from this sandbox (same honesty as mvp1/mvp2). If a build is signed,
the deliverable is built deploy-ready and verified HERE with the sharing server stood in
locally and the full publish → list → visitor-play → steer → unpublish loop exercised
headlessly, stating exactly what stays local at each step. Recommended order once a fork
is signed: (1) catalog + publish/unpublish + EXP-A/B/E on fork (iii) (zero-crossing,
lowest risk); (2) region-tilt visitor boundary + caps + EXP-C; (3) the chosen private-
set mechanism ((ii) relay, or (i) behind its signed amendment) + EXP-D; (4) the Explore
FE, re-pointed at the FIELD (ui-v6) play surface per #11's sequencing note. Auditor PASS
before merge; the release tuple gains a `deployment: cloud-mvp3` pin on merge; each step
logged to `LEDGER.md`.

## No build without sign-off

**This document is the registration of the plan, not a green light.** No code is written
and nothing is merged until the operator signs the PRIVACY FORK ((i) / (ii) / (iii), or a
phased combination). If the signed choice is fork (i), its CS-1 + R1 amendment is written
into `COMPANION_INVARIANTS.md` FIRST, on the record, per that file's enforcement rule.
Until then: no ingest change, no engine change, no wire change — the existing stage-3
whitelist remains the sole device→cloud exit.

---

## OPERATOR DECISION — recorded 2026-07-17

The operator has signed the fork, in their own words: "as of now its a simple
opt in to share their sets, whatevers easiest im not concerned about privacy /
data infra atm, just the simplest way to demo functionality."

Registered reading (on the record):
- **Demo-first**: build the SIMPLEST opt-in share + Explore list that
  demonstrates the functionality. Privacy/data infrastructure hardening is
  explicitly DEFERRED by the operator for the demo phase — this is a
  disclosed, operator-authorized scope decision, not a silent invariant drop.
- Concretely this selects the hosted-companion topology already live on the
  `ets-web` deployment: users who train there have ALREADY chosen to upload
  audio to that server (the hosted variant's ingest), so an opt-in "share this
  set" toggle + a server-side listing + load-into-play adds NO new crossing
  beyond what the operator has already accepted for the demo. Fork (ii)/(iii)
  remain the recorded path for the later, hardened version.
- Standing guardrails that still hold even in the demo (cheap, not deferred):
  sharing is OPT-IN per set; unshare delists; visitor steering uses only the
  region-tilt lane with the existing safe envelope; ingest/train/reset remain
  gated per R6.
- **BUILD WALL (blocks the build, surfaced not papered over):** the deployed
  `ets-web` companion (access-key gate, /api/auth, in-proc cloud) runs code
  that exists in NO branch of this repo — it was deployed from the crashed
  session's container and its source survives only in Railway's deployment
  snapshot. The explore build must wait for either (a) the operator recovering
  that snapshot (Railway dashboard → deployment → source download), or (b) an
  explicit decision to rebuild the access-key/in-proc delta in-repo from
  scratch. Until then, building "on top of" the live site is not possible
  from this repository.

---

## BUILD PLAN — demo phase (registered 2026-07-17, operator delegated "your call")

Scope (one prereg'd build, `cloud/` only; engine untouched; ui-v6 untouched):

1. **Rebuild the lost ets-web delta IN-REPO** (the deployed code exists only in
   Railway snapshot ddcadfb0; functionality fully characterized from live
   probes + logs + deploy metadata): access-key gate (`ETS_ACCESS_KEYS`
   comma-separated; `/api/auth` issues a session token; all API routes gated;
   access page), per-visitor server-side sessions, in-proc cloud mode.
2. **OOM fix designed in** (root cause measured: 7.997 GB peak against the
   8 GB cap; per-visitor engine worlds + in-proc training): ONE shared demo
   engine for all visitors; per-visitor TRAINED worlds behind an LRU cache
   (`ETS_MAX_LOADED_WORLDS`, default 2) with idle eviction; at most ONE
   in-proc training at a time (second gets an honest busy/queue response).
3. **Opt-in share + EXPLORE** (the operator-signed demo feature): per-set
   share toggle (opt-in, default OFF), server-side listing, Explore list +
   load-into-play, unshare delists immediately.
4. **Tab IA per `cloud/DESIGN-companion-tabs-v1.md`**: PLAY / TRAIN / EXPLORE;
   keyless visitor = access page (present behavior); honest progress states
   per design §4A — staged train progress from REAL backend stage transitions
   (train seam records its stage in session state; `/api/status` exposes it),
   loading/slow/dead distinguishable on the world-load overlay.

Invariant reading (disclosed): R6 gates ingest/train/reset for the PUBLIC
(keyless) surface — unchanged. ACCESS-KEYED visitors are authorized users of
the hosted companion (the operator issues the keys), so keyed training is the
companion's normal owner power, not a public-mode regression. Hosted ingest =
audio uploads to the operator's own server — the operator-accepted demo
topology recorded above. R1–R5, CS-1..CS-5 otherwise untouched; steering
remains region-tilt-lane-only with the safe envelope; no cloud decoder.

Harness (must bite): existing cloud suite stays green + EXP-A..E from this
prereg + AUTH (keyless 401 on every gated route; bad key rejected; keyed ok)
+ MEM (the shared-demo singleton is actually shared; the LRU cap evicts; a
second concurrent train is refused honestly) + PROG (train stages appear in
/api/status in order; no stage skipped or fabricated).

Deploy sequencing: builder → ets-auditor PASS (notes fixed) → merge to main →
connect Railway service to GitHub main → deploy → verify live (health + auth
+ play path) → record. Rollback point: Railway deployment ddcadfb0 (running
image retained in deployment history) + the operator's snapshot download.

## AUDIT RESULT — demo-phase build (2026-07-17)

ets-auditor: **PASS-WITH-NOTES** on commit 113217e. All claims verified (scope
clean; keyless byte-faithful; gate sound incl. traversal guard; memory bounds
real with leak-hunt clean; share/unshare revokes, EXP-D demo-analog reading
ACCEPTED; steering single-lane with envelope+cap; progress signal-bound; 61/61
tests + standalone verifier reproduced by the auditor).
- MUST-FIX (governance) — R1's server-side-library clause amended on the
  record in COMPANION_INVARIANTS.md (opt-in shared sets, demo phase,
  attribution preserved): DONE in this commit.
- Notes: per-set steer rate caps deferred to the hardened fork (operator-
  scoped); CatalogEntry.owner_token dead code (remove in hardened pass);
  eviction-cuts-live-listeners now disclosed in engine_bridge.py; catalog
  text escaping present, catalog-trust question stays open for hardened fork.
