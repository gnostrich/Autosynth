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

## M2.7 — momentum orbit (the brachistochrone principle)

- **Why**: the memoryless walk is overdamped diffusion — it wanders but never
  commits, so it cannot do what buildups/drops do (dip to buy speed, spend it
  on the release). Mori–Zwanzig says the projection onto slow coordinates
  *necessarily* carries a memory/momentum term — M2 was the approximation, and
  the M3 kernel's damped-cosine fit is precisely the measured signature of
  underdamped (momentum-carrying) motion in the corpus.

- **What**: a damped oscillator per macro in diffusion coordinates,
  `p ← e^{−γ}·p + Δa − ω²·a`, with (γ, ω) taken **from the fitted kernel
  modes** (corpus-measured damping and build/release frequency — nothing
  hand-picked), driven by the walk's actual motion; contributes one more
  additive tilt `β_p·ψ·p` in the same pathway as knobs/wanderlust/kernel.
  `momentum: 0` reproduces the memoryless walk bit-for-bit (unit-tested).

- **Regression (real corpus)**: knob deltas identical with momentum on/off
  (6.9/3.6/6.2/6.9 vs 6.9/3.6/6.1/6.9) — all controls remain modifiers.

- **Result (real corpus)**: the orbit's drive coordinate develops phrase-scale
  oscillation at the fitted periods — autocorr at 12/27 steps goes from
  ≈0 (memoryless) to **+0.83 / +0.59** with momentum on. This is the
  phrase-scale structure the original M3 position-history formulation failed
  to produce: the kernel acts as *velocity* memory, not a position nudge.

- **Listening outcome (honest)**: coordinate-level success did **not** yet
  translate to audible arcs — at any tested strength (1.0, 0.4) the momentum
  tilt raises per-step read churn (continuation-miss 32→67%) and the loudness
  arc stays flat, because the oscillating field jostles the grain read at
  step scale instead of steering drift at arc scale. Open item: timescale
  separation — momentum should modulate the walk's slow drift (e.g. acting on
  the knob at multi-step cadence, or low-passed before the tilt), not the
  per-step emission. Until then the audibly-best recipe is the coupled duo
  *without* momentum (γ=1.0, couple=0.5, flux term, seed-0 territory:
  continuation-miss 32–35%, judged most coherent by ear).

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

## Navigation consolidation (2026-07-10, after "track dominant throughout")
Measured: seed-7 performance spent 91% of its time inside one track; both
composed jumps landed back in it. Chain of causes, each fixed at the level
it lived at:
1. **Knob tilt vs locality scale.** The window-level tilt exp(β·ψ·a) is
   O(few) nats against a locality term calibrated to ln N — a whisper. The
   knobs' proper scale is the REGION walk (charts), where tilt spread ≈
   P-row log-spread (measured 5.6 vs 5.8). → Emission is now *gated* by the
   orbit's chart mixture (`p(w) ∝ [W@m]·locality·flux·presence`): the walk
   picks the region, the reader picks the window within it.
2. **Coupling direction.** Relocalizing the orbit to every played window
   pinned the walk to playback (one chart-step of drift, then snapped
   home). With the gate, coupling is structural — emission cannot leave the
   walk's region — so external relocalization is deleted from flow loops.
3. **Flux term charged the true successor.** mid_frames were baked at the
   old half-window offset; under beat-synchronous windows the actual splice
   is at the successor's start, so the stored frame misreported the splice
   and flux(successor) was −2..−24 nats (siblings beat it → micro-jump
   churn = the "looping locally" sound). Fixed by identity:
   mid[w] := head[w+1] within a track. No rebuild, no constants.
4. **Gate uses the untruncated mixture** (OrbitState.m_full): top-k
   truncation is an emission device; as a gate it jitters chart-to-chart
   and randomly bars the successor.
Measured after: zero lean = 10 tracks / 21 transitions / 7.5 min (corpus
routing); lean ±1.5σ on any mode relocates playback to that mode's pole
territory within seconds and holds it (m1+→t5, m1−→t14/15, m0−→t18,
m2−→t12). Territory map is measurable per instrument. Caveat: ψ poles are
skewed (e.g. ψ0 ∈ [−3.7, +0.5]) — the bulk sits at one end; leaning into
the ceiling is a no-op. The panel's flow view shows position; ears + map
name the poles.

