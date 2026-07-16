"""Tape / now-playing view (F3.3). Native Qt only (I-13).

`TapeView` paints the produced output tape from a `TapeModel`: committed past to
the left, the settled L-bar frontier to the right, the playhead marked, cells
coloured by source track from their existing provenance tag. The now-playing
strip is DRIVEN by provenance (TapeModel.now_playing), never recomputed from the
writer. Pure display: no signals out, no lane, no writer.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ets.instrument.model import TapeModel


class TapeView(QWidget):
    def __init__(self, model: Optional[TapeModel] = None, parent=None) -> None:
        super().__init__(parent)
        self.model = model if model is not None else TapeModel()
        self.setMinimumSize(320, 120)
        self.setToolTip("OUTPUT TAPE — committed left, settled frontier right, "
                        "playhead marked; cells coloured by source track from "
                        "provenance.\n\ninternal: provenance segments over output "
                        "samples")

    def _x(self, sample: int) -> float:
        n = max(1, self.model.n_samples)
        return self.width() * (sample / n)

    def paintEvent(self, _ev) -> None:
        qp = QPainter(self)
        m = self.model
        h = self.height()
        cell_h = int(h * 0.6)
        # frontier band (committed | settled-but-unplayed) backdrop.
        if m.n_samples > 0:
            fx = self._x(m.committed_samples)
            qp.fillRect(0, 0, int(fx), cell_h, QColor(245, 245, 245))
            qp.fillRect(int(fx), 0, self.width() - int(fx), cell_h,
                        QColor(230, 238, 250))    # L-bar frontier tint
        # cells, coloured by source track.
        for (_t, _u, a, b, (cr, cg, cb)) in m.cell_spans():
            xa, xb = self._x(a), self._x(b)
            qp.fillRect(int(xa), 0, max(1, int(xb - xa)), cell_h,
                        QColor(cr, cg, cb))
        # playhead.
        px = int(self._x(m.playhead))
        qp.setPen(QPen(Qt.red, 2))
        qp.drawLine(px, 0, px, cell_h)
        # now-playing readout (provenance-driven).
        qp.setPen(QPen(Qt.black, 1))
        np_tracks = m.now_playing_tracks()
        txt = "now: " + (", ".join(f"T{t}" for t in np_tracks) if np_tracks
                         else "(silence)")
        qp.drawText(6, cell_h + 18, txt)
        qp.end()
