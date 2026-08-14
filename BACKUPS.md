# Backup / restore points (version-control snapshots)

**Why this file exists.** Git *tags* are not durable in this build environment — the
remote rejects tag pushes and GitHub carries zero tags, so tag labels live only in a
local clone and vanish when the container is reclaimed. The restore points below are
therefore recorded by **commit SHA**, which *is* durable: every SHA here is an ancestor
of `main`, so a fresh clone can recover any of these states with:

```
git checkout <sha>            # detached snapshot of that milestone
# or branch from it:
git checkout -b <name> <sha>
```

Keep this file updated whenever a new milestone/backup is cut (the same moment you'd
have cut a tag). `release-manifest.json` remains the "what am I running" source of truth;
this file is the "how do I get back to X" index.

| label (local tag) | commit SHA | date | snapshot |
|---|---|---|---|
| `engine-v1.1-freeze` | `862fb6d949764605bd140d4d1d3e5acaae298a56` | 2026-07-18 | engine-v1.1-freeze (informative-B + strengthened receipt) |
| `pre-informative-B-2026-07-18` | `629a5ac9468c5e61a908b3da9f550f8c6c06a698` | 2026-07-18 | before the informative-B engine freeze |
| `pre-uiv6-field-2026-07-17` | `5ff6abdbc2ceb047d2143eb6eacca9ee19be6423` | 2026-07-17 | ui-v5 (pads + XY + drill), rollback for the ui-v6 field |
| `pre-webfab-remediation-2026-07-18` | `b054411ba6336fcd2d14f554b23fb2a6812eae9d` | 2026-07-18 | before the WEBFAB fabrication-surface remediation |
| `pre-sampler-xy-2026-07-19` | `de40dd87ff7c78c74e14cd7fde41ce2433ae3e2e` | 2026-07-19 | before any sampler/bias steering work (pre-channel-bias) |
| `field-bias-rev3-live-2026-07-19` | `042c274455a878d2f8400f787696621c99cc4f62` | 2026-07-19 | THE FIELD + soft track/unit fiber bias (deployed code at `eb557b9`) |
| `track-role-drill-live-2026-07-20` | `f3e4a2d9507e45b6861d9237adf061c35b004a77` | 2026-07-20 | **CURRENT LIVE** — track×role drill (emergent sub-track handle; drill re-enabled onto role cells; dodges the role wall) |
| `pre-render-throughput-2026-07-24` | `97221908c2acc3b27ee8d67e339568302c1f8d9f` | 2026-07-24 | before the render-throughput optimization (PREREG-render-throughput.md, ratified) — rollback point |
| `pre-waveform-scrub-2026-07-25` | `27a6fa8f757b9e8450d8757f57a5c81b5916bdde` | 2026-07-25 | before the WAVEFORM SCRUB-TO-STEER second view (PREREG-waveform-scrub.md, operator directive) |

## Milestone — track×role GRID (row/column/cell bias, seen-through routing) (2026-07-20)
- **What it is:** the Play surface as a **track × role grid**. Three bias gestures, each routed to
  the engine step that WEIGHS its type (the "seen-through" rule): **ROW (track)** → casting/pick
  (`set_channel_bias`), **CELL (track,role)** → casting/pick (`set_track_role_bias`), **COLUMN
  (role k)** → **settlement** (`payload.region[k] += amp·SAFE_REGION_MAGNITUDE` → `set_region`).
  The column is the honest whole-role handle: a pure-role FIBER push is the measured-inert role
  wall, so it rides the SETTLEMENT lane only, never the fiber. All three lanes coexist (arrange +
  cast at once); byte-identical when all neutral; column honestly disarms when region σ=0.
- **Flag:** `FIELD_GRID_ENABLED` (default true) — ONE flag back to the drill field (retained dormant + intact).
- **Gate (`cloud/tools/track_role_grid_verify.py`, corpus20 M=5 region-armed, PASS):** COLUMN→settlement
  role-2 share 0.246→1.000 (+1) / →0.018 (−1), ρ=1.000; ROW→pick track-4 0.303→0.984 ρ=0.975;
  CELL→pick (4,2) 0.083→0.116 ρ=0.900; byte-identical-neutral, honest-disarm, coexistence all True.
