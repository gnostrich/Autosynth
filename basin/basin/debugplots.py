"""M1 acceptance plots: terrain (charts in ψ-space) and spectrum (|λ| + cut)."""

from __future__ import annotations

import numpy as np


def terrain(psi: np.ndarray, chart_basin: np.ndarray, memberships: np.ndarray,
            track_bounds: list, out_path: str, n_sample_tracks: int = 3) -> None:
    """Scatter charts in (ψ1, ψ2) colored by basin; overdraw sample track paths.

    PASS = the overdrawn paths are visibly smooth curves in coherent regions.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if psi.shape[1] < 2:
        # not enough macros for a 2-D terrain; make a 1-D strip instead
        x = psi[:, 0] if psi.shape[1] else np.zeros(psi.shape[0])
        y = np.zeros_like(x)
    else:
        x, y = psi[:, 0], psi[:, 1]

    fig, ax = plt.subplots(figsize=(8, 7))
    ax.scatter(x, y, c=chart_basin, cmap="tab10", s=40, alpha=0.7,
               edgecolors="none")

    # window macro coords for sample-track paths
    win_psi = memberships @ psi                      # [n_windows, n_macros]
    wx = win_psi[:, 0]
    wy = win_psi[:, 1] if psi.shape[1] >= 2 else np.zeros_like(wx)
    step = max(1, len(track_bounds) // n_sample_tracks)
    for (s, e) in track_bounds[::step][:n_sample_tracks]:
        ax.plot(wx[s:e], wy[s:e], "-", lw=1.6, alpha=0.9)
        ax.plot(wx[s], wy[s], "ko", ms=5)

    ax.set_xlabel("ψ1")
    ax.set_ylabel("ψ2")
    ax.set_title("Terrain — charts by basin, 3 sample tracks overdrawn")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def spectrum(eigvals: np.ndarray, macro_indices: list, out_path: str) -> None:
    """Sorted |λ| with the chosen macro cut marked."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    mags = np.abs(eigvals)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(range(len(mags)), mags, "o-", ms=4)
    if macro_indices:
        cut = max(macro_indices) + 1
        ax.axvline(cut - 0.5, color="crimson", ls="--",
                   label=f"macro cut ({len(macro_indices)} macros)")
        ax.legend()
    ax.set_xlabel("eigenvalue index (|λ| desc)")
    ax.set_ylabel("|λ|")
    ax.set_title("Spectrum — |λ| with macro cut")
    ax.set_xlim(-0.5, min(len(mags), 40))
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
