"""Conflation-regression analysis (directive amendment
stage1-delete-conflated-jack, registered one-shot; ANALYSIS ONLY — reads
the Stage-0 shadow traces produced by analysis/run_conflation_traces.py,
touches no engine code).

QUESTION. Per gauge component g in {key, phase}: is the OLD conflated
drift value (drift_cv running winding, per bar) explainable by the NEW
pair (slide[g], loop[g])? Fit

    conflated[t] ~ a * slide[t] + b * loop[t] + c            (LINEAR)

per run and pooled, plus an augmented model with interaction and
quadratic columns (slide*loop, slide^2, loop^2) to report whether a
nonlinear residual improves the fit materially. Every bar whose
|residual| exceeds the derived threshold is flagged with its timestamp
(bar_index * bar_seconds) and run.

THRESHOLD DERIVATION (no hand constant beyond the declared family test
size). Null: the residuals r_1..r_T are iid N(0, sigma^2) — the "nothing
hidden" hypothesis; a bar where the conflated jack saw something the
pair misses is precisely a bar that violates this null. Two-sided
Bonferroni rule at family level alpha over the T pooled bars:

    flag bar t  iff  |r_t| > sigma_hat * k,   k = Phi^{-1}(1 - alpha/(2T))

This controls P(any false flag) <= alpha exactly under the null, and k
is DERIVED from the trace length (k ~ sqrt(2 ln T); the standard
max-of-T-Gaussians outlier rule). alpha = 0.05 is the single declared
conventional constant (family-level test size). sigma_hat is the
Gaussian-consistent robust scale sigma_hat = MAD / Phi^{-1}(3/4)
(= 1.4826 * MAD) — robust to the very outliers being hunted (50%
breakdown), so a hidden bar cannot inflate its own threshold.

DEGENERATE BRANCH (exact-constancy discipline, per registry entry
sigma-phi-untilted-fix1-2026-07-15): if the residuals are EXACTLY
constant 0.0 the null scale is 0 by definition — no floor is invented;
the rule reduces to flagging any residual != 0.0 exactly, and the
verdict "exact at machine precision" is reported plainly. R^2 is
reported as null (undefined) when Var(conflated) == 0 exactly — never
fabricated as 1.0.

STRUCTURAL CHECK (stronger than the fit, reported alongside): the
conflated KEY running value is analytically an EXACT trajectory
functional of the slide_key per-bar signal alone —

    conflated_key[t] = sum_{tau<=t} wrap_12(slide_key[tau] - slide_key[tau-1])

(wrap_12 = minimal signed representative in [-6,6)); both sides compose
the same connection 1-form, slide merely quotients the winding by Z_12,
and since per-bar increments are themselves minimal representatives the
winding unwraps exactly. This identity is VERIFIED empirically on every
trace. No analogous inverse exists for phase (the slide phase CHARGE is
a many-to-one |.| reduction: it discards the SIGN and the whole-circle
winding of the phase displacement) — so the phase conclusion rests on
the fit + the domain evidence, and any shortfall must be surfaced, not
smoothed.

Usage:  python3 analysis/conflation_regression.py
Output: analysis/conflation_regression.json
"""
from __future__ import annotations
import glob
import json
import os

import numpy as np
from scipy.stats import norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE_DIR = os.path.join(ROOT, "analysis", "traces")
OUT_PATH = os.path.join(ROOT, "analysis", "conflation_regression.json")

ALPHA = 0.05          # declared family-level test size (the one convention)
COMPONENTS = {
    "key": ("conflated_drift_key_running", "slide_key_disp"),
    "phase": ("conflated_drift_phase_running", "slide_phase_charge"),
}


def _wrap(x, modulus=12.0):
    m = float(modulus)
    return (np.asarray(x, float) + m / 2.0) % m - m / 2.0


