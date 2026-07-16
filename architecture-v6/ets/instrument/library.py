"""Source / library BROWSER for the connected instrument (F3, live).

`TrackLibraryBrowser` is a DISPLAY-ONLY list of the loaded source tracks — NOT a
tap grid. It reads the same read-only `PadModel` the engine already feeds and
paints, per source track, a vertical list row of:

  * a COLOUR SWATCH  — `track_palette(track_id)`, the tape-diagram colour;
  * a LABEL          — `T{id}`;
  * a NOW-PLAYING dot — driven by the PadModel's per-track activity (the same
                        /ets/nowplaying feed that breathes the material lights);
  * a SHOW/HIDE display-filter checkbox — a per-track BROWSER filter.

DISPLAY-ONLY LAW (the whole point of the re-role): this widget imports nothing
from the trained object and holds NO emitter / panel / lane handle. It drives no
gesture. The show/hide toggle is a pure BROWSER filter: unchecking a track only
collapses its row here; it NEVER tells the engine to exclude that source track —
there is no source-masking, no lane, no /ets/lanes emit, no engine authority of
any kind. A track hidden in the browser still sounds exactly as before, because
nothing about the produced audio can be reached from this module.

Native Qt only. No web tech (I-13).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from ets.instrument.model import PadModel, track_palette


# activity above this reads as "now playing" for the row's live dot.
_NOWPLAYING_THRESHOLD = 1e-3


class _TrackRow(QWidget):
    """One browser row for a source track. Pure display + a browser-local filter
    checkbox; it drives nothing outside this widget."""

    def __init__(self, track_id: int, parent=None) -> None:
        super().__init__(parent)
        self.track_id = int(track_id)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)

        cr, cg, cb = track_palette(self.track_id)
        self._swatch = QFrame(self)
        self._swatch.setFixedSize(16, 16)
        self._swatch.setStyleSheet(
            f"background-color: rgb({cr},{cg},{cb}); border: 1px solid #222;")

        self._label = QLabel(f"T{self.track_id}", self)
        self._label.setMinimumWidth(48)

        # the now-playing indicator — a coloured dot; brightness follows activity.
        self._dot = QLabel("●", self)      # ● filled circle
        self._dot.setMinimumWidth(18)
        self._dot.setToolTip("NOW PLAYING — lit from the track's live activity "
                             "(the /ets/nowplaying feed). Read-only.")

        # the SHOW/HIDE display filter. Checked = shown in this browser. Toggling
        # only re-paints THIS row; it reaches no engine (display-only).
        self._show = QCheckBox("show", self)
        self._show.setChecked(True)
        self._show.setToolTip("Show/hide this track in the browser (DISPLAY-ONLY "
                              "filter — does NOT mute or exclude the source; the "
                              "engine never hears this toggle).")

        lay.addWidget(self._swatch)
        lay.addWidget(self._label)
        lay.addWidget(self._dot)
        lay.addStretch(1)
        lay.addWidget(self._show)

        self.set_activity(0.0)

    @property
    def shown(self) -> bool:
        return self._show.isChecked()

    def set_shown(self, shown: bool) -> None:
        self._show.setChecked(bool(shown))

    def set_activity(self, level: float) -> None:
        """Paint the now-playing dot from the track's 0..1 activity. Purely
        cosmetic; drives nothing."""
        lvl = float(min(1.0, max(0.0, level)))
        playing = lvl > _NOWPLAYING_THRESHOLD
        if playing:
            c = QColor(60, 220, 90)
            c.setAlphaF(0.35 + 0.65 * lvl)
        else:
            c = QColor(90, 90, 90)
            c.setAlphaF(0.5)
        self._dot.setStyleSheet(f"color: rgba({c.red()},{c.green()},{c.blue()},"
                                f"{c.alpha()});")
        # a hidden track dims its detail (swatch/label) but keeps its toggle so it
        # can be restored — the row never disappears, so the filter is reversible.
        dim = not self.shown
        self._swatch.setVisible(not dim)
        self._dot.setVisible(not dim)
        self._label.setStyleSheet("color: #888;" if dim else "")


class TrackLibraryBrowser(QWidget):
    """A DISPLAY-ONLY vertical browser of loaded source tracks (see module docs).

    Reads a `PadModel`; owns no emitter and drives no lane. `sync()` (called from
    the instrument's GUI tick) adds a row for any newly-seen source track and
    refreshes each row's now-playing dot from the model's activity. The per-track
    show/hide checkbox is a browser filter only — `visible_tracks()` reflects it
    and nothing else does."""

    def __init__(self, model: Optional[PadModel] = None, parent=None) -> None:
        super().__init__(parent)
        self.model = model if model is not None else PadModel()
        self._rows: Dict[int, _TrackRow] = {}
        self.setMinimumSize(200, 160)
        self.setToolTip("SOURCE LIBRARY — the loaded source tracks. Each row: "
                        "colour swatch, T-id, a live now-playing dot, and a "
                        "show/hide display filter. Display-only: no engine path.")

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(2)
        self._header = QLabel("SOURCE LIBRARY", self)
        root.addWidget(self._header)
        self._list = QVBoxLayout()
        root.addLayout(self._list)
        root.addStretch(1)
        self._empty = QLabel("no source tracks yet", self)
        self._empty.setStyleSheet("color: #888;")
        self._list.addWidget(self._empty)

    def _ensure_row(self, track_id: int) -> _TrackRow:
        row = self._rows.get(track_id)
        if row is None:
            self._empty.setVisible(False)
            row = _TrackRow(track_id, self)
            self._rows[track_id] = row
            # insert before the trailing empty-placeholder slot.
            self._list.insertWidget(self._list.count() - 1, row)
        return row

    def sync(self) -> None:
        """Add rows for newly-seen tracks and refresh every row's now-playing dot
        from the PadModel's activity. Pure read + repaint; emits nothing."""
        for t in list(self.model.tracks):
            row = self._ensure_row(int(t))
            row.set_activity(self.model.activity.get(int(t), 0.0))

    # --- browser-local filter (display only) ---------------------------------
    def visible_tracks(self) -> List[int]:
        """Track ids whose show/hide filter is checked, in the model's stable
        order. This reflects ONLY the browser filter — it is never read by any
        engine-bound path."""
        return [int(t) for t in self.model.tracks
                if int(t) in self._rows and self._rows[int(t)].shown]

    def is_shown(self, track_id: int) -> bool:
        row = self._rows.get(int(track_id))
        return True if row is None else row.shown

    def set_shown(self, track_id: int, shown: bool) -> None:
        """Set a track's browser filter (display only). Re-paints the row; touches
        no engine, lane, or emitter."""
        row = self._rows.get(int(track_id))
        if row is not None:
            row.set_shown(shown)
            row.set_activity(self.model.activity.get(int(track_id), 0.0))
