# DECISIONS — running log of `[open]` calls

One line of reasoning per call, as required by the spec's definition of done.

## M1

- **PCA dims (`[open: dims]`)** — kept the spec default of 40, but cap the
  whitened dimensionality to the rank actually available
  (`min(40, n_windows-1, feature_rank)`). Small corpora (< 40 windows) can't
  support 40 whitened dims; capping avoids singular/degenerate axes. Whitening
  is done via SVD (stabler than a covariance eigendecomposition for tall-thin
  corpora).

- **Chart count cap** — `k = min(n_charts, n_windows // 8)` so the spec's
  "≥ 8 windows/chart minimum" holds even on small corpora; the config value
  256 is an upper bound, not a fixed count.

- **Spectral-gap heuristic (`[open: gap detection heuristic]`)** — among the
  linear (real-positive) eigenvalues below the stationary mode, sort |λ| and
  take the macro count just above the largest *relative* drop `|λ_i|/|λ_{i+1}|`
  within the [3, 6] band. If that largest drop is not ≥ 1.3× the median drop,
  declare "no clear gap", default to 4 macros, and set `gap_flagged=True`
  (surfaced in the build log and the instrument file).

- **ψ normalization** — scipy unit-normalizes each eigenvector, so the raw
  diffusion coordinates have scale ~1/√(n_charts) (~0.1). A knob expressed in
  σ-units then produces a negligible `exp(β·ψ·knob)` tilt (measured: Δ ≈ 1e-4,
  a false "dead macro"). We therefore standardize each macro column of ψ to
  zero-mean / unit-std across charts. After this, a ±2σ knob moves the orbit's
  resolved coordinate by ~3σ consistently across seeds (M2 knob test passes).
  This is a coordinate choice only; it rescales a(t) and the kernel uniformly.

- **Basin count** — silhouette over `n_basins ∈ [4, 10]` via
  `SpectralClustering(affinity='nearest_neighbors')` on the ψ embedding; falls
  back to a single basin when the embedding is degenerate (0 macros / too few
  charts).

## M3

- **Prony order (`[open: order]`)** — candidate orders {2, 3} (spec cap ≤ 3),
  chosen by **track-held-out cross-validation** of the autocorrelation fit;
  the lower CV error wins. On the synthetic validation corpus order 2 was
  selected.

- **Kernel identity (the "practical route" the spec asks us to document)** —
  we fit the *normalized resolved autocorrelation* `C(t)/C(0)` with a
  damped-oscillator basis and take the fitted modes as the memory-kernel modes
  (Markovian-embedding / mode-matching identity). Full derivation and the
  exact identity are in `basin/kernel.py`'s module docstring.

## M4

- **Websocket server** — implemented directly on the Python standard library
  (RFC 6455 handshake + framing in `basin/panel/server.py`) rather than
  depending on the `websockets` package, honoring the spec's "no other
  frameworks". One process serves both the static page and the socket.

- **Name persistence** — panel names are written to a small companion
  `panel_names.json` rather than rewritten into the (large, binary)
  `instrument.npz` on every keystroke. Same persistence guarantee, no
  full-instrument rewrite per rename. (Spec said "in the instrument file";
  this is the cheap `[default]`-class deviation, logged here.)

- **Audio streaming** — the server realizes one grain per orbit step and
  streams int16 PCM frames over the socket; the page schedules them through the
  Web Audio API. Latency of seconds is acceptable per the spec (not
  performance-grade).
