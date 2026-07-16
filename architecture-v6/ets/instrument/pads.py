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

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ets.instrument.model import PadModel, track_palette


class TrackPadGrid(QWidget):
    """Display pads, one per source track, lit from a PadModel.

    Lights/colour are PURE DISPLAY (read from the PadModel the engine feeds). The
    grid also emits TRACK-INDEXED tap signals so the operator can tap a sample to
    steer: it still touches no engine/writer/lane itself — the live app wires
    `tapped/held/released` into the region path (the single gesture→engine door).
    """

    tapped = Signal(int)     # source-track id under the cursor (a click = a tap)
    held = Signal(int)       # source-track id (press = start of a hold)
    released = Signal(int)   # source-track id (same pad the press started on)

    def __init__(self, model: Optional[PadModel] = None, parent=None) -> None:
        super().__init__(parent)
        self.model = model if model is not None else PadModel()
        self._pressed: Optional[int] = None
        self.setMinimumSize(160, 160)
        self.setToolTip("MATERIAL PADS — one per source track; lights and colour "
                        "come from the provenance the engine already emits. Tap a "
                        "pad to steer with that source track (routed to the region "
                        "path).\n\ninternal: provenance src_track light-up + tap")

    def _grid(self, n: int):
        cols = max(1, int(n ** 0.5 + 0.999))
        rows = max(1, (n + cols - 1) // cols)
        return rows, cols

    def _track_at(self, x: float, y: float) -> Optional[int]:
        """Source-track id of the pad under (x, y), using the same grid layout as
        paintEvent. Returns None if outside any pad."""
        tracks = self.model.tracks
        n = len(tracks)
        if n == 0:
            return None
        rows, cols = self._grid(n)
        w = self.width() / cols
        h = self.height() / rows
        if w <= 0 or h <= 0:
            return None
        c = int(x / w)
        r = int(y / h)
        if not (0 <= c < cols and 0 <= r < rows):
            return None
        k = r * cols + c
        return tracks[k] if 0 <= k < n else None

    def mousePressEvent(self, ev) -> None:
        t = self._track_at(ev.position().x(), ev.position().y())
        if t is not None:
            self._pressed = t
            self.tapped.emit(t)      # a click is at least a transient tap
            self.held.emit(t)        # and the start of a hold
        ev.accept()

    def mouseReleaseEvent(self, ev) -> None:
        if self._pressed is not None:
            self.released.emit(self._pressed)
            self._pressed = None
        ev.accept()

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
    drill = Signal(int)      # anchor — tap-HOLD to expand that role into its units

    HOLD_MS = 350            # press held this long (without release/move) → drill

    def __init__(self, n_anchors: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._K = int(n_anchors)
        self._pressed: Optional[int] = None
        self._values = {}
        self._activity: list[float] = []      # per-anchor light-up level 0..1
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.setInterval(self.HOLD_MS)
        self._hold.timeout.connect(self._fire_drill)
        self.setMinimumSize(160, 90)
        self.setToolTip("REGION TAP PADS — one pad per ROLE. Tap = a transient "
                        "spike on the region-tilt lane; tap-HOLD = drill into that "
                        "role's units. The machine still settles.\n\n"
                        "internal: region-tilt lane (u_region[anchor]) spike + drill")

    def set_anchor_count(self, K: int) -> None:
        self._K = int(K)
        self.update()

    def set_value(self, anchor: int, value: float) -> None:
        self._values[int(anchor)] = float(value)
        self.update()

    def set_role_activity(self, levels) -> None:
        """Per-anchor (per-ROLE) brightness 0..1 from a now-playing feed. levels[i]
        lights role-pad i; extra/short entries are tolerated (clamped/defaulted)."""
        self._activity = [float(min(1.0, max(0.0, v))) for v in levels]
        self.update()

    def _level(self, i: int) -> float:
        return self._activity[i] if 0 <= i < len(self._activity) else 0.0

    def _anchor_at(self, x: float) -> Optional[int]:
        if self._K <= 0:
            return None
        i = int(x / (self.width() / self._K))
        return i if 0 <= i < self._K else None

    def _fire_drill(self) -> None:
        if self._pressed is not None:
            self.drill.emit(self._pressed)

    def mousePressEvent(self, ev) -> None:
        a = self._anchor_at(ev.position().x())
        if a is not None:
            self._pressed = a
            self.tapped.emit(a)      # a click is at least a transient tap
            self.held.emit(a)        # and the start of a hold
            self._hold.start()       # → drill if held past HOLD_MS without move/up
        ev.accept()

    def mouseMoveEvent(self, ev) -> None:
        # A drag is a steer gesture, not a drill: cancel the pending hold.
        if self._pressed is not None and self._anchor_at(ev.position().x()) != self._pressed:
            self._hold.stop()
        ev.accept()

    def mouseReleaseEvent(self, ev) -> None:
        self._hold.stop()
        if self._pressed is not None:
            self.released.emit(self._pressed)
            self._pressed = None
        ev.accept()

    def paintEvent(self, _ev) -> None:
        qp = QPainter(self)
        if self._K <= 0:
            qp.setPen(QPen(Qt.gray, 1))
            qp.drawText(6, 16, "no roles yet")
            qp.end()
            return
        w = self.width() / self._K
        for i in range(self._K):
            x = i * w
            # brightness: role activity is the primary light-up; a tilt value gives
            # a floor so a steered-but-silent role still reads.
            lvl = max(self._level(i), min(1.0, abs(self._values.get(i, 0.0)) / 3.0))
            col = QColor(60, 90, 200)
            col.setAlphaF(0.20 + 0.80 * lvl)
            qp.fillRect(int(x) + 2, 2, int(w) - 4, self.height() - 4, col)
            qp.setPen(QPen(Qt.black, 1))
            qp.drawRect(int(x) + 2, 2, int(w) - 4, self.height() - 4)
            qp.drawText(int(x) + 6, 16, str(i))
        qp.end()


class UnitLayerView(QWidget):
    """Drill-in detail for ONE role: its units as a row/grid of small layer cells,
    coloured by role and lit by optional per-unit activity. Pure display — shown
    when RegionTapPads.drill(anchor) fires; emits no gesture."""

    def __init__(self, role: int = 0, n_units: int = 0, activity=None,
                 parent=None) -> None:
        super().__init__(parent)
        self._role = int(role)
        self._n = int(n_units)
        self._activity = list(activity) if activity is not None else []
        self.setMinimumSize(160, 72)
        self.setToolTip("UNIT LAYERS — the units inside the drilled role "
                        "(display only).")

    def set_role(self, role: int, n_units: int, activity=None) -> None:
        self._role = int(role)
        self._n = int(n_units)
        self._activity = list(activity) if activity is not None else []
        self.update()

    def _grid(self, n: int):
        cols = max(1, int(n ** 0.5 + 0.999))
        rows = max(1, (n + cols - 1) // cols)
        return rows, cols

    def _level(self, i: int) -> float:
        return (float(min(1.0, max(0.0, self._activity[i])))
                if 0 <= i < len(self._activity) else 0.0)

    def paintEvent(self, _ev) -> None:
        qp = QPainter(self)
        qp.setPen(QPen(Qt.gray, 1))
        qp.drawText(6, 14, f"role {self._role} — {self._n} units")
        if self._n <= 0:
            qp.end()
            return
        cr, cg, cb = track_palette(self._role)
        rows, cols = self._grid(self._n)
        top = 20
        w = self.width() / cols
        h = max(1.0, (self.height() - top) / rows)
        for k in range(self._n):
            r, c = divmod(k, cols)
            x, y = c * w, top + r * h
            col = QColor(cr, cg, cb)
            col.setAlphaF(0.20 + 0.80 * self._level(k))
            qp.fillRect(int(x) + 2, int(y) + 2, int(w) - 4, int(h) - 4, col)
            qp.setPen(QPen(Qt.black, 1))
            qp.drawRect(int(x) + 2, int(y) + 2, int(w) - 4, int(h) - 4)
            qp.drawText(int(x) + 5, int(y) + 15, str(k))
        qp.end()
