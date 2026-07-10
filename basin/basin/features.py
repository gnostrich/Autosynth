"""M1 — windowing + feature extraction.

Load mono audio at ``sr``, frame per-hop features (log-mel, RMS, onset
strength, chroma), aggregate frames into overlapping windows (mean + std per
feature), then standardize + PCA-whiten the corpus. Windows are the atomic
corpus units; each carries a ``(track_id, start_sample)`` handle so the
renderer can read the original audio back.

Spec: ``sr=22050  hop=1024  window_s=1.5  overlap=0.5  pca_dims=40``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# Per-frame feature block sizes. Concatenated per frame, then mean+std over the
# frames in a window gives the raw window vector.
N_MEL = 64
N_CHROMA = 12
# 64 mel + 1 rms + 1 onset + 12 chroma = 78 per-frame; *2 (mean,std) = 156.
FRAME_DIM = N_MEL + 1 + 1 + N_CHROMA
RAW_WINDOW_DIM = FRAME_DIM * 2


@dataclass
class WindowHandle:
    """Provenance for one window: where to read its audio back."""

    track_id: int
    start_sample: int
    n_samples: int


@dataclass
class Corpus:
    """The windowed, whitened corpus produced by :func:`build_corpus`."""

    raw: np.ndarray            # [n_windows, RAW_WINDOW_DIM]  standardized-input
    features: np.ndarray       # [n_windows, pca_dims]        whitened
    handles: list             # [n_windows] of WindowHandle
    track_bounds: list         # [n_tracks] (start_win, end_win) half-open
    track_paths: list          # [n_tracks] source paths
    # transforms recorded so the orbit can whiten new vectors identically
    mean: np.ndarray = field(default=None)
    scale: np.ndarray = field(default=None)
    pca_mean: np.ndarray = field(default=None)
    pca_components: np.ndarray = field(default=None)  # [pca_dims, RAW_WINDOW_DIM]
    # boundary frames for the splice-flux term (geodesic objective, local):
    # the per-frame feature vector at each window's start, and at one orbit
    # step (step_s) into it — i.e. exactly where the next grain splices in.
    head_frames: np.ndarray = field(default=None)   # [n_windows, frame_dim]
    mid_frames: np.ndarray = field(default=None)    # [n_windows, frame_dim]

    @property
    def n_windows(self) -> int:
        return self.features.shape[0]

    @property
    def n_tracks(self) -> int:
        return len(self.track_paths)


# ---------------------------------------------------------------------------
# Per-frame + per-window feature extraction
# ---------------------------------------------------------------------------

def frame_features(y: np.ndarray, sr: int, hop: int) -> np.ndarray:
    """Per-frame feature matrix ``[FRAME_DIM, n_frames]`` for one track.

    Blocks (in order): 64 log-mel, 1 RMS, 1 onset strength, 12 chroma.
    """
    import librosa

    mel = librosa.feature.melspectrogram(
        y=y, sr=sr, n_fft=2048, hop_length=hop, n_mels=N_MEL
    )
    log_mel = librosa.power_to_db(mel, ref=np.max)                    # [64, F]
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)  # [1, F]
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)   # [F]
    chroma = librosa.feature.chroma_stft(
        y=y, sr=sr, n_fft=2048, hop_length=hop, n_chroma=N_CHROMA
    )                                                                 # [12, F]

    # librosa's per-feature frame counts can differ by one; trim to the min.
    F = min(log_mel.shape[1], rms.shape[1], onset.shape[0], chroma.shape[1])
    blocks = [
        log_mel[:, :F],
        rms[:, :F],
        onset[np.newaxis, :F],
        chroma[:, :F],
    ]
    return np.vstack(blocks)                                          # [78, F]


def stem_frame_features(y: np.ndarray, sr: int, hop: int,
                        stems: str = "none") -> np.ndarray:
    """Per-frame features, optionally split into parallel source streams.

    ``stems='none'`` → the plain 78-d/frame block over the whole mix.
    ``stems='hpss'`` → classical (NN-free) harmonic/percussive separation
    (`librosa.effects.hpss`): features are computed on each stream and stacked,
    so a window vector distinguishes "percussion doing X while harmony does Y"
    instead of blending them into one texture. Grain audio is still read from
    the original mix — only *navigation* uses the richer coordinates.
    """
    if stems in ("none", None, ""):
        return frame_features(y, sr, hop)
    if stems == "hpss":
        import librosa
        y_h, y_p = librosa.effects.hpss(y)
        fh = frame_features(y_h, sr, hop)
        fp = frame_features(y_p, sr, hop)
        F = min(fh.shape[1], fp.shape[1])
        return np.vstack([fh[:, :F], fp[:, :F]])          # [2*78, F]
    raise ValueError(f"unknown stems mode: {stems!r}")


def _window_frames(window_s: float, overlap: float, sr: int, hop: int):
    """Return ``(frames_per_window, frame_stride)`` in frame units."""
    frames_per_window = max(1, int(round(window_s * sr / hop)))
    frame_stride = max(1, int(round(frames_per_window * (1.0 - overlap))))
    return frames_per_window, frame_stride


def aggregate_windows(frames: np.ndarray, window_s: float, overlap: float,
                      sr: int, hop: int):
    """Aggregate a frame matrix into window vectors (mean + std per feature).

    Returns ``(window_vectors [n_win, RAW_WINDOW_DIM], start_frames [n_win])``.
    """
    fpw, stride = _window_frames(window_s, overlap, sr, hop)
    F = frames.shape[1]
    starts = list(range(0, max(1, F - fpw + 1), stride))
    if not starts:                       # track shorter than one window
        starts = [0]

    vecs, start_frames = [], []
    for s in starts:
        block = frames[:, s:s + fpw]
        if block.shape[1] == 0:
            continue
        mean = block.mean(axis=1)
        std = block.std(axis=1)
        vecs.append(np.concatenate([mean, std]))
        start_frames.append(s)
    return np.asarray(vecs), np.asarray(start_frames)


# ---------------------------------------------------------------------------
# Corpus assembly + whitening
# ---------------------------------------------------------------------------

def _pca_whiten(x: np.ndarray, n_dims: int):
    """Standardize per-dimension then PCA-whiten to ``n_dims``.

    Returns ``(whitened, mean, scale, pca_mean, components)``. ``n_dims`` is
    capped to the rank actually available (see DECISIONS: small corpora).
    """
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale < 1e-8] = 1.0
    xs = (x - mean) / scale

    pca_mean = xs.mean(axis=0)
    xc = xs - pca_mean
    # SVD is stabler than forming the covariance for tall-thin corpora.
    U, S, Vt = np.linalg.svd(xc, full_matrices=False)
    k = int(min(n_dims, Vt.shape[0], max(1, (S > 1e-9).sum())))
    components = Vt[:k]                                   # [k, D]
    # Whiten: project and divide by singular-value-derived std.
    n = xc.shape[0]
    sv = S[:k] / np.sqrt(max(1, n - 1))
    sv[sv < 1e-8] = 1.0
    whitened = (xc @ components.T) / sv
    # fold the 1/sv into stored components so new vectors whiten identically
    components = components / sv[:, np.newaxis]
    return whitened, mean, scale, pca_mean, components


def build_corpus(paths: list, cfg: dict) -> Corpus:
    """Full M1 windowing pipeline over a list of audio files."""
    import librosa

    sr = int(cfg["sr"])
    hop = int(cfg["hop"])
    window_s = float(cfg["window_s"])
    overlap = float(cfg["overlap"])
    pca_dims = int(cfg["pca_dims"])
    fpw, _ = _window_frames(window_s, overlap, sr, hop)

    step_frames = max(1, int(round(float(cfg.get("step_s", 0.75)) * sr / hop)))

    raw_rows, handles, bounds, kept_paths = [], [], [], []
    head_rows, mid_rows = [], []
    cursor = 0
    for track_id, path in enumerate(sorted(paths)):
        y, _ = librosa.load(path, sr=sr, mono=True)
        if y.size < hop:
            continue
        frames = stem_frame_features(y, sr, hop, cfg.get("stems", "none"))
        vecs, start_frames = aggregate_windows(frames, window_s, overlap, sr, hop)
        if vecs.size == 0:
            continue
        win_samples = fpw * hop
        start = cursor
        F = frames.shape[1]
        for v, sf in zip(vecs, start_frames):
            raw_rows.append(v)
            head_rows.append(frames[:, min(sf, F - 1)])
            mid_rows.append(frames[:, min(sf + step_frames, F - 1)])
            handles.append(WindowHandle(
                track_id=len(kept_paths),
                start_sample=int(sf * hop),
                n_samples=int(win_samples),
            ))
            cursor += 1
        bounds.append((start, cursor))
        kept_paths.append(path)

    if not raw_rows:
        raise ValueError("No windows extracted — corpus empty or too short.")

    raw = np.asarray(raw_rows)
    whitened, mean, scale, pca_mean, components = _pca_whiten(raw, pca_dims)

    return Corpus(
        raw=(raw - mean) / scale,
        features=whitened,
        handles=handles,
        track_bounds=bounds,
        track_paths=kept_paths,
        mean=mean, scale=scale, pca_mean=pca_mean, pca_components=components,
        head_frames=np.asarray(head_rows),
        mid_frames=np.asarray(mid_rows),
    )