- **Prereg:** `papers/PREREG-track-role-grid.md`. **ets-auditor PASS** (all 8 claims verified; no engine edit). Provenance commit `db3365f` (+ manifest/backups).
- **Rollback:** `FIELD_GRID_ENABLED=false` (drill field) → or `track-role-drill-live-2026-07-20` (`f3e4a2d`) → or `field-bias-rev3-live-2026-07-19` (`042c274`).

## Live operational event — 20-track corpus posted (2026-07-20)
- **Not a code milestone** (no engine/UI change): the operator's real 20-track corpus was
  trained on the live 8 GB Hobby `ets-web` box via `/api/train` and published to Explore as
  set **`set-c0e8cdfabd`** ("20-track field (my corpus, M=5)"). Train: HTTP 200 in 283 s,
  `is_trained:true`, M=5, `/api/health` green throughout; a fresh anonymous listener streamed
  real audio (RMS 1483, 99.9 % non-zero). Bank dtype = float32 (service `ETS_BANK_DTYPE` unset;
  float16 is a one-redeploy flip that also touches the demo).
- **Faithfulness correction shipped alongside** (this commit): `papers/CAPACITY_STUDY.md` §2/§5
  carried a mis-applied "3.5-4× bank ⇒ 20 tracks OOM 8 GB / need 32 GB" number. That model
  measured the `cap_single` *eager-bank* path; the DEPLOYED `/api/train` is *lazy-bank*
  (`build_trained_world` never calls `build_bank`; the bank materialises at first playback).
  MEASURED deployed peaks (20 tracks / 30 min / float16): train **1.35 GB**, play **2.27 GB** —
  both well within 8 GB, proven by the live train above. Repro tool: `cloud/tools/train_peak_verify.py`.

## Current live milestone — track×role drill (2026-07-20)
- **Deployed code:** `f3e4a2d9507e45b6861d9237adf061c35b004a77` (`main`, live on `ets-web` / www.autosynth.fun).
- **What it is:** the field drill is re-enabled (`FIELD_DRILL_ENABLED=true`) and re-pointed from units to the **emergent `(track × role)` handle** — a track opens into ROLE cells (noise-floor gated), each damp/amplifying that track's material *within* a role via a third fiber grain `track_role_logbias` (keyed `(track_id, slot-role k)`) on the single carrier. Measured LIVE control (ρ=1.0, strong damp / moderate amp) that **dodges the role wall** (pure-role inert, track-pinned cell moves); byte-identical off; units retained dormant; ONE-FLAG shelve-able (`FIELD_DRILL_ENABLED=false` → track-level-only).
- **Prereg (PROMOTED + RATIFIED):** `PREREG-track-role-bias.md`; ets-auditor PASS on mechanism (`6f00fff`) + FE drill (`d860937`). Builds on the RATIFIED REV1-soft / REV2-bidirectional / REV3-unit-grain preregs.
- **Rollback:** `field-bias-rev3-live-2026-07-19` (`042c274`, track/unit drill), or set `FIELD_DRILL_ENABLED=false` for track-level-only, or `pre-sampler-xy-2026-07-19` (pre-bias).

### Prior milestone — field-bias REV3 (2026-07-19)
- Deployed `eb557b9`; provenance `042c274`. THE FIELD + soft track/unit fiber bias, drill track→units, per-track pool, noise-floor disarm. Preregs RATIFIED: REV1-soft / REV2-bidirectional / REV3-unit-grain.

