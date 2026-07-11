# LEDGER — honest status vs the Build Spec v0.1

**Scope.** Every module in the spec is implemented, runs end-to-end, and has
been exercised on a **real 20-track micro-genre corpus** (experimental / hard
electronic — jungle, tekno, goa-adjacent; ~2 h of audio). A synthetic 24-track
corpus was also used during development to unit-test invariants. Numbers below
are from the **real** corpus unless marked *(synthetic)*.

The corpus, `instrument.npz`, rendered WAVs, and debug PNGs are git-ignored
build artifacts; regenerate them with the scripts.

Reproduce:
```
python scripts/build_instrument.py --corpus corpus_real
python scripts/render_set.py --minutes 3 --seed 0 --out renders/base.wav
python scripts/ablate_k.py --minutes 3 --pairs 5
```

---

## M1 — the index  ✅ gate mechanism in place; real run healthy

| Item | Status | Real-corpus result |
|------|--------|--------|
| Windowing + 156-d raw vectors | ✅ | 10,091 windows over 20 tracks; `RAW_WINDOW_DIM == 156` (tested). |
| Standardize + PCA-whiten to 40 | ✅ | 40 dims retained. |
| Atlas: k-means k=256 + soft assign top-8 | ✅ | 256 charts, bandwidth 8.63; rows sum to 1, ≤8 nonzeros (tested). |
| Transfer operator P (within-track, row-stochastic) | ✅ | cross-track pairs excluded (unit-tested). |
| Eig decomposition + classification | ✅ | 102 linear, 154 oscillatory, 0 alternation. |
| Spectral-gap macro cut | ✅ | no clear gap → 4 macros, `gap_flagged=True`. |
| Diffusion coordinates ψ | ✅ | standardized per macro (DECISIONS). |
| Basins by silhouette [4,10] | ✅ | 4 basins. |
| `debug/terrain.png`, `debug/spectrum.png` | ✅ | produced. |
| Connectivity ≥90% + island report | ✅ | largest SCC covers **100.0%** of window-mass — no islands. |

**M1 gate:** basins form coherent regions in (ψ1, ψ2) — a dense multi-basin
core plus two distinct outlier arms (a bright/percussive arm and a low-timbre
arm). Sample-track paths stay within coherent regions. At the 0.75 s step rate
the paths read as coherent-but-textured rather than glass-smooth; that is
consistent with the micro-genre's busy surface. No islands, so the playlist is
well-connected.

## M2 — Markovian orbit (K-less control)  ✅ knob test passes on real audio

| Item | Status | Notes |
|------|--------|-------|
| Orbit step: PULL + knob tilt + sharpen + top-8 | ✅ | membership stays normalized/sparse (tested). |
| Wanderlust γ; **γ=0 reproduces pure PULL** | ✅ | unit-tested (deterministic; changes only when γ>0). |
| Temperature τ (drift) | ✅ | exponent 1/τ: low τ mode-follows, high τ diffuses. |
| Grain read + continuity prior | ✅ | samples window from mixture, biased by predecessor proximity. |
| Equal-power crossfade 0.375 s + fixed-target RMS | ✅ | render finite, in-range, non-silent (tested). |
| `render_set.py --minutes 3 --seed 0` | ✅ | 3-min 16-bit-PCM WAVs produced (`renders/`). |

**Two bugs found by actually listening (both fixed; see DECISIONS):**
1. The orbit *froze* — propagating the full mixture through P converges to the
   stationary distribution, so the walk got stuck on one chart (~16 windows over
   240 steps). Fixed by re-localizing to a sampled chart each step → 48–90
   charts, ~230 windows. Without this a(t) is constant and M3 is meaningless.
2. Renders were near-silent / unplayable — grain loudness was chained to the
   previous grain's tail (collapses to silence), and output was written as
   64-bit-float WAV (many players drop it). Fixed: fixed-target RMS + 16-bit PCM.

**M2 knob test (real):** ±2σ bias on each of the 4 macros, same seed, moves the
orbit's mean resolved coordinate by **+4.0 / +5.0 / +6.0 / +6.0** respectively,
same sign across all 5 seeds. **All four macros are live** — the check the spec
says to stop on if it fails. Whether the shift is *audibly* consistent is a
human call; `renders/macro0_pos.wav` vs `renders/macro0_neg.wav` (same seed) are
the A/B pair to listen to. (An initial false "dead macro" on the synthetic
corpus led to the ψ-standardization fix; see DECISIONS.)

