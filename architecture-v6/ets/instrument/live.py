"""The CONNECTED, playable INSTRUMENT window (F3, live):

    python -m ets.instrument.live --engine-port 9000

One process that (a) speaks the panel's existing outbound OSC to a running
engine and (b) receives the engine's read-only telemetry on an ephemeral port it
announces via /ets/hello. The play surface is the ROLE grid (`RegionTapPads`),
one pad per anchor/role, lit live from /ets/roleactivity.

Composition law (same as ets.instrument.app): this module imports ets.panel (the
control surface) + the instrument widgets + ets.instrument.feed, and NOTHING from
the trained object (render/engine/writer/functional/geometry). It reads telemetry
and paints; the ONE gesture that leaves for the engine is the role tap/hold,
routed through the panel's EXISTING region path:

    RegionTapPads.tapped/held/released(anchor) -> panel.tap_region_anchor(anchor,·)
                                                -> /ets/lanes  (the region-tilt lane)

Role i == region index i, so a role tap is a DIRECT spike on u_region[i]; no
anchor-profile join is invented. There is no second engine channel: a pad gesture
reaches the engine ONLY as a region-tilt spike on that one outbound message.

Threading discipline (mirrors ets.panel.__main__): the telemetry server runs on a
daemon thread and writes ONLY into plain Python inboxes; a single GUI QTimer reads
those inboxes, applies them to the widgets, decays the lights, and completes the
panel's outbound region slew. No widget is touched off the GUI thread.

Native Qt + OSC only. No web tech (I-13).
"""
from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional

from ets.instrument.cue import CueMonitor
from ets.instrument.feed import TelemetryReceiver
from ets.instrument.model import PadModel, TapeModel
from ets.instrument.pads import RegionTapPads, TrackPadGrid, UnitLayerView
from ets.instrument.tape import TapeView
from ets.instrument.transport import Transport


