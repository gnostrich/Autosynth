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

import os

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
        # --- flow-mode geometry (corpus-calibrated, no hand rules) -----------
        # Two terms, one objective — the geodesic-mixing loss applied locally:
        # 1. Region similarity in whitened feature space (medium scale).
        # 2. Splice flux: the actual spectral discontinuity the candidate
        #    would create at the splice point — distance between the outgoing
        #    grain's frame at the splice offset (mid_frames[prev]) and the
        #    candidate's opening frame (head_frames[w]). Zero for the true
        #    successor, small for phase-aligned copies, large for
        #    harmonically/rhythmically incompatible material.
        # Bandwidths: the one true successor must outweigh the *summed* mass of
        # all ~N unrelated windows → a typical random-pair distance must cost
        # > ln N nats (exact — trace carries no hand factors).
        X = self.features
        n = X.shape[0]
        rng0 = np.random.default_rng(0)
        i0 = rng0.integers(0, n, size=min(4000, n))
        i1 = rng0.integers(0, n, size=min(4000, n))
        self._flow_X = X
        rand_d2 = ((X[i1] - X[i0]) ** 2).sum(1)
        self._flow_scale2 = float(np.median(rand_d2) + 1e-9) \
            / (2.0 * np.log(max(n, 2)))
        # Presence weight: a voice belongs where its channel exists. Without
        # this, silence is an ABSORBING STATE of the flux objective (two
        # silent windows splice perfectly), and the whole walk carries a
        # dull-material bias — found by listening at the 36-minute horizon:
        # renders decayed stepwise into permanent silence. The weight is the
        # channel's own measured per-window energy (un-standardized from the
        # stored features), as a log term — silence self-penalizes exactly as
        # much as the channel is absent.
        stems_mode = str(cfg.get("stems", "none"))
        chan_rms = getattr(corpus, "chan_rms", None)
        if self.stem.startswith("ch") and chan_rms is not None:
            # measured loudness of the SYNTHESIZED channel — absolute and
            # corpus-comparable (activations are per-track-relative and can
            # report presence where the masked audio is actually silent)
            e = chan_rms[:, int(self.stem[2:])].astype(float)
        else:
            if self.stem == "percussive" and stems_mode == "hpss":
                pdim = 142
            else:
                pdim = 64                   # mix / harmonic: mean RMS dim
            e = corpus.raw[:, pdim] * corpus.scale[pdim] + corpus.mean[pdim]
        e = np.maximum(e, 0.0)
        pos = e[e > 0]
        floor = float(np.quantile(pos, 0.05)) if pos.size else 1.0
        # capped at the corpus median: quiet-but-alive material is equal-cost
        # (breakdowns are traversable); only near-dead material is repelled.
        # Uncapped, presence climbs constantly toward loud material and bans
        # quiet passages — the "everything sounds the same" flatness.
        med = float(np.median(pos)) if pos.size else 1.0
        self._log_presence = np.log(np.minimum(e, med) + floor)
        self._log_presence -= self._log_presence.max()

        # Revisit pressure (emission-level wanderlust): healthy flow never
        # replays a window (successor chains advance), so this penalty fires
        # ONLY on literal repetition — it breaks the small recurrent cycles
        # the flux objective can trap into (measured: a 12-window cycle held
        # for 30 minutes at the 36-min horizon). Strength = γ; memory
        # timescale = median track length (pure corpus statistic).
        med_track = float(np.median([e - s for (s, e) in corpus.track_bounds]))
        self._revisit_decay = 0.5 ** (1.0 / max(med_track, 4.0))
        self._revisit = np.zeros(len(self.handles))
        self._wander = float(cfg.get("gamma", 0.3))

        self._head = getattr(corpus, "head_frames", None)
        self._mid = getattr(corpus, "mid_frames", None)
        if self._head is not None and self._mid is not None and self._head.size:
            # The splice happens at the window's native stride — the start of
            # its in-track successor. So the outgoing frame at the splice IS
            # the successor's head frame, by identity of the beat-synchronous
            # representation (stored mid_frames were measured at the old
            # fixed half-window offset and misreport the splice: they charge
            # the true successor a discontinuity that playback never makes).
            self._mid = self._mid.copy()
            for w in range(len(self.handles) - 1):
                if self.handles[w + 1].track_id == self.handles[w].track_id:
                    self._mid[w] = self._head[w + 1]
            flux_d2 = ((self._head[i1] - self._mid[i0]) ** 2).sum(1)
            self._flux_scale2 = float(np.median(flux_d2) + 1e-9) \
                / (2.0 * np.log(max(n, 2)))
        else:
            self._flux_scale2 = None
        self._prev_emitted = None
        self.force_jump = False        # event-typed: leave the groove NOW

        # Beat grid (measured): each track's own pulse via onset
        # autocorrelation. Grains are cut ON beats and the emission step is a
        # whole-beat multiple of the corpus's median tempo, so all voices
        # share the material's own clock — the vertical (voice-vs-voice) part
        # of the summed-signal objective. No hand-set grid anywhere.
        self._beat_key = "__beats__"

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
                                sr=self.sr, mono=False)
            if y.ndim == 1:                    # mono source → duplicated sides
                y = np.stack([y, y])
            self._audio_cache[mix_key] = y.astype(np.float32)   # (2, n)
        if self.stem == "mix":
            return self._audio_cache[mix_key]
        if self.stem in ("harmonic", "percussive"):
            import librosa
            mono = self._audio_cache[mix_key].mean(0)
            y_h, y_p = librosa.effects.hpss(mono)
            self._audio_cache[(track_id, "harmonic")] = np.stack([y_h, y_h])
            self._audio_cache[(track_id, "percussive")] = np.stack([y_p, y_p])
            return self._audio_cache[key]
        if self.stem.startswith("ch") and \
                getattr(self.corpus, "nmf_templates", None) is not None:
            # emergent channel: synthesize all K masks for this track at once.
            # Splits are cached to disk on first computation — the walk now
            # blends many tracks per minute, and recomputing a split on every
            # LRU re-entry made rendering slower than realtime. Decoding the
            # cached file is cheap; the split happens once per track ever.
            import soundfile as _sf
            cache_dir = os.path.join(os.path.dirname(
                self.corpus.track_paths[track_id]) or ".", ".chansplit_cache")
            n_ch = int(getattr(self.corpus, "n_channels", 0) or 0)
            paths = [os.path.join(cache_dir, f"t{track_id}_ch{k}.flac")
                     for k in range(n_ch)]
            if paths and all(os.path.exists(p) for p in paths):
                for k, p in enumerate(paths):
                    yk, _ = _sf.read(p, dtype="float32")
                    self._audio_cache[(track_id, f"ch{k}")] = yk.T
            else:
                from . import channels
                outs = channels.split_track(self._audio_cache[mix_key],
                                            self.corpus.nmf_templates)
                os.makedirs(cache_dir, exist_ok=True)
                for k, yk in enumerate(outs):
                    self._audio_cache[(track_id, f"ch{k}")] = yk
                    _sf.write(paths[k] if k < len(paths) else os.path.join(
                        cache_dir, f"t{track_id}_ch{k}.flac"), yk.T, self.sr)
            # LRU: full-band stereo channel audio is heavy — keep ~4 tracks
            order = self._audio_cache.setdefault("__lru__", [])
            order.append(track_id)
            while len(order) > 4:
                old_t = order.pop(0)
                if old_t in order:
                    continue
                for kk in list(self._audio_cache):
                    if isinstance(kk, tuple) and kk[0] == old_t:
                        del self._audio_cache[kk]
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

    def native_stride(self, w: int) -> int:
        """The material's own step at window ``w``: distance to the next
        window of the same track (beat-synchronous representation), i.e. the
        local clock. Fast material paces the trace faster — tempo is a
        coordinate of the landscape, not something to normalize away."""
        h = self.handles[w]
        if w + 1 < len(self.handles) and \
                self.handles[w + 1].track_id == h.track_id:
            d = self.handles[w + 1].start_sample - h.start_sample
            if d > 0:
                return int(d)
        return max(1, h.n_samples // 2)

    def mean_chart_run(self) -> float:
        """The corpus's own chart-correlation length: mean run of consecutive
        same-chart windows along tracks (measured constant, used as the
        co-movement smoothing timescale)."""
        if not hasattr(self, "_mean_run"):
            wb = np.asarray(np.argmax(self.memberships, axis=1)).ravel()
            runs, cur, r = [], None, 0
            for w in range(len(self.handles)):
                same_track = (w > 0 and self.handles[w].track_id
                              == self.handles[w - 1].track_id)
                if same_track and wb[w] == cur:
                    r += 1
                else:
                    if r:
                        runs.append(r)
                    cur, r = wb[w], 1
            if r:
                runs.append(r)
            self._mean_run = float(np.mean(runs)) if runs else 1.0
        return self._mean_run

    def median_stride(self) -> int:
        if not hasattr(self, "_med_stride"):
            ds = [self.handles[i + 1].start_sample - self.handles[i].start_sample
                  for i in range(len(self.handles) - 1)
                  if self.handles[i + 1].track_id == self.handles[i].track_id]
            self._med_stride = int(np.median(ds)) if ds else \
                max(1, self.handles[0].n_samples // 2)
        return self._med_stride

    def _successor(self, v: int) -> int:
        """In-corpus successor window of ``v`` within its track, else ``v``."""
        if v + 1 < len(self.handles) and \
                self.handles[v + 1].track_id == self.handles[v].track_id:
            return v + 1
        return v

    def sample_flow(self, a_t: np.ndarray, m: np.ndarray = None) -> int:
        """Flow-mode read: the corpus's own motion, gated by the walk's region.

        ``p(w) ∝ [W@m]_w · exp(−|feat(w) − feat(succ(prev))|²/2σ²)
                 · exp(β_read·ψ_w·a_t)``

        The gate ``[W@m]_w`` is the orbit's chart mixture pushed down to
        windows: emission happens *inside the region the walk occupies*. This
        is the region-to-region trace acting at read time — the orbit walks
        chart-to-chart (where knobs, wanderlust, momentum and basin pressure
        have authority at the region scale), and the reader only chooses
        *which window within the region* by the material's own momentum: the
        locality/flux factor makes the previous window's successor (or its
        sonic parallel in another track) the default. When the knob leans,
        the chart walk migrates in diffusion space, the gate moves with it,
        and playback is carried across tracks/parts — navigation lives in the
        region walk, not in a tilt fighting the locality term. Zero lean =
        the corpus's own chart-to-chart routing. Dwell time and transition
        points emerge; no dwell counters, no beat grid.
        """
        n = len(self.handles)
        if self.win_psi is not None and a_t is not None and a_t.size \
                and np.any(a_t):
            tilt = self.beta_read * (self.win_psi @ a_t)
        else:
            tilt = np.zeros(n)

        # region gate: log of the orbit's mixture pushed to windows.
        # Zero-mass windows are simply outside the region (barred).
        if m is not None:
            g = self.W @ m
            with np.errstate(divide="ignore"):
                gate = np.where(g > 0, np.log(np.maximum(g, 1e-300)), -np.inf)
        else:
            gate = np.zeros(n)

        if self._prev_emitted is None:
            logp = tilt.astype(float) + self._log_presence + gate
        else:
            s = self._successor(self._prev_emitted)
            d2 = ((self._flow_X - self._flow_X[s]) ** 2).sum(1)
            logp = (-d2 / (2.0 * self._flow_scale2) + tilt + gate
                    + self._log_presence - self._wander * self._revisit)
            if self._flux_scale2 is not None:
                # spectral flux across the actual splice (the paper's loss)
                flux = ((self._head - self._mid[self._prev_emitted]) ** 2
                        ).sum(1)
                logp -= flux / (2.0 * self._flux_scale2)
            if s == self._prev_emitted:        # track end: must move on
                logp[s] = -np.inf

        if self.force_jump and self._prev_emitted is not None:
            # trigger gate: one step of pure field — drop the flow term so the
            # walk's region + tilt alone pick the destination, and bar the
            # successor's whole track (a jump must actually leave).
            logp = tilt.astype(float) + self._log_presence + gate
            prev_track = self.handles[self._prev_emitted].track_id
            same = np.array([h.track_id == prev_track for h in self.handles])
            if not np.all(same | ~np.isfinite(logp)):
                logp[same] = -np.inf
            else:
                logp[self._successor(self._prev_emitted)] = -np.inf
            self.force_jump = False

        if not np.any(np.isfinite(logp)):      # region excludes everything
            logp = tilt.astype(float) + self._log_presence

        logp -= logp.max()
        p = np.exp(logp)
        p /= p.sum()
        self.last_p = p                    # the live flow field (for displays)
        # Ridge read: ONE die in the machine — the walk. The reader is the
        # deterministic surface of the trace: it follows the maximum of the
        # measured evidence (the successor, while the region holds) and
        # switches exactly when the walk's region moves the ridge. Sampling
        # here was a second, extrinsic source of randomness — loop-based
        # material is full of near-duplicate windows with genuinely ~0 splice
        # cost, and drawing among them every beat was the mid-phrase mash.
        w = int(np.argmax(logp))

        succ = None if self._prev_emitted is None \
            else self._successor(self._prev_emitted)
        self.last_jump = (succ is None) or (w != succ)
        self.n_flow_steps += 1
        self.n_flow_jumps += int(self.last_jump)
        self._revisit *= self._revisit_decay
        self._revisit[w] += 1.0
        self._prev_emitted = w
        return w

    def window_membership(self, w: int) -> np.ndarray:
        """Chart-membership row of window ``w`` (for orbit re-localization)."""
        return self.memberships[w]

    def grain_audio(self, w: int, n_samples: int) -> np.ndarray:
        """Stereo grain, shape (n_samples, 2). With the beat-synchronous
        representation every window already starts ON a beat of its own
        material — no read-time alignment exists."""
        h = self.handles[w]
        y = self._track_audio(h.track_id)              # (2, n)
        seg = y[:, h.start_sample:h.start_sample + n_samples]
        if seg.shape[1] < n_samples:
            seg = np.pad(seg, ((0, 0), (0, n_samples - seg.shape[1])))
        return seg.T.astype(np.float32)


def _equal_power_fades(n: int):
    """Equal-power fade-in/out as column vectors (broadcast over channels)."""
    t = np.linspace(0, np.pi / 2, n, endpoint=False)
    return np.sin(t)[:, None], np.cos(t)[:, None]


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

    out = np.zeros((step * len(states) + grain_len, 2), dtype=np.float32)
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
    """Coupled walk↔playback on the material's OWN clock.

    Each emission advances time by the emitted window's native stride —
    fast material paces the trace faster, slow slower (tempo is part of the
    landscape). Grains are enveloped (fade-in/out over the crossfade span)
    and overlap-added; contiguous successors reconstruct seamlessly.
    """
    sr = int(cfg["sr"])
    xfade = int(round(float(cfg["crossfade_s"]) * sr))
    est = reader.median_stride()
    cap = int(n_steps * est * 1.35) + 8 * xfade
    out = np.zeros((cap, 2), dtype=np.float32)
    eq_in, _ = _equal_power_fades(xfade)
    lin = np.linspace(0.0, 1.0, xfade, endpoint=False)[:, None]
    target_rms = float(cfg.get("target_rms", 0.2))

    t = 0
    for i in range(n_steps):
        st = orbit.step()
        # The region gate IS the walk↔playback coupling: emission is always
        # drawn inside the walk's one-step measure, so sound cannot leave the
        # walk and no relocalization back onto playback is needed. (Snapping
        # the walk to the played window — even only on jumps — erases its
        # accumulated drift and no lean can ever move the set.)
        w = reader.sample_flow(st.a, st.m_full if st.m_full is not None else st.m)
        stride = reader.native_stride(w)   # material own clock, uncapped (measured: beat strides never exceed 2x median)
        glen = stride + xfade
        if t + glen >= cap:
            break
        g = reader.grain_audio(w, glen).copy()
        if not natural:
            r = _rms(g)
            if r > 1e-5:
                g *= np.clip(target_rms / r, 0.25, 4.0)
        if i > 0:
            g[:xfade] *= eq_in if reader.last_jump else lin
        g[-xfade:] *= (1.0 - lin)
        out[t:t + glen] += g
        t += stride
    out = out[:t + xfade]
    if normalize:
        peak = float(np.max(np.abs(out)) + 1e-9)
        if peak > 0.95:
            out *= 0.95 / peak
    return out


def render_flow_voices(orbits: list, readers: list, n_steps: int,
                       cfg: dict) -> np.ndarray:
    """N concurrent voices, each on its material's OWN clock, mixed on the
    absolute timeline. Voices step in time order; coupling reads the others'
    live coordinates. Beat alignment between voices is not enforced — it
    emerges when coupling co-locates them in tempo-compatible material.
    """
    sr = int(cfg["sr"])
    xfade = int(round(float(cfg["crossfade_s"]) * sr))
    couple = float(cfg.get("couple", 0.5))
    est = readers[0].median_stride()
    total = n_steps * est
    cap = int(total * 1.1) + 8 * xfade
    out = np.zeros((cap, 2), dtype=np.float32)
    eq_in, _ = _equal_power_fades(xfade)
    lin = np.linspace(0.0, 1.0, xfade, endpoint=False)[:, None]

    V = len(orbits)
    base_knobs = [o.knob.copy() for o in orbits]
    n_macros = orbits[0].n_macros
    vs = [{"t": 0, "i": 0, "a": np.zeros(n_macros), "da": np.zeros(n_macros)}
          for _ in range(V)]
    # co-movement is read at the landscape's own correlation length: the
    # corpus's mean chart-run (measured). Per-step velocity in the full
    # coordinate space is mostly jitter; coupling to it buffets the gates
    # every beat (heard as fast mash-switching). The EMA half-life is the
    # measured constant, not a chosen one.
    ema_decay = 0.5 ** (1.0 / max(readers[0].mean_chart_run(), 1.0))

    while True:
        live = [v for v in range(V) if vs[v]["t"] < total]
        if not live:
            break
        v = min(live, key=lambda u: vs[u]["t"])
        S = vs[v]
        if V > 1 and couple != 0.0:
            # couple to the others' MOTION, not their position. Position
            # coupling is a spring to the group centroid: measured, it parks
            # all voices at the deepest pole for 30 straight minutes (each
            # voice's standing lean toward the others exceeds any performed
            # lean). Velocity coupling makes voices travel together — no
            # reward for sitting still, full reward for co-moving.
            others = np.mean([vs[u]["da"] for u in range(V) if u != v], axis=0)
            orbits[v].knob = base_knobs[v] + couple * others
        st = orbits[v].step()
        # gate = coupling; see render_flow — the walk stays free to navigate
        w = readers[v].sample_flow(st.a, st.m_full if st.m_full is not None else st.m)
        vs[v]["da"] = (ema_decay * vs[v]["da"]
                       + (1.0 - ema_decay) * (st.a - vs[v]["a"]))
        vs[v]["a"] = st.a
        stride = readers[v].native_stride(w)
        glen = stride + xfade
        if S["t"] + glen < cap:
            g = readers[v].grain_audio(w, glen).copy()
            if S["i"] > 0:
                g[:xfade] *= eq_in if readers[v].last_jump else lin
            g[-xfade:] *= (1.0 - lin)
            out[S["t"]:S["t"] + glen] += g
        S["t"] += stride
        S["i"] += 1

    out = out[:total + xfade]
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
    out = np.zeros((n, 2), dtype=np.float32)
    for v in voices:
        out[:len(v)] += v
    peak = float(np.max(np.abs(out)) + 1e-9)
    if peak > 0.95:
        out *= 0.95 / peak
    return out
