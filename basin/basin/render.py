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
    """Samples corpus windows from chart-mixtures with a continuity prior.

    ``stem`` selects which audio stream grains are read from: ``'mix'`` (the
    original blend, default), or ``'harmonic'`` / ``'percussive'`` — classical
    NN-free HPSS streams computed lazily per track. Pass one ``shared_cache``
    dict to several readers so the mix load and the HPSS split are done once.
    """

    def __init__(self, corpus, memberships: np.ndarray, cfg: dict,
                 seed: int = 0, stem: str = "mix",
                 shared_cache: dict | None = None, psi: np.ndarray = None):
        self.corpus = corpus
        self.features = corpus.features
        self.handles = corpus.handles
        self.memberships = memberships
        self.W = _col_normalize(memberships)
        self.sr = int(cfg["sr"])
        self.stem = stem
        self.beta_read = float(cfg.get("beta_read", 1.0))
        self.rng = np.random.default_rng(seed)
        # continuity bandwidth = median nearest-neighbour feature distance scale
        self._cont_scale = float(np.median(np.linalg.norm(
            np.diff(self.features, axis=0), axis=1)) + 1e-9)
        # Flow-kernel bandwidth, calibrated from the corpus itself: the one
        # true successor must outweigh the *summed* mass of all ~N unrelated
        # windows, i.e. a typical random-pair distance must cost > ln N nats
        # (×1.5 headroom so the walk's field decides ties, not noise). Windows
        # at consecutive-pair distance stay cheap → sonically-matching jump
        # targets (loop copies, parallel moments) remain reachable.
        n = self.features.shape[0]
        idx = np.random.default_rng(0).integers(0, n, size=(min(4000, n), 2))
        rand_d2 = ((self.features[idx[:, 0]] - self.features[idx[:, 1]]) ** 2
                   ).sum(1)
        med_rand_d2 = float(np.median(rand_d2) + 1e-9)
        self._flow_scale2 = med_rand_d2 / (3.0 * np.log(max(n, 2)))
        self._prev_emitted = None
        self._audio_cache: dict = shared_cache if shared_cache is not None else {}
        # window diffusion coordinates (for flow-mode field alignment)
        self.win_psi = memberships @ psi if psi is not None else None
        self.last_jump = True
        self.n_flow_steps = 0
        self.n_flow_jumps = 0

    def _track_audio(self, track_id: int) -> np.ndarray:
        key = (track_id, self.stem)
        if key in self._audio_cache:
            return self._audio_cache[key]
        mix_key = (track_id, "mix")
        if mix_key not in self._audio_cache:
            import librosa
            y, _ = librosa.load(self.corpus.track_paths[track_id],
                                sr=self.sr, mono=True)
            self._audio_cache[mix_key] = y
        if self.stem == "mix":
            return self._audio_cache[mix_key]
        if self.stem in ("harmonic", "percussive"):
            import librosa
            y_h, y_p = librosa.effects.hpss(self._audio_cache[mix_key])
            self._audio_cache[(track_id, "harmonic")] = y_h
            self._audio_cache[(track_id, "percussive")] = y_p
            return self._audio_cache[key]
        raise ValueError(f"unknown stem: {self.stem!r}")

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

    def _successor(self, v: int) -> int:
        """In-corpus successor window of ``v`` within its track, else ``v``."""
        if v + 1 < len(self.handles) and \
                self.handles[v + 1].track_id == self.handles[v].track_id:
            return v + 1
        return v

    def sample_flow(self, a_t: np.ndarray) -> int:
        """Flow-mode read: the corpus's own motion, tilted by the walk's field.

        ``p(w) ∝ exp(−|feat(w) − feat(succ(prev))|²/2σ²)·exp(β_read·ψ_w·a_t)``

        The first factor is the material's momentum: the overwhelmingly most
        likely emission is the previous window's own successor (or anything
        that sounds like it — e.g. the parallel moment of another track). The
        second is the walk acting as a field in diffusion coordinates: as
        knobs/wanderlust/kernel move the orbit's coordinate ``a_t`` away from
        where playback is, pressure builds until a jump wins — and it lands on
        sonically matching material. Dwell time and transition points emerge;
        no dwell counters, no beat grid.
        """
        n = len(self.handles)
        if self.win_psi is not None and a_t is not None and a_t.size \
                and np.any(a_t):
            tilt = self.beta_read * (self.win_psi @ a_t)
        else:
            tilt = np.zeros(n)

        if self._prev_emitted is None:
            logp = tilt.astype(float).copy()
        else:
            s = self._successor(self._prev_emitted)
            d2 = ((self.features - self.features[s]) ** 2).sum(1)
            logp = -d2 / (2.0 * self._flow_scale2) + tilt
            if s == self._prev_emitted:        # track end: must move on
                logp[s] = -np.inf

        logp -= logp.max()
        p = np.exp(logp)
        p /= p.sum()
        w = int(self.rng.choice(n, p=p))

        succ = None if self._prev_emitted is None \
            else self._successor(self._prev_emitted)
        self.last_jump = (succ is None) or (w != succ)
        self.n_flow_steps += 1
        self.n_flow_jumps += int(self.last_jump)
        self._prev_emitted = w
        return w

    def window_membership(self, w: int) -> np.ndarray:
        """Chart-membership row of window ``w`` (for orbit re-localization)."""
        return self.memberships[w]

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


