"""M1 features + M2 render on a tiny generated corpus."""

import os

import numpy as np
import pytest
import soundfile as sf

from basin import features, atlas as atlas_mod, operator
from basin.render import GrainReader, render
from basin.orbit import Orbit

CFG = dict(sr=22050, hop=1024, window_s=1.5, overlap=0.5, pca_dims=40,
           n_charts=256, top_memberships=8, beta=1.0, gamma=0.3, tau=1.0,
           kappa=1.0, crossfade_s=0.375, step_s=0.75)


@pytest.fixture
def tiny_corpus(tmp_path):
    sr = CFG["sr"]
    rng = np.random.default_rng(0)
    paths = []
    for k in range(6):
        t = np.arange(int(6 * sr)) / sr
        f = 220 * (1 + 0.1 * k)
        y = 0.5 * np.sin(2 * np.pi * f * t) + 0.05 * rng.standard_normal(t.size)
        p = str(tmp_path / f"t{k}.wav")
        sf.write(p, y.astype(np.float32), sr)
        paths.append(p)
    return paths


def test_raw_window_dim_is_156():
    assert features.RAW_WINDOW_DIM == 156


def test_build_corpus_shapes(tiny_corpus):
    c = features.build_corpus(tiny_corpus, CFG)
    assert c.raw.shape[1] == features.RAW_WINDOW_DIM
    assert c.features.shape[0] == c.n_windows
    assert c.features.shape[1] <= CFG["pca_dims"]
    assert np.isfinite(c.features).all()
    assert len(c.handles) == c.n_windows
    # handles point inside their tracks
    for h in c.handles:
        assert 0 <= h.track_id < c.n_tracks


def test_render_produces_finite_audio(tiny_corpus):
    c = features.build_corpus(tiny_corpus, CFG)
    atlas = atlas_mod.build_atlas(c.features, CFG["n_charts"],
                                  CFG["top_memberships"])
    built = operator.build(atlas.memberships, c.track_bounds, n_basins="auto")
    orbit = Orbit(built.P, built.spectrum.psi, CFG, seed=0)
    states = orbit.run(20)
    reader = GrainReader(c, atlas.memberships, CFG, seed=0)
    audio = render(states, reader, CFG)
    assert np.isfinite(audio).all()
    assert np.abs(audio).max() <= 1.0 + 1e-6
    assert np.sqrt(np.mean(audio ** 2)) > 0          # not silent
