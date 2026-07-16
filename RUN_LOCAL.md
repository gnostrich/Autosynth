# Run ETS locally — release `engine-v1 · ui-v4 · psytech`

ETS is **two processes** that talk over OSC on localhost: the **engine** (the audio
machine — engine-v1, at the repo root) and the **panel** (the control surface — ui-v4,
in `architecture-v5/`). Killing the panel leaves the engine playing; the panel holds no
engine state (the two-process law).

## 0. Get the code

```bash
git fetch origin claude/basin-build-spec-v01-gmeiqq
git checkout claude/basin-build-spec-v01-gmeiqq
git pull origin claude/basin-build-spec-v01-gmeiqq
```

## 1. Python env + deps (once)

Python ≥ 3.10.

```bash
python -m venv .venv && source .venv/bin/activate     # (Windows: .venv\Scripts\activate)
# core (engine): numpy + audio stack
pip install numpy soundfile librosa pyloudnorm
# panel (ui-v4): Qt + OSC + audio out
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

## 3. Terminal 2 — start the PANEL (ui-v4, from `architecture-v5/`)

```bash
cd architecture-v5
python -m ets.panel --engine-port 9000
```

The panel announces itself (`/ets/hello`); the engine replies (`/ets/welcome`) and the
REGION anchors populate. Running the panel from **this folder** is what makes it ui-v4
(the interaction fixes) rather than the founding panel — same OSC wire, newer UI.

## 4. What to test (the v5 fixes)

- **Hover does nothing.** Move the mouse over any slider or the pad without clicking or
  scrolling — no value should change, no sound should shift.
- **Scalars = scroll.** Scroll-wheel over a lane slider adjusts it (no click needed).
- **XY pad = pick-and-place.** Click to ARM (dot jumps to cursor and follows, you hear
  it move live), move to aim (angle = which regions, distance = how hard), click to
  DROP (it parks). The **magnitude ring is a hard wall** — the dot cannot go past it.
- **The scraping test.** Drive the pad hard — slam to the ring edge, jump around,
  crank continuity/temperature. With the slew + clamp it should stay musical. **If it
  still scrapes here**, that confirms the live-writer hypothesis (the real-time settle
  budget), and we investigate the engine's live path next — the offline path never
  reproduced it.

## Notes

- To run a different instance: `--world instantiations/futuregarage/corpus.etsworld`
  (that's `engine-v1 · ui-v4 · futuregarage`).
- Offline render (no panel): `python -m ets.engine --world corpus.etsworld --render out.flac --seconds 30 --seed 0`.
- `release-manifest.json` is the source of truth for what's current.