def render(states: list, reader: GrainReader, cfg: dict,
           natural: bool = False, normalize: bool = True) -> np.ndarray:
    """Realize a sequence of :class:`~basin.orbit.OrbitState` to a mono signal.

    ``natural=False`` (default): each grain is normalized to a fixed target RMS
    — stable, but it flattens the corpus's loudness structure.
    ``natural=True``: grains play at their native amplitude, so the loudness
    information already in the audio (quiet breakdown vs full-on drop; a stem
    falling silent) passes straight through — channel fades *emerge* instead of
    being imposed. Used by :func:`render_voices`.
    """
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

        if not natural:
            # Normalize each grain to a *fixed* target RMS. Matching to the
            # previous grain's tail instead chains multiplicatively and
            # collapses to silence once any quiet grain appears; a fixed
            # reference keeps loudness stable across the splice.
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

    if normalize:
        peak = np.max(np.abs(out)) + 1e-9
        if peak > 1.0:
            out /= peak
    return out


def render_flow(orbit, reader: GrainReader, n_steps: int, cfg: dict,
                natural: bool = True, normalize: bool = True) -> np.ndarray:
    """Coupled walk↔playback realization (flow mode).

    Each tick: the orbit steps (PULL + knobs + wanderlust + kernel), the reader
    samples via :meth:`GrainReader.sample_flow` with the orbit's coordinate as
    a field, and the orbit **re-localizes to the window actually played** — one
    closed dynamics, so the walk can't teleport away from what is sounding.
    Successor emissions are contiguous audio and get a linear (sums-to-one)
    splice; jumps get an equal-power crossfade.
    """
    sr = int(cfg["sr"])
    step = int(round(float(cfg["step_s"]) * sr))
    xfade = min(int(round(float(cfg["crossfade_s"]) * sr)), step)
    grain_len = step + xfade
    eq_in, eq_out = _equal_power_fades(xfade)
    t = np.linspace(0.0, 1.0, xfade, endpoint=False)
    lin_in, lin_out = t, 1.0 - t
    target_rms = float(cfg.get("target_rms", 0.2))

    out = np.zeros(step * n_steps + grain_len, dtype=np.float32)
    prev_tail = None
    for i in range(n_steps):
        st = orbit.step()
        w = reader.sample_flow(st.a)
        orbit.relocalize(reader.window_membership(w))
        g = reader.grain_audio(w, grain_len).copy()
        if not natural:
            r = _rms(g)
            if r > 1e-5:
                g *= np.clip(target_rms / r, 0.25, 4.0)

        pos = i * step
        if prev_tail is not None and xfade > 0:
            fi, fo = (eq_in, eq_out) if reader.last_jump else (lin_in, lin_out)
            out[pos:pos + xfade] = prev_tail * fo + g[:xfade] * fi
            out[pos + xfade:pos + grain_len] = g[xfade:]
        else:
            out[pos:pos + grain_len] = g
        prev_tail = out[pos + step:pos + grain_len].copy()

    if normalize:
        peak = float(np.max(np.abs(out)) + 1e-9)
        if peak > 0.95:
            out *= 0.95 / peak
    return out


def render_flow_voices(orbits: list, readers: list, n_steps: int,
                       cfg: dict) -> np.ndarray:
    """N concurrent flow-mode voices, each a closed walk↔playback loop, summed."""
    voices = [render_flow(o, r, n_steps, cfg, natural=True, normalize=False)
              for o, r in zip(orbits, readers)]
    n = max(len(v) for v in voices)
    out = np.zeros(n, dtype=np.float32)
    for v in voices:
        out[:len(v)] += v
    peak = float(np.max(np.abs(out)) + 1e-9)
    if peak > 0.95:
        out *= 0.95 / peak
    return out


def render_voices(states_list: list, readers: list, cfg: dict) -> np.ndarray:
    """Polyphonic realization: N concurrent voices, summed.

    Each (states, reader) pair is an independent voice — its own orbit through
    the index, its own stem stream, its own crossfaded grain chain — rendered
    at *natural* amplitude and summed. Concurrency and channel fades come from
    the material itself: when a voice's walk passes through regions where its
    stem is quiet, that channel recedes; nothing imposes it.
    """
    voices = [render(sts, rd, cfg, natural=True, normalize=False)
              for sts, rd in zip(states_list, readers)]
    n = max(len(v) for v in voices)
    out = np.zeros(n, dtype=np.float32)
    for v in voices:
        out[:len(v)] += v
    peak = float(np.max(np.abs(out)) + 1e-9)
    if peak > 0.95:
        out *= 0.95 / peak
    return out
