# The Basin — v0.1

An offline **instrument-builder + orbit-renderer** over a playlist. Point it at
a folder of audio (one micro-genre, 20–40 tracks) and it builds an *instrument*
(atlas + transfer operator + spectral coordinates + memory kernel) and renders
DJ-set-length audio by orbiting that index, steerable via a knob vector.

No neural networks anywhere. Build spec: `The Basin — Build Spec v0.1`.
Honest status vs the spec is in [`LEDGER.md`](LEDGER.md); every `[open]`
judgment call is in [`DECISIONS.md`](DECISIONS.md).

## Install

```bash
pip install numpy scipy soundfile scikit-learn matplotlib librosa pyyaml
```

## Use

```bash
# 1. drop 20–40 tracks of one micro-genre into corpus/  (or use --corpus DIR)

# 2. build the instrument (M1 index + M3 kernel) → instrument.npz + debug plots
python scripts/build_instrument.py

# 3. render a 3-minute set (M2 orbit; add --kappa 0 for the K-less control)
python scripts/render_set.py --minutes 3 --seed 0 --out set.wav

#    steer it: bias macro 0 by +2σ / −2σ (the M2 knob test)
python scripts/render_set.py --minutes 3 --seed 0 --macro 0  2 --out pos.wav
python scripts/render_set.py --minutes 3 --seed 0 --macro 0 -2 --out neg.wav

# 4. the deciding experiment (M3): kernel on vs off, objective + A/B
python scripts/ablate_k.py --minutes 3 --pairs 5

# 5. the live panel (M4) — only meaningful after M3 outcome (a)
python scripts/run_panel.py            # open the printed URL, "enable audio"
```

## Modules

```
basin/
  features.py    M1  windowing (1.5 s / 50%) + log-mel/RMS/onset/chroma → PCA-whiten
  atlas.py       M1  k-means charts (k=256) + Gaussian soft assignment (top 8)
  operator.py    M1  transfer operator P, eigen-spectrum + classification, ψ, basins
  orbit.py       M2  PULL + knob bias + wanderlust + temperature (+ M3 memory)
  render.py      M2  concatenative grain read, equal-power crossfade, RMS match
  kernel.py      M3  autocorr → damped-oscillator fit → memory term (CV-selected order)
  store.py           instrument.npz (de)serialization
  debugplots.py  M1  terrain.png + spectrum.png
  panel/         M4  stdlib HTTP+WebSocket server + single-page canvas panel
scripts/         build_instrument.py · render_set.py · ablate_k.py · run_panel.py
config.yaml      all tunables (windowing, atlas, orbit, kernel, render)
```

## Tests

```bash
pytest tests/ -q
```

Covers the spec's load-bearing invariants: P row-stochastic and within-track
only, `γ=0` reproduces pure PULL, `κ=0` exactly reproduces M2, memberships stay
normalized/sparse, 156-d raw windows, render finiteness, Prony order ≤ 3.
