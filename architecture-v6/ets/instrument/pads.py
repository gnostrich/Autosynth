"""Pad widgets (F3.1 display + F3.2 tap surface). Native Qt only (I-13).

  * `TrackPadGrid` — MPC-style pads, ONE per source track, LIT from provenance
    (PadModel) and coloured by source track. Pure display: it emits no gesture
    and drives no lane. This is what F3.1/F3-C validate.
  * `RegionTapPads` — the tap/hold surface, ONE pad per ANCHOR (1:1 with the
    region-tilt lane). Tap/hold emit anchor-indexed signals the app routes to
    RegionTapController → the panel's existing region path. This is the ONLY
    gesture→engine path; it addresses the region lane and nothing else.

The two grids are separate because the material DISPLAY keys on source track
(what provenance carries) while the TAP keys on anchor (what the region lane
addresses); no track→anchor join is fabricated (see model.py disclosure).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ets.instrument.model import PadModel, track_palette


class TrackPadGrid(QWidget):
    """Display pads, one per source track, lit from a PadModel. No signals out."""

    def __init__(self, model: Optional[PadModel] = None, parent=None) -> None:
        super().__init__(parent)
        self.model = model if model is not None else PadModel()
        self.setMinimumSize(160, 160)
        self.setToolTip("MATERIAL PADS — one per source track; lights and colour "
                        "come from the provenance the engine already emits "
                        "(display only).\n\ninternal: provenance src_track light-up")

    def _grid(self, n: int):
        cols = max(1, int(n ** 0.5 + 0.999))
        rows = max(1, (n + cols - 1) // cols)
        return rows, cols

    def paintEvent(self, _ev) -> None:
        qp = QPainter(self)
        tracks = self.model.tracks
        n = len(tracks)
        if n == 0:
            qp.setPen(QPen(Qt.gray, 1))
            qp.drawText(6, 16, "no material yet")
            qp.end()
            return
        rows, cols = self._grid(n)
        w = self.width() / cols
        h = self.height() / rows
        for k, t in enumerate(tracks):
            r, c = divmod(k, cols)
            x, y = c * w, r * h
            cr, cg, cb = track_palette(t)
            lit = self.model.activity.get(t, 0.0)
            base = QColor(cr, cg, cb)
            base.setAlphaF(0.20 + 0.80 * max(0.0, min(1.0, lit)))
            qp.fillRect(int(x) + 2, int(y) + 2, int(w) - 4, int(h) - 4, base)
            qp.setPen(QPen(Qt.black, 1))
            qp.drawRect(int(x) + 2, int(y) + 2, int(w) - 4, int(h) - 4)
            qp.drawText(int(x) + 6, int(y) + 16, f"T{t}")
        qp.end()


class RegionTapPads(QWidget):
    """Tap/hold surface — one pad per anchor (region lane). Click = TAP (transient
    spike), press-and-hold = HOLD, release = ease. Emits anchor-indexed gestures;
    the app routes them through RegionTapController to the panel region path."""

    tapped = Signal(int)     # anchor
    held = Signal(int)       # anchor (mouse held down beyond the tap threshold)
    released = Signal(int)   # anchor

    def __init__(self, n_anchors: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._K = int(n_anchors)
        self._pressed: Optional[int] = None
        self._values = {}
        self.setMinimumSize(160, 90)
        self.setToolTip("REGION TAP PADS — a transient (tap) or held spike on the "
                        "existing region-tilt lane; the machine still settles.\n\n"
                        "internal: region-tilt lane (u_region[anchor]) spike")

    def set_anchor_count(self, K: int) -> None:
        self._K = int(K)
        self.update()

    def set_value(self, anchor: int, value: float) -> None:
        self._values[int(anchor)] = float(value)
        self.update()

    def _anchor_at(self, x: float) -> Optional[int]:
        if self._K <= 0:
            return None
        i = int(x / (self.width() / self._K))
        return i if 0 <= i < self._K else None

    def mousePressEvent(self, ev) -> None:
        a = self._anchor_at(ev.position().x())
        if a is not None:
            self._pressed = a
            self.tapped.emit(a)      # a click is at least a transient tap
        ev.accept()

    def mouseReleaseEvent(self, ev) -> None:
        if self._pressed is not None:
            self.released.emit(self._pressed)
            self._pressed = None
        ev.accept()

    def paintEvent(self, _ev) -> None:
        qp = QPainter(self)
        if self._K <= 0:
            qp.setPen(QPen(Qt.gray, 1))
            qp.drawText(6, 16, "no anchors yet")
            qp.end()
            return
        w = self.width() / self._K
        for i in range(self._K):
            x = i * w
            v = self._values.get(i, 0.0)
            col = QColor(60, 90, 200)
            col.setAlphaF(0.20 + 0.80 * min(1.0, abs(v) / 3.0))
            qp.fillRect(int(x) + 2, 2, int(w) - 4, self.height() - 4, col)
            qp.setPen(QPen(Qt.black, 1))
            qp.drawRect(int(x) + 2, 2, int(w) - 4, self.height() - 4)
            qp.drawText(int(x) + 6, 16, str(i))
        qp.end()
