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
| `field-bias-rev3-live-2026-07-19` | `042c274455a878d2f8400f787696621c99cc4f62` | 2026-07-19 | **CURRENT LIVE** — THE FIELD + soft track/unit fiber bias (deployed code at `eb557b9`) |

## Current live milestone — field-bias REV3
- **Deployed code:** `eb557b909c6d6a13455a7a0960b67a468733a238` (`main`, live on `ets-web` / www.autosynth.fun).
- **Provenance commit (this record + manifest):** `042c274455a878d2f8400f787696621c99cc4f62`.
- **What it is:** THE FIELD restored as the single Play steering surface (replaces the XY pad, socket-swap); soft `channel_logbias` fiber-choice bias at track (roll-up) + unit (ultimate "channel") grains, bidirectional amplify/damp `[-1,1]`; drill track→units (role internal — a measured fiber no-op); per-track unit pool so every track drills its own units; participation-ratio noise-floor disarm; byte-identical audio at neutral.
- **Preregs (all RATIFIED):** `PREREG-channel-bias-squares-REV1-soft.md`, `-REV2-bidirectional.md`, `PREREG-field-bias-REV3-unit-grain.md`. ets-auditor PASS across every phase.
- **Rollback:** `pre-uiv6-field-2026-07-17` (companion pad+XY), or `pre-sampler-xy-2026-07-19` (pre-bias).
