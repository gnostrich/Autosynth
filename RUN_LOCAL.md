# Run ETS locally — release `engine-v1 · ui-v6 · psytech`

ETS is **two processes** that talk over OSC on localhost: the **engine** (the audio
machine — engine-v1, at the repo root) and the **instrument** (the control surface —
ui-v6 THE FIELD, in `ui-v6/`). Killing the instrument leaves the engine playing; the
instrument holds no engine state (the two-process law).

## 0. Get the code

```bash
git checkout main && git pull origin main
```

(Everything current is on `main` — no other branch needed. Rollback surface: the
previous pads+XY+drill instrument is intact in `architecture-v6/`, tag
`pre-uiv6-field-2026-07-17`.)

## 1. Python env + deps (once)

Python ≥ 3.10.

```bash
python -m venv .venv && source .venv/bin/activate     # (Windows: .venv\Scripts\activate)
# core (engine): numpy + audio stack
pip install numpy soundfile librosa pyloudnorm
# instrument (ui-v6): Qt + OSC + audio out
pip install "PySide6-Essentials>=6.6" "python-osc>=1.8" "sounddevice>=0.4"
```

## 2. Terminal 1 — start the ENGINE (engine-v1, from the repo ROOT)

```bash
python -m ets.engine --world corpus.etsworld --latency-profile desktop --port 9000
```

First run rebuilds the unit bank from `corpus/` (committed) if you have no
`cache/units` — that can take a few minutes; later runs are fast. If you already have a
bank cache, point at it: `ETS_BANK_CACHE=cache/units python -m ets.engine ...`.
The engine listens for control on **:9000** and streams audio to your default output.
(No local corpus? A fresh clone plays the committed self-contained demo:
`--world demo.etsworld`.)

## 3. Terminal 2 — start THE FIELD (ui-v6, from `ui-v6/`)

```bash
cd ui-v6
python -m ets.instrument.live --engine-port 9000
```

The instrument announces itself (`/ets/hello`); the engine replies (`/ets/welcome`)
and the field populates from live telemetry. Running from **this folder** is what
makes it ui-v6 (THE FIELD) rather than the pads/XY/drill surface — same OSC wire,
new UI.

## 4. What to test (the FIELD)

- **One surface.** No pad grid, no XY pad, no drill popup — a field of squares.
  Zoomed out you see TRACKS (colored per source track); zoom into a track for the
  ROLES it loads; zoom into a role for its UNIT slices.
- **Hover + scroll = bias.** Scroll up on a square to favor its material, down to
  disfavor. The scroll saturates at "strongly (dis)favored" — it can NEVER mute
  (that's the crate/library's job, deliberately separate).
- **Ctrl+scroll (or pinch) = zoom.** Only squares with real sub-structure above the
  noise floor expand (marked `▸n`); atomic squares refuse — that refusal is honest
  information, not a bug.
- **The realness test.** Bias one square and watch RELATED squares move that you did
  not touch — that's the engine re-settling, not your input echoed. The square's
  FILL is the engine's settled answer; the colored RING on its edge is your input —
  watch the gap between how hard you pushed and how much it took.
- **Hover does nothing.** Moving the mouse without scrolling changes and emits
  nothing. Scalar sliders are still scroll-driven.
- **Feel report wanted.** Scroll sensitivity (an eighth of the range per wheel
  notch) and zoom ergonomics were untestable in the build sandbox — report how they
  feel on real hardware; both are single named constants (`FieldView.BIAS_STEP`,
  the zoom gesture) if they need tuning.

## Notes

- To run a different instance: `--world instantiations/futuregarage/corpus.etsworld`
  (that's `engine-v1 · ui-v6 · futuregarage`).
- Offline render (no instrument): `python -m ets.engine --world corpus.etsworld --render out.flac --seconds 30 --seed 0`.
- The previous instrument (ui-v5) still runs for A/B: `cd architecture-v6 && python -m ets.instrument.live --engine-port 9000`.
- `release-manifest.json` is the source of truth for what's current.
