"""M1 — transfer operator, spectrum, diffusion coordinates, basins.

Build the row-stochastic transfer operator ``P`` from consecutive
within-track window pairs, eigendecompose it, classify the eigenvalues into
control-topology types (linear / oscillatory / alternation), cut the macro
coordinates at the first clear spectral gap, form diffusion coordinates, and
cluster charts into basins.

``P`` classification drives the M4 panel topology, so it is stored verbatim
in the instrument file.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.linalg


@dataclass
class EigMode:
    """One eigenvalue of ``P`` and its control-topology classification."""

    index: int
    value: complex
    kind: str          # 'linear' | 'oscillatory' | 'alternation'
    damping: float     # |lambda|
    frequency: float   # arg(lambda), radians/step (0 for real modes)


@dataclass
class Spectrum:
    """Eigendecomposition of ``P`` plus the derived macro structure."""

    eigvals: np.ndarray          # [k] complex, sorted by |lambda| desc
    right: np.ndarray            # [k, k] right eigenvectors (columns)
    modes: list                  # [k] of EigMode
    macro_indices: list          # eigenindices chosen as macros
    gap_flagged: bool            # True if no clear gap found (took default 4)
    psi: np.ndarray              # [n_charts, n_macros] diffusion coords (charts)


@dataclass
class BuiltOperator:
    P: np.ndarray                # [k, k] row-stochastic
    spectrum: Spectrum
    chart_basin: np.ndarray      # [n_charts] basin id per chart
    n_basins: int
    largest_component: np.ndarray  # bool [n_charts] charts in giant SCC
    component_coverage: float      # fraction of windows on that component


# ---------------------------------------------------------------------------
# Transfer operator
# ---------------------------------------------------------------------------

def build_operator(memberships: np.ndarray, track_bounds: list) -> np.ndarray:
    """Row-stochastic ``P[a,b]`` from consecutive within-track window pairs.

    ``P[a,b] = sum_{(t,t+1) within a track} m_t(a) * m_{t+1}(b)``, row-normalized.
    Consecutive pairs never cross a track boundary.
    """
    k = memberships.shape[1]
    P = np.zeros((k, k))
    for start, end in track_bounds:
        if end - start < 2:
            continue
        m = memberships[start:end]              # [T, k]
        # sum of outer products m_t (x) m_{t+1}
        P += m[:-1].T @ m[1:]
    rowsum = P.sum(1, keepdims=True)
    dangling = (rowsum[:, 0] < 1e-12)
    rowsum[dangling, 0] = 1.0                   # leave dangling rows at zero
    return P / rowsum


# ---------------------------------------------------------------------------
# Spectrum + classification
# ---------------------------------------------------------------------------

def _classify(lam: complex, tol_real: float = 1e-6) -> str:
    """Classify one eigenvalue into a control-topology kind."""
    if abs(lam.imag) > tol_real and abs(lam.imag) > 1e-3 * abs(lam):
        return "oscillatory"          # complex pair → phase dial + depth
    if lam.real < -tol_real:
        return "alternation"          # real negative → toggle
    return "linear"                   # real +, macro candidate → bounded knob


def _detect_gap(mags: np.ndarray, lo: int = 3, hi: int = 6):
    """Pick the macro count from the largest relative gap in |lambda|.

    ``mags`` is sorted descending and excludes the trivial stationary
    eigenvalue at index 0. Returns ``(n_macros, flagged)`` where *flagged* is
    True when no clear gap was found and the default of 4 was taken.

    DECISIONS [gap detection heuristic]: within the [lo, hi] macro-count band,
    take the count just above the largest relative drop ``m[i]/m[i+1]``. If the
    biggest drop is not meaningfully larger than the median drop (ratio < 1.3),
    declare no clear gap and default to 4 (clamped to what's available).
    """
    avail = len(mags)
    hi = min(hi, avail)
    if avail <= lo:
        return max(1, avail), True
    # relative drops between successive magnitudes
    ratios = mags[:-1] / np.maximum(mags[1:], 1e-12)
    band = ratios[lo - 1:hi]                    # candidate cut positions
    if band.size == 0:
        return min(4, avail), True
    best = int(np.argmax(band)) + lo            # count above the largest drop
    med = np.median(ratios[ratios > 0]) if np.any(ratios > 0) else 1.0
    clear = band.max() >= 1.3 * med
    if clear:
        return best, False
    return min(4, avail), True


def eigendecompose(P: np.ndarray) -> Spectrum:
    """Eigendecompose ``P`` (non-symmetric), classify, cut macros, build psi."""
    vals, vecs = scipy.linalg.eig(P)            # right eigenvectors (columns)
    order = np.argsort(-np.abs(vals))
    vals, vecs = vals[order], vecs[:, order]

    modes = [
        EigMode(index=i, value=complex(v), kind=_classify(complex(v)),
                damping=float(abs(v)), frequency=float(np.angle(v)))
        for i, v in enumerate(vals)
    ]

    # macro candidates: real, near +1 (linear kind), excluding the stationary
    # mode at index 0 (|lambda| ~ 1, the constant right-eigenvector).
    linear_idx = [m.index for m in modes[1:] if m.kind == "linear"]
    mags = np.abs(vals[linear_idx]) if linear_idx else np.array([])
    n_macros, flagged = _detect_gap(mags)
    macro_indices = linear_idx[:n_macros] if linear_idx else []

    # diffusion coords for charts: psi_i(chart) = lambda_i^t * right_vec_i, t=1.
    # take real parts (macros are real modes). scipy unit-normalizes each
    # eigenvector, so raw psi has scale ~1/sqrt(n_charts); we standardize each
    # macro column to zero-mean/unit-std across charts so that a knob expressed
    # in σ units produces an O(1) bias tilt (see DECISIONS: psi normalization).
    if macro_indices:
        psi = np.real(vecs[:, macro_indices] * vals[macro_indices][None, :])
        psi = psi - psi.mean(0, keepdims=True)
        std = psi.std(0, keepdims=True)
        std[std < 1e-12] = 1.0
        psi = psi / std
    else:
        psi = np.zeros((P.shape[0], 0))

    return Spectrum(eigvals=vals, right=vecs, modes=modes,
                    macro_indices=list(macro_indices), gap_flagged=flagged,
                    psi=psi)


# ---------------------------------------------------------------------------
# Connectivity + basins
# ---------------------------------------------------------------------------

def build_pair_operator(memberships: np.ndarray, track_bounds: list) -> dict:
    """Second-order trace: measured routing over PATH states (c_prev, c_cur).

    The corpus's dynamics is not Markov at chart resolution — projecting it
    onto single-chart states is what forces separate compensation parts
    (memory kernel, momentum flywheel) into the walk. Give the state one
    step of path instead and those parts fold into the measured operator:
    direction persistence, phrase cycles and dwell/leave statistics are all
    properties of the corpus's own path segments. Built from consecutive
    within-track window triples (same data as ``build_operator``, one order
    higher); rows are normalized over successor charts. States never seen in
    the corpus simply don't exist — callers fall back to the first-order row.
    """
    wb = np.asarray(np.argmax(memberships, axis=1)).ravel()
    counts: dict = {}
    for (s, e) in track_bounds:
        for i in range(s + 1, e - 1):
            key = (int(wb[i - 1]), int(wb[i]))
            row = counts.setdefault(key, {})
            nxt = int(wb[i + 1])
            row[nxt] = row.get(nxt, 0) + 1
    n_charts = memberships.shape[1]
    P2 = {}
    for key, row in counts.items():
        v = np.zeros(n_charts)
        for nxt, c in row.items():
            v[nxt] = c
        P2[key] = v / v.sum()
    return P2


def largest_component(P: np.ndarray, memberships: np.ndarray):
    """Largest strongly-connected component of ``P`` and its window coverage."""
    from scipy.sparse.csgraph import connected_components
    from scipy.sparse import csr_matrix

    adj = csr_matrix((P > 1e-9).astype(int))
    n_comp, labels = connected_components(adj, directed=True, connection="strong")
    # pick the component holding the most window-mass
    chart_mass = memberships.sum(0)             # [n_charts]
    best, best_mass = 0, -1.0
    for c in range(n_comp):
        mass = chart_mass[labels == c].sum()
        if mass > best_mass:
            best, best_mass = c, mass
    in_comp = labels == best
    coverage = float(chart_mass[in_comp].sum() / max(chart_mass.sum(), 1e-12))
    return in_comp, coverage


def cluster_basins(psi: np.ndarray, lo: int = 4, hi: int = 10, seed: int = 0):
    """Spectral-clustering of charts in the top-eigenvector embedding.

    Chooses ``n_basins in [lo, hi]`` by silhouette score. Falls back to a
    single basin if the embedding is degenerate (< lo charts / zero macros).
    """
    from sklearn.cluster import SpectralClustering
    from sklearn.metrics import silhouette_score

    n = psi.shape[0]
    if psi.shape[1] == 0 or n < lo + 1:
        return np.zeros(n, dtype=int), 1

    best_labels, best_k, best_score = None, lo, -np.inf
    for k in range(lo, min(hi, n - 1) + 1):
        try:
            sc = SpectralClustering(n_clusters=k, affinity="nearest_neighbors",
                                    n_neighbors=min(10, n - 1),
                                    random_state=seed, assign_labels="kmeans")
            labels = sc.fit_predict(psi)
        except Exception:
            continue
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(psi, labels)
        if score > best_score:
            best_labels, best_k, best_score = labels, k, score

    if best_labels is None:
        return np.zeros(n, dtype=int), 1
    return best_labels, best_k


def build(memberships: np.ndarray, track_bounds: list,
          n_basins="auto", seed: int = 0) -> BuiltOperator:
    """Full M1 operator stage: P, spectrum, connectivity, basins."""
    P = build_operator(memberships, track_bounds)
    spectrum = eigendecompose(P)
    in_comp, coverage = largest_component(P, memberships)
    if n_basins == "auto":
        chart_basin, nb = cluster_basins(spectrum.psi)
    else:
        chart_basin, nb = cluster_basins(spectrum.psi, lo=int(n_basins),
                                         hi=int(n_basins))
    return BuiltOperator(P=P, spectrum=spectrum, chart_basin=chart_basin,
                         n_basins=nb, largest_component=in_comp,
                         component_coverage=coverage)
