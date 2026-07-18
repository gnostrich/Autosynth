# FINDING — paper-vs-impl divergence: covariance-on-ensemble (E1) vs finite-difference response kernel

**Standing-law disclosure.** E1 (the eigenpanel directive) specified the object's control
basis as the **covariance on the sampling ensemble**. The implementation instead uses a
**per-lever finite-difference response kernel** (`compute_eigenmodes`). Per the operator's
instruction I implemented the E1-literal covariance read (`eigen_experimental.covariance_read`),
ran it head-to-head against the FD baseline, and log the divergence here. Sampler / F /
world untouched; both reads are read-only measurement.

## Measured (demo world, M=2 direction-lanes + density/cont/novelty, full 24×32 ensemble)

| read | k | spectrum \|λ\| | floor |
|------|---|----------------|-------|
| **FD response kernel** (impl) | **2** | 5.72, 2.45, 1.16, 0.17, … | 1.88 |
| **covariance on ensemble** (E1) | **1** | 1.88, 1.57, 1.00, 0.79, 0 | 1.58 |

They **diverge**: the FD response resolves **k=2**; the raw joint-fluctuation covariance
resolves **k=1**. The covariance spectrum is markedly **flatter** (1.88 / 1.57 / 1.00 vs the
response's 5.72 / 2.45 / 1.16) — the object's *free wobble at u=0* is more isotropic than its
*response to the controls*.

## Two things worth recording

1. **The originally-documented reason (P5 continuity variance) is NOT the operative one under
   σ-whitening.** The impl's header says a plain covariance would be "fooled by continuity's
   large marginal variance." But once the covariance is σ-whitened (divided by each
   observable's own σ_φ, scale-consistent with the response kernel's `R/σ`), no single
   observable dominates — the whitened marginals are all ~0.7–1.5 and the top covariance mode
   here is **region1**, not continuity. So σ-whitening already neutralizes the P5 trap; that
   is not what drives the divergence.

2. **The operative reason is that FDT is not tight for this sampler.** Theorem A's identity is
   `d⟨Φ⟩/du = (1/ε)·Cov|_PROJECTED` — the **projected** covariance. The raw ensemble covariance
   is *not* the projected one: the free fluctuation at u=0 is flatter than the response, so
   reading modes from it **under-counts** — it loses the demo's genuine 2nd steerable mode
   (k 2→1). The FD response kernel realizes the projection operationally (it measures the
   response directly); the literal "covariance on the ensemble" does not.

## Verdict (for the operator's call)

- **Re-reported k from the joint read:** demo **k_cov = 1** (vs FD k=2). It should **not** be
  adopted as the panel's k — it drops a real, steerable mode.
- **The impl's divergence from E1's wording is CORRECT and should stay.** Recommend amending
  E1's text from "covariance on the sampling ensemble" to **"the *projected* conjugate
  covariance (Theorem A), realized operationally as the symmetrized finite-difference response
  kernel"** — which is what the code already does.
- **Open thread for the finite-T prereg:** the gap between free-fluctuation and response is
  itself a measurement of how far this (near-greedy, entropic-OT) sampler sits from a true
  Gibbs ensemble. The temperature sweep (PREREG-temperature-sweep.md) is the right instrument
  to characterize that gap — if at some T_s the free covariance *does* reproduce the response
  spectrum, that is the temperature at which the sampler is genuinely thermal.

## Repro
`covariance_read` and `diagnose` in `cloud/companion/eigen_experimental.py`; run both on
`demo.etsworld` at n_seed=24/n_bar=32. Trained-set numbers can be taken via the key-gated
`/api/admin/eigen_spectrum` endpoint once `covariance_read` is wired into it (follow-up).