## M3 — the kernel and the deciding experiment  ⚠️ outcome (c) → (b)

| Item | Status | Notes |
|------|--------|-------|
| a(t) → autocorr C(τ) to 30 s | ✅ | per-track then averaged, normalized to C(0)=1. |
| Damped-oscillator fit, J=2 then 3, CV-selected | ✅ | order 2 chosen; CV error 0.028; ≤3 enforced (tested). |
| Kernel identity documented | ✅ | `kernel.py` docstring (DECISIONS). |
| Tempo cross-check | ✅ | measurable modes at ~8.8 s and ~20.6 s land near ¼-bar / phrase relations to the corpus tempo; the rest are overdamped. |
| Orbit with memory; **κ=0 exactly reproduces M2** | ✅ | unit-tested (κ=0 ≡ kernel=None, bit-identical). |
| Spectral-radius clamp (outcome-c guard) | ⚠️ | implemented, but does **not** rescue this instance — the collapse is history *accumulation*, not peak magnitude. Normalizing the memory term + lowering κ is what keeps the orbit alive. |
| `ablate_k.py` objective metric | ✅ | onset-autocorr at measurable periods. |
| Blind A/B subjective protocol | ⏳ | `ablate_*_seed*.wav` written per pair; human notes still to fill in. |

**M3 gate (real, the deciding experiment) — corrected after the M2 fixes:**

The first ablation ran on the *frozen* orbit and is void. Re-run on the fixed
pipeline, the honest picture is:

- **Outcome (c) at the spec default.** With κ=1.0 the memory term
  `κ·Σ K(t−s)·a(s)` is self-reinforcing — recent history points where the orbit
  already is, so the tilt snowballs and **collapses the orbit** (down to ~4
  charts). This is exactly the spec's outcome (c). The spec's first remedy
  (clamp the spectral radius) does **not** help here: the instability is
  accumulation of ~40 same-sign history steps, not peak mass. Normalizing the
  memory knob to unit magnitude and lowering κ to **0.3** keeps the orbit alive.
- **Outcome (b) at safe κ.** At κ=0.3, the objective metric shows **no clear
  difference**: at the two measurable periods (~8.8 s, ~20.6 s) K-on mean |Δ|
  0.032 vs K-off 0.011 — i.e. K-on is if anything slightly *further* from the
  corpus, and per-seed it splits 2-help / 1-hurt. **Verdict: outcome (b)** — no
  objective evidence the kernel restores phrase structure on this corpus.
- **Structure is thin anyway.** Only 2 of 8 fitted modes have a measurable
  phrase-scale period; the other 6 are overdamped. There may simply not be much
  phrase-periodicity in the resolved coordinates for K to restore.
- **What (b) means (per spec):** not a failure — a result. Before any M4 UI
  work, the pivot is *"what projection makes K matter"*: the leading candidates
  are beat-synchronous windows (align windows to bars so a(t) carries real
  phrase periodicity) and **richer per-stem features** (see the note at the end
  of this file). Blind A/B listening can still overturn a (b) if K is audibly
  different; that check is outstanding.
- Raw numbers are auto-appended at the bottom by `ablate_k.py`.

## M4 — the panel  ✅ implemented; ⛔ gate NOT cleared (M3 = outcome b)

The spec builds M4 only after a real-corpus M3 **outcome (a)**. The corrected
M3 result is **outcome (b)**, so by the spec the panel is *not* gate-cleared —
the honest next step is the projection pivot, not UI. The panel is nonetheless
fully implemented and smoke-tested (it's useful for exploring M2 steering and
for re-judging once the projection improves), and clearly flagged as
ahead-of-gate:

| Item | Status | Notes |
|------|--------|-------|
| stdlib HTTP + WebSocket server | ✅ | no third-party framework (DECISIONS). |
| Control topology from eigenvalue type | ✅ | real+ → bounded knob; complex pair → phase dial + depth; real− → toggle — read from the instrument classification. (This corpus: 4 macro knobs + groove dials; no alternation modes survived, so no toggles.) |
| Co-moving frame (needle = innovation, collar = absolute) | ✅ | innovation = a − (PULL+kernel) prediction; thin collar = true position. |
| Gestures: lean / grip / phase nudge / rename | ✅ | rename persists to `panel_names.json` (DECISIONS). |
| Meta knobs (β, γ, τ, κ) live | ✅ | update the running orbit. |
| Hysteresis stub (dwell ≥ 8 s) | ⏳ | no conditional/weather logic in v0.1 to gate (non-goals); stub deferred. |

