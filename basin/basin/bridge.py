"""The bridge: measured musical descriptors ↔ emergent landscape directions.

Humans hear music along a handful of well-defined measured axes (energy,
onset drive, brightness, bass weight, noisiness, tonality, pacing). The
landscape's knobs are the flow's own directions. Neither replaces the
other — but their alignment is MEASURABLE, and that measurement is the
bridge:

* fingerprint: every emergent fader gets its measured descriptor profile
  ("rms +0.5, bass −0.3") — you know what a fader is before touching it;
* bridge controls: each descriptor defines a lean VECTOR (its projection
  onto the landscape) — drag "brightness" and the emergent faders move.

Nothing here enters the trace: descriptors are standard signal
measurements computed from the stored per-window features, the alignment
is a correlation, and the bridge is control-surface vocabulary. Descriptor
names are measurement names, not aesthetic labels — naming stays with the
listener.
"""

from __future__ import annotations

import numpy as np

# per-frame feature layout (features.py): 64 log-mel, 1 rms, 1 onset,
# 12 chroma [, K nmf activations]; raw window = mean block + std block.
N_MEL = 64


def descriptors(corpus) -> dict:
    """Measured per-window descriptor signals from the stored features."""
    raw = corpus.raw * corpus.scale[None, :] + corpus.mean[None, :]
    P = raw.shape[1] // 2                      # per-frame dim (mean block)
    mel_db = raw[:, :N_MEL]                    # mean log-mel (dB)
    mel_pow = np.power(10.0, mel_db / 10.0)    # back to power
    mel_pow /= mel_pow.sum(1, keepdims=True) + 1e-12
    bands = np.arange(N_MEL)
    chroma = raw[:, 66:78]
    chroma = chroma / (chroma.sum(1, keepdims=True) + 1e-12)

    H = corpus.handles
    stride = np.zeros(corpus.n_windows)
    for w in range(corpus.n_windows):
        if w + 1 < corpus.n_windows and H[w + 1].track_id == H[w].track_id:
            stride[w] = H[w + 1].start_sample - H[w].start_sample
        else:
            stride[w] = H[w].n_samples / 2

    return {
        "rms":    raw[:, 64],                                  # energy
        "onset":  raw[:, 65],                                  # drive
        "bright": (mel_pow * bands).sum(1),                    # mel centroid
        "bass":   mel_pow[:, :8].sum(1),                       # low-band mass
        "flat":   (np.exp(np.log(mel_pow + 1e-12).mean(1))
                   / (mel_pow.mean(1) + 1e-12)),               # noisiness
        "tonal":  chroma.max(1),                               # pitch focus
        "pace":   -stride,        # + = faster material (shorter beat step)
    }


def build_bridge(corpus, memberships, psi) -> dict:
    """Correlate every descriptor with every landscape direction.

    Returns ``names`` (descriptor order), ``corr`` [D, n_modes], and
    ``lean`` [D, n_modes] — unit-norm lean vectors (correlation profile,
    strongest 12 modes kept) so bridge value v ⇒ knob += v · lean[d].
    """
    desc = descriptors(corpus)
    wp = memberships @ psi                       # [n_windows, n_modes]
    wp = wp - wp.mean(0, keepdims=True)
    wn = np.sqrt((wp ** 2).sum(0)) + 1e-12
    names = list(desc.keys())
    D, M = len(names), psi.shape[1]
    corr = np.zeros((D, M))
    for i, k in enumerate(names):
        x = desc[k] - desc[k].mean()
        xn = np.sqrt((x ** 2).sum()) + 1e-12
        corr[i] = (wp * x[:, None]).sum(0) / (wn * xn)
    lean = np.zeros_like(corr)
    for i in range(D):
        keep = np.argsort(-np.abs(corr[i]))[:12]   # its main carriers
        lean[i, keep] = corr[i, keep]
        n = np.linalg.norm(lean[i])
        if n > 1e-12:
            lean[i] /= n
    return {"names": names, "corr": corr, "lean": lean}
