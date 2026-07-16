"""Tests for the EXTERNAL output-mastering layer (ets.render.master).

This layer is deliberately OUTSIDE the intrinsic ETS discipline (it consumes
finished audio, feeds nothing back, is opt-in). These tests assert it behaves as
a clean, deterministic, separable output stage — NOT that it is theory-derived.
"""
from __future__ import annotations
import numpy as np
import pytest

pyln = pytest.importorskip("pyloudnorm")  # external extra; skip if absent

from ets.render.master import master, _compress


def _uneven_signal(sr=44100, seconds=6.0):
    """A signal with a loud half and a quiet half — the thing mastering evens."""
    rng = np.random.default_rng(0)
    n = int(seconds * sr)
    y = rng.standard_normal(n) * 0.02
    t = np.arange(n) / sr
    y += 0.4 * np.sin(2 * np.pi * 110 * t)          # tone bed
    y[: n // 2] *= 6.0                               # first half much louder
    return y, sr


def test_master_is_deterministic():
    y, sr = _uneven_signal()
    a = master(y, sr)
    b = master(y, sr)
    assert np.array_equal(a, b), "mastering must be a deterministic pure function"


def test_master_reduces_spread_and_respects_ceiling():
    y, sr = _uneven_signal()
    m = master(y, sr, target_lufs=-14.0, peak_ceil_db=-1.0)

    def spread_db(a):
        w = int(0.5 * sr)
        r = np.array([np.sqrt(np.mean(a[i:i + w] ** 2))
                      for i in range(0, len(a) - w, w)])
        r = r[r > 1e-6]
        return 20 * np.log10(r.max() / r.min())

    assert spread_db(m) < spread_db(y), "master did not even the loud/quiet spread"
    # true-peak ceiling honored (-1 dBFS => ~0.891), with a hair of FP tolerance.
    assert np.max(np.abs(m)) <= 10 ** (-1.0 / 20) + 1e-6, "peak ceiling breached"


def test_master_still_breathes_not_flattened():
    """Mastering evens, it must NOT crush to dead-flat — some dynamics survive."""
    y, sr = _uneven_signal()
    m = master(y, sr)
    w = int(0.5 * sr)
    r = np.array([np.sqrt(np.mean(m[i:i + w] ** 2))
                  for i in range(0, len(m) - w, w)])
    r = r[r > 1e-6]
    assert r.max() / r.min() > 1.1, "mastering flattened all dynamics (over-compressed)"


def test_compressor_reduces_gain_only_above_threshold():
    """Below threshold the compressor is (near) unity; loud input is attenuated."""
    sr = 44100
    quiet = np.full(sr, 0.01)          # ~-40 dB, below -26 threshold
    loud = np.full(sr, 0.5)            # ~-6 dB, well above
    gq = _compress(quiet, sr)
    gl = _compress(loud, sr)
    assert np.allclose(gq, quiet, atol=1e-3), "quiet signal should pass ~unity"
    assert np.max(np.abs(gl)) < 0.5, "loud signal should be attenuated"


def test_missing_dependency_message(monkeypatch):
    """If pyloudnorm is unavailable, the error names the fix (not a bare ImportError
    deep in the chain)."""
    import builtins
    real_import = builtins.__import__

    def fake(name, *a, **k):
        if name == "pyloudnorm":
            raise ImportError("no module")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    with pytest.raises(ImportError, match="mastering"):
        master(np.zeros(1000), 44100)
