# PREREG — Gibbs-EBM-natural mode cutoff (experimental variant)

**Status:** operator-signed-off exploration ("make an engine version to try out,
protecting the previous one, give this a shot"). Baseline is PROTECTED; this is
additive and opt-in. No change to F / settlement / render / world definition. The
frozen `ets/` and `architecture-v6/ets` engines are byte-untouched. The production
estimator `cloud/companion/engine_bridge.compute_eigenmodes` is the PROTECTED BASELINE
and is not modified.

## Motivation
Two genuinely different trained corpora both measure **k=1** under the current
estimator (full 24×32 response kernel + shuffle-null p97.5 + 2·SE cutoff). The demo
world measures **k=2**. The current estimator's *object* is already the EBM-correct
one: the symmetrized **response kernel** `Ksym = ½(K+Kᵀ)`, `K=R/σ`, which by Theorem A
is the projected conjugate fluctuation `d⟨Φ⟩/du = (1/ε)·Cov|_projected` — and it
correctly dodges the P5 covariance trap (continuity: huge marginal variance, ~0
response → the response kernel zeroes its row, the plain covariance would not). So the
object is not what we vary.

What is UNTESTED is the **cutoff**. Today's floor is a *statistical* null (permute the
±h labels, take the p97.5 of the max noise eigenvalue, require the mode to clear it by
2·SE). The Gibbs-EBM-natural floor is a *physical* one: by equipartition each
independent quadratic mode carries ~½ε of fluctuation, so a "real" (soft) mode is one
whose susceptibility eigenvalue stands above the **thermal scale ε**, equivalently one
that sits above the **spectral gap** separating collective soft modes from the thermal
bulk.

## Hypothesis
H1: On the k=1 trained sets, the 2nd eigenvalue of Ksym sits **just below** the
shuffle-null floor (a soft mode the conservative statistical cutoff suppresses), and a
thermal/spectral-gap criterion would legitimately admit it → k≥2.
H0 (null / honest-negative): the 2nd eigenvalue sits **far below** the floor and any
spectral gap → the object genuinely has one mode; no cutoff change is honest; report
k=1 as the truth and stop.

## Method (additive; `cloud/companion/eigen_experimental.py`)
1. Reuse the EXACT baseline `Ksym` and its full signed eigenvalue spectrum + the same
   shuffle-null draws and bootstrap SE (no re-derivation of the object).
2. Expose the FULL spectrum + floor + per-eigenvalue SE (baseline only returns k and
   the surviving modes) — the diagnostic that decides H1 vs H0.
3. Add two ALTERNATIVE cutoffs, computed alongside the baseline (never replacing it):
   - **Spectral-gap:** largest ratio gap λ_r/λ_{r+1} in the sorted |spectrum|; k = the
     index before the dominant gap (classic soft-mode/bulk separation).
   - **Thermal-scale:** k = # eigenvalues whose |λ| exceeds a physical multiple of the
     measured thermal fluctuation scale (σ_φ-derived), reported for a small sweep of
     the multiple so the operator sees the sensitivity.
4. Report, per world, the baseline-k AND each alternative-k WITH the raw spectrum, so
   the decision is made on data, not on a single number.

## Protected baseline / walls (surfaced, not papered over)
- The sampler is UNTOUCHED (greedy argmin — the protected baseline; the seed ensemble
  is the fluctuation source, same as the baseline estimator).
- The response kernel (not plain covariance) is KEPT — the P5 trap stays fixed.
- A true no-nudge FDT read (susceptibility from equilibrium fluctuations without ±h
  perturbation) is OUT OF SCOPE for this first shot: it needs finite-T Gibbs samples a
  greedy argmin does not provide, and per-control conjugate-observable identification.
  Noted as the natural next step IF the cutoff experiment shows near-threshold modes.

## Success / stop criteria
- H1 supported (a real soft mode is being suppressed) → propose the thermal cutoff as
  an opt-in, WITH the spectrum shown to the operator for the final call. Still their
  decision — a looser cutoff trades some fabrication risk for more axes.
- H0 supported (k=1 is decisive) → report honestly, keep the conservative cutoff, and
  the answer to "why one mode" is: these objects genuinely have one soft mode.
