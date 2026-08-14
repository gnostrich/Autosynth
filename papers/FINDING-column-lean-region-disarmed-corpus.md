# FINDING — the settlement COLUMN lean does nothing on a region-disarmed corpus

**Date:** 2026-08-14 · **Status:** WALL, disclosed and MEASURED (not a prereg for new work —
this documents an existing, already-ratified honest-disarm behavior that a same-day commit
tried to route around instead of surfacing). Companion to `papers/PREREG-waveform-scrub.md`
(Amendment 2, WS-9/WS-10) — see that file's "Amendment-2 honest wall" line, which this
expands with the incident and numbers.

## Why this exists
Commit `f0db9d3` ("TRACKS: restore the cell steering component the click used to send")
diagnosed a real symptom — the operator reported the TRACKS click going dead about twelve
hours after Amendment 2 shipped — and answered it correctly in kind (the CELL grain
`["role", tid, r]` does steer) but wrongly in process: it shipped as an unregistered A/B on
the columns-only mechanism Amendment 2 deliberately typed, deleted-then-restored a comment
inconsistently (see below), and put two writers on the `(track,role)` cell lane WS-9/WS-10
say has exactly one owner (the GRID cell gesture). Per operator ruling 2026-08-14, that hunk
is reverted to the columns-only form. This finding is the other half of that ruling: write
up and MEASURE the wall the hunk was actually reacting to, instead of letting it disappear
back into a commit message.

## What "region-disarmed" means
Every ETS world carries a per-lane identifiability flag, `sigma.identifiable[lane]`, computed
from the trained corpus's own statistics (`ets.engine.engine.resolve_sigma`). `region` is one
lane. The bridge reports it to the FE as `region_armed` (`engine_bridge.py:1255`,
`"region_armed": ("region" in armed)`); the FE mirrors it (`world.regionArmed`,
`index.html:1583`) and dims/tags the affected UI (`"region DISARMED — steer inactive"`,
`index.html:1641`).

**This is not a UI-only label.** When region is unidentifiable, the writer's own settlement
step applies the *exact identity tilt* on that lane — pushed values are transmitted but never
applied, by construction, not by a UI gate. The engine even logs this per-bar when it happens:

```
DISARMED lane leaned: region[0] — uncalibrated scale (instrument measured zero untilted
fluctuation under the MAP writer); u transmitted, NO tilt applied. Unblocking: registered
σ_φ re-run under the T_s>0 sampling writer.
```

So "region-disarmed corpus" means: a trained world whose settlement/region statistics didn't
come out identifiable (either flatly `identifiable["region"]=False`, or — as the log line
above shows — an "uncalibrated scale" variant of the same honest no-tilt path under the MAP
writer). Which corpora land here is a property of the TRAINING DATA and the writer mode, not
a bug and not something the FE, the click gesture, or this finding can fix.

## What the click's two possible grains do on such a corpus

| grain | wire key | jack | gated by region-armed? |
|---|---|---|---|
| COLUMN (role) | `["col", r]` → `region_add[r]` | SETTLEMENT (`set_region`, O-block occupancy) | **YES** — `index.html:2280/2292`: `regionArmed = !fieldRegionDisarmed(); if(regionArmed && k>=0 && k<M) ra[k] += ...` — on a disarmed corpus `ra` stays all-zero, so the payload is byte-identical to neutral no matter how hard the click leans. |
| CELL (track,role) | `["role", tid, r]` → `track_role_bias` | CASTING/pick (`set_track_role_bias`, fiber addend within a role-k choice set) | **NO** — this lane has nothing to do with region identifiability; it steers via the choice-set fiber measure regardless. |

This is exactly the asymmetry `f0db9d3`'s commit message named ("a settlement column lean is
soft by construction and does nothing at all on a region-disarmed corpus") — correctly
diagnosed, but the response (silently add the stronger channel back in) is the thing the
operator's ruling reverts. The honest options were always: (1) leave the click columns-only
and accept it goes inert on a disarmed corpus (Amendment 2's actual choice, already disclosed
in `PREREG-waveform-scrub.md`'s "Amendment-2 honest wall" line), or (2) bring the cell grain
back through a **registered** amendment/prereg with operator sign-off, updating WS-9/WS-10's
lane-ownership law on purpose instead of by omission. `f0db9d3` did neither.

## Measurement (not recalled from a commit message — run and reproducible)

Instrument: `cloud/tools/track_role_grid_verify.py` (the ratified WS/grid gate; item (d) is
built exactly for this: it clones the world's real sigma with `identifiable["region"]=False`
— the same all-or-nothing predicate the bridge reports as `region_armed=False` — and compares
the SAME column push against that clone vs. the real, armed sigma). One mechanical fix was
needed to run it against current engine code: `_choose`'s signature gained a `slot` parameter
since this tool's monkey-patch probe was written (unrelated LIVE-fence work, Amendment
4/A4.2/LM-11); the probe wrapper now forwards `*args, **kwargs` instead of a fixed arg list,
a pass-through fix with no behavior change (`cloud/tools/track_role_grid_verify.py`, `_install_probe`).

