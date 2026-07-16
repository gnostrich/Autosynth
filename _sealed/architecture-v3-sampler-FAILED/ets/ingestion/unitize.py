"""Unitization + descriptors (spec §2 steps 3-5), computed in the STFT domain.

Per (tatum slot, band) we produce one unit. All work is done on the masked STFT
S_k = S * mask_k so no per-band time signal is materialized during ingestion
(lean-memory). Descriptors feed ONLY within-track cost matrices (spec §2 step 5,
I-2): a timbre vector, a transposition-quotient pitch-class profile (12-bin
chroma; the quotient is taken inside CostStructure), and a circular metrical
position (from beatclock). Unit mass = perceptual energy/salience.
"""
from __future__ import annotations
import numpy as np
from . import filterbank as fb


def a_weight(f_hz: np.ndarray) -> np.ndarray:
    """IEC A-weighting gain (linear), a cheap perceptual loudness weight."""
    f = np.asarray(f_hz, dtype=float)
    f2 = f * f
    ra = (12194.0 ** 2 * f2 ** 2) / (
        (f2 + 20.6 ** 2) * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2))
        * (f2 + 12194.0 ** 2))
    return ra * (10 ** (2.0 / 20.0))  # normalized so ~1 at 1 kHz


def _pitchclass_matrix(freqs: np.ndarray, fmin: float = 55.0) -> np.ndarray:
    """(12, n_freq) fold from FFT bins to pitch classes."""
    n = len(freqs)
    M = np.zeros((12, n))
    for j, f in enumerate(freqs):
        if f < fmin:
            continue
        pc = int(round(12 * np.log2(f / fmin))) % 12
        M[pc, j] = 1.0
    return M


def _aggregate_by_slot(vals: np.ndarray, slot_idx: np.ndarray, n_slots: int,
                       how: str = "sum") -> np.ndarray:
    """Aggregate a per-frame quantity (n_frames,) or (d,n_frames) into slots."""
    if vals.ndim == 1:
        out = np.zeros(n_slots)
        cnt = np.zeros(n_slots)
        np.add.at(out, slot_idx, vals)
        np.add.at(cnt, slot_idx, 1.0)
        if how == "mean":
            out = out / np.maximum(cnt, 1.0)
        return out
    d = vals.shape[0]
    out = np.zeros((n_slots, d))
    cnt = np.zeros(n_slots)
    for k in range(d):
        np.add.at(out[:, k], slot_idx, vals[k])
    np.add.at(cnt, slot_idx, 1.0)
    if how == "mean":
        out = out / np.maximum(cnt, 1.0)[:, None]
    return out


def descriptors_and_mass(S: np.ndarray, masks: np.ndarray, sr: int,
                         tatum_boundaries: np.ndarray, n_fft: int = fb.N_FFT,
                         hop: int = fb.HOP):
    """Returns per (slot, band): mass, timbre desc, chroma desc.

    Shapes: mass (n_slots, n_bands); timbre (n_slots, n_bands, D_timbre);
    chroma (n_slots, n_bands, 12).
    """
    import librosa
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    n_frames = S.shape[1]
    n_bands = masks.shape[0]
    n_slots = len(tatum_boundaries) - 1

    # frame centers (librosa center=True) -> slot assignment
    frame_center = np.arange(n_frames) * hop
    slot_idx = np.searchsorted(tatum_boundaries, frame_center, side="right") - 1
    valid = (slot_idx >= 0) & (slot_idx < n_slots)

    pc_mat = _pitchclass_matrix(freqs)
    aw = a_weight(fb.band_centers(sr, n_bands))
    magS = np.abs(S)

    mass = np.zeros((n_slots, n_bands))
    timbre = np.zeros((n_slots, n_bands, 4))
    chroma = np.zeros((n_slots, n_bands, 12))

    fr = frame_center[valid]
    sidx = slot_idx[valid]
    fvec = freqs

    for k in range(n_bands):
        Pk = magS[:, valid] * masks[k][:, None]       # (n_freq, n_valid) band magnitude
        e_frame = np.sum(Pk ** 2, axis=0)             # ~ energy per frame
        m_frame = np.sum(Pk, axis=0) + 1e-12
        cen_frame = (fvec @ Pk) / m_frame             # spectral centroid (Hz)
        spread_frame = np.sqrt(np.maximum(
            (fvec ** 2 @ Pk) / m_frame - cen_frame ** 2, 0.0))
        # spectral flatness (geo/arith mean over freq), band-local
        logPk = np.log(Pk + 1e-12)
        flat_frame = np.exp(np.mean(logPk, axis=0)) / (np.mean(Pk, axis=0) + 1e-12)

        e_slot = _aggregate_by_slot(e_frame, sidx, n_slots, "sum")
        cen_slot = _aggregate_by_slot(cen_frame, sidx, n_slots, "mean")
        spread_slot = _aggregate_by_slot(spread_frame, sidx, n_slots, "mean")
        flat_slot = _aggregate_by_slot(flat_frame, sidx, n_slots, "mean")

        mass[:, k] = aw[k] * e_slot
        timbre[:, k, 0] = np.log(e_slot + 1e-12)
        timbre[:, k, 1] = np.log(cen_slot + 1.0)
        timbre[:, k, 2] = np.log(spread_slot + 1.0)
        timbre[:, k, 3] = flat_slot

        ch_frame = pc_mat @ Pk                        # (12, n_valid)
        ch_slot = _aggregate_by_slot(ch_frame, sidx, n_slots, "sum")  # (n_slots,12)
        chroma[:, k, :] = ch_slot

    # L1-normalize chroma per unit (pitch profile), guard zeros
    csum = chroma.sum(axis=2, keepdims=True)
    chroma = np.where(csum > 0, chroma / np.maximum(csum, 1e-12), 0.0)
    return mass, timbre, chroma
