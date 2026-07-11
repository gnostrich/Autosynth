"""Native desktop panel — a real window, no browser, no web stack.

Same PanelEngine as the web panel; audio goes straight to the sound device
(sounddevice), the UI is tkinter (ships with Python — no new UI deps).
Redraws are event-driven + a 2 Hz tick, so the interface costs almost
nothing next to the browser's per-frame canvas storm.

    python scripts/play_native.py [--project DIR] [--record out.wav]

Layout:
  top bar     JUMP | ZERO | gamma / tau / couple | voice toggles
  fader bank  scrollable sliders ranked by measured persistence; labels
              carry |lambda| and clk tags; double-click a fader to zero
  flow view   tracks as rows, channel sub-rows (each track's own measured
              decomposition as base brightness), the LIVE sampling field
              as green heat, playheads in red — deforms as you lean
  status      what each voice is playing, active leans, 2 Hz
"""
import argparse
import os
import queue
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402


def _flow_rows(state, stems_order, n_tracks, bins):
    """Rows of hex colors for the flow image: per track, one sub-row per
    stem — base = measured decomposition, green = live sampling field,
    red = playhead. Pure function (testable headless)."""
    content = state["content"]
    heat_by_stem = {f["stem"]: f for f in state["flow"]}
    # color lookups: base 0-9 x heat 0-9
    lut = [[f"#{16 + 6 * b:02x}{16 + 6 * b + 18 * h:02x}{24 + 5 * b:02x}"
            for h in range(10)] for b in range(10)]
    rows = []
    for t in range(n_tracks):
        for stem in stems_order:
            base = content.get(stem, [[0] * bins] * n_tracks)[t]
            f = heat_by_stem.get(stem)
            heat = f["heat"][t] if (f and f.get("heat")) else [0] * bins
            row = [lut[min(base[x], 9)][min(heat[x], 9)] for x in range(bins)]
            if f and f["track"] == t:
                row[min(int(f["pos"] * bins), bins - 1)] = "#ff5050"
            rows.append("{" + " ".join(row) + "}")
    return " ".join(rows)


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
    n_tracks = len(eng.track_names)
    BINS = eng.FLOW_BINS
    stems_order = [s for s in
                   (["mix"] + [v["stem"] for v in eng.voices
                               if v["stem"] != "mix"])
                   if s in eng.content]

    rec = None
    if args.record:
        import soundfile as sf
        rec = sf.SoundFile(args.record, "w", samplerate=sr, channels=2,
                           subtype="PCM_16")

    audio_q: queue.Queue = queue.Queue(maxsize=4)
    running = threading.Event()
    running.set()
    shared = {"state": None}

    def produce():
        while running.is_set():
            shared["state"] = eng.step_state()
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
    root.geometry("1240x870")

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

    # ---- fader bank (scrollable) ---------------------------------------------
    bank_wrap = ttk.Frame(root)
    bank_wrap.pack(fill="x", padx=6)
    canvas = tk.Canvas(bank_wrap, height=270)
    hbar = ttk.Scrollbar(bank_wrap, orient="horizontal",
                         command=canvas.xview)
    canvas.configure(xscrollcommand=hbar.set)
    hbar.pack(side="bottom", fill="x")
    canvas.pack(fill="x")
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
                     orient="vertical", length=180, variable=v, width=12,
                     showvalue=False,
                     command=lambda val, kk=k: eng.set_lean(kk, float(val)))
        s.pack()
        s.bind("<Double-Button-1>",
               lambda e, kk=k, vv=v: (vv.set(0.0), eng.set_lean(kk, 0.0)))
        ttk.Label(col, text=f"{k}\n|λ| {lam:.2f}{tag}",
                  justify="center", font=("TkDefaultFont", 7)).pack()
    bank.update_idletasks()
    canvas.configure(scrollregion=canvas.bbox("all"))

    # ---- flow view: tracks × channel sub-rows, live field ---------------------
    NAME_W, ZX, ZY = 220, 40, 3
    n_rows = n_tracks * len(stems_order)
    flow_wrap = ttk.Frame(root)
    flow_wrap.pack(fill="both", expand=True, padx=6, pady=4)
    fcv = tk.Canvas(flow_wrap, bg="#101018",
                    width=NAME_W + BINS * ZX, height=n_rows * ZY + 8)
    fvbar = ttk.Scrollbar(flow_wrap, orient="vertical", command=fcv.yview)
    fcv.configure(yscrollcommand=fvbar.set,
                  scrollregion=(0, 0, NAME_W + BINS * ZX, n_rows * ZY + 8))
    fvbar.pack(side="right", fill="y")
    fcv.pack(side="left", fill="both", expand=True)
    img_small = tk.PhotoImage(width=BINS, height=n_rows)
    img_ref = {"zoomed": None}
    for t in range(n_tracks):
        fcv.create_text(
            4, t * len(stems_order) * ZY + 4, anchor="nw",
            text=eng.track_names[t][:34], fill="#c8c8d8",
            font=("TkDefaultFont", 7))
    img_item = fcv.create_image(NAME_W, 0, anchor="nw")

    status = ttk.Label(root, text="", justify="left",
                       font=("TkFixedFont", 9))
    status.pack(fill="x", padx=8, pady=2)

    def tick():
        if not running.is_set():
            return
        st = shared["state"]
        if st is not None:
            img_small.put(_flow_rows(st, stems_order, n_tracks, BINS),
                          to=(0, 0))
            img_ref["zoomed"] = img_small.zoom(ZX, ZY)
            fcv.itemconfig(img_item, image=img_ref["zoomed"])
            lines = []
            for f in st["flow"]:
                if f["track"] >= 0:
                    lines.append(f'{f["stem"]:4s} '
                                 f'{eng.track_names[f["track"]][:52]}'
                                 f'  @{100 * f["pos"]:.0f}%')
            leans = {k: round(fv.get(), 2) for k, fv in
                     enumerate(fader_vars) if abs(fv.get()) > 1e-3}
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
