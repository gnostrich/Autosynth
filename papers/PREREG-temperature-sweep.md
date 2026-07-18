# PREREG — temperature-sweep of the mode spectrum (T2 as a measurement axis)

**Status:** operator-signed-off; COMMIT-BEFORE-RUN (this prereg + the sweep script are
committed before any sweep is executed — the method is fixed before results are seen).
Sampler / F / world / settlement UNTOUCHED. T_s is the EXISTING temperature control
(the writer's `_T_s`, the TEMP throttle); this experiment only *reads* the mode spectrum
at several of its settings — it authors nothing and changes no engine code.

## Motivation
The mode measurement is currently taken at a SINGLE temperature (the default `_T_s=1`).
But `_T_s` sets how much the settlement fluctuates, and temperature is exactly the axis
along which soft modes freeze in / out (equipartition: a mode carries ~½·(scale) of
fluctuation; heating raises the fluctuation, cooling freezes it). A corpus can look k=1
at one temperature and reveal a second soft mode at another. We never look along this
axis. This sweep does.

## Hypothesis
H1: `k(T_s)` is non-constant — at least one corpus shows a mode crossing the floor as
`T_s` varies (a mode freezing in on heating or out on cooling), i.e. structure the
single-temperature measurement misses.
H0: `k(T_s)` is flat over the swept range → the single-temperature reading was
representative; no hidden temperature-dependent mode. Report and stop.

## Method (additive; new offline script, e.g. `scratchpad/eigen/temp_sweep.py`)
1. **Floors first.** At each `T_s` in the grid, the shuffle-null floor is RE-DERIVED
   from that temperature's own ensemble (the floor scales with the fluctuation, so a
   fixed floor would be wrong). Compute and record the per-`T_s` floor BEFORE counting
   any surviving modes. No mode is counted against a floor from a different temperature.
2. **Fixture scale first.** Validate the whole sweep at a CHEAP fixture ensemble
   (small n_seed/n_bar, coarse `T_s` grid) — confirm the mechanics, the floor re-derivation,
   and the plotting — BEFORE committing compute to the authoritative ensemble. Disclose
   the fixture precision like the boot-ensemble note does.
3. **Sweep.** `T_s` grid across the control's real range (`SCALAR_T_LO..SCALAR_T_HI` =
   0.001..4.0, the deployed throttle range), e.g. geometric spacing. At each point:
   build the response kernel (the PROTECTED baseline estimator, unchanged) at that
   `_T_s`, record the full spectrum + the re-derived floor + per-mode SE + `k`.
4. **Report** `k(T_s)` and the spectrum trajectory (each eigenvalue vs `T_s`, with the
   floor overlaid) for the demo (k=2 control) and the two trained sets (k=1). A mode
   that crosses the floor as `T_s` moves is the H1 signal.

## Protected baseline / walls
- The estimator, sampler, F, and world are unchanged; only `_T_s` (an existing control)
  is set to each grid value before a read.
- The floor is per-temperature (re-derived), never shared across `T_s` — stated up front
  so a mode is never judged against a foreign-temperature noise level.
- Compute is heavy (each `T_s` is a full ensemble ~minutes on the container); the sweep
  runs offline (not on the playback path), fixture-scale first.

## Success / stop criteria
- H1 (a mode crosses): report the `k(T_s)` curve; the temperature at which the mode
  appears is a real, previously-unseen steering axis → propose exposing temperature as a
  measurement/render axis, operator's call.
- H0 (flat): report the flat curve; the single-temperature k is the honest answer, no
  hidden thermal mode. Stop.

---

## ADDENDUM — exposing temperature as a PLAYABLE steering axis (operator's call, taken)

**Status:** the H1 success criterion above explicitly deferred "exposing temperature as a
measurement/render axis" to the operator. The operator took that call: *"just fix the build
such that the modes show up as we change temperature … so i can play"* / *"yes do this
upgrade."* This addendum records the decision and its faithfulness design. **This is a
STEERING/RENDER change, not read-only** — it is scoped here so it is not mislabeled.

