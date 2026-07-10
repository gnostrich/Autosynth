"""Instrument file (de)serialization.

The instrument bundles everything the renderer and panel need: atlas (centers,
memberships), transfer operator P, spectrum + eigenvalue classification,
diffusion coordinates ψ, basins, the fitted kernel, the corpus window handles,
and the feature-whitening transforms (so new vectors can be whitened
identically). Saved as a single ``.npz`` (pickled object arrays for the
non-numeric parts).
"""

from __future__ import annotations

import numpy as np

from .features import Corpus, WindowHandle
from .atlas import Atlas
from .kernel import KernelFit


def save_instrument(path: str, corpus: Corpus, atlas: Atlas, built, kernel,
                    cfg: dict) -> None:
    """Write the built instrument to ``path`` (.npz)."""
    sp = built.spectrum
    classification = [
        {"index": m.index, "value_real": m.value.real, "value_imag": m.value.imag,
         "kind": m.kind, "damping": m.damping, "frequency": m.frequency}
        for m in sp.modes
    ]
    handles = np.array(
        [(h.track_id, h.start_sample, h.n_samples) for h in corpus.handles],
        dtype=np.int64,
    )
    payload = dict(
        # corpus / whitening
        raw=corpus.raw, features=corpus.features, handles=handles,
        track_bounds=np.array(corpus.track_bounds, dtype=np.int64),
        track_paths=np.array(corpus.track_paths, dtype=object),
        mean=corpus.mean, scale=corpus.scale,
        pca_mean=corpus.pca_mean, pca_components=corpus.pca_components,
        head_frames=corpus.head_frames if corpus.head_frames is not None
        else np.zeros((0, 0)),
        mid_frames=corpus.mid_frames if corpus.mid_frames is not None
        else np.zeros((0, 0)),
        nmf_templates=corpus.nmf_templates if corpus.nmf_templates is not None
        else np.zeros((0, 0)),
        n_channels=np.int64(corpus.n_channels),
        chan_rms=corpus.chan_rms if corpus.chan_rms is not None
        else np.zeros((0, 0)),
        # atlas
        centers=atlas.centers, bandwidth=np.float64(atlas.bandwidth),
        memberships=atlas.memberships, top_k=np.int64(atlas.top_k),
        # operator / spectrum
        P=built.P, eigvals=sp.eigvals, eig_right=sp.right,
        classification=np.array(classification, dtype=object),
        macro_indices=np.array(sp.macro_indices, dtype=np.int64),
        gap_flagged=np.bool_(sp.gap_flagged), psi=sp.psi,
        chart_basin=built.chart_basin, n_basins=np.int64(built.n_basins),
        component_coverage=np.float64(built.component_coverage),
        # config
        config=np.array(cfg, dtype=object),
    )
    if kernel is not None:
        payload.update(
            kernel_modes=np.array(kernel.modes, dtype=object),
            kernel_order=np.int64(kernel.order),
            kernel_step_s=np.float64(kernel.step_s),
            kernel_max_lag=np.int64(kernel.max_lag_steps),
            kernel_Kvals=kernel.Kvals,
            kernel_cv_error=np.float64(kernel.cv_error),
            kernel_omega_hz=np.array(kernel.omega_hz, dtype=float),
            kernel_tempo=np.array(kernel.tempo_hz, dtype=object),
            kernel_tempo_check=np.array(kernel.tempo_check, dtype=object),
            kernel_clamped=np.bool_(kernel.clamped),
        )
    np.savez(path, **payload)


def load_instrument(path: str) -> dict:
    """Load an instrument .npz into a dict with reconstructed objects."""
    d = np.load(path, allow_pickle=True)
    out = {k: d[k] for k in d.files}

    handles = [WindowHandle(int(t), int(s), int(n)) for t, s, n in out["handles"]]
    hf = out.get("head_frames")
    mf = out.get("mid_frames")
    nt = out.get("nmf_templates")
    cr = out.get("chan_rms")
    corpus = Corpus(
        raw=out["raw"], features=out["features"], handles=handles,
        track_bounds=[tuple(map(int, b)) for b in out["track_bounds"]],
        track_paths=list(out["track_paths"]),
        mean=out["mean"], scale=out["scale"],
        pca_mean=out["pca_mean"], pca_components=out["pca_components"],
        head_frames=hf if hf is not None and hf.size else None,
        mid_frames=mf if mf is not None and mf.size else None,
        nmf_templates=nt if nt is not None and nt.size else None,
        n_channels=int(out["n_channels"]) if "n_channels" in out else 0,
        chan_rms=cr if cr is not None and cr.size else None,
    )
    atlas = Atlas(centers=out["centers"], bandwidth=float(out["bandwidth"]),
                  memberships=out["memberships"], top_k=int(out["top_k"]))

    kernel = None
    if "kernel_Kvals" in out:
        kernel = KernelFit(
            modes=[list(m) for m in out["kernel_modes"]],
            order=int(out["kernel_order"]), step_s=float(out["kernel_step_s"]),
            max_lag_steps=int(out["kernel_max_lag"]), Kvals=out["kernel_Kvals"],
            cv_error=float(out["kernel_cv_error"]),
            omega_hz=list(out["kernel_omega_hz"]),
            tempo_hz=dict(out["kernel_tempo"].item())
            if out["kernel_tempo"].dtype == object else {},
            tempo_check=list(out["kernel_tempo_check"]),
            clamped=bool(out["kernel_clamped"]),
        )

    out["corpus"] = corpus
    out["atlas"] = atlas
    out["kernel"] = kernel
    out["config"] = out["config"].item()
    out["classification"] = list(out["classification"])
    return out
