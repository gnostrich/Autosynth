# GATE — render-path throughput optimization (PREREG-render-throughput.md)

**Prereg:** `papers/PREREG-render-throughput.md`, operator-RATIFIED 2026-07-24.
**Engine tree:** `architecture-v6/ets` (the deployed companion engine) — see §6.
**Instrument:** `cloud/tools/fast_realize_verify.py` (this file's numbers are its
output; every measured pass runs in its own interpreter — see §5.1).
**Date:** 2026-07-24/25 (sandbox).

## 0. What was changed

Two IMPLEMENTATION memos. Neither changes what is composed or rendered; both are
selected at call time by an env kill-switch, with the original code retained
verbatim as the miss/off path.

| # | Where | What | Kill switch (default) |
|---|---|---|---|
| A | `ets/writer/realize.py` `FiberThreader._choose` | dispatches to `_choose_fast` (the same Layer-0 measure on precomputed arrays) or `_choose_original` (verbatim) | `ETS_FAST_REALIZE` (`1`) |
| B | `ets/render/render.py` `render` | memoizes the loudness-independent half of `_apply_gauge` (pitch shift + time-stretch + fix_length) per `SourceUnitBank` | `ETS_STRETCH_CACHE` (`1`), budget `ETS_STRETCH_CACHE_MB` (`128`) |

Why B is inside the ratified scope: the prereg's scope line reads "…and, only if
profiling demands, the mixing loop in `ets/render/render.py`". Profiling demanded
it — see §2.

F, settlement, the O-block, tilt/measure definitions, tape semantics, world
format, RNG seeding and the schedule are untouched.

## 1. Test worlds

| tag | tracks | units | M | bands | s_phase | pools | max pool | note |
|---|---|---|---|---|---|---|---|---|
| `demo.etsworld` | 4 | 768 | 2 | 8 | 8 | 16 | 96 | the committed self-contained demo |
| big-single-tempo | 6 x 30 s @ 120 bpm | **5760** | 3 | 8 | 8 | 24 | 720 | synthesized, trained through the real path |
| big-multi-tempo | 6 x 30 s @ 112..147 bpm | **6192** | 3 | 8 | 8 | 24 | 774 | synthesized, trained through the real path |

Both big worlds are synthesized (rhythmic non-stationary WAVs, the
`CAPACITY_STUDY` / `seam_verify` recipe) and built through the actual path
(`ingest -> stage-3 -> anchor fit -> build_index -> save_world`), then rendered
from a real audio bank. Rebuild with
`python3 cloud/tools/fast_realize_verify.py --build-world --bpm 120 --spread 0`
(18 s) / `--bpm 112 --spread 7` (116 s).

## 2. Where the bar goes (the profiling that redirected the work)

Per-bar split, measured by the tool (compose = settlement + fiber choice, i.e.
what A touches; finish = render + telemetry, i.e. what B touches), baseline
configuration:

| world | ms/bar | compose | finish | finish share |
|---|---:|---:|---:|---:|
| demo | 18.8 | 8.9 | 9.8 | 52% |
| big-single-tempo | 396.0 | 32.6 | 363.4 | **92%** |
| big-multi-tempo | 361.4 | 23.2 | 338.3 | **94%** |

On any >=4k-unit world the bar is dominated by ONE `librosa.time_stretch` per
placement (~4 ms x 64 placements/bar), not by the placement loop. The prereg's
motivating profile (`write_bar` 54%) is a demo-world profile: the demo world's
units already match the output tatum, so `_apply_gauge` short-circuits and no
phase vocoder runs. Consequently **the fiber-choice memo alone cannot reach 2x on
a big world** (measured: 1.00x / 1.15x) — it is bounded by an 8% share. This was
reported as a wall and the coordinator redirected to the render half within the
ratified scope.

Repeat structure that makes B work (big-multi-tempo, 150 bars, u=0):
9600 placements carry only **2657 distinct** `(unit, out_len)` stretch inputs;
the repeat rate is 15.9% over the first 10 bars and **91.6% over the last 10**.
Stretch ratios span 0.78–1.24 (median 1.044); only 3.8% are within 1% of unity,
so these are real stretches, not near-identity ones.

## 3. Gate table

### G1 — bit-identity of the choices (placement rows)
12 bars per pass under a deterministic lane + FIELD-BIAS program (region lean,
continuity, novelty, live temperature, and all three grains: track / unit /
(track, role)), comparing every row field `(slot, track, unit, section, mass)`
and every φ_cont flag. Three comparisons per world so neither half can mask the
other: `both vs base`, `both vs fiber`, `fiber vs base`.

| world | rows compared | verdict |
|---|---:|---|
| demo | 768 | **PASS** — identical on all three comparisons |
| big-single-tempo | 768 | **PASS** — identical on all three comparisons |
| big-multi-tempo | 768 | **PASS** — identical on all three comparisons |

### G2 — byte-identity of the audio
(a) the direct `produce_one_bar` sequence, (b) the REAL produce loop through
`subscribe()` (the pacing/threading path a listener gets).

