"""The CONNECTED, playable INSTRUMENT window (ui-v6, live):

    python -m ets.instrument.live --engine-port 9000

One process that (a) speaks the panel's existing outbound OSC to a running
engine and (b) receives the engine's read-only telemetry on an ephemeral port it
announces via /ets/hello. The play surface is THE FIELD (`FieldView`): one
unified surface of squares you push (hover-scroll bias) and zoom (drill), which
REPLACES the ui-v5 role-pad grid, the XY/vector pad, and the drill-in overlay.

Composition law (unchanged from ui-v5): this module imports ets.panel (the
control surface) + the instrument widgets + ets.instrument.feed, and NOTHING
from the trained object (render/engine/writer/functional/geometry). It reads
telemetry and paints; the ONE thing that leaves for the engine is the field's
composite region bias, routed through the panel's EXISTING region path:

    FieldView.bias_changed -> FieldModel.region_vector()
                           -> panel.set_region_vector(...)   (clamp + slew)
                           -> /ets/lanes  (the region-tilt lane)

There is no second engine channel: a field gesture reaches the engine ONLY as a
region-tilt lean on that one outbound message. The machine RE-SETTLES around
the bias; the squares' fills then show the engine's answer from the read-only
telemetry (FIELD-INV: brightness = settled weight, never the input echoed).

Threading discipline (unchanged): the telemetry server runs on a daemon thread
and writes ONLY into plain Python inboxes; a single GUI QTimer drains those
inboxes into the FieldModel via its capability-guarded telemetry writer and
completes the panel's outbound region slew. No widget is touched off the GUI
thread.

P6 (display honesty): brightness holds the LAST REAL telemetry read between
frames — a sample-and-hold of real data, never a UI-side decay/fade toward
some other value (papers/paper1 §3 C': any UI easing/damping is a
falsification of the display). If telemetry arrives slower than the GUI tick,
the square/pad simply keeps showing the last frame the engine actually sent
until the next one lands.

Native Qt + OSC only. No web tech (I-13).
"""
from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional

from ets.instrument.cue import CueMonitor
from ets.instrument.feed import TelemetryReceiver
from ets.instrument.field import FieldModel, FieldView
from ets.instrument.library import TrackLibraryBrowser
from ets.instrument.model import PadModel, TapeModel
from ets.instrument.tape import TapeView
from ets.instrument.transport import Transport


