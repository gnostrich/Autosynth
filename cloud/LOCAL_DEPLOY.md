# Run the ETS instrument locally

`main` always has the latest — you never need to touch branches.

## 1. Get current (once, and any time you want the newest)

If you have local edits that block a pull, stash them first:

```bash
git stash            # only if git complains about local changes
git checkout main
git pull origin main
git stash pop        # reapply your local edits (if you stashed)
```

## 2. Install deps (once)

```bash
pip install numpy scipy scikit-learn librosa beat_this soundfile
```

(`numpy scipy soundfile` = play the demo world; `librosa beat_this scikit-learn` = ingest/train your own audio.)

## 3. Run

**Just play + steer the demo world** (no token, fully local):

```bash
./cloud/run_companion.sh
# open http://localhost:8770
```

**Train and play YOUR own corpus** — set your Railway token first:

```bash
export ETS_TRAIN_TOKEN=<token from Railway → service Geodesic-Mixing → Variables>
./cloud/run_companion.sh
```

Then in the browser: drag audio onto the drop zone → **Train on cloud** → your world
goes live to play & steer. **New corpus** resets back to the demo.

## Notes

- Playing/steering is 100% local; only *training* talks to the cloud (and only sends
  stage-3 math, never your audio).
- First **PLAY** has a one-time warmup while the sound bank loads, then it streams.
- Region steering arms only if your corpus has real bar-to-bar variety; the UI dims
  the pads + says "region DISARMED" if it doesn't. Feed it several real, longer tracks.
- Ingest needs `librosa` + `beat_this` (the same audio-analysis deps the native app uses).