## Curvature consolidation (2026-07-11, after "same track / flat / brachistochrone?")
Forensic on the 30-min unattended set: 100% of emissions, all 3 voices, one
track (t12) for the full half hour. Two causes:
1. **Position coupling = consensus trap.** Each voice leaned toward the
   others' mean coordinate; with the group at a deep ψ pole (t12 at
   ψ2≈−4.5), every voice felt a standing lean of ~2.25σ — stronger than any
   performed lean. A spring to the centroid parks. → Coupling is now to the
   others' MOTION (velocity/innovation): no reward for sitting, full reward
   for co-moving. Measured: same seeds go from 1 track/30 min to 6–8
   tracks with set-paced dominant-track changes.
2. **The curved dynamics was switched off.** κ=0, momentum=0 in the render
   scripts = pure gradient flow into the deepest well — straight-line
   descent. The corpus's own curvature lives in the measured oscillatory
   eigenmodes (flywheel: the field rotates arg λ per step and integrates
   ~1/(1−|λ|) steps of history — holonomy of the trace) and the measured
   memory kernel (Mori–Zwanzig). Defaults now: momentum=1.0, κ=0.3 — the
   brachistochrone point: the natural path overshoots and swings, it does
   not settle on the straight line.

## Path-state trace (2026-07-11, "memory kernel etc aren't separate parts right")
The user's objection was architecturally true: kernel, flywheel, momentum — separately
named, separately gained parts bolted onto a first-order walk — are the
Mori–Zwanzig *symptom* of projecting dynamics with memory onto a state
that is too small. Give the state one step of path instead:
`operator.build_pair_operator` measures the corpus's routing over path
segments (c_prev, c_cur) → c_next from the same window data, one order
higher. The Orbit pulls from its measured path segment when one exists
(measured hit rate on this corpus: 100.0% of steps; 1256 observed
segments), falling back to first order otherwise.
Subsumption measured (same seeds, 15 min, 3 voices, velocity coupling):
- first-order + kernel + flywheel on: 6 tracks, dominant track 100% of
  each minute;
- path-state, ALL parts off (κ=0, momentum=0): all 20 tracks touched,
  each minute a blend of 4–14 tracks with the dominant at 30–45%, slow
  territory evolution (t12-era → t5-era).
Memory, direction persistence and phrase cycles now live in the operator
itself. Defaults: kappa=0, momentum=0 (parts retired; code kept for the
ablation story). No rebuild needed — P2 derives from stored memberships
at load. The knobs remain the spectral directions of the landscape; the
lean is the only external input.

## The clock distributary (2026-07-11, "does region-to-region allow speedup/slowdown")
Measured: the corpus's own pacing spans 0.35–0.94 s per beat step (170%
range) — the emission level has always carried it (native clocks). But at
the ROUTING level, the material-clock direction correlated with the 4
exposed knobs at only |r| ≤ 0.21 — the speed degree of freedom was nearly
orthogonal to the whole panel. The strongest clock-aligned directions are
eigenmodes 11 (r=+0.42) and 7 (r=+0.34), BOTH below the flagged default-4
cut. The arbitrary knob terminator had amputated the tempo distributary.
Resolution (operator.full_psi): the landscape now carries EVERY linear
direction (99 on this corpus), ordered by measured persistence, no
significance cutoff — ears terminate, not machinery. First 4 columns are
bit-identical to the old macros (existing leans keep meaning). Measured:
leaning the clock pair ±2σ swings mean step 0.49s ↔ 0.76s (54%) purely by
routing — no stretching, no rate rule.

## One die, one flow (2026-07-11, after "beat-coherent but mashing / fast switching")
The mid-phrase mash had two sources, both extrinsic freedoms, both removed:
1. **The reader's die.** Emission sampled p(w) every beat; loop-based
   material is full of near-duplicate windows with genuinely ~0 splice
   cost, so sampling drew a different parallel bar every few beats. The
   reader is now the DETERMINISTIC surface of the walk (argmax of the
   measured evidence): it rides the successor while the region holds and
   switches exactly when the walk moves the ridge. One die in the machine —
   the trace itself. (Jump rate 0.52 → ~0.27; measured runs match the
   corpus's own chart-run statistics.)
2. **Independent voice walks.** In the corpus, channels are perfectly
   co-located — the trace is ONE flow; channels are emission surfaces.
   Three separately-walking coupled voices was an invented freedom heard as
   vertical mash (7–14 tracks blended per minute). Default rendering is now
   a single walk on the whole-mix surface; per-channel voices remain a
   PERFORMANCE mode (panel), with the coupling signal smoothed at the
   corpus's measured chart-correlation length (mean run 4.1 windows).
Measured single-walk zero-lean behavior (20-min horizon): track changes
every 1–2 min, 16–17 tracks (seeds 5/40); seed 21 parks in the Baryon
pocket — that track is a genuinely self-contained region of this corpus
(its basin is single-track); escape is the performer's move, not a rule.
