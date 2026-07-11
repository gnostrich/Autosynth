"""Native desktop panel — a real window, no browser, no web stack.

Same PanelEngine as the web panel; audio goes straight to the sound device
(sounddevice), the UI is tkinter (ships with Python — no new UI deps).
Redraws are event-driven + a 2 Hz status tick, so the interface costs
almost nothing next to the browser's per-frame canvas storm.

    python scripts/play_native.py [--project DIR] [--record out.wav]

Layout:
  top bar     JUMP | ZERO LEANS | gamma / tau / couple | voice toggles
  fader bank  scrollable vertical sliders, ranked by measured persistence;
              each labeled with its number, |lambda|, and clk tag where
              measured; double-click a fader to zero it
  status      what each voice is playing + live pacing, 2 Hz
"""
import argparse
import os
import queue
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=os.path.join(
        os.path.dirname(__file__), ".."))
    ap.add_argument("--record", default=None)
    ap.add_argument("--faders", type=int, default=32,
                    help="how many ranked faders to show (default 32)")
    args = ap.parse_args()

    try:
        import sounddevice as sd
    except ImportError:
        print("needs the native audio backend once:  pip install sounddevice")
        sys.exit(1)
    import tkinter as tk
    from tkinter import ttk

    from basin.panel.server import PanelEngine
    print("loading instrument ...")
    eng = PanelEngine(os.path.abspath(args.project))
    sr = eng.sr
    clock_corr = list(getattr(eng, "clock_corr", []))

    rec = None
    if args.record:
        import soundfile as sf
        rec = sf.SoundFile(args.record, "w", samplerate=sr, channels=2,
                           subtype="PCM_16")

    audio_q: queue.Queue = queue.Queue(maxsize=4)
    running = threading.Event()
    running.set()
    pace = {"strides": []}

    def produce():
        while running.is_set():
            eng.step_state()
            pcm = np.frombuffer(eng.audio_chunk(), dtype=np.int16)
            chunk = pcm.reshape(-1, 2)
            if rec is not None:
                rec.write(chunk)
            audio_q.put(chunk)

    def consume(stream):
        while running.is_set():
            stream.write(audio_q.get())

    # ---- window ------------------------------------------------------------
    root = tk.Tk()
    root.title("Basin — native panel")
    root.geometry("1080x560")

    top = ttk.Frame(root)
    top.pack(fill="x", padx=6, pady=4)
    ttk.Button(top, text="JUMP", command=lambda: eng.jump()).pack(
        side="left", padx=2)

    def zero_all():
        for k in range(eng.psi.shape[1]):
            eng.set_lean(k, 0.0)
        for s in fader_vars:
            s.set(0.0)
    ttk.Button(top, text="ZERO", command=zero_all).pack(side="left", padx=2)

    def meta_slider(name, lo, hi, init):
        ttk.Label(top, text=name).pack(side="left", padx=(10, 2))
        v = tk.DoubleVar(value=init)
        s = ttk.Scale(top, from_=lo, to=hi, variable=v, length=90,
                      command=lambda _=None: eng.set_meta(name, v.get()))
        s.pack(side="left")
        return v
    meta_slider("gamma", 0.0, 2.0, 1.0)
    meta_slider("tau", 0.3, 2.0, 1.0)
    meta_slider("couple", 0.0, 1.5, eng.couple)

    for v in eng.voices:
        var = tk.BooleanVar(value=v["on"])
        ttk.Checkbutton(
            top, text=v["stem"], variable=var,
            command=lambda s=v["stem"], vv=var: eng.set_voice(s, vv.get())
        ).pack(side="right")

    # ---- fader bank (scrollable) --------------------------------------------
    bank_wrap = ttk.Frame(root)
    bank_wrap.pack(fill="both", expand=True, padx=6)
    canvas = tk.Canvas(bank_wrap, height=340)
    hbar = ttk.Scrollbar(bank_wrap, orient="horizontal",
                         command=canvas.xview)
    canvas.configure(xscrollcommand=hbar.set)
    hbar.pack(side="bottom", fill="x")
    canvas.pack(fill="both", expand=True)
    bank = ttk.Frame(canvas)
    canvas.create_window((0, 0), window=bank, anchor="nw")

    n_show = min(args.faders, eng.psi.shape[1])
    fader_vars = []
    for k in range(n_show):
        col = ttk.Frame(bank)
        col.grid(row=0, column=k, padx=3)
        lam = float(np.abs(eng.eigvals[eng.macro_indices[k]]))
        clk = clock_corr[k] if k < len(clock_corr) else 0.0
        tag = f"\nclk {clk:+.2f}" if abs(clk) >= 0.15 else ""
        v = tk.DoubleVar(value=0.0)
        fader_vars.append(v)
        s = tk.Scale(col, from_=2.0, to=-2.0, resolution=0.05,
                     orient="vertical", length=200, variable=v, width=12,
                     showvalue=False,
                     command=lambda val, kk=k: eng.set_lean(kk, float(val)))
        s.pack()
        s.bind("<Double-Button-1>",
               lambda e, kk=k, vv=v: (vv.set(0.0), eng.set_lean(kk, 0.0)))
        ttk.Label(col, text=f"{k}\n|λ| {lam:.2f}{tag}",
                  justify="center", font=("TkDefaultFont", 7)).pack()
    bank.update_idletasks()
    canvas.configure(scrollregion=canvas.bbox("all"))

    # ---- status ------------------------------------------------------------
    status = ttk.Label(root, text="", justify="left",
                       font=("TkFixedFont", 9))
    status.pack(fill="x", padx=8, pady=4)

    def tick():
        if not running.is_set():
            return
        lines = []
        for v in eng.voices:
            if v["on"] and v["w"] is not None:
                w = v["w"]
                st = eng.win_frac[w]
                lines.append(f'{v["stem"]:4s} {eng.track_names[eng.win_track[w]][:56]}'
                             f'  @{100*st:.0f}%')
        leans = {k: round(fv.get(), 2) for k, fv in enumerate(fader_vars)
                 if abs(fv.get()) > 1e-3}
        lines.append(f'leans: {leans or "0 (corpus routing)"}')
        status.config(text="\n".join(lines))
        root.after(500, tick)

    def on_close():
        running.clear()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    with sd.OutputStream(samplerate=sr, channels=2, dtype="int16") as out:
        threading.Thread(target=produce, daemon=True).start()
        threading.Thread(target=consume, args=(out,), daemon=True).start()
        root.after(500, tick)
        root.mainloop()

    if rec is not None:
        rec.close()
        print(f"session recorded to {args.record}")


if __name__ == "__main__":
    main()
