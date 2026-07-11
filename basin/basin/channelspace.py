"""Per-channel region geometry + the measured vertical (across-channel) trace.

The design goal (the listener's): the trace's degrees of freedom are
region-to-region WITHIN each channel and ACROSS channels. Construction —
the same recipe as the main landscape, once per channel, plus one new
measured object for the vertical dimension:

* per channel k: whiten its own window features (its own view of every
  beat window, computed from its own synthesized audio) → its own charts
  → its own path-state operator (within-track successor pairs of its own
  regions) → its own diffusion directions. "Within channel k" = this
  operator's routing.
* across channels: the CO-OCCURRENCE measure — for each channel pair
  (j, k), the conditional P(region_k | region_j) counted over corpus
  windows. This is the corpus's vertical statement: which bass-regions
  actually sound against which percussion-regions. Counterpoint sampling
  weights a channel's candidate regions by the measured conditionals given
  the other channels' current regions — channels may recombine material
  across tracks exactly as far as the vertical measure licenses.

The mutual information of each pair's co-occurrence (vs its marginals) is
the measured answer to "how much across-channel freedom does the corpus
allow": high MI = tightly scored vertical structure, low MI = channels
nearly free. Nothing hand-set: same config inputs as the main landscape
(pre-trace), everything else counted.
"""

from __future__ import annotations

import numpy as np

from . import operator as op
from .atlas import build_atlas
from .features import _pca_whiten


def build_channel_spaces(chanfeats: dict, corpus, cfg: dict) -> dict:
    """One landscape per channel + pairwise vertical conditionals.

    ``chanfeats``: {'ch0': [n_windows, 156], ...} — per-channel window
    features from the channel's own audio.
    Returns per channel: memberships, labels, P (first order), P2 (path
    state), psi (full, standardized), eigvals; and across channels:
    ``cooc[(j, k)]`` conditional rows P(r_k | r_j), plus ``mi[(j, k)]``.
    """
    n_charts = int(cfg["n_charts"])
    top_k = int(cfg["top_memberships"])
    pca_dims = int(cfg["pca_dims"])
    bounds = corpus.track_bounds

    chans = sorted(chanfeats.keys(), key=lambda s: int(s[2:]))
    spaces = {}
    for ch in chans:
        white, *_ = _pca_whiten(np.asarray(chanfeats[ch], float), pca_dims)
        atlas = build_atlas(white, n_charts, top_k)
        built = op.build(atlas.memberships, bounds, n_basins="auto")
        psi, idx = op.full_psi(built.spectrum.eigvals, built.spectrum.right)
        P2 = op.build_pair_operator(atlas.memberships, bounds)
        spaces[ch] = {
            "memberships": atlas.memberships,
            "labels": np.asarray(atlas.memberships.argmax(axis=1)).ravel(),
            "P": built.P,
            "P2": P2,
            "psi": psi,
            "eig_idx": idx,
            "eigvals": built.spectrum.eigvals,
            "basins": built.chart_basin,
        }

    # vertical trace: pairwise co-occurrence conditionals + their MI
    cooc, mi = {}, {}
    for j in chans:
        for k in chans:
            if j == k:
                continue
            # soft co-occurrence: counted with the memberships themselves —
            # "never argmax-co-seen" is not "impossible" at this sample size,
            # and the soft assignments are already the measured uncertainty
            Mj = np.asarray(spaces[j]["memberships"])
            Mk = np.asarray(spaces[k]["memberships"])
            C = Mj.T @ Mk
            rows = C / np.maximum(C.sum(1, keepdims=True), 1e-12)
            cooc[(j, k)] = rows
            pj = C.sum(1) / C.sum()
            pk = C.sum(0) / C.sum()
            pjk = C / C.sum()
            with np.errstate(divide="ignore", invalid="ignore"):
                lg = np.log(pjk / (pj[:, None] * pk[None, :] + 1e-300)
                            + 1e-300)
            mi[(j, k)] = float((pjk * np.where(pjk > 0, lg, 0.0)).sum())
    return {"spaces": spaces, "cooc": cooc, "mi": mi, "chans": chans}


def vertical_logweight(bundle: dict, ch: str, others: dict) -> np.ndarray:
    """log-weight over channel ``ch``'s regions given the other channels'
    current regions — the measured vertical evidence (sum of pairwise
    conditionals, the corpus's own co-occurrence measure)."""
    n = bundle["spaces"][ch]["P"].shape[0]
    lw = np.zeros(n)
    for oc, r in others.items():
        if oc == ch or r is None:
            continue
        rows = bundle["cooc"].get((oc, ch))
        if rows is not None:
            with np.errstate(divide="ignore"):
                lw += np.where(rows[r] > 0, np.log(rows[r]), -np.inf)
    return lw
