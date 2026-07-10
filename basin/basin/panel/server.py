"""M4 — panel websocket server (stdlib only, no frameworks).

Serves the single-page panel over plain HTTP and runs the orbit in a
background thread, streaming state (co-moving needles + absolute collars, groove
phase/depth, alternation toggles) and chunked audio to the browser, and
receiving control gestures (lean, grip, phase nudge, meta knobs, rename).

WebSocket (RFC 6455) handshake + text/binary framing are implemented here
directly so the panel needs no third-party dependency. Latency of a few seconds
is fine — this is not performance-grade (spec).

Gate: build M4 only after M3 outcome (a). See LEDGER before relying on it.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import threading
import time

import numpy as np

_WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


# ---------------------------------------------------------------------------
# Instrument-driven orbit engine (runs in a background thread)
# ---------------------------------------------------------------------------

class PanelEngine:
    """Live orbit + audio producer feeding the panel.

    Reads the eigenvalue classification to expose the right controls:
    real+ macros → bounded knobs; complex pairs → groove (phase dial + depth);
    real− → alternation toggles. Needles carry the *innovation* (actual motion
    minus PULL+kernel prediction); collars carry absolute position.
    """

    def __init__(self, project_dir: str):
        from basin import store
        from basin.orbit import Orbit
        from basin.render import GrainReader

        self.project_dir = project_dir
        inst = store.load_instrument(os.path.join(project_dir, "instrument.npz"))
        self.cfg = dict(inst["config"])
        self.psi = inst["psi"]
        self.P = inst["P"]
        self.corpus = inst["corpus"]
        self.atlas = inst["atlas"]
        self.kernel = inst["kernel"]
        self.eigvals = inst["eigvals"]
        self.eig_right = inst["eig_right"]
        self.classification = inst["classification"]
        self.macro_indices = list(inst["macro_indices"])

        # oscillatory (groove) and alternation modes, strongest first
        self.groove_modes = [c["index"] for c in self.classification
                             if c["kind"] == "oscillatory"][:4]
        self.alt_modes = [c["index"] for c in self.classification
                          if c["kind"] == "alternation"][:4]

        self.names = self._load_names()
        self.knob = np.zeros(self.psi.shape[1])
        self.slider_knob = np.zeros(self.psi.shape[1])   # absolute fader leans
        self.nudge_knob = np.zeros(self.psi.shape[1])    # transient, decays
        self._lean_burst = 0.0               # fast-throw detector → jump gate
        self.grip = {}                       # macro idx -> held value
        self.lock = threading.Lock()

        # Voices — the oscillator section. With an HPSS instrument the panel
        # runs coupled stem-walkers (the layered sound of the duo renders);
        # a whole-mix instrument gets a single mix voice.
        stems_mode = str(self.cfg.get("stems", "none"))
        n_ch = int(getattr(self.corpus, "n_channels", 0) or 0)
        if stems_mode == "nmf" and n_ch:
            chans = [f"ch{k}" for k in range(n_ch)]
            available = chans + ["mix"]
            default_on = chans
        elif stems_mode == "hpss":
            available = ["harmonic", "percussive", "mix"]
            default_on = ["harmonic", "percussive"]
        else:
            available = ["mix"]
            default_on = ["mix"]
        shared_cache: dict = {}
        n_macros = self.psi.shape[1]
        self.cfg["basin_halflife_steps"] = float(np.median(
            [e - s for (s, e) in self.corpus.track_bounds]))
        basins = inst["chart_basin"]
        self.voices = []
        for vi, stem in enumerate(available):
            orbit = Orbit(self.P, self.psi, self.cfg, knob_vector=self.knob,
                          kernel=self.kernel, seed=101 * vi,
                          modes=(self.eigvals, self.eig_right), basins=basins)
            orbit.seed_state()
            reader = GrainReader(self.corpus, self.atlas.memberships, self.cfg,
                                 seed=101 * vi, stem=stem,
                                 shared_cache=shared_cache, psi=self.psi)
            self.voices.append({"stem": stem, "on": stem in default_on,
                                "orbit": orbit, "reader": reader,
                                "prev_tail": None, "w": None,
                                "loop": None,           # {"win": [...], "pos"}
                                "a": np.zeros(n_macros)})
        self.couple = float(self.cfg.get("couple", 0.5))
        self._mean_a = np.zeros(n_macros)
        self._mean_innov = np.zeros(n_macros)
        # provenance index for the flow view: window -> (track, time bin)
        self.FLOW_BINS = 24
        H = self.corpus.handles
        self.track_names = [os.path.splitext(os.path.basename(p))[0][:48]
                            for p in self.corpus.track_paths]
        self.win_track = np.array([h.track_id for h in H])
        n_win = len(H)
        self.win_bin = np.zeros(n_win, dtype=int)
        self.win_frac = np.zeros(n_win)
        for (s, e) in self.corpus.track_bounds:
            n = max(1, e - s)
            self.win_bin[s:e] = np.minimum(
                (np.arange(n) * self.FLOW_BINS) // n, self.FLOW_BINS - 1)
            self.win_frac[s:e] = np.arange(n) / n
        # static per-channel content map: each track's own decomposition along
        # its timeline (mean stem loudness per bin), the base layer of the
        # flow view. raw layout (hpss): mean_h RMS at 64, mean_p RMS at 142.
        raw = self.corpus.raw
        if stems_mode == "nmf" and n_ch:
            # channel content = mean activation dims (78..78+K-1 in the mean block)
            rms_dims = {f"ch{k}": 78 + k for k in range(n_ch)}
            rms_dims["mix"] = 64
        elif stems_mode == "hpss" and raw.shape[1] >= 156 * 2:
            rms_dims = {"harmonic": 64, "percussive": 142}
        else:
            rms_dims = {"mix": 64}
        self.content = {}
        nT = len(self.track_names)
        for stem_name, dim in rms_dims.items():
            cm = np.zeros((nT, self.FLOW_BINS))
            cnt = np.ones((nT, self.FLOW_BINS))
            np.add.at(cm, (self.win_track, self.win_bin), raw[:, dim])
            np.add.at(cnt, (self.win_track, self.win_bin), 1.0)
            cm = cm / cnt
            lo, hi = cm.min(), cm.max()
            cm = (cm - lo) / (hi - lo + 1e-9)
            self.content[stem_name] = (cm * 9).astype(int).tolist()
        if stems_mode == "hpss" and "mix" not in self.content:
            h = np.array(self.content["harmonic"])
            p = np.array(self.content["percussive"])
            self.content["mix"] = ((h + p) // 2).tolist()
        # eig-column of each flywheel mode (for phase nudges); mirrors
        # Orbit._init_modes' selection
        self._fly_eig_idx = [i for i in range(len(self.eigvals))
                             if np.imag(self.eigvals[i]) > 1e-9][:4]
        self._fly_max = np.full(len(self._fly_eig_idx), 1e-9)
        self.sr = int(self.cfg["sr"])
        self.running = True

    # -- naming -------------------------------------------------------------

    def _names_path(self):
        # DECISIONS: names live in a small companion JSON, not rewritten into
        # the (large) instrument .npz on every keystroke.
        return os.path.join(self.project_dir, "panel_names.json")

    def _load_names(self):
        p = self._names_path()
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
        return {}

    def set_name(self, key: str, name: str):
        with self.lock:
            self.names[key] = name
            with open(self._names_path(), "w") as f:
                json.dump(self.names, f, indent=2)

    # -- controls -----------------------------------------------------------

    def lean(self, macro: int, delta: float):
        """Transient lean (legacy drag gesture): decays after release."""
        with self.lock:
            if 0 <= macro < len(self.nudge_knob):
                self.nudge_knob[macro] += delta

    def set_lean(self, macro: int, value: float):
        """Absolute fader lean in σ units: holds until the fader moves.

        Moving a fader also carries an *impulse* (the derivative of a position
        command is a velocity kick), and a fast hard throw fires the jump gate
        — so big gestures are heard immediately instead of waiting for the
        next natural transition.
        """
        with self.lock:
            if 0 <= macro < len(self.slider_knob):
                delta = float(value) - self.slider_knob[macro]
                self.slider_knob[macro] = float(value)
                self.nudge_knob[macro] += delta          # transient kick
                self._lean_burst += abs(delta)           # throw-speed detector

    def set_grip(self, macro: int, on: bool, value: float = 0.0):
        with self.lock:
            if on:
                self.grip[macro] = value
            else:
                self.grip.pop(macro, None)

    def nudge_phase(self, fly_index: int, delta: float):
        # push the knob along the real part of that flywheel mode's
        # eigenvector so the orbit's projection onto it rotates.
        with self.lock:
            if not (0 <= fly_index < len(self._fly_eig_idx)):
                return
            v = np.real(self.eig_right[:, self._fly_eig_idx[fly_index]])
            proj = self.psi.T @ v                      # mode -> macro space
            n = np.linalg.norm(proj)
            if n > 1e-9:
                self.nudge_knob += delta * proj / n

    def set_meta(self, name: str, value: float):
        with self.lock:
            for v in self.voices:
                if name in ("beta", "gamma", "tau", "kappa"):
                    setattr(v["orbit"], name, float(value))
                elif name == "momentum":
                    v["orbit"].beta_p = float(value)
            if name == "couple":
                self.couple = float(value)

    def set_voice(self, stem: str, on: bool):
        with self.lock:
            for v in self.voices:
                if v["stem"] == stem:
                    v["on"] = bool(on)
                    v["prev_tail"] = None      # fresh splice when re-enabled

    def jump(self, stem: str = "all"):
        """Trigger: force the voice(s) to leave the groove on the next step."""
        with self.lock:
            for v in self.voices:
                if stem in ("all", v["stem"]):
                    v["reader"].force_jump = True

    def set_loop(self, stem: str, on: bool, length: int = 8):
        """Commit primitive: hold this voice's current phrase and cycle it.

        Capture = the contiguous same-track window chain ending at the voice's
        current window (~6 s at length 8). While looped, the voice's walk
        pauses; on release the flow resumes *from the loop*, seamlessly.
        """
        with self.lock:
            H = self.corpus.handles
            for v in self.voices:
                if v["stem"] != stem:
                    continue
                if on and v["w"] is not None:
                    w = v["w"]
                    chain = [w]
                    while len(chain) < length:
                        p = chain[0] - 1
                        if p < 0 or H[p].track_id != H[w].track_id:
                            break
                        chain.insert(0, p)
                    v["loop"] = {"win": chain, "pos": 0}
                elif not on and v["loop"]:
                    last = v["loop"]["win"][v["loop"]["pos"] - 1]
                    v["reader"]._prev_emitted = last
                    v["orbit"].relocalize(v["reader"].window_membership(last))
                    v["loop"] = None

    def set_groove_depth(self, fly_index: int, value: float):
        with self.lock:
            for v in self.voices:
                mw = v["orbit"].mode_weights if v["orbit"]._fly is not None \
                    else None
                if mw is not None and 0 <= fly_index < len(mw):
                    mw[fly_index] = float(value)

    # -- step + state -------------------------------------------------------

    def _apply_decay_and_grip(self):
        self.nudge_knob *= 0.9                          # transient leans decay
        self.knob = self.slider_knob + self.nudge_knob  # faders hold absolutely
        # a fast hard fader throw (≳1σ within ~a step) fires the jump gate so
        # the gesture is heard at the next grain instead of the next natural
        # transition
        if self._lean_burst > 1.0:
            for v in self.voices:
                if v["on"] and not v["loop"]:
                    v["reader"].force_jump = True
            self._lean_burst = 0.0
        else:
            self._lean_burst *= 0.6
        for macro, held in self.grip.items():
            # clamp: strong restoring bias toward the held coordinate value
            self.knob[macro] += 3.0 * (held - self._mean_a[macro])

    def step_state(self) -> dict:
        with self.lock:
            self._apply_decay_and_grip()
            enabled = [v for v in self.voices if v["on"]]
            # looped voices hold their phrase; only free voices walk
            free = [v for v in enabled if not v["loop"]]
            for v in free:
                others = [u["a"] for u in enabled if u is not v]
                v["orbit"].knob = self.knob + (
                    self.couple * np.mean(others, axis=0) if others else 0.0)
                st = v["orbit"].step()
                w = v["reader"].sample_flow(st.a)
                v["orbit"].relocalize(v["reader"].window_membership(w))
                v["a"], v["st"], v["w"] = st.a, st, w
            if free:
                self._mean_a = np.mean([v["a"] for v in free], axis=0)
                self._mean_innov = np.mean(
                    [v["st"].a - v["st"].a_pred for v in free], axis=0)
            ref_orbit = ((free or enabled or self.voices)[0])["orbit"]

        macros = []
        for k, mi in enumerate(self.macro_indices):
            macros.append({
                "index": int(mi),
                "lam": float(np.abs(self.eigvals[mi])),
                "name": self.names.get(f"macro:{mi}", str(k + 1)),
                "position": float(self._mean_a[k]),            # true position
                "innovation": float(self._mean_innov[k]),      # beyond prediction
                "lean": float(self.slider_knob[k]),            # fader position
                "gripped": k in self.grip,
            })

        # groove = the LFO bank: live flywheel phase/amplitude per mode
        grooves = []
        fly = ref_orbit._fly
        if fly is not None and len(fly):
            self._fly_max = np.maximum(self._fly_max[:len(fly)] * 0.995,
                                       np.abs(fly))
            n_macros_shown = len(self.macro_indices)
            for i in range(len(fly)):
                lam = ref_orbit._mode_vals[i]
                grooves.append({
                    "index": i,
                    "name": self.names.get(f"groove:{i}",
                                           str(n_macros_shown + i + 1)),
                    "phase": float(np.angle(fly[i])),
                    "depth": float(np.abs(fly[i]) / self._fly_max[i]),
                    "freq": float(np.angle(lam)),
                    "damping": float(np.abs(lam)),
                    "weight": float(ref_orbit.mode_weights[i]),
                })

        toggles = []
        ref_st = next((v["st"] for v in self.voices if v.get("st") is not None
                       and v["on"]), None)
        if ref_st is not None:
            for mi in self.alt_modes:
                z = float(ref_st.m @ np.real(self.eig_right[:, mi]))
                toggles.append({
                    "index": int(mi),
                    "name": self.names.get(f"alt:{mi}", f"alt {mi}"),
                    "on": z > 0,
                })

        # flow view: per-voice sampling distribution aggregated to
        # (track, time-bin) heat + current playhead — the live "where it is /
        # where it could go" field; deforms visibly as knobs move.
        flow = []
        for v in self.voices:
            if not v["on"]:
                continue
            p = getattr(v["reader"], "last_p", None)
            heat = None
            if p is not None:
                hm = np.zeros((len(self.track_names), self.FLOW_BINS))
                np.add.at(hm, (self.win_track, self.win_bin), p)
                mx = hm.max()
                if mx > 1e-12:
                    hm = hm / mx
                heat = (hm * 9).astype(int).tolist()
            if v["loop"]:
                L = v["loop"]
                w = L["win"][L["pos"] % len(L["win"])]
            else:
                w = v["w"]
            flow.append({
                "stem": v["stem"],
                "track": int(self.win_track[w]) if w is not None else -1,
                "pos": float(self.win_frac[w]) if w is not None else 0.0,
                "loop": v["loop"] is not None,
                "heat": heat,
            })

        return {
            "type": "state",
            "tracks": self.track_names,
            "content": self.content,
            "flow": flow,
            "voices": [{"stem": v["stem"], "on": v["on"],
                        "loop": v["loop"] is not None} for v in self.voices],
            "macros": macros, "grooves": grooves, "toggles": toggles,
            "meta": {"beta": ref_orbit.beta, "gamma": ref_orbit.gamma,
                     "tau": ref_orbit.tau, "kappa": ref_orbit.kappa,
                     "momentum": ref_orbit.beta_p, "couple": self.couple},
        }

    def audio_chunk(self) -> bytes:
        """PCM (int16 LE) for one step: all enabled voices spliced and summed.

        Each voice keeps its own crossfade tail (linear splice on the
        material's own continuation, equal-power on jumps) at natural
        amplitude, so layer fades emerge from the material.
        """
        from basin.render import _equal_power_fades
        step = int(round(float(self.cfg["step_s"]) * self.sr))
        xfade = min(int(round(float(self.cfg["crossfade_s"]) * self.sr)), step)
        grain_len = step + xfade
        mix = np.zeros((step, 2), dtype=np.float32)
        heard = False
        for v in self.voices:
            if not v["on"]:
                continue
            if v["loop"]:
                # cycle the held phrase; wrap point gets an equal-power splice
                L = v["loop"]
                w = L["win"][L["pos"]]
                contiguous = L["pos"] != 0
                L["pos"] = (L["pos"] + 1) % len(L["win"])
            elif v["w"] is not None:
                w = v["w"]
                contiguous = not v["reader"].last_jump
            else:
                continue
            g = v["reader"].grain_audio(w, grain_len)
            if v["prev_tail"] is not None and xfade > 0:
                if contiguous:
                    t = np.linspace(0.0, 1.0, xfade,
                                    endpoint=False)[:, None]
                    fi, fo = t, 1.0 - t
                else:
                    fi, fo = _equal_power_fades(xfade)
                head = v["prev_tail"] * fo + g[:xfade] * fi
                chunk = np.concatenate([head, g[xfade:step]])
            else:
                chunk = g[:step]
            v["prev_tail"] = g[step:grain_len].copy()
            mix += chunk
            heard = True
        if not heard:
            return np.zeros(step, dtype="<i2").tobytes()
        mono = mix.mean(axis=1)              # panel stream stays mono
        return np.clip(mono * 0.7 * 32767, -32768,
                       32767).astype("<i2").tobytes()


# ---------------------------------------------------------------------------
# Minimal WebSocket framing (stdlib only)
# ---------------------------------------------------------------------------

def _ws_accept(key: str) -> str:
    return base64.b64encode(
        hashlib.sha1((key + _WS_MAGIC).encode()).digest()).decode()


def _recv_frame(conn):
    """Read one WebSocket frame from client (masked). Returns (opcode, data)."""
    hdr = _recv_exact(conn, 2)
    if hdr is None:
        return None, None
    b1, b2 = hdr[0], hdr[1]
    opcode = b1 & 0x0F
    masked = b2 & 0x80
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exact(conn, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(conn, 8))[0]
    mask = _recv_exact(conn, 4) if masked else b"\0\0\0\0"
    payload = _recv_exact(conn, length) or b""
    data = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))
    return opcode, data


def _send_frame(conn, data: bytes, opcode: int = 0x1):
    """Send a single unmasked frame (server→client)."""
    header = bytearray([0x80 | opcode])
    n = len(data)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header += struct.pack(">H", n)
    else:
        header.append(127)
        header += struct.pack(">Q", n)
    try:
        conn.sendall(bytes(header) + data)
    except OSError:
        pass


def _recv_exact(conn, n: int):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


# ---------------------------------------------------------------------------
# HTTP + WS server
# ---------------------------------------------------------------------------

def _serve_client(conn, engine, html: bytes):
    req = conn.recv(65536).decode("latin1", "ignore")
    if not req:
        conn.close(); return
    headers = {}
    for line in req.split("\r\n")[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    if "sec-websocket-key" not in headers:
        # plain HTTP: serve the panel page
        body = html
        resp = (b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        conn.sendall(resp)
        conn.close(); return

    accept = _ws_accept(headers["sec-websocket-key"])
    conn.sendall(
        b"HTTP/1.1 101 Switching Protocols\r\n"
        b"Upgrade: websocket\r\nConnection: Upgrade\r\n"
        b"Sec-WebSocket-Accept: " + accept.encode() + b"\r\n\r\n")

    # reader thread for incoming control messages
    def reader():
        while engine.running:
            try:
                opcode, data = _recv_frame(conn)
            except OSError:
                break
            if opcode is None or opcode == 0x8:            # close / gone
                break
            if opcode == 0x1:
                try:
                    _handle_control(engine, json.loads(data.decode()))
                except Exception:
                    pass
    threading.Thread(target=reader, daemon=True).start()

    period = float(engine.cfg["step_s"])
    try:
        while engine.running:
            state = engine.step_state()
            _send_frame(conn, json.dumps(state).encode(), opcode=0x1)
            _send_frame(conn, engine.audio_chunk(), opcode=0x2)
            time.sleep(period)
    finally:
        conn.close()


def _handle_control(engine, msg: dict):
    t = msg.get("type")
    if t == "lean":
        engine.lean(int(msg["macro"]), float(msg["delta"]))
    elif t == "set_lean":
        engine.set_lean(int(msg["macro"]), float(msg["value"]))
    elif t == "grip":
        engine.set_grip(int(msg["macro"]), bool(msg["on"]), float(msg.get("value", 0)))
    elif t == "nudge":
        engine.nudge_phase(int(msg["mode"]), float(msg["delta"]))
    elif t == "meta":
        engine.set_meta(msg["name"], float(msg["value"]))
    elif t == "voice":
        engine.set_voice(str(msg["stem"]), bool(msg["on"]))
    elif t == "jump":
        engine.jump(str(msg.get("stem", "all")))
    elif t == "loop":
        engine.set_loop(str(msg["stem"]), bool(msg["on"]))
    elif t == "groove_depth":
        engine.set_groove_depth(int(msg["index"]), float(msg["value"]))
    elif t == "rename":
        engine.set_name(msg["key"], msg["name"])


def serve(project_dir: str, host: str = "127.0.0.1", port: int = 8765):
    engine = PanelEngine(project_dir)
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, "rb") as f:
        html = f.read()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(8)
    print(f"[panel] http://{host}:{port}  (Ctrl-C to stop)")
    try:
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=_serve_client,
                             args=(conn, engine, html), daemon=True).start()
    except KeyboardInterrupt:
        engine.running = False
        print("\n[panel] stopped")
    finally:
        srv.close()
