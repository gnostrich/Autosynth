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

## M2 — fixes found by listening to real renders

- **Orbit re-localization** — propagating the full chart-mixture through P each
  step (`m ← m@P`) converges to P's stationary distribution and *freezes* the
  orbit (argmax stuck on one chart; ~16 distinct windows over 240 steps). Since
  M3 explicitly needs a *moving* resolved trajectory a(t), the orbit instead
  re-localizes each step: it samples a concrete chart from the emission mixture
  and steps from there. This keeps it a moving walk (48–90 distinct charts, ~230
  distinct windows over 240 steps) while still stepping through P and honoring
  every tilt term. γ=0 stays a pure-PULL walk; κ=0 still reproduces M2
  bit-for-bit (identical seeded rng draws). Unit tests updated/passing.

- **Render loudness = fixed target, not chained** — the original "match RMS
  across the splice" scaled each grain to the *previous grain's tail*, a
  multiplicative chain that collapses to silence the moment a quiet grain
  appears (observed: a 3-min render at RMS 0.001, effectively silent). Each
  grain is now normalized to a fixed target RMS (0.2, gain clipped to
  [0.25, 4×]); the equal-power crossfade handles splice continuity.

- **16-bit PCM output** — `soundfile` writes a float64 array as a 64-bit float
  WAV, which many players/browsers silently drop (plays as silence). Renders are
  now written `subtype="PCM_16"`.

- **Memory term normalized; κ default lowered to 0.3** — the M3 memory tilt
  `κ·Σ K(t−s)·a(s)` is a *self-reinforcing* term (recent history points where
  you are → memory reinforces staying), so an unnormalized windowed sum
  (~40 same-sign steps) snowballs and collapses the orbit — this corpus's
  instance of M3 **outcome (c)**. Clamping the kernel's L1 mass does not fix it
  (the instability is accumulation, not peak). We normalize `memory_knob` to
  unit magnitude so κ is a well-scaled strength, and lower the default κ from
  1.0 to 0.3: κ≈0.3–0.5 adds phrase-memory while keeping the orbit alive; κ≳0.7
  over-sticks. κ=0 still reproduces M2 exactly.

## M2.5 — polyphony (the concurrency fix)

- **Multi-voice rendering (`render_voices`, `--voices`)** — v0.1 was strictly
  monophonic: one walker, one whole-mix grain per step, so "mixing" was really
  sequential collage. Now N independent voices — each its own orbit through the
  same index, each reading a different stem stream (`mix`/`harmonic`/
  `percussive`, classical HPSS at read time, cached & shared) — are rendered in
  parallel and summed. Drums from one region can sound *under* harmony from
  another: genuine concurrency, region-to-region per channel.

- **Natural amplitude for voices (loudness fades emerge, not imposed)** — the
  fixed-target grain RMS (added to stop the silence collapse) also flattened
  all loudness structure. In voice mode grains play at native amplitude: the
  corpus's own dynamics (a stem falling silent, a breakdown, a drop) pass
  through, so channels fade in/out on their own. Only the summed mix is
  peak-guarded. The monophonic path keeps fixed-target as its stable default.

## M2.6 — flow mode (emergent transitions, no extrinsic rules)

- **Inverted the walk↔playback hierarchy** — hop mode let the walk dictate and
  forced playback to find a grain in the current mixture every 0.75 s: ~80
  source changes/min = scrambled, regardless of navigation quality. Flow mode
  makes the corpus's own time-flow the default motion (each window's most
  likely emission is its own successor, or anything that *sounds* like it) and
  the walk acts as a **field** tilting it:
  `p(w) ∝ exp(−d(w, succ(prev))²/2σ²) · exp(β_read·ψ_w·a_t)`.
  Dwell, transition timing and destination all emerge: wanderlust/knobs move
  the orbit's coordinate away from what's playing until a jump wins, and the
  jump lands on sonically matching material (loop copies, parallel moments of
  other tracks). Measured on the real corpus: track changes dropped from ~80
  effective/min to **~1.5/min**, with same-track re-edit hops at consecutive-
  pair feature distance. No dwell counters, no beat grid.

- **Flow-kernel bandwidth is corpus-calibrated, not hand-set** — the successor
  must outweigh the *summed* mass of all ~N unrelated windows, so a typical
  random-pair distance must cost > ln N nats (we use 3·ln N /2 for field
  headroom): `2σ² = median_random_pair_d² / (1.5·ln N)`. Derived from corpus
  statistics; the earlier median-consecutive-distance bandwidth let 10k soft
  candidates collectively swamp the one successor (measured 100% jump rate).

- **Closed the loop** — after each emission the orbit re-localizes to the
  played window's chart membership (`Orbit.relocalize`), so walk and sound are
  one trajectory; knobs/kernel act on what is actually sounding.

- **Splice type follows contiguity** — successor emissions are contiguous
  audio → linear (sums-to-one) splice; jumps → equal-power crossfade.

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