Launch: `python scripts/run_panel.py` → open the printed URL → "enable audio".

---

## Known risks — status

- **Kernel ill-conditioning** — order capped ≤3, track-held-out CV, failure
  reportable (CV error printed + stored). ✅ On the real corpus the fit was
  stable (CV 0.028) but *thin* (6/8 modes overdamped) — the honest limiting
  factor here is how much phrase-periodicity the material actually has.
- **Grain read degenerating to a granular sampler** — exactly what M3 measures;
  audio quality deliberately not polished before the gate. ✅ as specified.
- **Dead macros** — not triggered; all 4 macros live after ψ-standardization.
  The beat-synchronous-window alternative remains a future hook if a later
  corpus shows dead macros.
- **Patchy atlas / islands** — none on this corpus (100% coverage). Reporter is
  in place for corpora that do fragment.

## Listening verdicts (the subjective protocol, filled in)

Chronological, same listener (project owner), real corpus:

- hop-mode renders (all voices/settings): **"sounds scrambled"** — rejected.
- flow-mode solo/duo: coherent-but-chopped; **duo_coupled judged most
  coherent** of the mono/duo generation; coupled 8-min held up.
- momentum v1/v2 renders: indistinguishable-to-worse at clip length; parked.
- **emergent_trio.wav** (NMF channels ch1+ch0+ch6, coupled walkers, flux
  flow, γ=1.0, κ=0): **"actually sounds like a legit set snippet"** — the
  first positive verdict. This recipe is now the config default.
- **emergent_set_12min** (same recipe, 12 min): reads as long expanded
  single-track stretches ("pulled-out, not slowed") — measured: 5+ tracks
  visited, top track 33%, in minutes-long dwells. Verdict: **"not bad,
  lots of sets sound like this in short parts."** Dwell length identified
  as the tunable (γ now; basin-scale pressure queued if ever needed).

Pattern worth recording: audible quality improved monotonically as
hand-designed elements were replaced by measured ones (imposed 2-channel
split → measured channels; scheduled transitions → flux objective; solo
walk → coupled concurrent walks).

## Theory-faithfulness audit (quick pass)

Checked every spec formula against the code. Verdicts: **F** = faithful as
written · **D** = deliberate deviation (logged in DECISIONS) · **T** = genuine
tension between spec text and theory intent.

