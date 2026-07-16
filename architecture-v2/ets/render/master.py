"""EXTERNAL output-mastering layer — NOT part of the intrinsic object.

This is a conventional, off-the-shelf mastering chain applied to an ALREADY
rendered tape: gentle RMS compressor -> EBU R128 loudness normalize -> peak
limiter. It exists purely for listening comfort and is, by design, OUTSIDE the
ETS faithfulness discipline:

  * it never touches the synth, the world, F, the settlement, the writer, the
    schedule, the tape, or the corpus — it consumes finished audio samples only;
  * it does not feed back anywhere (no self-ingestion, no effect on any gate);
  * it is OPT-IN. The pure render is unchanged and remains the canonical output;
    mastering is an explicit downstream stage the caller requests. With it off,
    render output is byte-identical to before (determinism / H-8 preserved).

Because it is external and non-feedback, it is deliberately conventional (a
standard mastering tool), not derived from the intrinsic geometry — hand-deriving
a compressor from first principles would be misplaced rigor for a playback stage.
Registered as decision output-master-external.

Dependency: pyloudnorm (EBU R128 / ITU-R BS.1770). Imported lazily so core and CI
run without it; only callers that request mastering need it (extra 'mastering').
"""
from __future__ import annotations
import numpy as np


def master(audio: np.ndarray, sr: int, target_lufs: float = -14.0,
           peak_ceil_db: float = -1.0, *, compress: bool = True) -> np.ndarray:
    """Return a mastered copy of `audio` (mono float array). Pure function of its
    inputs (deterministic). Chain: gentle soft-knee RMS compressor -> R128
    loudness normalize to `target_lufs` -> soft peak limiter at `peak_ceil_db`.

    Raises ImportError with an actionable message if pyloudnorm is absent."""
    try:
        import pyloudnorm as pyln
    except ImportError as e:  # pragma: no cover - environment dependent
        raise ImportError(
            "output mastering needs pyloudnorm (EBU R128). Install the extra: "
            "pip install 'ets[mastering]'  (or: pip install pyloudnorm)") from e

    y = np.asarray(audio, dtype=np.float64)
    if y.ndim > 1:
        y = y.mean(axis=1)

    if compress:
        y = _compress(y, sr)

    meter = pyln.Meter(sr)
    loud = meter.integrated_loudness(y)
    if np.isfinite(loud):
        y = pyln.normalize.loudness(y, loud, target_lufs)

    ceil = 10.0 ** (peak_ceil_db / 20.0)
    peak = float(np.max(np.abs(y))) + 1e-12
    if peak > ceil:
        y = np.tanh(y / ceil) * ceil          # soft knee above the ceiling
    y = np.clip(y, -ceil, ceil)
    return y.astype(np.float32)


def _compress(y: np.ndarray, sr: int, *, thresh_db: float = -26.0,
              ratio: float = 3.0, knee_db: float = 6.0,
              atk: float = 0.010, rel: float = 0.180) -> np.ndarray:
    """Standard feed-forward soft-knee compressor with an RMS detector and
    asymmetric attack/release gain smoothing. Textbook DSP, deterministic."""
    win = max(1, int(0.020 * sr))
    env = np.sqrt(np.convolve(y ** 2, np.ones(win) / win, mode="same") + 1e-12)
    env_db = 20.0 * np.log10(env + 1e-12)

    g = np.zeros_like(env_db)
    lo = thresh_db - knee_db / 2.0
    hi = thresh_db + knee_db / 2.0
    above = env_db > hi
    knee = (env_db >= lo) & (env_db <= hi)
    g[above] = (thresh_db - env_db[above]) * (1.0 - 1.0 / ratio)
    xk = env_db[knee] - lo
    g[knee] = -(1.0 - 1.0 / ratio) * (xk ** 2) / (2.0 * knee_db)

    a_atk = np.exp(-1.0 / (atk * sr))
    a_rel = np.exp(-1.0 / (rel * sr))
    sm = np.empty_like(g)
    prev = 0.0
    for i in range(len(g)):
        target = g[i]
        coeff = a_atk if target < prev else a_rel   # gain reduction = attack
        prev = coeff * prev + (1.0 - coeff) * target
        sm[i] = prev
    return y * (10.0 ** (sm / 20.0))
