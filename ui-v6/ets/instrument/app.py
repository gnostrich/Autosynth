"""The INSTRUMENT window (ui-v6): the existing panel + THE FIELD + tape view +
transport + cue, wired together. Native Qt only (I-13).

The FIELD replaces the ui-v5 pad grid + tap surface in this monitor window too:
one surface of squares, fills fed ONLY from the MonitorState a feeder (offline
render provenance, out of this package) populates — via the field model's
capability-guarded telemetry writer (FIELD-INV). The ONLY gesture that leaves
for the engine is the field's composite bias, routed:

    FieldView.bias_changed -> FieldModel.region_vector()
                           -> panel.set_region_vector -> /ets/lanes

Composition law: this module imports ets.panel (the control surface) and the
instrument widgets, and NOTHING from the trained object (render/engine/writer/
functional/geometry).

Offline honesty: this monitor is fed from provenance (per-track activity); no
role-activity or profile telemetry exists here, so ROLE squares appear with the
world's public anchor count K but glow only if a feeder supplies levels, and
TRACK squares carry no profile (rendered ATOMIC — no fake drill affordance).
The connected instrument (ets.instrument.live) is the full-depth field.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ets.instrument.cue import CueMonitor
from ets.instrument.field import FieldModel, FieldView
from ets.instrument.model import MonitorState
from ets.instrument.tape import TapeView
from ets.instrument.transport import Transport


class InstrumentWindow(QWidget):
    def __init__(self, panel, monitor: Optional[MonitorState] = None,
                 n_anchors: int = 0, tick_ms: int = 33, parent=None) -> None:
        super().__init__(parent)
        self.panel = panel
        self.monitor = monitor if monitor is not None else MonitorState()
        self.transport = Transport()
        self.cue = CueMonitor()
        self._tick_s = tick_ms / 1000.0

        root = QVBoxLayout(self)
        root.addWidget(self.panel)

        # THE FIELD (display fed from the monitor's provenance-derived
        # activity) + tape/now-playing view.
        self.field_model = FieldModel()
        self._field_writer = self.field_model.telemetry_writer()
        if n_anchors > 0:
            # structural init from the world's PUBLIC anchor count: real roles,
            # zero glow until a feeder supplies settled levels (real-or-absent).
            self._field_writer.apply_roleactivity([0.0] * int(n_anchors))
        mid = QHBoxLayout()
        self.field = FieldView(self.field_model, self)
        self.tape_view = TapeView(self.monitor.tape, self)
        mid.addWidget(self.field)
        mid.addWidget(self.tape_view, 2)
        root.addLayout(mid)

        # field bias -> the ONE sanctioned engine path (panel region lane).
        self.field.bias_changed.connect(self._push_field_bias)

        # transport + cue controls.
        ctl = QHBoxLayout()
        self._play = QPushButton("PLAY", self)
        self._pause = QPushButton("PAUSE", self)
        self._stop = QPushButton("STOP", self)
        self._play.clicked.connect(self.transport.play)
        self._pause.clicked.connect(self.transport.pause)
        self._stop.clicked.connect(self.transport.stop)
        self._cue_on = QCheckBox("CUE (frontier monitor)", self)
        self._cue_on.toggled.connect(self.cue.set_active)
        self._pos = QLabel("t 0.00s", self)
        for wdg in (self._play, self._pause, self._stop, self._cue_on, self._pos):
            ctl.addWidget(wdg)
        root.addLayout(ctl)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(tick_ms)

    def set_anchor_count(self, K: int) -> None:
        self._field_writer.apply_roleactivity([0.0] * int(K))

    def _push_field_bias(self) -> None:
        K = self.panel.u.n_anchors
        if K > 0:
            self.panel.set_region_vector(self.field_model.region_vector(K))

    def _on_tick(self) -> None:
        dt = self._tick_s
        # feed the field from the monitor's provenance-derived per-track
        # activity (the capability-guarded path), then advance the playhead.
        self._field_writer.apply_nowplaying(dict(self.monitor.pads.activity))
        pos = self.transport.tick(dt)
        self.monitor.tape.set_playhead(pos)
        self._pos.setText(f"t {self.transport.seconds:.2f}s")
        self.field.update()
        self.tape_view.update()


def main(argv=None) -> int:
    """Headless smoke: build the instrument window against an EMPTY monitor
    (no engine, no trained-object import), paint one offscreen frame, exit 0."""
    import argparse
    import sys

    from PySide6.QtWidgets import QApplication
    from ets.panel.widget import Panel

    ap = argparse.ArgumentParser(prog="python -m ets.instrument.app")
    ap.add_argument("--anchors", type=int, default=3)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    panel = Panel(emitter=None, n_anchors=args.anchors)
    win = InstrumentWindow(panel, n_anchors=args.anchors)
    win.setWindowTitle("ETS instrument")
    win.show()
    if args.smoke:
        win.repaint()
        app.processEvents()
        print(f"[instrument] smoke ok (anchors={args.anchors}, "
              f"squares={len(win.field.current_squares())}, "
              f"lanes={list(panel.lane_control_ids)})")
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
