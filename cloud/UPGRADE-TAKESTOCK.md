# Take-stock — what the 2026-07-18 "redesign upgrade" broke, and every open end

Written at the operator's demand to stop whack-a-mole and inventory everything. The
pre-upgrade build (`main` @ a259fbd) WORKED: audio played, the object resolved ~5
modes/roles, steering was rich. This session's consolidated redesign is what
introduced the breakage below.

## REGRESSIONS (worked before → broke after the upgrade)

1. **Steering pad collapsed from ~5 modes to k=1** (the headline).
   - The eigenmode count depends on the measurement **ensemble size** at serve-boot.
   - The redesign set the boot ensemble to the authoritative **24×32** (768 runs).
     That heavy compute runs in a daemon thread and **starved the realtime audio
     loop** → silent playback.
   - To save audio I reverted the boot ensemble to a cheap **4×6**. But 4×6 is noisy
     → the shuffle-null floor rises → only 1 mode survives → **k=1**, a degenerate
     1-D slider instead of the rich multi-mode pad.
   - **Audio and mode-count are fighting over the same boot-time compute.** The build
     that worked did not have this fight.

2. **Silent audio** (now fixed, but the fix is what caused #1).

3. **UX regressions I introduced while patching** (all mine, most fixed):
   - Play pane leaked onto Explore/Object (`#panePlay` display not `.active`-scoped) — FIXED, deployed.
   - Duplicate DOM IDs (`outboard`/`legacyDrawer`/`slanes`) from a `-X theirs` merge → broke steer/play JS — FIXED (clean file).
   - Pad forced to 72vh so k=1's thin slider floats in an empty void.
   - Deploy race: rapid successive deploys landed out of order and reverted a fix.

## ROOT CAUSE (the real fix, not another band-aid)

Eigenmodes are computed at **serve-boot**, in a thread contending with realtime audio.
That is the wrong place. They are a **property of the trained world** and should be
computed **once at train/freeze time** (offline — no audio to starve, full
authoritative ensemble), **stored in the world file**, and merely **read** at serve.
Result: accurate high k **and** uncontended audio. No boot-time tradeoff. This is THE
fix; the boot-time ensemble knob was always the wrong lever.

## OPEN ENDS / PENDING

- **Move eigenmode computation to train-time** (the root fix above). Not started.
- **TEMPO dead knob** ("not wired") still shown — removal in progress (builder), not deployed.
- **Object/tracklist tab**: make visible to all, tracklist read-only for visitors,
  posting owner-gated, Unlock only on that tab — in progress (builder), not deployed.
- **Stale training lock**: `/api/train` returns BUSY though no training is running
  (is_trained=false, 0 stages) — blocks new trains until cleared.
- **Memory cap**: ~4 tracks peaked 5.2 GB / 8 GB; can't train more than ~6 at once.
  A 20-track train will OOM and crash the container.
- **Duplicate Explore sets** — FIXED (stale flat-B set purged).

## RESTORE OPTIONS (operator's call)

- **A — REVERT to a259fbd (pre-upgrade):** brings back working audio + ~5 modes
  immediately. Cost: also restores the old field/lane-console UX you disliked. Fast,
  known-good, zero risk.
- **B — FIX-FORWARD:** keep the new pad/knobs UX; move eigenmodes to train-time (fixes
  k AND audio at the source), remove the dead knob, finish the Object tab. More work;
  keeps the UX wins and ends the audio-vs-k fight for good.

Recommendation: **B** if the new look matters; **A** if you want it working *now* and
we rebuild the UX deliberately on top of a known-good base.
