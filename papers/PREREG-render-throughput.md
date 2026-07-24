# PREREG — render-path throughput optimization (per-bar cost), OPERATOR SIGN-OFF REQUIRED

**Date:** 2026-07-24 · **Status:** DRAFT — awaiting operator ratification. NO engine code
is modified until this prereg is signed.

## Motivating wall (measured live, 2026-07-24)
Full-length corpora render slower than real-time on the deployed ets-web box, with every
confounder eliminated by measurement:
- 4-track full-length set, warm bank, box verified at **0.00 CPU** beforehand, ONE stream
  alone: **0.50-0.51× real-time** (two independent runs, two host placements; a third
  placement measured 0.22×). 10-track full-length: **0.49×**.
- Identical at `ETS_BANK_DTYPE=float16` and `float32` → dtype ruled out.
- Zero background loops (idle-stop live, CPU-verified silence) → contention ruled out.
- `git diff` of the deployed bridge vs the prior known-good deploy touches only analysis
  defer + idle-stop, NOT the render path → code regression ruled out.
- Railway plan limits are maxed (24 vCPU/24 GB, dashboard-verified) and the renderer uses
  ~1 vCPU → platform throttling ruled out. The render loop is single-threaded by design.
- These live rates match `papers/CAPACITY_STUDY.md` §4's sandbox per-bar table (~4k units
  → ~0.5×), i.e. the per-bar cost model, not an anomaly.

## Profile (sandbox, real engine path, demo world, cProfile over 6 bars)
`produce_one_bar` = 100%:
- `writer.stream.write_bar` ≈ **54%** — dominated by `realize.place_slot` /
  `realize._choose` (the per-slot unit-placement inner loop; `_reuse` called ~2.6k×/bar)
- `render.render` ≈ **27%**
- caps/telemetry/schedule ≈ 19%
Cost scales with corpus unit count (candidate sets per slot), matching the live scaling.

## Proposed change (scope, strictly bounded)
Optimize the IMPLEMENTATION of the placement inner loop (`ets/writer/realize.py:
place_slot/_choose/_reuse` and, only if profiling demands, the mixing loop in
`ets/render/render.py`) via vectorization / precomputation / caching — in
`architecture-v6/ets` and mirrored byte-identically to the other engine trees per the
established multi-tree discipline. **NO semantic change**: identical candidate sets,
identical measure, identical RNG consumption, identical chosen units, identical audio.
F / settlement / O-block / world definition / tape semantics are OUT OF SCOPE and
untouched.

## Gates (all must pass; ets-auditor adversarial pass required)
- **G1 (bit-identity of choices):** on fixed seeds across demo + synthetic multi-track
  worlds, the optimized `_choose` returns bit-identical placement rows to the baseline.
- **G2 (byte-identity of audio):** offline render and live-loop streamed PCM byte-equal
  to baseline on the same worlds/seeds (existing test_stream_decode pattern).
- **G3 (throughput):** ≥2× produce_one_bar throughput on a ≥4k-unit world (sandbox
  measured), and live delivery ≥1.0× real-time on the operator's 4-track set.
- **G4:** full cloud suite green; no engine-tree divergence (diff -q across trees).
- **G5:** live verification on ets-web before "done" is claimed.

## Rollback
Single revert commit; worlds/banks are unaffected (read-only compute optimization —
no on-disk format change).

## Operator sign-off
- [x] RATIFIED (operator, in-session: "ok go ahead using persistent opus builder /agents while retaining the existing thing as backup and retaining version control"): 2026-07-24
