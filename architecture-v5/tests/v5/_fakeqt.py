"""Headless event synthesis helpers for the v5 widget tests.

The widget event handlers touch only `ev.position()`, `ev.accept()` and
`ev.ignore()`, so a tiny stub drives press/move programmatically with no display
and no real QMouseEvent plumbing (offscreen platform). This is "synthesize
press/move and assert on emitted signals" — no pixel assertions.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF


class FakeMouseEvent:
    def __init__(self, x: float, y: float) -> None:
        self._p = QPointF(float(x), float(y))
        self.accepted = None

    def position(self) -> QPointF:
        return self._p

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.accepted = False


class Recorder:
    """Collects emitted region vectors for assertions."""

    def __init__(self) -> None:
        self.vectors = []

    def __call__(self, vec) -> None:
        import numpy as np
        self.vectors.append(np.asarray(vec, dtype=np.float32).reshape(-1).copy())
