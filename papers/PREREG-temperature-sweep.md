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
