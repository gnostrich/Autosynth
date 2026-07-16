# Genre set — the canonical psytech deliverable + its reproduction recipe

This folder is the **version-controlled home** of the genre-best psytech tracks
("driving / spacey") and the exact recipe that produces them. Previously these
lived only in ephemeral scratch (`/tmp`) and were never committed — that gap is
closed here.

## What made these sound right (the recipe, not luck)

They are rendered on the **v1 streaming engine** (`Engine.render_offline`) with the
v1 default σ, driven by a **steered knob journey per track** — NOT u=0, and NOT the
stochastic-heavy settings that caused switching/chaos. The journey character that
carries the sound:

- **`temperature` ≈ 0.1** — very low. The temperature sampler barely fluctuates, so
  the arrangement is *committed* (no "switch-switch-switch", no chaotic periods).
  This is the single most important knob and the one most easily gotten wrong.
- **`continuity` high (≈ 3.0)** — sustains textures (the "spacey" hold).
- **`region` moves across the track** (e.g. at bars 24 / 48 / 60 / 84 / 96) — this
  is the *development*; without region motion a u=0 render tiles into "one loop".
- Fixed **seed per track** → deterministic and exactly reproducible.

## Files

- `recipes/batch_render.py` — loads world + full bank once, then renders every
  journey in `batch_journeys.json` and masters each.
- `recipes/batch_journeys.json` — the set: `{name, seed, seconds, knobs}` per track.
- `recipes/k_driving.json`, `k_spacious.json`, `k_shifting.json`, `k_deep.json` —
  the per-track knob journeys (region/continuity/temperature/novelty over bars).
- `renders/` — the rendered, mastered audio. **Not committed** (`*.flac` is
  git-ignored by repo policy, and the point is reproducibility, not byte-hoarding):
  the recipe + fixed seeds + byte-unchanged v1 engine regenerate it exactly. The
  bytes are held outside git; regenerate any time with the command below.

## Reproduce

```bash
# renders into <dir>/deliver/*_MASTERED.flac ; needs the root corpus.etsworld + cache
python3 samples/genre_set/recipes/batch_render.py samples/genre_set/recipes
```

Deterministic: same seeds + same journeys + byte-unchanged v1 engine → same audio.

## Note on the two render paths

This uses the **streaming** path with low-temperature steering. The separate
**batch settler** (`scripts/generate_batch.py`, u=0) is deterministic and coherent
but, with lanes held constant, has no time development (it "loops"); add a journey
for movement. See `reports/2026-07-16-decision-park-v3-sampler.md` for the full
two-paths note and why the v3 sampler track is archived.