class LiveInstrument:
    """Owns the window, the connected panel, and the telemetry receiver, and
    wires the FIELD to the panel's region path. Kept as a plain object (not a
    QWidget subclass) so the wiring reads top-to-bottom; the visible container
    is `self.window`."""

    def __init__(self, engine_host: str, engine_port: int,
                 meters_port: int = 0, n_anchors: int = 0) -> None:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import (
            QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
        )
        from ets.panel.transport import OscEmitter, build_meter_dispatcher
        from ets.panel.widget import Panel

        # --- connected control surface (the one outbound boundary channel) ----
        self.emitter = OscEmitter(host=engine_host, port=engine_port)
        self.panel = Panel(emitter=self.emitter, n_anchors=n_anchors)
        # The FIELD is the region surface. The panel's REGION vector strips are
        # hidden (not deleted — they stay constructed, keep mirroring region
        # values, and remain the §8-exhaustive region control). Region tilt
        # still flows only through the SAME region-tilt lane / _push path.
        self.panel.hide_region_strips()

        # --- live display state (plain inboxes; GUI timer drains them) --------
        self.field_model = FieldModel()
        self._field_writer = self.field_model.telemetry_writer()
        self.pad_model = PadModel()            # feeds the library browser dots
        self.tape_model = TapeModel()
        self.transport = Transport()
        self.role_unit_counts: Dict[int, int] = {}
        self._inbox_roleactivity: Optional[List[float]] = None
        self._inbox_nowplaying: Optional[Dict[int, float]] = None
        self._inbox_profiles: Optional[Dict[int, List[float]]] = None
        self._inbox_unitpools: List = []
        self._want_K: Optional[int] = None
        # CUE audition bus: unchanged ui-v5 semantics + disclosed wall (the
        # produced audio + source bank live in the ENGINE process; the cue
        # records audition intent, never touches main-out, never re-renders).
        self.cue = CueMonitor()
        self._meter_dispatch = build_meter_dispatcher(self.panel.meter_state)

        # --- telemetry receiver (announced to the engine in /ets/hello) -------
        self.receiver = TelemetryReceiver(
            on_roleactivity=self._feed_roleactivity,
            on_rolemeta=self._feed_rolemeta,
            on_unitpool=self._feed_unitpool,
            on_nowplaying=self._feed_nowplaying,
            on_profiles=self._feed_profiles,
            on_meter=self._feed_meter,
            host="127.0.0.1", port=meters_port)

        # --- widgets ----------------------------------------------------------
        self.window = QWidget()
        self.window.setWindowTitle("ETS instrument (live)")
        root = QVBoxLayout(self.window)

        # PRIMARY (and only) play surface: THE FIELD.
        self.field = FieldView(self.field_model, self.window)
        self.field.setMinimumSize(360, 260)
        root.addWidget(QLabel(
            "THE FIELD — hover+scroll to bias, Ctrl+scroll/pinch to zoom",
            self.window))
        root.addWidget(self.field, 3)

        # CUE toggle for unit auditions (same semantics as the ui-v5 drill CUE).
        self._cue_btn = QPushButton("CUE", self.window)
        self._cue_btn.setCheckable(True)
        self._cue_btn.setToolTip(
            "CUE: a click on a UNIT square routes to PRIVATE audition intent "
            "instead of nothing (never touches main-out).")
        self._cue_btn.toggled.connect(self.on_cue_toggled)
        root.addWidget(self._cue_btn)

        # control surface (scalar lanes + tolerances + meters).
        root.addWidget(self.panel)

        # secondary SOURCE LIBRARY browser (display-only) + the output tape.
        mid = QHBoxLayout()
        self.track_library = TrackLibraryBrowser(self.pad_model, self.window)
        self.tape_view = TapeView(self.tape_model, self.window)
        mid.addWidget(self.track_library, 1)
        mid.addWidget(self.tape_view, 2)
        root.addLayout(mid)

        # transport row (playhead over produced output; never re-settles a bar).
        ctl = QHBoxLayout()
        self._play = QPushButton("PLAY", self.window)
        self._pause = QPushButton("PAUSE", self.window)
        self._stop = QPushButton("STOP", self.window)
        self._play.clicked.connect(self.transport.play)
        self._pause.clicked.connect(self.transport.pause)
        self._stop.clicked.connect(self.transport.stop)
        self._pos = QLabel("t 0.00s", self.window)
        for wdg in (self._play, self._pause, self._stop, self._pos):
            ctl.addWidget(wdg)
        root.addLayout(ctl)

        # wrap all content in a scroll area so nothing is unreachable off-screen.
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.window)
        self.scroll.setWidgetResizable(True)
        self.scroll.setWindowTitle("ETS instrument (live)")
        self.scroll.resize(600, 900)

        # --- gesture wiring: field -> panel's EXISTING region path ------------
        self.field.bias_changed.connect(self.push_field_bias)
        self.field.unit_clicked.connect(self.on_unit_clicked)

        # --- single GUI timer: drain inboxes, breathe lights, finish slew -----
        self._timer = QTimer(self.window)
        self._timer.timeout.connect(self._on_tick)
        self._tick_ms = 33
        self._timer.start(self._tick_ms)

    # === region biasing (the ONLY engine-bound gesture) ======================
    def push_field_bias(self) -> None:
        """Route the field's composite bias through the panel's EXISTING
        whole-vector region path. The panel clamps to the safe envelope and
        slews the emitted glide, so the writer still settles — the field is a
        steering surface over the sanctioned tilt lane, not a new authority
        (FIELD-D)."""
        K = self.panel.u.n_anchors
        if K > 0:
            self.panel.set_region_vector(self.field_model.region_vector(K))

    def on_cue_toggled(self, on: bool) -> None:
        self.cue.set_active(bool(on))
        if not on:
            self.cue.clear_audition()

    def on_unit_clicked(self, key: tuple) -> None:
        """A UNIT square was clicked. With CUE on, record the audition intent
        (by source track — the honest subset, disclosed ui-v5 wall). With CUE
        off a click is inert: the ONE steering gesture is hover-scroll bias."""
        if self.cue.active and len(key) == 4:
            self.cue.audition(int(key[3]))

    # === telemetry inboxes (called on the receiver thread; data only) ========
    def _feed_roleactivity(self, levels: List[float]) -> None:
        self._inbox_roleactivity = levels
        if levels:
            self._want_K = len(levels)

    def _feed_rolemeta(self, counts: List[int]) -> None:
        self.role_unit_counts = {i: int(c) for i, c in enumerate(counts)}

    def _feed_unitpool(self, role: int, units: List[dict]) -> None:
        self._inbox_unitpools.append((int(role), list(units)))

    def _feed_nowplaying(self, activity: Dict[int, float]) -> None:
        self._inbox_nowplaying = activity

    def _feed_profiles(self, profiles: Dict[int, List[float]]) -> None:
        self._inbox_profiles = {int(t): [float(x) for x in v]
                                for t, v in profiles.items()}
        ks = [len(v) for v in self._inbox_profiles.values() if v]
        if ks:
            self._want_K = max(ks)

    def _feed_meter(self, address: str, *args) -> None:
        for handler in self._meter_dispatch.handlers_for_address(address):
            handler.invoke(address, args)

    # === GUI tick: the only place widgets are touched ========================
    def _on_tick(self) -> None:
        # grow the world to the telemetry's K (widget op — GUI thread only).
        if self._want_K is not None and self._want_K != self.panel.u.n_anchors:
            self.panel.set_anchor_count(self._want_K)

        # drain telemetry inboxes into the field via its CAPABILITY-GUARDED
        # writer (the one legitimate brightness path — FIELD-INV). No decay: a
        # square/pad not refreshed this tick simply KEEPS its last real engine
        # read (sample-and-hold of real data) until the next telemetry frame —
        # never a fade toward some other value (P6: no UI-side easing/damping
        # of a settlement-backed display value).
        act = self._inbox_roleactivity
        if act is not None:
            self._field_writer.apply_roleactivity(act)
            self._inbox_roleactivity = None
        npa = self._inbox_nowplaying
        if npa is not None:
            self._field_writer.apply_nowplaying(npa)
            self.pad_model.set_activity(npa)        # library browser dots
            self._inbox_nowplaying = None
        profs = self._inbox_profiles
        if profs is not None:
            self._field_writer.apply_profiles(profs)
            self._inbox_profiles = None
        while self._inbox_unitpools:
            role, units = self._inbox_unitpools.pop(0)
            self._field_writer.apply_unitpool(role, units)
        self.track_library.sync()
        self.field.update()

        # advance the playhead over produced output (no re-settle).
        pos = self.transport.tick(self._tick_ms / 1000.0)
        self.tape_model.set_playhead(pos)
        self._pos.setText(f"t {self.transport.seconds:.2f}s")
        self.tape_view.update()

        # read-only meters + complete any in-flight outbound region slew (the
        # panel's own single emit path; a no-op once converged).
        self.panel.refresh_meters()
        self.panel.tick_slew()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m ets.instrument.live",
        description="ETS connected instrument — THE FIELD + panel, OSC to engine")
    ap.add_argument("--engine-host", default="127.0.0.1")
    ap.add_argument("--engine-port", type=int, default=9000,
                    help="engine OSC control port (lanes/tolerances/hello)")
    ap.add_argument("--meters-port", type=int, default=0,
                    help="local telemetry-receiver UDP port (0 = ephemeral)")
    ap.add_argument("--anchors", type=int, default=0,
                    help="initial role/anchor count (grown by telemetry K)")
    ap.add_argument("--smoke", action="store_true",
                    help="construct, feed one telemetry frame, bias+zoom, exit 0")
    args = ap.parse_args(argv)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    inst = LiveInstrument(engine_host=args.engine_host, engine_port=args.engine_port,
                          meters_port=args.meters_port, n_anchors=args.anchors)
    inst.receiver.start()
    print(f"[live] telemetry receiver on udp:{inst.receiver.bound_host}:"
          f"{inst.receiver.bound_port}")
    print(f"[live] HELLO -> {args.engine_host}:{args.engine_port} "
          f"(meters_port={inst.receiver.bound_port})")
    inst.emitter.emit_hello(inst.receiver.bound_port)

    inst.scroll.show()
    if args.smoke:
        # feed one telemetry frame (K=3) through the REAL receiver parse,
        # apply it via a GUI tick, then simulate a bias + a zoom drill.
        inst.receiver._handle_roleactivity("/ets/roleactivity", 0.9, 0.2, 0.5)
        inst.receiver._handle_rolemeta("/ets/rolemeta", 4, 2, 3)
        inst.receiver._handle_nowplaying("/ets/nowplaying", 0, 0.8, 7, 0.3)
        inst.receiver._handle_profiles(
            "/ets/profiles", 0, 0.7, 0.2, 0.1, 7, 0.1, 0.2, 0.7)
        inst.receiver._handle_unitpool(
            "/ets/unitpool", 0, 3,
            0, 0, 2, 0.6, 0.3, 0.1,
            5, 7, 4, 0.2, 0.2, 0.6)
        inst._on_tick()                 # apply K=3 + settled fills (GUI thread)
        inst.field_model.add_bias(("role", 0), 0.5)
        inst.push_field_bias()          # -> panel region path -> /ets/lanes
        zoomed = inst.field.zoom_into(("track", 0)) if \
            inst.field.model.track_squares() else False
        inst.window.repaint()
        app.processEvents()
        routed = inst.emitter.last_args is not None
        print(f"[live] smoke ok (K={inst.panel.u.n_anchors}, "
              f"bias_emitted_region_lanes={routed}, zoom_into_track0={zoomed}, "
              f"squares={len(inst.field.current_squares())}, "
              f"lanes={list(inst.panel.lane_control_ids)})")
        inst.receiver.stop()
        return 0 if routed else 1
    try:
        return app.exec()
    finally:
        inst.receiver.stop()


if __name__ == "__main__":
    raise SystemExit(main())
