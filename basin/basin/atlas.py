"""M1 — charts and soft assignment.

k-means over the whitened window features gives ``k`` chart centers. Each
window is softly assigned to charts by a Gaussian kernel on distance to
centers (bandwidth = median center-to-center distance), keeping the top
``top_memberships`` and renormalizing so each window's memberships sum to 1.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Atlas:
    """Charts + the corpus's soft memberships over them."""

    centers: np.ndarray        # [n_charts, dim]
    bandwidth: float
    memberships: np.ndarray    # [n_windows, n_charts] sparse-in-practice, rows sum 1
    top_k: int

    @property
    def n_charts(self) -> int:
        return self.centers.shape[0]


def _soft_assign(x: np.ndarray, centers: np.ndarray, bandwidth: float,
                 top_k: int) -> np.ndarray:
    """Gaussian soft assignment of rows of ``x`` to ``centers``.

    Returns ``[n, n_charts]`` with each row keeping its ``top_k`` largest
    memberships (rest zeroed) and renormalized to sum 1.
    """
    # squared distances [n, k]
    d2 = (
        (x ** 2).sum(1)[:, None]
        - 2.0 * x @ centers.T
        + (centers ** 2).sum(1)[None, :]
    )
    d2 = np.maximum(d2, 0.0)
    w = np.exp(-d2 / (2.0 * bandwidth ** 2 + 1e-12))

    k = min(top_k, centers.shape[0])
    # zero all but the top-k per row
    keep = np.argpartition(-w, k - 1, axis=1)[:, :k]
    mask = np.zeros_like(w, dtype=bool)
    np.put_along_axis(mask, keep, True, axis=1)
    w = np.where(mask, w, 0.0)

    rowsum = w.sum(1, keepdims=True)
    rowsum[rowsum < 1e-12] = 1.0
    return w / rowsum


def build_atlas(features: np.ndarray, n_charts: int, top_k: int,
                seed: int = 0) -> Atlas:
    """Fit k-means charts and soft-assign the corpus.

    ``n_charts`` is capped so charts keep the spec's ~8-windows-per-chart
    minimum (see DECISIONS).
    """
    from sklearn.cluster import KMeans

    n = features.shape[0]
    k = int(min(n_charts, max(1, n // 8)))
    km = KMeans(n_clusters=k, random_state=seed, n_init=10)
    km.fit(features)
    centers = km.cluster_centers_

    # bandwidth = median center-to-center distance
    if k > 1:
        cc = np.sqrt(
            ((centers[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
        )
        iu = np.triu_indices(k, k=1)
        bandwidth = float(np.median(cc[iu]))
    else:
        bandwidth = 1.0
    bandwidth = max(bandwidth, 1e-6)

    memberships = _soft_assign(features, centers, bandwidth, top_k)
    return Atlas(centers=centers, bandwidth=bandwidth,
                 memberships=memberships, top_k=top_k)


def assign_vector(atlas: Atlas, x: np.ndarray) -> np.ndarray:
    """Soft-assign a single whitened window vector to the atlas charts."""
    return _soft_assign(x[None, :], atlas.centers, atlas.bandwidth,
                        atlas.top_k)[0]