def load_runs():
    runs = []
    for p in sorted(glob.glob(os.path.join(TRACE_DIR, "*.gauge_trace.json"))):
        with open(p) as f:
            d = json.load(f)
        runs.append((os.path.basename(p), d["run"], d["trace"]))
    if not runs:
        raise SystemExit(f"no traces under {TRACE_DIR} "
                         "(run analysis/run_conflation_traces.py first)")
    return runs


def ols(y, cols):
    """Least squares y ~ cols (list of 1-D arrays) + intercept. Returns
    (beta, residuals, ssr, r2_or_None). Minimal-norm solution via lstsq;
    on an exactly-zero y this yields beta = 0 and residuals exactly 0.0."""
    X = np.column_stack(cols + [np.ones(len(y))])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    r = y - X @ beta
    ssr = float(r @ r)
    sst = float(np.sum((y - y.mean()) ** 2))
    r2 = None if sst == 0.0 else 1.0 - ssr / sst
    return beta, r, ssr, r2


def analyze_component(comp, runs):
    conf_key, slide_key = COMPONENTS[comp]
    y_all, s_all, l_all, tags = [], [], [], []
    per_run = {}
    for fname, meta, trace in runs:
        pb = trace["per_bar"]
        y = np.asarray(pb[conf_key], float)
        s = np.asarray(pb[slide_key], float)
        l = np.asarray(pb["loop_g"], float)
        beta, r, ssr, r2 = ols(y, [s, l])
        per_run[meta["config"]] = {
            "n_bars": len(y),
            "a_slide": float(beta[0]), "b_loop": float(beta[1]),
            "c_intercept": float(beta[2]),
            "R2": r2, "R2_note": None if r2 is not None else
                "undefined: Var(conflated) == 0 exactly on this run",
            "ssr": ssr, "max_abs_residual": float(np.max(np.abs(r))) if len(r) else 0.0,
            "conflated_exactly_zero": bool(np.all(y == 0.0)),
            "max_abs": {"conflated": float(np.max(np.abs(y))) if len(y) else 0.0,
                        "slide": float(np.max(np.abs(s))) if len(s) else 0.0,
                        "loop": float(np.max(np.abs(l))) if len(l) else 0.0},
        }
        y_all.append(y); s_all.append(s); l_all.append(l)
        tags += [(meta["config"], i, float(meta["bar_seconds"])) for i in range(len(y))]

    y = np.concatenate(y_all); s = np.concatenate(s_all); l = np.concatenate(l_all)
    T = len(y)

    # pooled linear fit
    beta, r, ssr, r2 = ols(y, [s, l])
    # augmented (interaction + quadratic) fit
    beta_a, r_a, ssr_a, r2_a = ols(y, [s, l, s * l, s * s, l * l])
    material = None
    if ssr > 0:
        material = bool((ssr - ssr_a) / ssr > 0.01)   # >1% SSR reduction

    # threshold: sigma_hat = MAD / Phi^{-1}(3/4); k = Phi^{-1}(1 - alpha/(2T))
    mad = float(np.median(np.abs(r - np.median(r))))
    exact_const = bool(np.all(r == r[0])) if T else True
    sigma_hat = 0.0 if (exact_const and (T == 0 or r[0] == 0.0)) \
        else mad / norm.ppf(0.75)
    k = float(norm.ppf(1.0 - ALPHA / (2.0 * max(T, 1))))
    thr = k * sigma_hat
    flagged_idx = np.where(np.abs(r) > thr)[0] if thr > 0.0 \
        else np.where(r != 0.0)[0]
    flagged = [{
        "run": tags[i][0], "bar_index": int(tags[i][1]),
        "t_seconds": float(tags[i][1] * tags[i][2]),
        "conflated": float(y[i]), "slide": float(s[i]), "loop": float(l[i]),
        "residual": float(r[i]),
    } for i in flagged_idx]

    return {
        "component": comp,
        "n_bars_pooled": T,
        "pooled_fit": {
            "a_slide": float(beta[0]), "b_loop": float(beta[1]),
            "c_intercept": float(beta[2]), "R2": r2,
            "R2_note": None if r2 is not None else
                "undefined: Var(conflated) == 0 exactly over all pooled bars "
                "(never fabricated as 1.0)",
            "ssr": ssr,
        },
        "augmented_fit": {
            "columns": ["slide", "loop", "slide*loop", "slide^2", "loop^2"],
            "ssr": ssr_a, "R2": r2_a,
            "materially_better": material,
            "note": None if material is not None else
                "no improvement possible: linear SSR is already exactly 0",
        },
        "residuals": {
            "max_abs": float(np.max(np.abs(r))) if T else 0.0,
            "mean": float(np.mean(r)) if T else 0.0,
            "std": float(np.std(r)) if T else 0.0,
            "MAD": mad,
            "n_exactly_zero": int(np.sum(r == 0.0)),
            "exact_at_machine_precision": bool(np.all(r == 0.0)),
        },
        "threshold": {
            "rule": "flag |r| > sigma_hat * k; sigma_hat = MAD/Phi^{-1}(3/4) "
                    "(Gaussian-consistent, 50% breakdown); "
                    "k = Phi^{-1}(1 - alpha/(2T)) (two-sided Bonferroni over "
                    "the T pooled bars, family-wise error <= alpha under the "
                    "iid-Gaussian residual null)",
            "alpha": ALPHA, "T": T, "k": k, "sigma_hat": float(sigma_hat),
            "threshold": float(thr),
            "degenerate_branch": bool(thr == 0.0),
            "degenerate_note": None if thr > 0.0 else
                "residuals exactly constant 0.0 -> null scale 0 by definition "
                "(exact-constancy discipline, sigma-phi-untilted-fix1): any "
                "residual != 0.0 exactly would flag",
        },
        "flagged_bars": flagged,
        "per_run": per_run,
    }


