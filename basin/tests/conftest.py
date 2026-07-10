"""Make the project's `basin` package importable and provide shared fixtures."""

import os
import sys

import numpy as np
import pytest

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)


@pytest.fixture
def toy_memberships():
    """A small soft-membership matrix + track bounds (2 tracks, 20 windows)."""
    rng = np.random.default_rng(0)
    n_win, n_charts, top = 20, 8, 4
    m = rng.random((n_win, n_charts))
    # keep top-k per row, renormalize (mirrors atlas soft assignment)
    keep = np.argpartition(-m, top - 1, axis=1)[:, :top]
    mask = np.zeros_like(m, bool)
    np.put_along_axis(mask, keep, True, axis=1)
    m = np.where(mask, m, 0.0)
    m /= m.sum(1, keepdims=True)
    bounds = [(0, 10), (10, 20)]
    return m, bounds