| world | G2a bytes / sha256-16 | G2b bytes / sha256-16 | verdict |
|---|---|---|---|
| demo | 1,058,304 / `5b09529451ee451d` | 705,536 / `812d97307a344f30` | **PASS** |
| big-single-tempo | 2,116,800 / `b51c8d9e97043bf9` | 1,411,200 / `87d9b41e139e9f8c` | **PASS** |
| big-multi-tempo | 1,971,648 / `394a49c17ce54bb5` | 1,314,432 / `ee2af48ec4709219` | **PASS** |

Every hash is identical for `both`, `fiber` and `base`. Additional direct-render
identity (audio AND provenance bytes, including the recorded `stretch_ratio`) is
pinned in `cloud/tests/test_stretch_memo.py`.

### G3 — throughput
40 bars timed after 20 warm-up bars, ONE PROCESS PER CONFIGURATION, back to
back. `base` = both switches off (the pre-change engine).

The prereg's G3 has TWO clauses: ">=2x produce_one_bar throughput on a >=4k-unit
world (sandbox measured)" AND "live delivery >=1.0x real-time on the operator's
4-track set". Only the SANDBOX clause is settled below. The live clause is
prereg G5 (live verification on ets-web) and is PENDING DEPLOY — every "PASS"
in these tables is the sandbox clause only.

**big-multi-tempo (6192 units) — the corpus class that failed:**

| config | bars/s | ms/bar | compose | finish | realtime | speedup |
|---|---:|---:|---:|---:|---:|---:|
| base | 2.767 | 361.4 | 23.2 | 338.3 | 5.15x | — |
| fiber | 2.773 | 360.6 | 8.1 | 352.5 | 5.17x | 1.00x |
| memo | 5.546 | 180.3 | 24.5 | 155.8 | 10.33x | 2.00x |
| **both** | **6.546** | **152.8** | **7.1** | **145.7** | **12.19x** | **2.37x  PASS (sandbox clause, >=2.0x); live >=1.0x realtime clause = G5, pending deploy** |

**big-single-tempo (5760 units):**

| config | bars/s | ms/bar | compose | finish | realtime | speedup |
|---|---:|---:|---:|---:|---:|---:|
| base | 2.525 | 396.0 | 32.6 | 363.4 | 5.05x | — |
| fiber | 2.912 | 343.4 | 7.2 | 336.2 | 5.82x | 1.15x |
| memo | 7.267 | 137.6 | 32.6 | 105.0 | 14.53x | 2.88x |
| **both** | **10.011** | **99.9** | **7.3** | **92.5** | **20.02x** | **3.96x  PASS (sandbox clause); live >=1.0x realtime clause = G5, pending deploy** |

**demo (768 units) — reported honestly, not gated:**

| config | bars/s | ms/bar | compose | finish | realtime | speedup |
|---|---:|---:|---:|---:|---:|---:|
| base | 53.164 | 18.8 | 8.9 | 9.8 | 53.16x | — |
| fiber | 62.679 | 16.0 | 5.7 | 10.1 | 62.67x | 1.18x |
| memo | 56.524 | 17.7 | 8.5 | 9.2 | 56.52x | 1.06x |
| both | 64.060 | 15.6 | 5.6 | 9.9 | 64.05x | 1.20x |

The demo world is where the fiber memo shows and the stretch memo cannot: no
placement needs a stretch there, so B only saves the `asarray`/`fix_length`
bookkeeping (1.06x, near noise). The compose half alone is 1.6x (demo), 4.5x
(single-tempo), 2.9x (multi-tempo) — that is the honest measure of change A.

### Memo residency and the budget curve (big-multi-tempo, 60 bars)

| `ETS_STRETCH_CACHE_MB` | bars/s | hit rate | entries | resident | evictions |
|---:|---:|---:|---:|---:|---:|
| 64 | 4.539 | 37.8% | 779 | 64 MB | 1608 |
| **128 (default)** | **6.546** | **50.1%** | 1558 | 128 MB | 359 |
| 256 | 6.698 | 50.9% | 1884 | 155 MB | 0 |
| 512 | 6.461 | 50.9% | 1884 | 155 MB | 0 |

The 60-bar working set on that world is 1884 entries / 155 MB; the default 128 MB
buys 97% of the attainable speedup at 83% of the memory. A longer session's
working set grows toward the corpus (6192 units x 82 KB = 509 MB), so at a fixed
128 MB the steady-state hit rate settles in the 50–66% band (simulated: 66.1% at
128 MB over 150 bars). Eviction is never semantic: a dropped entry is recomputed
(pinned by `test_budget_is_a_memory_bound_not_a_semantic_one`).

### G4 — suites
- `python3 -m pytest cloud/tests/ -q` -> **291 passed** (170 s), including the
  two new files (`test_fast_realize.py` 5, `test_stretch_memo.py` 5).
