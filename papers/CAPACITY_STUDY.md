# ETS Companion — Capacity / Scaling Study (single-user)

**Date:** 2026-07-19
**Author:** measurement pass (read-only; no product code changed)
**Question:** For a SINGLE user (train OR listen, one corpus at a time), how big a
corpus can one Railway box handle, and is a plan upgrade needed?
**Operator framing (2026-07-19):** assume ≤1 user at a time. Concurrency is NOT a
factor — at most ONE trained world + the demo singleton is ever warm, so the
existing `ETS_MAX_LOADED_WORLDS=2` is already sufficient. This report therefore
studies the SINGLE-WORLD case only.

Every number below is tagged **[MEASURED]** or **[MODELED]**. Nothing is fabricated.
Method and environment are disclosed so any number can be reproduced or re-scaled.

---

## 0. Environment & method (disclosure)

- **Measured on:** this sandbox — 4 vCPU, 15 GiB RAM, Python 3.11, numpy 2.4.6,
  librosa 0.11.0. **This sandbox renders ~100× slower than real hardware**
  (per `CLAUDE.md`); all *CPU/time* numbers are annotated accordingly. *Memory*
  numbers are hardware-independent (byte counts) and transfer directly.
- **Scripts** (in `scratchpad/`, standalone, re-runnable):
  - `cap_bank.py` — bank memory vs audio duration / track count / storage dtype.
  - `cap_cpu.py` — per-bar `produce_one_bar` time vs corpus size (live play path).
  - `cap_single.py` — one build per subprocess: resident bank + **peak RSS
    (VmHWM)** + stage wall-times.
- **Real-audio worlds** were synthesized (rhythmic non-stationary WAVs, sr=44100)
  and built through the **actual engine path**: `ingest → extract_prototypes →
  anchors.build_world (the same GW/traffic anchor-fit the cloud runs) →
  build_index → save_world(corpus) → build_bank`. The bank is decoded audio held
  in RAM (`ets.render.sources.load_source_units`, `storage_dtype=float32` = the
  live default), which is the dominant and directly-measurable memory term.
- Bank measured with disk cache OFF (`ETS_BANK_NOCACHE=1`) so we measure the
  decode footprint, not a cache read.

---

## 1. Per-world bank memory vs corpus size  **[MEASURED]**

Single-track bank, float32 storage (live default), 8-band partition-of-unity:

| track dur (s) | units | bank MB | MB / s |
|---:|---:|---:|---:|
| 15 | 480  | 21.17  | 1.411 |
| 30 | 960  | 42.34  | 1.411 |
| 60 | 1920 | 84.67  | 1.411 |
| 90 | 2880 | 127.01 | 1.411 |

**Linear fit (R²=1.000): bank_MB = 1.4112 × (seconds of audio) per track.**
This equals `8 bands × 44100 Hz × 4 bytes / 1e6` exactly — the measurement lands
on the closed form, which is why confidence is high.