## Milestone — session recovery once-and-for-all (2026-07-24)
- **Deployed code:** `faf0c02a8b7493b1fb606e53167cfaba585d5d75` (`main`, live on ets-web / www.autosynth.fun; env: `ETS_ACCESS_KEYS` rotated to the operator's key, `ETS_BANK_DTYPE=float16`, `ETS_MAX_LOADED_WORLDS=2`).
- **What it is:** durable per-KEY owner identity (`owners.json`; one key = one session across logins AND redeploys), orphan ADOPTION on first login (single-key deploys; recovered the operator's real 10-track set live), legacy-token in-place migration, key-gated `/api/recover` (inventory + explicit rebind; refuses `_store`/foreign-owner/outside-base), ASYNC `/api/train` with FE status-reconcile (gateway timeouts/reloads/re-clicks can no longer wedge or double-train), background bank warm on open/restore. NO engine/steering edit — audio byte-identical.
- **Gate:** 280 cloud tests green incl. 15 new (`cloud/tests/test_owner_identity_recover.py`); ets-auditor FAIL (B1/B2/B3, all reproduced) → fixed + pinned → PASS-WITH-NOTES → notes fixed. Runtime-verified on a live server AND on production: 10-track auto-recovered under the operator's key, streams RMS ~2400.
- **Prereg:** `papers/PREREG-session-recovery.md`. **Rollback:** `5cfb041` (pre-recovery main).

## 2026-08-14 — the day TRACKS went quiet, and what actually happened

**Restore points**
| tag / sha | what it is |
|---|---|
| `9722190` | before the render-throughput optimization (rolled the live site here mid-day; made NO audible difference — 213Hz vs 215Hz centroid, so the optimization was exonerated) |
| `9be70af` | before all LIVE work — proven byte-identical in render output to today's HEAD on the same world |
| `060a119` | main before the TRACKS steering restore |
| `e5bf64f` | this build: TRACKS cell steering restored + LIVE fence widened |

**The real regression (found, fixed).** Amendment 2 made a TRACKS click emit
COLUMNS ONLY, dropping the `["role", track, r]` CELL component. The cell grain is
the measured-strong handle (ratified gate: cell share 0.068 → 0.001 damped,
→ 0.101 amplified); a settlement column lean is soft and does nothing at all on a
region-disarmed corpus. So clicks went dead about twelve hours after that shipped,
exactly as the operator reported. `fieldScrubLeans` now emits BOTH.
Verified live, A/B on one stream: RMS 0.090 neutral → 0.048 leaned → 0.067 released.

**A regression I introduced and then reduced.** LIVE's fence starved nearly every
bar (a bar's own tatums often carry no unit of a role the settlement demands), and
under the hard-fence law those slots correctly fell silent — audibly thin. Widening
the fence to the surrounding tatums OF THE SAME TRACK cut it from 9/9 samples to
3/6. Starvation did NOT exist before today; it is a consequence of the fence.

**Three diagnoses I asserted and then had to withdraw** — all the same error, a
metric compared against the wrong baseline. Recorded so nobody repeats them:
1. *"The output is 94% bass, therefore not music."* A synthetic normal mix (kick,
   bass, chords, hats) measures 71% bass / centroid 248Hz; the site measures 93% /
   213Hz. Power-weighted spectra of bass-heavy dance music legitimately look like
   this. WITHDRAWN.
2. *"The deployment mangles audio — same world renders 11kHz locally, 142Hz on the
   server."* The server was never playing the demo world; closing a set left it
   serving `trained.etsworld`. Two different worlds. WITHDRAWN.
3. *"The render destroys the treble — source units are 36% high, output is 0%."*
   Per-unit spectra are normalised to each unit; the output fraction is absolute. A
   treble unit can be "100% high" and carry almost no energy. Nothing is destroyed.
   WITHDRAWN.

**The standing gap this exposed.** Every gate in this repo measures CONTROL
RESPONSE — does the lean move the placements, is the carrier byte-identical. Not
one measures what the audio sounds like. That is why a sound complaint had no
instrument to answer it, and why three bad diagnoses went unchallenged. An
audio-sanity gate (band balance + centroid against the source material's OWN
absolute spectrum, not a normalised one) is the missing check.
