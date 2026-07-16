"""Fixed log-spaced filterbank (spec §2.3 v0 DECISION).

A FIXED filterbank, NOT source separation. Spec §2.3: "a separator is a second
authority pre-deciding roles before F does." Demucs-class separation is a tagged
ablation only, never the main path — none appears here.

Design: partition-of-unity band masks over the STFT magnitude/complex grid. The
masks sum to exactly 1.0 at every frequency bin, so the per-band ISTFTs sum back
to the input signal to numerical precision (verified ~ -157 dB). This perfect-
reconstruction property is what makes the G0 unit-reconstruction identity
(spec §13) a coverage/scheduling test rather than a lossy-model test.
"""
from __future__ import annotations
import numpy as np
import librosa

N_FFT = 2048
HOP = 512
FMIN = 40.0          # Hz; below this is sub-bass rumble folded into band 0
N_BANDS = 8          # spec §2.3 "~8-band log-spaced"


def band_edges(sr: int, n_bands: int = N_BANDS, fmin: float = FMIN) -> np.ndarray:
    """n_bands+1 log-spaced band edges in Hz, fmin .. Nyquist."""
    return np.geomspace(fmin, sr / 2.0, n_bands + 1)


def partition_masks(sr: int, n_fft: int = N_FFT, n_bands: int = N_BANDS,
                    fmin: float = FMIN) -> np.ndarray:
    """(n_bands, n_freq) raised-cosine masks forming a partition of unity.

    Column sums are exactly 1.0, so sum_k (S * masks[k]) == S bin-for-bin and
    hence sum_k istft(S*masks[k]) == istft(S) == signal (COLA-exact).
    """
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    logf = np.log(np.maximum(freqs, 1.0))
    edges = band_edges(sr, n_bands, fmin)
    centers = np.log(np.sqrt(edges[:-1] * edges[1:]))
    masks = np.zeros((n_bands, len(freqs)))
    for k in range(n_bands):
        lo = centers[k - 1] if k > 0 else logf.min() - 1.0
        hi = centers[k + 1] if k < n_bands - 1 else logf.max() + 1.0
        c = centers[k]
        for j, lf in enumerate(logf):
            if lf <= c and k > 0:
                w = 0.5 * (1 + np.cos(np.pi * (c - lf) / (c - lo))) if lf > lo else 0.0
            elif lf > c and k < n_bands - 1:
                w = 0.5 * (1 + np.cos(np.pi * (lf - c) / (hi - c))) if lf < hi else 0.0
            else:
                w = 1.0
            masks[k, j] = max(w, 0.0)
    colsum = masks.sum(0)
    colsum[colsum == 0] = 1.0
    return masks / colsum[None, :]


def band_centers(sr: int, n_bands: int = N_BANDS, fmin: float = FMIN) -> np.ndarray:
    e = band_edges(sr, n_bands, fmin)
    return np.sqrt(e[:-1] * e[1:])


def stft(y: np.ndarray, n_fft: int = N_FFT, hop: int = HOP) -> np.ndarray:
    return librosa.stft(y, n_fft=n_fft, hop_length=hop, window="hann")


def band_signal(S: np.ndarray, masks: np.ndarray, k: int, length: int,
                hop: int = HOP) -> np.ndarray:
    """Time-domain signal of band k (istft of the masked STFT)."""
    return librosa.istft(S * masks[k][:, None], hop_length=hop,
                         window="hann", length=length)