### H1 result (demo, full 24×32 ensemble, per-T_s re-derived floor)
`k(T_s)`: 0.25→**1**, 0.5→**1**, 1.0→**2**, 1.5→**2**, 2.0→**3**, 3.0→**3**, 4.0→**3**.
H1 CONFIRMED: modes freeze IN as `T_s` rises (a 2nd steerable mode appears at the default
`T_s=1.0`, a 3rd by `T_s=2.0`). The trained sets' curves are reported alongside when their
sweeps land.

### What the exposure does
The Play pad's control basis IS `radialModes`/`radialK` (the `/api/steer` force vector is
built from the surviving modes' eigenvector compositions). Exposing temperature as a playable
axis means: **as the TEMP throttle moves, the pad reselects its control basis to the modes
measured at that `T_s`.** Petals appear/vanish as the operator heats/cools, and the newly-
appeared modes become steerable.

### Why this is faithful (not a second hidden channel)
The engine genuinely settles at `T_s` (the writer samples `p(a) ∝ exp(−F/T_s + Σλφ)`,
`ξ ~ N(0, T_s·H⁻¹)`). The eigenmodes of the response kernel measured at `T_s` ARE the real
steerable directions of the object at that operating point. So TEMP does ONE physical thing
— it sets the sampler's operating temperature — and "more modes become steerable" is the
faithful *consequence* of that one thing, not a separate undeclared authority. The force
vector still projects only into the EXISTING sanctioned steer lanes
(continuity/novelty/density/region); no new control channel to the engine is created.

### Fidelity guards (address the authoritative-vs-sweep split)
1. **Default operating point uses the FULL authoritative ensemble, never a sweep row.** At
   `T_s=1.0` (the neutral default, and what the boot ensemble measures) the pad restores the
   authoritative boot modes (`radialAuthoritative`), so load-time and TEMP-default agree
   exactly and the pad is never silently downgraded to a sweep-measured row.
2. **Off-default uses the sweep row for the nearest measured `T_s`** — the best available
   measurement at that operating point (same estimator, same n_seed/n_bar; there is no
   separate authoritative ensemble at non-default temperatures).
3. **Clean return path:** returning the throttle to default reinstalls the authoritative
   basis; there is no latch-out.

### Automatic measurement (any world, no manual step)
The sweep is measured ONCE per world by an off-playback background worker in
`StreamPlayer`, mirroring the existing boot-eigen worker: it is triggered only AFTER the
single-temperature eigen ensemble has landed (it is 7× heavier, so it runs last and never
before audio warms), computes `temperature_sweep`, lands the table in one atomic assignment,
and persists a STAMPED sidecar (`world_path + ".sweep.json"`) that self-invalidates on any
world/param change. So a freshly-trained set gets the temperature axis automatically — the
set is playable immediately and the axis fills in a few minutes later (`sweep_pending` is the
honest "measuring temperature modes…" state, distinct from a world that has no table). A
cache hit (the committed demo, an admin upload, or a prior auto-run) loads instantly. No
world is ever served a stale or foreign table; nothing runs on the audio path.

### Data provenance / walls (unchanged from the body)
- Every mode shown is a REAL measured eigenvector/eigenvalue that survives the double floor
  (`|λ|>floor AND |λ|−2·SE>floor`) at that `T_s`; nothing is fabricated. A degenerate corpus
  that resolves no 2nd mode at any `T_s` shows a flat pad honestly.
- The sweep table is measured off-playback (minutes on the container) and cached in a sidecar
  (`world_path + ".sweep.json"`); the committed demo carries its own real sweep sidecar so a
  fresh clone shows the axis (R5 intact). `/api/admin/upload_sweep` (key-gated) injects a
  set's table without a live re-solve. Sampler / F / world / settlement remain UNTOUCHED —
  the change is purely which measured basis the pad steers, at the operator's chosen operating
  temperature.
