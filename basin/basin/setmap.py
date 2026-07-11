"""Project a GIVEN set onto the landscape and extract its steering.

A recorded set — anyone's — is a trajectory over this instrument's
landscape. Window it exactly like the corpus (beat-synchronous, same
frame features, same whitening), soft-assign to the same charts, and it
becomes a measured path a(t) through diffusion space. Then the same
Mori–Zwanzig cut that built the machinery separates the path into:

    what the corpus flow explains   (the operator's one-step prediction)
  + what it does not                (the INNOVATION — the performer's hand)

The innovation, smoothed at the corpus's own chart-correlation timescale,
IS the extracted knob journey: the set's arc as a lean schedule over the
emergent directions. Products: replay it on this instrument, read it
through the bridge (energy/brightness/pace arcs), or aggregate many sets
into a grammar of arcs. Nothing hand-set: same features, same transforms,
same operator, and the smoothing timescale is measured.
"""

from __future__ import annotations

import numpy as np

from . import features as F
from .atlas import _soft_assign


def project_set(path: str, corpus, atlas, psi: np.ndarray, cfg: dict) -> dict:
    """Window + whiten an external set with the corpus's stored transforms.

    Returns per-window: ``a`` [T, n_modes] diffusion trajectory,
    ``memberships`` [T, n_charts], ``strides`` (native clock, samples),
    ``starts`` (sample offsets), ``raw`` (for descriptor curves).
    """
    import librosa
    sr, hop = int(cfg["sr"]), int(cfg["hop"])
    window_s = float(cfg["window_s"])
    stems_mode = str(cfg.get("stems", "none"))
    chunk_s = float(cfg.get("project_chunk_s", 600.0))

    rows, starts, strides = [], [], []
    # chunked: a long set at 44.1k would OOM in one piece (the NMF
    # activation pass over a 100k+-frame spectrogram); memory stays
    # bounded and windows are computed per chunk on the chunk's own beats.
    dur = librosa.get_duration(path=path)
    off = 0.0
    while off < dur - 1.0:
        y, _ = librosa.load(path, sr=sr, mono=True, offset=off,
                            duration=min(chunk_s, dur - off))
        if y.size < hop * 4:
            break
        if stems_mode == "nmf" and \
                getattr(corpus, "nmf_templates", None) is not None:
            from . import channels
            base = F.frame_features(y, sr, hop)
            act = channels.track_activations(y, corpus.nmf_templates, hop)
            n = min(base.shape[1], act.shape[1])
            act = act[:, :n] / (act.max() + 1e-9) * 10.0
            frames = np.vstack([base[:, :n], act])
        else:
            frames = F.stem_frame_features(y, sr, hop, stems_mode)
        base_sample = int(off * sr)
        bw = F.beat_windows(y, sr, window_s)
        nF = frames.shape[1]
        if bw is not None:
            b_starts, b_spans, _tempo = bw
            for s0, span in zip(b_starts, b_spans):
                f0 = min(int(s0 // hop), nF - 1)
                f1 = min(max(int((s0 + span) // hop), f0 + 2), nF)
                block = frames[:, f0:f1]
                rows.append(np.concatenate([block.mean(1), block.std(1)]))
                starts.append(base_sample + int(s0))
                strides.append(int(span))
        else:
            vecs, sfs = F.aggregate_windows(frames, window_s,
                                            float(cfg["overlap"]), sr, hop)
            step = int(round(window_s * (1 - float(cfg["overlap"])) * sr))
            for v, sf in zip(vecs, sfs):
                rows.append(v)
                starts.append(base_sample + int(sf * hop))
                strides.append(step)
        off += chunk_s
    raw = np.asarray(rows)

    # the corpus's exact whitening (sv already folded into components)
    xs = (raw - corpus.mean[None, :]) / corpus.scale[None, :]
    feats = (xs - corpus.pca_mean[None, :]) @ corpus.pca_components.T
    memberships = _soft_assign(feats, atlas.centers, atlas.bandwidth,
                               int(cfg.get("top_memberships", 8)))
    return {
        "a": memberships @ psi,
        "memberships": memberships,
        "strides": np.asarray(strides),
        "starts": np.asarray(starts),
        "raw": raw,
        "sr": sr,
    }


def extract_arc(proj: dict, P: np.ndarray, psi: np.ndarray,
                mean_run: float) -> dict:
    """The performer's hand: innovation of the set's path vs the corpus flow.

    lean(t) = EMA over the corpus's measured chart-run timescale of
    ``a(t+1) − prediction(t)`` where prediction = one operator step from
    the set's own position. Zero where the set just follows the corpus's
    routing; sustained structure where it is being steered.
    """
    m = proj["memberships"]
    a = proj["a"]
    pred = (m[:-1] @ P) @ psi                # [T-1, n_modes]
    innov = a[1:] - pred
    dec = 0.5 ** (1.0 / max(mean_run, 1.0))
    lean = np.zeros_like(innov)
    acc = np.zeros(innov.shape[1])
    for t in range(innov.shape[0]):
        acc = dec * acc + (1.0 - dec) * innov[t]
        lean[t] = acc
    return {"innovation": innov, "lean": lean}
