"""PANEL process entry point (spec §12):  python -m ets.panel

Native PySide6 app, second process of the two-process architecture. Speaks the
closed OSC message space of ets.panel.osc_schema to the engine on localhost:

  outbound → engine :  /ets/lanes  /ets/tolerances  /ets/hello
  inbound  ← engine :  /ets/welcome  /ets/clock  /ets/meter/*

Handshake: on startup the panel opens its meter receiver on an ephemeral UDP
port and announces it via /ets/hello; the engine replies /ets/welcome with
(K anchors, world hash, declared latency L, bar seconds, sr) — the panel then
sizes its REGION strips to K and shows the link + latency in the status row.
Killing this process leaves the engine playing (the two-process law): the
panel holds no engine state, only display and control emission.

Headless CI: QT_QPA_PLATFORM=offscreen python -m ets.panel --smoke
constructs the full app, performs the handshake attempt, paints one frame
offscreen, and exits 0 — no display, no audio, no web tech (I-13).
"""
from __future__ import annotations
import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m ets.panel",
        description="ETS panel — native Qt control surface (OSC to the engine)")
    ap.add_argument("--engine-host", default="127.0.0.1")
    ap.add_argument("--engine-port", type=int, default=9000,
                    help="engine OSC control port (lanes/tolerances/hello)")
    ap.add_argument("--meters-port", type=int, default=0,
                    help="local meter-receiver UDP port (0 = ephemeral)")
    ap.add_argument("--anchors", type=int, default=0,
                    help="initial REGION strip count (grown by /ets/welcome)")
    ap.add_argument("--smoke", action="store_true",
                    help="construct, handshake, paint one offscreen frame, exit")
    args = ap.parse_args(argv)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from ets.panel.transport import MeterReceiver, OscEmitter
    from ets.panel.widget import Panel

    app = QApplication.instance() or QApplication(sys.argv[:1])
    emitter = OscEmitter(host=args.engine_host, port=args.engine_port)
    panel = Panel(emitter=emitter, n_anchors=args.anchors)
    panel.setWindowTitle("ETS panel")

    receiver = MeterReceiver(panel.meter_state, port=args.meters_port)
    receiver.start()
    print(f"[panel] meter receiver on udp:{receiver.bound_host}:"
          f"{receiver.bound_port}")
    print(f"[panel] HELLO -> {args.engine_host}:{args.engine_port} "
          f"(meters_port={receiver.bound_port})")
    emitter.emit_hello(receiver.bound_port)

    # display refresh: pull MeterState into the read-only jacks ~30 Hz. The
    # meter path stays one-way (I-5); this timer reads, never emits.
    timer = QTimer(panel)
    timer.timeout.connect(panel.refresh_meters)
    timer.start(33)

    panel.show()
    if args.smoke:
        panel.repaint()
        app.processEvents()
        connected = panel.meter_state.engine_K is not None
        print(f"[panel] smoke ok (lanes={list(panel.lane_control_ids)}, "
              f"tolerances={list(panel.tolerance_control_ids)}, "
              f"welcome_received={connected})")
        receiver.stop()
        return 0
    try:
        return app.exec()
    finally:
        receiver.stop()


if __name__ == "__main__":
    raise SystemExit(main())