| Spec item | Code | Verdict |
|---|---|---|
| 156-d windows (mean+std of 78/frame), 1.5 s / 50% | `features.py` | **F** (unit-tested) |
| Standardize → PCA-whiten 40 | `features.py` | **F** (rank-capped) |
| Atlas k=256, Gaussian soft-assign, top-8, median bandwidth | `atlas.py` | **F** |
| `P[a,b]=Σ m_t(a)m_{t+1}(b)` within-track, row-normalized | `operator.py` | **F** (unit-tested) |
| Eig classify real+/complex/real− → knob/dial/toggle | `operator.py`, panel | **F** |
| Spectral-gap cut, default-4 + flag | `operator.py` | **F** (`[open]` heuristic logged) |
| `ψ_i = λ_i^t·right-eigvec, t=1` | `operator.py:145` | **F**, then standardized per macro — **D** (dead-knob fix; pure coordinate rescale) |
| `m' ∝ (m@P)·exp(β·align − γ·visit)` ; sharpen τ ; top-8 | `orbit.py:110-125` | **F** for the *emission* mixture |
| State stays a soft mixture step-to-step | `orbit.py` re-localizes by sampling a chart | **T** — the spec's literal recursion `m←m@P` converges to the stationary density and **freezes** (measured: 1 chart / 240 steps). A transfer operator evolves *densities*; an "orbit" is a *sample path*. We sample. Truer to the word "orbit," not to the pseudocode line. |
| Memory `κ·Σ K(t−s)·a(s)` projected via ψ | `orbit.py` | **D** — unit-normalized + κ→0.3; raw form self-reinforces → outcome (c) collapse |
| κ=0 ≡ M2, γ=0 ≡ pure PULL | tests | **F** (bit-exact) |
| Kernel = damped-cosine fit of C(τ), identity documented | `kernel.py` | **F** (spec's sanctioned practical route) |
| "Match RMS across the splice" | `render.py` | **D** → **T** — chained matching collapses to silence; the fixed-target replacement is stable but **flattens all dynamics**, which is precisely what suppressed natural channel fades. Fixed in multi-voice mode (below): stems play at *natural amplitude*, so loudness structure re-emerges from the audio itself. |
| Grain = sample from m' + continuity prior, equal-power 0.375 s | `render.py` | **F** |
| One grain per step (monophonic) | `render.py` | **T** with the theory's multi-channel picture — v0.1 spec is explicitly monophonic; multi-voice added below as the concurrency fix |
| Panel: topology-from-spectrum, co-moving needles, collar | `panel/` | **F** |
| HPSS stems | `features.py` | extension beyond spec (NN-free, so compliant in spirit) |

Net: the mechanics are faithful; the three real tensions are (1) density-vs-
sample-path, (2) raw memory term unstable, (3) loudness normalization erasing
dynamics — all three are places where the spec's letter and the theory's
intent disagree, and we sided with intent, logged.

## Definition of done — where we are

- **M1 + M2**: implemented and **passing on real audio** (100% connectivity;
  all 4 macros live; renders audible and traversing the corpus after the
  orbit/render fixes).
- **M3**: implemented and run on real audio. Corrected verdict: **outcome (c)
  at κ=1 (memory collapses the orbit), outcome (b) at safe κ=0.3 (no objective
  difference)**. Structure is thin (2 of 8 modes measurable). Not load-bearing
  on this corpus/projection as-is; blind A/B is the outstanding tie-breaker.
- **M4**: implemented but **gate not cleared** (needs outcome a). Kept as an
  M2 exploration tool.
- Every `[open]` decision logged in `DECISIONS.md`.

## Next: the projection pivot (M3 outcome-b follow-up)

Outcome (b) sends the project to *"what projection makes K matter."* Two
concrete directions, both **NN-free** (spec-compliant — no Demucs/Spleeter):

1. **Beat-synchronous windows.** Use librosa beat tracking to align windows to
   bars instead of a fixed 0.75 s grid, so a(t) carries genuine phrase
   periodicity for the kernel to model. (Already the spec's first alternative
   for dead macros; here it's the first alternative for a dead kernel.)
2. **Per-stem decomposition (the "monolith" fix).** Today each window is one
   156-d vector over the *whole* mix, so the atlas captures overall texture, not
   "bass doing X while drums do Y." Decompose each track into classical NN-free
   streams — **HPSS** (harmonic vs percussive, `librosa.effects.hpss`) and/or a
   multiband split — feature each stream, concatenate into a richer window
   vector. Shipped as `stems: hpss` (config) / `--stems hpss` (build).

   **HPSS result (built, real corpus, `--stems hpss`):** richer chart structure
   — **basins 4 → 6**, the atlas now separates harmonic-led from percussion-led
   sections. Macros stay live (knob deltas 3.4–6.9). Kernel ablation nudges from
   whole-mix **outcome (b)** toward a **weak outcome (a)**: K-on mean |Δ| 0.059
   vs K-off 0.069 (still per-seed noisy). So the layer-split *helps* — modestly,
   not transformatively — and is the right base for the next projection work
   (e.g. HPSS **+ beat-sync windows** together, or a percussion-only operator).
   Top-4 macros remain smooth global coordinates with thin oscillation, so K is
   still not strongly load-bearing; blind A/B on the HPSS renders is the open
   question.

---

## M3 ablation (raw, auto-appended by ablate_k.py)

*(void — frozen-orbit run, κ=1.0, kept for the record)*
- 5 pairs × 3 min: K-on |Δ|=0.065 vs K-off 0.113 → looked like (a), but the
  orbit was collapsed so this is not a valid trajectory. Superseded below.

*(current — fixed pipeline, κ=0.3)*
- renders: 3 seed pairs × 2.0 min, kappa=0.3
- measured periods (s): [8.76, 20.61]  (6 overdamped modes excluded)
- corpus autocorr:  [0.0014, -0.0162]
- K-off autocorr:   [0.011, -0.0041]  (mean |Δ|=0.0108)
- K-on autocorr:    [0.0499, -0.0008]  (mean |Δ|=0.0319)
- objective verdict: **(b) no clear objective difference — a result, not a failure**
- subjective blind A/B notes: _TODO human listener_

## M3 ablation (auto-appended)
- renders: 3 seed pairs × 2.0 min, kappa=0.3
- measured periods (s): [13.98]  (7 overdamped modes excluded)
- corpus autocorr:  [0.0632]
- K-off autocorr:   [-0.0056]  (mean |Δ|=0.0687)
- K-on autocorr:    [0.0041]  (mean |Δ|=0.0591)
- objective verdict: (a) K moves toward corpus — theory load-bearing
- subjective blind A/B notes: _TODO human listener_

## Performed set (2026-07-10)
- First recorded *performance*: 10 min, 3 voices (ch1/ch0/ch6), all moves via
  emergent controls only — mode-0 lean sweep +1.5σ→−1.5σ→0 with mode-2
  counter-lean, scheduled γ (1.2→0.8→1.3), τ (1.1→0.8→1.1), coupling
  (0.3→0.8→0.4), composed all-voice jumps at ⅓ and ⅔.
- Reactive watchdog (jump + 30 s γ boost when a voice's last 60 emissions
  hold <15 distinct windows) armed but **never fired** — local variety held
  without intervention.
- Script: reproducible, seed 7; every action timestamped in a printed log.
- 44.1 kHz beat-synchronous instrument (`instrument_nmf44.npz`) built:
  11,056 windows / 20 tracks / K=8, chan_rms baked; performance re-recorded
  on it for the full-quality version.

## Navigation edition (2026-07-11)
- Listening verdict on `performed_nav` (region-gated emission, free walk,
  splice-true flux; journey composed from the measured territory map):
  **"sounds coherent"** — first recording where fader moves demonstrably
  carried the set across five territories (log-confirmed: t5 → t14 → t12 →
  m0− pole → home).
- Open: within-track parallel-bar hopping (~0.5 jump rate) — audible churn
  candidate; if it bothers the ear, fix belongs in the walk's own step
  statistics, not read-time rules.
- Next validation: 30-min unattended zero-lean set (`longset_nav`).

## A/B: parts vs path-state (2026-07-11)
- `longset_holonomy` (first-order walk + kernel + flywheel, velocity
  coupling) vs `longset_intrinsic` (path-state trace, zero parts) — same
  seeds, both 15 min unattended, zero lean. Delivered as 3 parts each.
- Intrinsic trace stats: 100% measured-segment hit rate, 4–14 tracks
  blended per minute (dominant 30–45%), migrating territory center,
  loudness envelope 0.05→0.08 (first unattended render with an arc).
- Channel splits now disk-cached (2.3 GB, one-time per corpus) — path-state
  blending made per-render recomputation slower than realtime.

## Pacing-arc performance (2026-07-11)
- `performed_arc` (10 min, 3 voices, path-state, full landscape): the set's
  speed arc as a knob journey on the two measured clock-carrying directions
  (eigs 11+7). Composed: slow open → build → peak → breakdown → release.
- Measured pacing s/step per minute: 0.79 0.73 0.73 0.53 0.54 0.60 0.69
  0.75 0.67 0.67 — the arc realized purely by routing; playback rate
  untouched. Most dynamic loudness envelope of any render (0.05–0.10).
- Zero new machinery: leans + velocity coupling + logged watchdog (silent).

## Reference set read (2026-07-11): "Eastern Distributor ~ Jörmungandr @ Dragon Dreaming"
- 86 min → 7,565 windows projected with the corpus's exact transforms.
- **Landing**: median top-chart weight 0.13 vs the corpus's own 0.14 —
  the reference sits on this landscape almost as much at home as the
  corpus itself; 177/256 charts traversed. (Corpus contains a
  Jörmungandr track — stylistic adjacency confirmed by measurement.)
- **Arc**: steering concentrates in the private-language tail (f24, f69,
  f18, f70, f20, f34 — directions with near-zero descriptor R²),
  confirming the conjecture that the interesting hands live where the
  named-vocabulary knobs can't reach. One loud public-language move: the
  finale (last 10%: tonal +0.50, bass −0.38, bright +0.29, rms −0.32,
  flat +0.28 — an airy outro executed hard, with f24 at −0.56).
- Sustained subtle signature elsewhere: rms mildly negative, pace mildly
  negative (rides slightly slower/quieter material than the corpus flow
  would drift to) — a restrained hand, not a dramatic one.
- `replayed_reference` (12 min) delivered: the corpus played by the
  extracted hands. Arc installed as `grammar.npz` — the panel autopilot
  now defaults to playing like this set (follow=1.0), hands are
  deviations, gravity eases back onto the reference trajectory.
