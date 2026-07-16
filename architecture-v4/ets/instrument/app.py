"""The INSTRUMENT window (F3): the existing panel + the pad grid + tape view +
transport + cue, wired together. Native Qt only (I-13).

Composition law: this module imports ets.panel (the control surface) and the
instrument widgets, and NOTHING from the trained object (render/engine/writer/
functional/geometry). It receives a `MonitorState` that some feeder (the engine,
offline, out of this package) fills; the widgets READ it. The ONLY gesture that
leaves for the engine is the region tap/hold, routed:

    RegionTapPads → RegionTapController → panel.tap_region_anchor → /ets/lanes

Live provenance feed is a DISCLOSED WALL (see the Feature-3 report): streaming the
engine's provenance to this second process would need a new inbound OSC address,
which breaks the closed message space (H-6). So the tape/pad DISPLAY is fed from a
MonitorState that an offline render (or a future spec-revised feed) populates; the
window is fully functional against that, and the tap/transport/cue paths are live.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ets.instrument.cue import CueMonitor
from ets.instrument.model import MonitorState
from ets.instrument.pads import RegionTapPads, TrackPadGrid
from ets.instrument.tap import RegionTapController
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

        # material pads (display) + tape/now-playing view.
        mid = QHBoxLayout()
        self.pad_grid = TrackPadGrid(self.monitor.pads, self)
        self.tape_view = TapeView(self.monitor.tape, self)
        mid.addWidget(self.pad_grid)
        mid.addWidget(self.tape_view, 2)
        root.addLayout(mid)

        # region tap/hold surface → the ONE sanctioned engine path.
        self.tap_pads = RegionTapPads(n_anchors, self)
        self.tap = RegionTapController(
            n_anchors, region_sink=self.panel.tap_region_anchor)
        self.tap_pads.tapped.connect(self.tap.tap)
        self.tap_pads.held.connect(self.tap.hold)
        self.tap_pads.released.connect(self.tap.release)
        root.addWidget(self.tap_pads)

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
        self.tap_pads.set_anchor_count(K)
        self.tap.set_anchor_count(K)

    def _on_tick(self) -> None:
        dt = self._tick_s
        # ease the region tap envelopes onto the lane (the sanctioned path).
        self.tap.advance(dt)
        for i in range(self.tap.n_anchors):
            self.tap_pads.set_value(i, self.tap.value(i))
        # advance the playhead over produced output; refresh the display.
        pos = self.transport.tick(dt)
        self.monitor.tape.set_playhead(pos)
        self._pos.setText(f"t {self.transport.seconds:.2f}s")
        self.pad_grid.update()
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
              f"lanes={list(panel.lane_control_ids)})")
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