**Run 1 — the ratified gate, self-contained `demo.etsworld` (M=2, 4 tracks, committed —
reproducible from a fresh clone), region-armed by training, column target role 0:**

| column amp | −1.0 | −0.6 | −0.3 | 0.0 | 0.3 | 0.6 | 1.0 |
|---|---|---|---|---|---|---|---|
| role-0 share | 0.4010 | 0.4622 | 0.4648 | **0.5365** | 0.5352 | 0.5794 | 0.6224 |

Spearman ρ = 0.964 — the column lane steers, monotonically, when region is armed. (b)/(c)/(e)
also PASS: ROW and CELL steer their own lanes (ρ=1.000 / 0.900), byte-identical at neutral,
all three lanes coexist disjointly. Full output: `/tmp/.../scratchpad/track_role_grid_demo_results.json`
(not committed — scratch run; rerun with `python3 cloud/tools/track_role_grid_verify.py
--world demo.etsworld` to reproduce).

**Run 1(d) — the SAME column push (amp = +1.0, role 0) against a region-DISARMED clone of
that same world's sigma:** `column_disarm_inert = True`, `column_armed_moves = True` — i.e.
the push is bit-identical to no-push under the disarmed clone, and is confirmed NOT
bit-identical under the real armed sigma (the contrast). This is the direct, numeric form of
"does nothing at all": not a smaller effect, a **byte-identical-to-off** effect.

**Run 2 — the direct side-by-side (this finding's own script,
`/tmp/.../scratchpad/cell_vs_column_disarmed.py`, same world/seeds/bars/target cell as Run 1,
one region-disarmed sigma clone, CELL vs. COLUMN back to back):**

| lane | amp −1.0 | amp 0.0 (base) | amp +1.0 |
|---|---|---|---|
| CELL `(track 1, role 0)` share | 0.000326 | 0.150798 | **0.479248** |
| COLUMN region-0 share (pushed at +1.0) | — | 0.536458 | **0.536458** |

The CELL row moves by two orders of magnitude in the expected direction (damp toward ~0,
amplify toward ~0.48) **under the identical disarmed sigma** the COLUMN row is measured
against. The COLUMN row's pushed value (`0.536458...`) is identical to 15 decimal places to
its own unpushed baseline — not approximately equal, exactly equal, because the engine's
identity-tilt backstop means no floating-point operation involving the push ever executes.
This is the numeric confirmation of the asymmetry `f0db9d3` named: on a region-disarmed
corpus, CELL is a live control and COLUMN is provably inert.

**What is NOT measured here (disclosed gap):** these runs use `demo.etsworld` (self-contained,
committed, always region-ARMED per its own training) with a *synthetic* disarm clone of its
sigma — the same technique the ratified `track_role_grid_verify.py` gate already uses for its
item (d), not a new mechanism invented for this finding. This finding does **not** have access
to whichever specific corpus was live on `ets-web` when the operator reported TRACKS going
dead (per `BACKUPS.md`'s 2026-08-14 entry, the server at the time was serving
`trained.etsworld`, a runtime-trained world not checked into this repo) — that corpus's own
`region_armed` state was never captured as data before the site moved on. NOT DONE: measuring
the actual production corpus's disarm state directly; what's measured instead is the general
mechanism (identical for every region-disarmed corpus by construction, since the identity-tilt
backstop is unconditional on `identifiable["region"]`), which is the thing that determines
whether ANY corpus in this state behaves the way the operator described.

## Honest options going forward (no action taken here — this is the write-up, not a new prereg)
1. **Leave it as Amendment 2 shipped it** (columns-only, honest-inert on disarmed corpora) —
   the status quo after this revert. Simplest, matches the ratified WS-9/WS-10 lane-ownership
   law exactly, costs the CELL grain's steering power on the corpora where it's needed most.
2. **A registered amendment restoring the CELL grain**, with WS-9/WS-10's lane-ownership
   matrix updated on purpose (two writers on one cell lane, arbitrated or re-typed as a
   compose rule) and the FE's D-1 strip readout (`fieldRoleStripMarks`) updated to source
   `force` from both `["col", r]` and `["role", tid, r]` so YOUR LEAN keeps reporting exactly
   what is sent (the MISLABEL rule) — i.e. everything `f0db9d3` did, done through the front
   door with a prereg and operator sign-off instead of a same-day unregistered branch.
3. **A region-armed-aware click**: emit COLUMN when armed, fall back to CELL only when the
   world is measured region-disarmed (an explicit, disclosed, per-corpus branch rather than
   an always-both emission) — narrower than option 2, keeps one writer per lane in the common
   (armed) case.
None of these three is picked by this document; it is a findings write-up per the standing
"walls are surfaced, not patched" rule, not a decision.
