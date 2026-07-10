"""M2 — concatenative audio realization (grain read).

Turn a sequence of orbit chart-mixtures into audio. Each step samples one
corpus window from the mixture (biased for continuity toward grains whose
in-corpus predecessor is near the last emitted grain), reads that window's raw
audio via its handle, RMS-matches it across the splice, and equal-power
crossfades it with the previous emission.

This sounds like rough concatenative collage at track quality — expected and
acceptable for v0.1. The question is navigational coherence, not fidelity.
"""

from __future__ import annotations

import numpy as np


def _col_normalize(memberships: np.ndarray) -> np.ndarray:
    """P(window | chart): normalize each chart column over windows."""
    W = memberships.copy()
    s = W.sum(0, keepdims=True)
    s[s < 1e-12] = 1.0
    return W / s


def _predecessor(handles: list, w: int) -> int:
    """In-corpus predecessor window of ``w`` within its track, else ``w``."""
    if w > 0 and handles[w - 1].track_id == handles[w].track_id:
        return w - 1
    return w


class GrainReader:
    """Samples corpus windows from chart-mixtures with a continuity prior."""

    def __init__(self, corpus, memberships: np.ndarray, cfg: dict,
                 seed: int = 0):
        self.corpus = corpus
        self.features = corpus.features
        self.handles = corpus.handles
        self.W = _col_normalize(memberships)
        self.sr = int(cfg["sr"])
        self.rng = np.random.default_rng(seed)
        # continuity bandwidth = median nearest-neighbour feature distance scale
        self._cont_scale = float(np.median(np.linalg.norm(
            np.diff(self.features, axis=0), axis=1)) + 1e-9)
        self._prev_emitted = None
        self._audio_cache: dict = {}

    def _track_audio(self, track_id: int) -> np.ndarray:
        if track_id not in self._audio_cache:
            import librosa
            y, _ = librosa.load(self.corpus.track_paths[track_id],
                                sr=self.sr, mono=True)
            self._audio_cache[track_id] = y
        return self._audio_cache[track_id]

    def sample(self, m: np.ndarray) -> int:
        """Sample a window index from chart-mixture ``m`` with continuity bias."""
        p = self.W @ m                                    # [n_windows]
        if self._prev_emitted is not None:
            prev_feat = self.features[self._prev_emitted]
            # bias toward grains whose predecessor sits near the last emission
            active = np.nonzero(p > 1e-9)[0]
            if active.size:
                preds = np.array([_predecessor(self.handles, w) for w in active])
                d = np.linalg.norm(self.features[preds] - prev_feat, axis=1)
                cont = np.exp(-(d ** 2) / (2 * self._cont_scale ** 2))
                p = p.copy()
                p[active] *= cont
        s = p.sum()
        if s < 1e-12:
            w = int(self.rng.integers(len(self.handles)))
        else:
            w = int(self.rng.choice(len(p), p=p / s))
        self._prev_emitted = w
        return w

    def grain_audio(self, w: int, n_samples: int) -> np.ndarray:
        h = self.handles[w]
        y = self._track_audio(h.track_id)
        seg = y[h.start_sample:h.start_sample + n_samples]
        if seg.size < n_samples:
            seg = np.pad(seg, (0, n_samples - seg.size))
        return seg.astype(np.float32)


def _equal_power_fades(n: int):
    """Equal-power (sin/cos) fade-in / fade-out curves of length ``n``."""
    t = np.linspace(0, np.pi / 2, n, endpoint=False)
    return np.sin(t), np.cos(t)


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2) + 1e-12))


def render(states: list, reader: GrainReader, cfg: dict) -> np.ndarray:
    """Realize a sequence of :class:`~basin.orbit.OrbitState` to a mono signal."""
    sr = int(cfg["sr"])
    step = int(round(float(cfg["step_s"]) * sr))
    xfade = int(round(float(cfg["crossfade_s"]) * sr))
    xfade = min(xfade, step)
    grain_len = step + xfade
    fade_in, fade_out = _equal_power_fades(xfade)

    target_rms = float(cfg.get("target_rms", 0.2))

    out = np.zeros(step * len(states) + grain_len, dtype=np.float32)
    prev_tail = None                                   # last grain's overlap tail
    for i, st in enumerate(states):
        w = reader.sample(st.m)
        g = reader.grain_audio(w, grain_len).copy()

        # Normalize each grain to a *fixed* target RMS. Matching to the previous
        # grain's tail instead chains multiplicatively and collapses to silence
        # once any quiet grain appears; a fixed reference keeps loudness stable
        # across the splice without that feedback.
        r = _rms(g)
        if r > 1e-5:
            g *= np.clip(target_rms / r, 0.25, 4.0)

        pos = i * step
        if prev_tail is not None and xfade > 0:
            # equal-power crossfade over the overlap region
            out[pos:pos + xfade] = prev_tail * fade_out + g[:xfade] * fade_in
            out[pos + xfade:pos + grain_len] = g[xfade:]
        else:
            out[pos:pos + grain_len] = g

        prev_tail = out[pos + step:pos + grain_len].copy()

    peak = np.max(np.abs(out)) + 1e-9
    if peak > 1.0:
        out /= peak
    return out
