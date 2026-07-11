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


def _stem_hue(i):
    """Golden-angle hue per channel — same identity scheme as the web panel."""
    return (i * 137.508) % 360.0


def _hsv_hex(h, s, v):
    import colorsys
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, s, v)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def _stem_luts(stems_order):
    """Per-stem color lookup [content 0-9][heat 0-9]: each channel keeps its
    own hue (identity), brightness = measured content, live field pushes
    toward white. Red is reserved for playheads."""
    luts = {}
    for i, stem in enumerate(stems_order):
        hue = 210.0 if stem == "mix" else _stem_hue(i)
        lut = []
        for b in range(10):
            row = []
            for h in range(10):
                v = min(1.0, 0.10 + 0.055 * b + 0.09 * h)
                sat = max(0.15, 0.75 - 0.07 * h)   # field whitens the cell
                row.append(_hsv_hex(hue, sat, v))
            lut.append(row)
        luts[stem] = lut
    return luts


def _flow_rows(state, stems_order, n_tracks, bins, luts):
    """Rows of hex colors for the flow image: per track, one sub-row per
    stem. hue = channel, brightness = measured content, whiter = live
    sampling field, red = playhead. Pure function (testable headless)."""
    content = state["content"]
    heat_by_stem = {f["stem"]: f for f in state["flow"]}
    rows = []
    for t in range(n_tracks):
        for stem in stems_order:
            base = content.get(stem, [[0] * bins] * n_tracks)[t]
            f = heat_by_stem.get(stem)
            heat = f["heat"][t] if (f and f.get("heat")) else [0] * bins
            lut = luts[stem]
            row = [lut[min(base[x], 9)][min(heat[x], 9)] for x in range(bins)]
            if f and f["track"] == t:
                row[min(int(f["pos"] * bins), bins - 1)] = "#ff5050"
            rows.append("{" + " ".join(row) + "}")
    return " ".join(rows)


def _track_mass(state, n_tracks):
    """Per-track live field mass (sum over bins of the first active voice's
    heat) — one waterfall slice."""
    for f in state["flow"]:
        if f.get("heat"):
            return [sum(r) for r in f["heat"]]
    return [0] * n_tracks


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

    # ---- flow views ----------------------------------------------------------
    # left:  tracks × channel sub-rows (hue = channel, brightness = measured
    #        content, whiter = live field, red = playhead)
    # right: 3D waterfall — the live field's per-track mass receding through
    #        time (newest slice at the front); lean a fader and watch the
    #        ridge bend through the depth axis
    luts = _stem_luts(stems_order)
    legend = ttk.Frame(root)
    legend.pack(fill="x", padx=8)
    tk.Label(legend, text="hue = channel:", font=("TkDefaultFont", 8)
             ).pack(side="left")
    for i, stem in enumerate(stems_order):
        tk.Label(legend, text=stem, fg=luts[stem][9][2], bg="#101018",
                 font=("TkDefaultFont", 8), padx=4).pack(side="left")
    tk.Label(legend,
             text="   brightness = measured content · whiter = live field · "
                  "red = playhead (where the voice reads NOW)",
             font=("TkDefaultFont", 8)).pack(side="left")

    NAME_W, ZX, ZY = 210, 24, 3
    n_rows = n_tracks * len(stems_order)
    flow_wrap = ttk.Frame(root)
    flow_wrap.pack(fill="both", expand=True, padx=6, pady=4)
    fcv = tk.Canvas(flow_wrap, bg="#101018",
                    width=NAME_W + BINS * ZX, height=n_rows * ZY + 8)
    fvbar = ttk.Scrollbar(flow_wrap, orient="vertical", command=fcv.yview)
    fcv.configure(yscrollcommand=fvbar.set,
                  scrollregion=(0, 0, NAME_W + BINS * ZX, n_rows * ZY + 8))
    fvbar.pack(side="left", fill="y")
    fcv.pack(side="left", fill="both", expand=True)
    img_small = tk.PhotoImage(width=BINS, height=n_rows)
    img_ref = {"zoomed": None}
    for t in range(n_tracks):
        fcv.create_text(
            4, t * len(stems_order) * ZY + 4, anchor="nw",
            text=eng.track_names[t][:32], fill="#c8c8d8",
            font=("TkDefaultFont", 7))
    img_item = fcv.create_image(NAME_W, 0, anchor="nw")

    # 3D waterfall (time depth)
    import collections as _c
    WF_D = 64                        # depth slices kept (~30 s at step rate)
    wf_hist = _c.deque(maxlen=WF_D)
    WFW, WFH = 420, n_rows * ZY + 8
    wcv = tk.Canvas(flow_wrap, bg="#0b0b12", width=WFW, height=WFH)
    wcv.pack(side="left", fill="y", padx=(6, 0))
    track_hue = [ (t * 137.508) % 360 for t in range(n_tracks) ]
    wcv.create_text(6, 4, anchor="nw", fill="#c8c8d8",
                    font=("TkDefaultFont", 8),
                    text="flow through time  (front = now)")

    status = ttk.Label(root, text="", justify="left",
                       font=("TkFixedFont", 9))
    status.pack(fill="x", padx=8, pady=2)

    def tick():
        if not running.is_set():
            return
        st = shared["state"]
        if st is not None:
            img_small.put(_flow_rows(st, stems_order, n_tracks, BINS, luts),
                          to=(0, 0))
            img_ref["zoomed"] = img_small.zoom(ZX, ZY)
            fcv.itemconfig(img_item, image=img_ref["zoomed"])
            # 3D waterfall: newest slice at the front, receding into depth
            wf_hist.append(_track_mass(st, n_tracks))
            wcv.delete("wf")
            D = len(wf_hist)
            bw = (WFW - 90) / max(n_tracks, 1)
            for di in range(D):               # oldest first (painters order)
                slice_ = wf_hist[di]
                depth = D - 1 - di            # 0 = newest
                shrink = 1.0 - 0.55 * depth / WF_D
                y0 = WFH - 22 - depth * (WFH - 60) / WF_D
                x_off = 12 + depth * 1.1
                mx = max(slice_) or 1
                for t in range(n_tracks):
                    m = slice_[t] / mx
                    if m < 0.04:
                        continue
                    h = m * 52 * shrink
                    x = x_off + t * bw * shrink
                    fade = 0.25 + 0.75 * (1 - depth / WF_D)
                    col = _hsv_hex(track_hue[t], 0.6, 0.25 + 0.75 * fade * m)
                    wcv.create_rectangle(x, y0 - h, x + bw * shrink * 0.8,
                                         y0, fill=col, outline="",
                                         tags="wf")
            # front-edge track ticks
            for t in range(0, n_tracks, 2):
                wcv.create_text(12 + t * bw, WFH - 18, anchor="nw",
                                text=str(t), fill="#8888a0",
                                font=("TkDefaultFont", 7), tags="wf")
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