**The governing quantity is TOTAL audio, independent of how it splits into tracks**
(each track's units are independent). MEASURED confirmation: 4×60 s and 8×30 s
(both 240 s total) gave **338.7 MB vs 337.6 MB** — identical bank.

So, for a corpus of **T tracks × D seconds each = S = T·D total seconds**:

> **Resident bank ≈ 1.4112 MB × S  =  84.7 MB per minute of audio (float32) [MEASURED]**

Storage-dtype lever (MEASURED, 60 s track):

| dtype | MB/s per track | note |
|---|---:|---|
| float16 (`ETS_BANK_DTYPE=float16`) | 0.7056 | ~1e-3 rel precision; halves RAM |
| **float32 (default)** | **1.4112** | ~1e-7 rel precision; render math stays f64 |
| float64 | 2.8224 | exact; not used in prod |

Cross-check vs the code's own note (`engine.build_bank`: "20-track corpus ≈ 8.5 GB
float32"): 8500 MB ÷ 1.4112 = 6023 s ÷ 20 = **~5 min/track** — i.e. that note
assumes full-length songs. Consistent.

---

## 2. Peak RAM during a TRAIN — the real single-world limit  **[MEASURED + MODELED]**

Steady-state playback holds only the bank (§1). But a **train** transiently holds
much more: librosa decode + the STFT/filterbank working buffers + 8 float64 band
arrays per track, *on top of* the accumulating float32 bank. **Peak RSS (VmHWM)**,
one build per subprocess:

| tracks × dur | total s | M | units | resident bank MB | **peak RSS MB** | peak / bank |
|---|---:|---:|---:|---:|---:|---:|
| 2 × 30 | 60  | 2 | 1936  | 84.7  | 1051 | 12.4× |
| 4 × 30 | 120 | 3 | 4064  | 169.3 | 1136 | 6.7× |
| 8 × 30 | 240 | 4 | 8864  | 337.6 | 1306 | 3.9× |
| 4 × 60 | 240 | 2 | 8128  | 338.7 | 1497 | 4.4× |
| 4 × 90 | 360 | 2 | 12192 | 508.0 | 1824 | 3.6× |

Reading this:
- A **~0.95–1.0 GB fixed transient floor** [MEASURED here] dominates tiny corpora
  (Python + numpy + librosa + scipy working set + per-track STFT). This floor is
  environment-specific and will differ on Railway.
- Above the floor, peak grows at ≈ the bank slope plus a per-track STFT transient
  that scales with *per-track* duration (why 4×60 > 8×30 at equal total audio).
- For **non-trivial corpora the peak settles to ≈ 3.5–4× the resident bank**
  [MEASURED, converging at the 360 s point].

**MODELED training peak (the sizing rule):**
> **peak_train ≈ base(~1 GB transient) + ~3.5–4 × 1.4112 MB × S**
> ≈ base + **(5–5.6) MB per second of total audio**.

**Independent cross-check against history [MEASURED, prior]:**
`cloud/UPGRADE-TAKESTOCK.md` records "~4 tracks peaked **5.2 GB / 8 GB**" (the OOM
that motivated the LRU cap). Four full songs ≈ 960 s total → resident bank ≈ 1.36 GB
→ at the ~3.8× multiplier that is ≈ 5.2 GB. **The model reproduces the historical
Railway OOM point.** Confidence: good.

### CORRECTION (2026-07-20) — the §2 model measured a NON-DEPLOYED path; the real ceiling is ~4× lower  **[MEASURED — LIVE PROOF]**

The §2 table above (and its §5 conclusion "≈4–6 songs max, a 20-track train will
OOM 8 GB") measures `cap_single.py`, whose sequence is
`ingest → build_world → build_index → save_world → build_bank` **in one process** —
so `build_bank` materialises the full audio bank **while the ingest/STFT transients
are still resident**. That co-residency is what produces the 3.5–4× multiplier. **The
deployed `/api/train` path does NOT do this.** `cloud/companion/train_local.build_trained_world`
runs `ingest → stage3 → cloud_fit → verify → build_index → sigma_φ → save` and **never
calls `build_bank`** — the audio bank is built **lazily at first playback**
(`StreamPlayer.produce_one_bar`), a separate, later moment when the ingest transients
are gone. So the deployed path has TWO smaller peaks, not one 4× peak:

| deployed regime (20 tracks · 30 min audio · float16) | peak RSS | basis |
|---|---:|---|
| **Train** (`build_trained_world`, exact `/api/train` code) | **1351 MB** | [MEASURED 2026-07-20 — deployed `build_trained_world` path; repro `cloud/tools/train_peak_verify.py`] |
| **Playback** (lazy bank materialised, `produce_one_bar`) | **2271 MB** | [MEASURED 2026-07-20 — same run, `produce_one_bar`] |

**LIVE PROOF:** the operator's real 20-track corpus was trained on the live 8 GB
Hobby `ets-web` box via `/api/train` on 2026-07-20 — HTTP 200 in 283 s, `is_trained:true`,
M=5, `/api/health` **green throughout the entire train** (polled every 15 s), and a
fresh anonymous listener streamed **real audio** (RMS 1483, 99.9 % non-zero). No OOM.
Published as Explore set `set-c0e8cdfabd`.

**What was wrong:** an earlier estimate (this agent's) applied the §2 "3.5–4× bank ⇒
~8.4 GB for 20 tracks ⇒ upgrade or compress" model to the deployed path. That was a
**mis-applied model, not a measurement** — the deployed path is lazy-bank and never
reaches 4× bank. The §2 rows remain valid **for the `cap_single` eager-bank sequence**
(and for any future code that warms the bank inline during train); they do **not**
bound the deployed lazy-bank + LRU service. Corrected sizing for the deployed path:

> **MEASURED point (20 tracks / 30 min / float16):** train peak **~1.35 GB**, playback
> peak **~2.27 GB** — both well within 8 GB. An 8 GB box therefore trains + plays a
> **20-track corpus with headroom**; the earlier "≈4–6 songs" limit applied only to the
> eager-bank measurement path.
>
> **Sizing rule — use the PLAYBACK peak, which is the deployed maximum** (train is
> always *lower*, since the bank is not resident at train):
> **playback ≈ ~1.0 GB base + 0.7056 MB × (total audio seconds)** — the *base* is
> [MEASURED here ~1.0 GB] and the slope is the §1-[MEASURED] float16 bank slope; for
> 1800 s that gives ~2.27 GB, matching the point above. (No per-second *train* slope is
> asserted: only ONE deployed-path train point was measured, which cannot fit a slope.
> Train stays below playback by the absence of the resident bank — measured 1.35 vs
> 2.27 GB here.)

---

## 3. Train / anchor-fit TIME vs track count  **[MEASURED, sandbox]**

One-time per train (÷ ~100 for real hardware):

| tracks (×30 s) | ingest s | anchor-fit `build_world` s | build_bank s |
|---:|---:|---:|---:|
| 2 | 10.9 | 0.49 | 2.0 |
| 4 | 13.2 | 0.98 | 4.6 |
| 8 | 23.4 | 2.94 | 9.0 |

- **Anchor-fit** (the cross-track traffic operator, ~O(tracks²), then GW/barycenter
  sweeps): 2→8 tracks (4×) → 0.49→2.94 s (**6×**) — super-linear, consistent with
  the O(tracks²) term. But absolute cost is trivial: even 8 tracks is ~3 s in the
  ~100×-slow sandbox → **~30 ms real hardware [MODELED from the ~100× factor]**.
- **Ingest + build_bank** scale ~linearly with total audio and dominate wall time.
  A full train of 8 short tracks ≈ 35 s sandbox → **sub-second to a few seconds on
  real hardware**.
- **Extrapolation [MODELED]:** even a 50-track corpus's anchor-fit is (50/8)² ≈ 39×
  the 8-track time ≈ ~2 min sandbox ≈ **~1 s real**. Ingest of 50 full songs is the
  larger term (minutes) but is linear and non-fatal. **Train time is a mild
  one-time cost, not a wall, until very large corpora.**

---

## 4b. LIVE CORRECTION (2026-07-24) — the ×realtime conversion was WRONG for the deployed box  **[MEASURED, live]**

Measured on the LIVE ets-web box (Railway Pro, post-train, single produce loop, eigen worker
parked by the audio-defer, no other engines resident): a **10-track full-length DJ corpus
(M=4, ~70 min total audio) delivers 0.49× real-time**, steady over 90 s, identical under
`ETS_BANK_DTYPE=float16` and `float32` (dtype is NOT the bottleneck). The §4 sandbox rows
scale consistently (8 tracks/8.9k units → 0.3× sandbox); the live box is only ~1.5-2× faster
per core than this sandbox — the disclosed "~100×" sandbox→hardware factor (and therefore the
"30-113× realtime / CPU is a non-issue" conclusion) does NOT hold on Railway-class shared
vCPU. **CPU is the binding constraint for full-length corpora on the current host.**
Corpora at the 20-track/30-min-clips scale DO play ≥1× live (verified). Options, none
applied without operator sign-off: (a) producer pipelining in the bridge (≤2× bound),
(b) preregistered engine-path optimization guided by an on-box per-stage profile,
(c) corpus guidance (clip-length sources), (d) faster single-core host.

## 4. Per-bar playback CPU vs corpus size  **[MEASURED, sandbox]**

`StreamPlayer.produce_one_bar` (the exact live path: settle → temperature sample →
fiber threading → schedule → render → soft cap), steady-state:

| tracks | M | units | bar realtime (s) | produce s/bar (sandbox) | ×realtime (sandbox) |
|---:|---:|---:|---:|---:|---:|
| 2 | 2 | 1936 | 1.98 | 3.47 | 0.6× |
| 4 | 3 | 4064 | 1.89 | 3.70 | 0.5× |
| 8 | 4 | 8864 | 1.72 | 6.21 | 0.3× |

- **Sub-linear growth:** 2→8 tracks (4× tracks, 4.6× units) raises produce time only
  **1.8×**. It does **not** blow up with corpus size — settlement cost is set by M
  (small: 2–4, it's `effective_rank`, data-capped) and render is a flat per-unit copy.
- **Real-hardware reference [MEASURED, prior]:** 0.0088 s/bar on the 4-track demo =
  **~113× realtime**. Applying the observed 1.8×-per-4× growth, an 8-track trained
  world is still **≈ 30–60× realtime on real hardware [MODELED]**. One vCPU serves
  the single stream with vast headroom. **CPU is a non-issue for one user.**

---

## 5. Bottom line — how big can ONE corpus be, and is an upgrade needed?

> **⚠ SUPERSEDED for the deployed service — see the CORRECTION in §2 (2026-07-20).**
> The "≈4–6 songs / 20-track OOM / need 32 GB" numbers below were derived from the
> `cap_single` eager-bank path. The DEPLOYED `/api/train` is lazy-bank: a 20-track /
> 30-min corpus was trained + played LIVE on the 8 GB box (train ~1.35 GB, play
> ~2.3 GB, health green throughout). **An 8 GB box handles a 20-track corpus.** The
> section below is retained as the (correct) analysis of the eager-bank sizing model.

**The single binding constraint is TRAIN-TIME PEAK RAM.** Not CPU (30–113×
realtime), not train time (seconds), not steady-state playback RAM (bank only).

Sizing for the current **8 GB**-class box, single world (reserve ~1.0 GB base
transient + ~0.1 GB demo singleton + margin → ~6.5 GB usable for the train peak):

| what fits in 8 GB (one corpus) | value | basis |
|---|---|---|
| Steady-state playback (bank only) | **~90 min** total audio (8000/1.4112·60) | [MEASURED] — never the limit |
| **Train peak (the real cap)** | **~18–20 min** total audio ≈ **4–6 full songs** | [MODELED ~4× ×-checked to the historical 5.2 GB/4-song OOM] |

> **For a single user, an 8 GB box comfortably trains + plays a corpus of roughly
> 4–6 full-length tracks (~15–20 min of audio).** This matches the historical
> operator note ("can't train more than ~6 at once; a 20-track train will OOM").

**Railway recommendation:**
- **The lever is RAM, not CPU.** One vCPU already serves the single stream at
  30–113× realtime; more cores buy nothing for one user.
- **`ETS_MAX_LOADED_WORLDS=2` is correct and needs no change** for the single-user
  model (one trained world + demo singleton).
- **If the operator only needs ≤ ~5-song corpora:** the current 8 GB-class plan is
  **sufficient — no upgrade required.**
- **To support larger single corpora**, size RAM by the train peak:
  > **RAM ≈ 1.5 GB (base+demo+margin) + ~5.6 MB × (total audio seconds).**

  | target corpus | total audio | RAM needed (train peak) | plan |
  |---|---:|---:|---|
  | ~5 songs (today) | ~20 min | ~8 GB | current |
  | ~10 songs | ~40 min | ~14 GB | 16 GB |
  | ~20 songs / ~1 h | ~60 min | ~21 GB | 32 GB |

- **Cheaper alternative to a bigger plan (config-only, already supported):**
  `ETS_BANK_DTYPE=float16` halves the resident bank (0.7056 MB/s). It shrinks the
  steady-state and the bank portion of the train peak — the fixed STFT transient is
  unaffected — buying roughly +50–70% corpus headroom at ~1e-3 audio precision. A
  zero-cost first step before paying for RAM.

---

## What could NOT be fully measured (honest gaps)

- **Absolute Railway RAM/CPU** was not measured live — training against live Railway
  for many sizes would load the prod service. Bank RAM is a hardware-independent
  byte count (transfers exactly); the ~1 GB *transient floor* in §2 is
  **environment-specific** and may differ on Railway (different lib versions /
  allocator). The train-peak *multiplier* (~3.5–4×) is what's load-bearing, and it
  is cross-checked against the historical Railway 5.2 GB point.
- **All time/×-realtime numbers are sandbox-measured** and converted to real
  hardware via the disclosed ~100× factor (`CLAUDE.md`) — labeled [MODELED] wherever
  that conversion is applied. The playback reference (0.0088 s/bar = 113× realtime)
  is prior-measured, not re-measured here.
- Worlds were built from **synthesized** real-audio WAVs, not the operator's music.
  Bank size depends only on total duration/sr/bands (not musical content), so this
  does not bias the memory result; anchor count M and unit count can vary somewhat
  with real material.
