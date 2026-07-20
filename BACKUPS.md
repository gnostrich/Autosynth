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