def key_reconstruction_check(runs):
    """Verify the analytic identity: conflated_key_running[t] ==
    sum_{tau<=t} wrap_12(slide_key[tau] - slide_key[tau-1]), exactly."""
    worst = 0.0
    for fname, meta, trace in runs:
        pb = trace["per_bar"]
        ck = np.asarray(pb["conflated_drift_key_running"], float)
        sk = np.asarray(pb["slide_key_disp"], float)
        if len(sk) == 0:
            continue
        rec = np.concatenate([[sk[0]], np.cumsum(_wrap(np.diff(sk)))])
        worst = max(worst, float(np.max(np.abs(rec - ck))))
    return worst


def main():
    runs = load_runs()
    result = {
        "analysis": "conflation regression: conflated ~ a*slide + b*loop + c "
                    "per gauge component",
        "directive": "stage1-delete-conflated-jack (registered one-shot; "
                     "replaces the deprecation window's observational purpose)",
        "traces": {meta["config"]: {
            "file": fname, "n_bars": trace["n_bars"],
            "bar_seconds": meta["bar_seconds"],
            "clamp_summary": meta["clamp_summary"],
            "F_monotone": meta["F_monotone"], "F_converged": meta["F_converged"],
            "render_run": meta["render_run"],
        } for fname, meta, trace in runs},
        "components": {c: analyze_component(c, runs) for c in COMPONENTS},
        "structural_check": {
            "claim": "conflated_key_running is an EXACT trajectory functional "
                     "of the slide_key per-bar signal alone (winding unwraps "
                     "exactly because per-bar increments are minimal signed "
                     "representatives in [-6,6))",
            "max_abs_reconstruction_error": key_reconstruction_check(runs),
            "phase_caveat": "no analogous inverse exists for phase: the slide "
                            "phase CHARGE is a many-to-one |.| reduction "
                            "(discards sign and whole-circle winding of the "
                            "displacement); the phase conclusion rests on the "
                            "fit + the producible-domain evidence only",
        },
    }
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=1)
    print(json.dumps({k: v for k, v in result.items() if k != "traces"},
                     indent=1)[:4000])
    print(f"\nwritten -> {OUT_PATH}")


if __name__ == "__main__":
    main()
