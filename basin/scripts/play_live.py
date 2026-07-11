"""Native live player — no browser, no websocket, no canvas redraws.

The same PanelEngine the web panel uses, but audio goes straight to the
sound device and the faders are terminal commands. The engine measures
~6 ms/step; everything the browser adds (100 canvas redraws per frame,
WebSocket framing, AudioWorklet ring) is gone.

    python scripts/play_live.py [--instrument PATH] [--record out.wav]

Commands (type + enter):
    10 1.5        lean fader 10 to +1.5 sigma (any fader number)
    z             zero every lean
    j             jump (all voices leave their current track)
    g 1.2         gamma (restlessness)      t 0.8   tau (spread)
    c 0.5         couple (counterpoint mode)
    v ch3         toggle a channel voice on/off (counterpoint)
    v mix         toggle the mix voice
    s             status: what's playing, active leans, pacing
    clk           show the measured clock-carrying faders
    q             quit
"""
import argparse
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=os.path.join(
        os.path.dirname(__file__), ".."))
    ap.add_argument("--record", default=None,
                    help="also write the session to this wav")
    args = ap.parse_args()

    try:
        import sounddevice as sd
    except ImportError:
        print("needs the native audio backend once:  pip install sounddevice")
        sys.exit(1)

    from basin.panel.server import PanelEngine
    print("loading instrument ...")
    eng = PanelEngine(os.path.abspath(args.project))
    sr = eng.sr
    names = eng.track_names
    clk_tagged = sorted(
        [(k, c) for k, c in enumerate(getattr(eng, "clock_corr", []))
         if abs(c) >= 0.15], key=lambda x: -abs(x[1]))

    rec = None
    if args.record:
        import soundfile as sf
        rec = sf.SoundFile(args.record, "w", samplerate=sr, channels=2,
                           subtype="PCM_16")

    q: queue.Queue = queue.Queue(maxsize=4)   # ~4 steps of lookahead
    running = threading.Event()
    running.set()

    def produce():
        while running.is_set():
            eng.step_state()
            pcm = np.frombuffer(eng.audio_chunk(), dtype=np.int16)
            chunk = pcm.reshape(-1, 2)
            if rec is not None:
                rec.write(chunk)
            q.put(chunk)              # blocks when buffer is full — paces us

    threading.Thread(target=produce, daemon=True).start()

    def status():
        v0 = next((v for v in eng.voices if v["on"]), None)
        w = v0["w"] if v0 else None
        tname = names[eng.win_track[w]] if w is not None else "—"
        leans = {k: round(float(x), 2)
                 for k, x in enumerate(eng.slider_knob) if abs(x) > 1e-3}
        on = [v["stem"] for v in eng.voices if v["on"]]
        print(f"  playing: {tname}\n  voices: {on}   leans: {leans or '0'}")

    print(f"{eng.psi.shape[1]} faders | voices on: "
          f"{[v['stem'] for v in eng.voices if v['on']]} | "
          f"clock faders: {[(k, round(c, 2)) for k, c in clk_tagged[:3]]}")
    print("playing — commands: <fader> <lean> | z | j | g/t/c <v> | "
          "v <stem> | s | clk | q")

    with sd.OutputStream(samplerate=sr, channels=2, dtype="int16") as out:
        def consume():
            while running.is_set():
                out.write(q.get())
        threading.Thread(target=consume, daemon=True).start()
        while True:
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                line = "q"
            if not line:
                continue
            p = line.split()
            try:
                if p[0] == "q":
                    break
                elif p[0] == "z":
                    for k in range(eng.psi.shape[1]):
                        eng.set_lean(k, 0.0)
                    print("  all leans zeroed")
                elif p[0] == "j":
                    eng.jump()
                    print("  jump fired")
                elif p[0] in ("g", "t", "c"):
                    eng.set_meta({"g": "gamma", "t": "tau",
                                  "c": "couple"}[p[0]], float(p[1]))
                    print(f"  {p[0]} = {p[1]}")
                elif p[0] == "v":
                    v = next((v for v in eng.voices if v["stem"] == p[1]),
                             None)
                    if v:
                        eng.set_voice(p[1], not v["on"])
                        print(f"  {p[1]} {'on' if v['on'] else 'off'}")
                elif p[0] == "s":
                    status()
                elif p[0] == "clk":
                    print("  clock faders:",
                          [(k, round(c, 2)) for k, c in clk_tagged])
                else:
                    k, val = int(p[0]), float(p[1])
                    eng.set_lean(k, val)
                    print(f"  fader {k} -> {val:+.2f}")
            except (ValueError, IndexError):
                print("  ? commands: <fader> <lean> | z | j | g/t/c <v> | "
                      "v <stem> | s | clk | q")
    running.clear()
    if rec is not None:
        rec.close()
        print(f"session recorded to {args.record}")


if __name__ == "__main__":
    main()