- `architecture-v6`: `tests/invariants tests/render` -> 34 passed, 5 skipped,
  **1 pre-existing failure unrelated to this work**: `I-9` reads
  `architecture-v6/training_results.json`, which only exists at the repo root
  (`ROOT = parents[2]`; test last touched at `c604bcd`, before this work).
  I-11 (render applies, never chooses: AST scan + determinism +
  order-independence) and I-12 (provenance) PASS with the memo in place.
- `architecture-v6`: `tests/writer tests/engine tests/meters` -> 66 passed, 1 skipped.

## 4. Invariants touched and how they are tested

| invariant | how this change touches it | test |
|---|---|---|
| I-1 (single control entry) | none — no new control channel; the memos read no lane | existing C-3/I-1 tests |
| I-8 (state bounded by material) | A adds memos derived from the FROZEN index + the grid; B adds a per-bank memo with a byte budget | `test_fast_realize.py::test_fast_memos_are_bounded` (warm == late over 24 further bars; <= pools, pools x s_phase, units); `test_stretch_memo.py::test_budget_is_a_memory_bound_not_a_semantic_one` |
| I-11 (render applies, never chooses) | B lives in the render | arch-v6 `_check_i11`: AST decision-name scan of the whole render package, determinism, order-independence — all pass; eviction is by use order only, nothing is scored/ranked |
| I-12 (provenance) | B caches the `stretch_ratio` the provenance records | `test_stretch_memo.py::test_direct_render_is_byte_identical_with_the_memo` compares provenance BYTES |
| I-14 (instruments are not decision channels) | `stretch_memo_stats()` is read-only telemetry | nothing reads it back; grep-able single definition |
| H-8 (same world+tilt+seed -> identical tape) | the whole point | G1/G2 above |

Extra tooth specific to the memo keys: `test_memo_is_per_bank` renders the SAME
schedule against two banks carrying the same `(track, unit)` ids but different
audio and asserts the outputs DIFFER — one world's material can never be served
for another's (the memo is held in a weak map keyed by the bank object).

## 5. Instrument notes (honest measurement)

**5.1 Process isolation is part of the instrument.** The first A/B ran both flag
states in ONE process and reported the fast path as **6x SLOWER** (0.206 vs 1.285
bars/s). Cause, measured: `subscribe()` leaves the warm produce loop running for
`ETS_WARM_IDLE_S` (120 s default) after the last listener leaves, so a later
timed pass shares the core with a background renderer; each pass also leaves a
~250 MB bank resident. The same code, one pass per process, reads 4.371 vs 4.309.
Every measured pass in this report therefore ran as `--phase` in its own
interpreter with its own env. One further outlier was observed and discarded by
repetition (a single bench child read 2974 ms/bar where five repeats of the same
configuration read 346–387 ms/bar); the tables above come from runs whose
repeats agreed.

**5.2 What is NOT claimed.** These are sandbox numbers on synthesized corpora.
No live ets-web verification was run (prereg G5 remains open, operator action).
The operator's real corpora may differ in unit-length dispersion, which is what
sets the stretch memo's hit rate.

## 6. Tree mirror — recorded decision

**arch-v6 ONLY.** `ets/` (engine-v1.1-freeze) and `ui-v6/ets/` are untouched by
this work; no `release-manifest.json` re-bless is pending from it.

Two facts behind that decision, stated precisely:

1. `writer/realize.py` **already** diverged before this work: `ets/` and
   `ui-v6/ets/` are byte-identical to each other but lack the arch-v6 field-bias
   block (commits `b9e4b7b`, `59d91dc`, `6f00fff`). Byte-identical mirroring is
   IMPOSSIBLE without leaving scope: `ets/writer/tilt.py`'s
   `fiber_choice_logits(energies, is_continuation, reuse, tilt)` has no
   `channel_bias` parameter, so the arch-v6 file would raise `TypeError` on the
   first tilted choice there.
2. `render/render.py` was byte-identical across ALL THREE trees at `e57bc28`
   (`md5 66f7311b3d8c24452898a26d74a36e1e`). This work introduces a NEW
   arch-v6-only divergence in that file. It is a deliberate scope choice, not a
   technical necessity: `render.py`'s memo has no dependency on the diverged
   `tilt.py`, so mirroring it to `ets/` and `ui-v6/` later is a clean one-file
   copy (which WOULD then require the canonical manifest re-bless,
   `scripts/verify_version.py --update`, same pattern as the engine-v1.1 freeze).

## 7. Wall left open (reported, NOT patched)

On multi-tempo corpora the remaining 146 ms/bar is still ~95% phase vocoder on
the ~50% of placements that miss the memo. Two levers exist and BOTH are
semantic changes that this prereg does not authorize:

- an identity band (skip the stretch when `|ratio - 1|` is below a threshold) —
  measured to affect only 3.8% of placements at 1% width on the multi-tempo
  world, and it would change the audio;
- a different stretch backend (the prereg's "rubberband-class" note).

Neither was implemented. If throughput beyond this is wanted, it needs its own
pre-registered run.