class LiveInstrument:
    """Owns the window, the connected panel, and the telemetry receiver, and
    wires the role grid to the panel's region path. Kept as a plain object (not a
    QWidget subclass) so the wiring reads top-to-bottom; the visible container is
    `self.window`."""

    def __init__(self, engine_host: str, engine_port: int,
                 meters_port: int = 0, n_anchors: int = 0) -> None:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import (
            QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
            QVBoxLayout, QWidget,
        )
        from ets.panel.transport import OscEmitter, build_meter_dispatcher
        from ets.panel.widget import Panel

        # --- connected control surface (the one outbound boundary channel) ----
        self.emitter = OscEmitter(host=engine_host, port=engine_port)
        self.panel = Panel(emitter=self.emitter, n_anchors=n_anchors)

        # --- live display state (plain inboxes; GUI timer drains them) --------
        self.pad_model = PadModel()
        self.tape_model = TapeModel()
        self.transport = Transport()
        self.profiles: Dict[int, List[float]] = {}
        self.role_unit_counts: Dict[int, int] = {}
        self.unit_pools: Dict[int, List[dict]] = {}    # role -> its drill-in pool
        self._inbox_roleactivity: Optional[List[float]] = None
        self._inbox_nowplaying: Optional[Dict[int, float]] = None
        self._want_K: Optional[int] = None
        # CUE audition bus (F3.5): a read-only cue monitor. In this CONNECTED
        # instrument the produced audio + the source-unit bank live in the ENGINE
        # process, so the cue bus records the audition intent but has no buffer to
        # sound here — a DISCLOSED WALL (see the module report). It never touches
        # main-out and never re-renders; toggling CUE only reroutes a unit tap.
        self.cue = CueMonitor()
        # meter telemetry flows into the panel's own read-only MeterState via its
        # existing dispatcher — no new meter logic, and it can reach no emitter.
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

        # PRIMARY play surface: the role/anchor grid, prominent.
        self.role_pads = RegionTapPads(n_anchors, self.window)
        self.role_pads.setMinimumSize(360, 180)
        root.addWidget(QLabel("ROLE PADS — tap to steer, tap-HOLD to drill", self.window))
        root.addWidget(self.role_pads, 3)

        # drill-in overlay for one role (hidden until a drill fires).
        self.unit_layer = UnitLayerView(parent=self.window)
        self.unit_layer.setVisible(False)
        self.unit_layer.unit_tapped.connect(self.on_unit_tapped)
        self.unit_layer.cue_toggled.connect(self.on_cue_toggled)
        self.unit_layer.closed.connect(self.close_unit_layer)
        root.addWidget(self.unit_layer, 1)

        # control surface (region vector control + tolerances + meters).
        root.addWidget(self.panel)

        # secondary per-track material pads + the output tape, side by side.
        mid = QHBoxLayout()
        self.track_pads = TrackPadGrid(self.pad_model, self.window)
        self.tape_view = TapeView(self.tape_model, self.window)
        mid.addWidget(self.track_pads, 1)
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

        # wrap all content in a scroll area so nothing is unreachable off-screen
        # (the role pads, drill view, panel, tape and transport can exceed one
        # screen); resizable, with a sane default size.
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.window)
        self.scroll.setWidgetResizable(True)
        self.scroll.setWindowTitle("ETS instrument (live)")
        self.scroll.resize(600, 900)

        # --- gesture wiring: role grid -> panel's EXISTING region path --------
        self.role_pads.tapped.connect(self.steer_anchor)
        self.role_pads.held.connect(self.steer_anchor)      # sustain the lean
        self.role_pads.released.connect(self.ease_anchor)   # ease home
        self.role_pads.drill.connect(self.open_unit_layer)
        # CLICK-AWAY: interacting with the coarse role pads dismisses an open
        # drill (returns to the 5 play-pads). A tap fires before the 350 ms drill,
        # so this never blocks re-opening; it just makes a re-tap shallow-close.
        self.role_pads.tapped.connect(self._click_away)

        # --- single GUI timer: drain inboxes, breathe lights, finish slew -----
        self._timer = QTimer(self.window)
        self._timer.timeout.connect(self._on_tick)
        self._tick_ms = 33
        self._timer.start(self._tick_ms)

    # === region steering (the ONLY engine-bound gesture) =====================
    def steer_anchor(self, anchor: int) -> None:
        """Spike the region-tilt lane toward role `anchor`, DIRECTLY: role i is
        region index i, so this is `panel.tap_region_anchor(i, spike)` — the same
        public region path the panel already exposes, emitting on /ets/lanes and
        no other channel. The spike sits at the panel's safe envelope; the panel
        clamps + slews it, so the writer still settles."""
        from ets.panel.envelope import SAFE_REGION_MAGNITUDE
        a = int(anchor)
        if 0 <= a < self.panel.u.n_anchors:
            self.panel.tap_region_anchor(a, float(SAFE_REGION_MAGNITUDE))

    def ease_anchor(self, anchor: int) -> None:
        """Release: ease that role's tilt back to neutral through the SAME region
        path (the panel's outbound slew ramps it down, no discontinuity)."""
        a = int(anchor)
        if 0 <= a < self.panel.u.n_anchors:
            self.panel.tap_region_anchor(a, 0.0)

    def open_unit_layer(self, anchor: int) -> None:
        """Tap-HOLD drill: expand role `anchor` into its UNIT POOL (from the
        read-only /ets/unitpool telemetry) as mini-cells coloured by source
        track. Pure display — opens no engine channel."""
        a = int(anchor)
        pool = self.unit_pools.get(a, [])
        self.unit_layer.set_role(a, pool)
        self.unit_layer.setVisible(True)

    def close_unit_layer(self) -> None:
        """Shallow-close the drill and return to the 5 play-pads. Clears any cue
        audition so a closed drill leaves the cue bus idle."""
        self.unit_layer.setVisible(False)
        self.cue.clear_audition()

    def _click_away(self, _anchor: int) -> None:
        # isHidden() is the explicit show/hide flag (True only when we hid it),
        # independent of whether a top-level window is currently shown.
        if not self.unit_layer.isHidden():
            self.close_unit_layer()

    # === unit-in-drill FINE steer / cue (the ONLY new gesture surface) ========
    def on_cue_toggled(self, on: bool) -> None:
        """CUE toggle: ON routes a unit tap to private audition; OFF routes it to
        a FINE steer. Toggling OFF also clears the cue audition."""
        self.cue.set_active(bool(on))
        if not on:
            self.cue.clear_audition()

    def on_unit_tapped(self, index: int) -> None:
        """A unit cell in the drilled role was tapped. CUE OFF → FINE STEER; CUE
        ON → private cue audition. `index` is the cell's index into the role's
        /ets/unitpool pool."""
        role = self.unit_layer.role
        pool = self.unit_pools.get(role, [])
        if not (0 <= index < len(pool)):
            return
        rec = pool[index]
        if self.cue.active:
            self.audition_unit(rec)
        else:
            self.steer_unit(rec)

    def steer_unit(self, rec: dict) -> None:
        """FINE STEER: lean the region toward THIS unit's anchor-profile
        (rec['profile'] = the frozen B[:, band] 5-vector), peak-NORMALIZED and
        scaled to SAFE_REGION_MAGNITUDE, via the panel's EXISTING whole-vector
        region path (`set_region_vector`). This is NOT clamping/force-one-unit: it
        sets a soft lean over ALL roles in the unit's true proportions, so the
        writer favours that unit AND its neighbours (breathing brings friends).
        A unit tap reaches the engine ONLY as this region-tilt lean."""
        from ets.panel.envelope import SAFE_REGION_MAGNITUDE
        import numpy as np
        prof = np.asarray(rec.get("profile", ()), dtype=np.float32).reshape(-1)
        peak = float(np.max(np.abs(prof))) if prof.size else 0.0
        if peak <= 0.0:
            return
        vec = (prof / peak) * np.float32(SAFE_REGION_MAGNITUDE)
        self.panel.set_region_vector(vec)

    def audition_unit(self, rec: dict) -> None:
        """CUE audition: route this unit's SOURCE TRACK to the private cue bus.
        DISCLOSED WALL: the source-unit bank and the produced audio live in the
        ENGINE process, so this connected instrument holds no buffer to sound and
        cannot isolate a single unit's audio; the cue records the audition intent
        (by source track, the honest subset the cue-buffer path supports) and
        never touches main-out or re-renders. A real private audition needs an
        engine-side cue output (out of scope: engine edits are read-only
        telemetry) or the monitor app that holds produced audio (ets.instrument
        .app). This is exactly the cue-buffer fallback the task allows."""
        self.cue.set_active(True)
        self.cue.audition(int(rec.get("track_id", -1)))

    # === telemetry inboxes (called on the receiver thread; data only) ========
    def _feed_roleactivity(self, levels: List[float]) -> None:
        self._inbox_roleactivity = levels
        if levels:
            self._want_K = len(levels)

    def _feed_rolemeta(self, counts: List[int]) -> None:
        self.role_unit_counts = {i: int(c) for i, c in enumerate(counts)}

    def _feed_unitpool(self, role: int, units: List[dict]) -> None:
        # static, arrives once per role right after welcome; plain data only.
        self.unit_pools[int(role)] = list(units)

    def _feed_nowplaying(self, activity: Dict[int, float]) -> None:
        self._inbox_nowplaying = activity

    def _feed_profiles(self, profiles: Dict[int, List[float]]) -> None:
        self.profiles = {int(t): [float(x) for x in v] for t, v in profiles.items()}
        ks = [len(v) for v in self.profiles.values() if v]
        if ks:
            self._want_K = max(ks)

    def _feed_meter(self, address: str, *args) -> None:
        # route into the panel's read-only MeterState via its own dispatcher.
        for handler in self._meter_dispatch.handlers_for_address(address):
            handler.invoke(address, args)

    # === GUI tick: the only place widgets are touched ========================
    def _on_tick(self) -> None:
        # grow the world to the telemetry's K (widget op — GUI thread only).
        if self._want_K is not None and self._want_K != self.panel.u.n_anchors:
            self.panel.set_anchor_count(self._want_K)
            self.role_pads.set_anchor_count(self._want_K)

        # role-pad lights: apply the newest roleactivity frame, then breathe.
        act = self._inbox_roleactivity
        if act is not None:
            self.role_pads.set_role_activity(act)
            self._inbox_roleactivity = None
        else:
            self._decay_role_lights()

        # secondary per-track pads from the newest nowplaying frame.
        npa = self._inbox_nowplaying
        if npa is not None:
            self.pad_model.set_activity(npa)
            self._inbox_nowplaying = None
        self.pad_model.decay(0.90)
        self.track_pads.update()

        # drill cell breathing: no PER-UNIT sounding signal is emitted, so we
        # light each pool cell by its SOURCE TRACK's now-playing activity (the
        # per-track /ets/nowplaying feed). Track-level breathing, honestly not
        # per-unit; all cells of an active track brighten together.
        if self.unit_layer.isVisible():
            pool = self.unit_pools.get(self.unit_layer.role, [])
            self.unit_layer.set_activity(
                [self.pad_model.activity.get(int(u.get("track_id", -1)), 0.0)
                 for u in pool])

        # advance the playhead over produced output (no re-settle; F3-D).
        pos = self.transport.tick(self._tick_ms / 1000.0)
        self.tape_model.set_playhead(pos)
        self._pos.setText(f"t {self.transport.seconds:.2f}s")
        self.tape_view.update()

        # read-only meters + complete any in-flight outbound region slew (the
        # panel's own single emit path; a no-op once converged).
        self.panel.refresh_meters()
        self.panel.tick_slew()

    def _decay_role_lights(self) -> None:
        cur = list(getattr(self.role_pads, "_activity", []) or [])
        if cur:
            self.role_pads.set_role_activity([v * 0.90 for v in cur])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m ets.instrument.live",
        description="ETS connected instrument — role pads + panel, OSC to engine")
    ap.add_argument("--engine-host", default="127.0.0.1")
    ap.add_argument("--engine-port", type=int, default=9000,
                    help="engine OSC control port (lanes/tolerances/hello)")
    ap.add_argument("--meters-port", type=int, default=0,
                    help="local telemetry-receiver UDP port (0 = ephemeral)")
    ap.add_argument("--anchors", type=int, default=0,
                    help="initial role/anchor count (grown by telemetry K)")
    ap.add_argument("--smoke", action="store_true",
                    help="construct, feed one telemetry frame, tap+drill, exit 0")
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
        # feed one /ets/roleactivity frame (K=3) through the REAL receiver parse,
        # apply it via a GUI tick, then simulate a role tap + a drill.
        inst.receiver._handle_roleactivity("/ets/roleactivity", 0.9, 0.2, 0.5)
        inst.receiver._handle_rolemeta("/ets/rolemeta", 4, 2, 3)
        inst.receiver._handle_nowplaying("/ets/nowplaying", 0, 0.8, 7, 0.3)
        inst.receiver._handle_profiles(
            "/ets/profiles", 0, 0.7, 0.2, 0.1, 7, 0.1, 0.2, 0.7)
        # a /ets/unitpool for role 0 (M=3): two units on two source tracks.
        inst.receiver._handle_unitpool(
            "/ets/unitpool", 0, 3,
            0, 0, 2, 0.6, 0.3, 0.1,       # unit 0, track 0, band 2, profile
            5, 7, 4, 0.2, 0.2, 0.6)       # unit 5, track 7, band 4, profile
        inst._on_tick()                 # apply K=3 + lights on the GUI thread
        inst.steer_anchor(0)            # simulate tapped(0) -> region path
        inst.open_unit_layer(0)         # simulate drill(0) -> unit layer
        inst.on_unit_tapped(0)          # CUE off: unit 0 -> FINE steer (region)
        inst.window.repaint()
        app.processEvents()
        routed = inst.emitter.last_args is not None
        print(f"[live] smoke ok (K={inst.panel.u.n_anchors}, "
              f"role_tap_emitted_region_lanes={routed}, "
              f"unit_pool_role0={len(inst.unit_pools.get(0, []))}, "
              f"unit_layer_visible={inst.unit_layer.isVisible()}, "
              f"lanes={list(inst.panel.lane_control_ids)})")
        inst.receiver.stop()
        return 0 if routed else 1
    try:
        return app.exec()
    finally:
        inst.receiver.stop()


if __name__ == "__main__":
    raise SystemExit(main())
