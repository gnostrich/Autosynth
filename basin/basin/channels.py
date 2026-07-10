"""Emergent channel decomposition — NMF spectrogram factorization.

The corpus is asked what sound-shapes it reuses: magnitude spectrograms are
factorized as ``|S| ≈ A·W`` with corpus-global spectral templates ``W``
(K × freq) and per-track activations ``A`` (frames × K). Both the templates
*and the channel count K* are measured, not chosen:

* K comes from held-out reconstruction error over candidate ranks — we keep
  adding channels while each one still explains ≥ ``GAIN_MIN`` of the
  remaining error, and flag honestly if no clear elbow appears.
* Channel audio is synthesized by Wiener soft-masking: channel k's mask is
  its share of the reconstruction, applied to the complex STFT.

Classical linear algebra only (multiplicative updates / sklearn NMF) — no
neural networks, per the spec.
"""

from __future__ import annotations

import numpy as np

N_FFT = 2048
GAIN_MIN = 0.08          # a channel must explain ≥8% of remaining error
CANDIDATE_KS = (2, 3, 4, 5, 6, 8)


def _stft_mag(y: np.ndarray, hop: int) -> np.ndarray:
    import librosa
    return np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=hop)).astype(
        np.float32)


def activations(M_t: np.ndarray, W: np.ndarray, n_iter: int = 60) -> np.ndarray:
    """Non-negative activations A ≥ 0 minimizing ||M − A·W||_F, W fixed.

    ``M_t`` [frames, freq], ``W`` [K, freq] → A [frames, K].
    Standard multiplicative updates; deterministic.
    """
    K = W.shape[0]
    A = np.full((M_t.shape[0], K), M_t.mean() / max(K, 1) + 1e-6,
                dtype=np.float32)
    WWt = (W @ W.T).astype(np.float32)
    MWt = (M_t @ W.T).astype(np.float32)
    for _ in range(n_iter):
        A *= MWt / (A @ WWt + 1e-9)
    return A


def _sample_frames(paths, sr, hop, seed=0, per_track_s=60, per_track_frames=400):
    import librosa
    rng = np.random.default_rng(seed)
    cols = []
    step = max(1, len(paths) // 8)
    for p in paths[::step][:8]:
        y, _ = librosa.load(p, sr=sr, mono=True, duration=per_track_s)
        S = _stft_mag(y, hop)
        if S.shape[1] < 8:
            continue
        idx = rng.choice(S.shape[1], size=min(per_track_frames, S.shape[1]),
                         replace=False)
        cols.append(S[:, idx])
    return np.concatenate(cols, axis=1).T          # [frames, freq]


def choose_rank(paths, sr, hop, seed=0, candidates=CANDIDATE_KS, log=None):
    """Measured channel count: held-out reconstruction-error elbow.

    Returns ``(K, flagged, errs)`` — flagged=True when improvements never
    dropped below GAIN_MIN (no clear elbow; K capped at the largest
    candidate) or the corpus is too small to test.
    """
    from sklearn.decomposition import NMF
    X = _sample_frames(paths, sr, hop, seed=seed)
    n = X.shape[0]
    if n < 64:
        return candidates[0], True, {}
    rng = np.random.default_rng(seed)
    perm = rng.permutation(n)
    tr, te = X[perm[: n // 2]], X[perm[n // 2:]]
    te_norm = np.linalg.norm(te) + 1e-9

    errs = {}
    for K in candidates:
        m = NMF(n_components=K, init="nndsvda", max_iter=200,
                random_state=seed, tol=1e-3)
        m.fit(tr)
        A = activations(te, m.components_)
        errs[K] = float(np.linalg.norm(te - A @ m.components_) / te_norm)
        if log:
            log(f"      K={K}: held-out err {errs[K]:.4f}")

    ks = list(candidates)
    chosen, flagged = ks[0], True
    for i in range(1, len(ks)):
        gain = (errs[ks[i - 1]] - errs[ks[i]]) / max(errs[ks[i - 1]], 1e-9)
        if gain >= GAIN_MIN:
            chosen = ks[i]
        else:
            flagged = False           # a clear elbow: improvements dried up
            break
    return chosen, flagged, errs


def fit_templates(paths, sr, hop, K, seed=0, frame_stride=2):
    """Fit corpus-global spectral templates W [K, freq] (sklearn NMF)."""
    import librosa
    from sklearn.decomposition import NMF
    cols = []
    for p in paths:
        y, _ = librosa.load(p, sr=sr, mono=True)
        cols.append(_stft_mag(y, hop)[:, ::frame_stride])
    X = np.concatenate(cols, axis=1).T             # [frames, freq]
    m = NMF(n_components=K, init="nndsvda", max_iter=250, random_state=seed,
            tol=1e-3)
    m.fit(X)
    W = m.components_.astype(np.float32)
    # order channels by energy share (emergent ordering, like |lambda|)
    A = activations(X[:: max(1, X.shape[0] // 4000)], W)
    order = np.argsort(-(A.sum(0) * W.sum(1)))
    return W[order]


def track_activations(y, W, hop):
    """Per-frame channel activations for one track: [K, frames]."""
    M = _stft_mag(y, hop)
    return activations(M.T, W).T


def split_track(y, W, hop: int = 512):
    """Synthesize each channel's audio for a track via Wiener soft-masks.

    ``y`` may be mono (n,) or stereo (2, n); masks are estimated on the mono
    fold and applied per side. Returns a list of K arrays shaped like ``y``
    (stereo in → stereo channels out).
    """
    import librosa
    y = np.asarray(y)
    stereo = y.ndim == 2
    sides = y if stereo else y[None, :]
    n = sides.shape[1]
    mono = sides.mean(0)
    Sm = librosa.stft(mono, n_fft=N_FFT, hop_length=hop)
    A = activations(np.abs(Sm).astype(np.float32).T, W)   # [frames, K]
    recon = (A @ W).T + 1e-9                              # [freq, frames]
    Ss = [librosa.stft(sides[c], n_fft=N_FFT, hop_length=hop)
          for c in range(sides.shape[0])]
    outs = []
    for k in range(W.shape[0]):
        mask = (W[k][:, None] * A[:, k][None, :]) / recon
        yk = np.stack([librosa.istft(S * mask, hop_length=hop, length=n)
                       for S in Ss])
        outs.append((yk if stereo else yk[0]).astype(np.float32))
    return outs
