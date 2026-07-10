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
        self.grip = {}                       # macro idx -> held value
        self.lock = threading.Lock()

        self.orbit = Orbit(self.P, self.psi, self.cfg, knob_vector=self.knob,
                           kernel=self.kernel, seed=0,
                           modes=(self.eigvals, self.eig_right))
        self.orbit.seed_state()
        self.reader = GrainReader(self.corpus, self.atlas.memberships, self.cfg,
                                  seed=0, psi=self.psi)
        self.sr = int(self.cfg["sr"])
        self._prev_tail = None                 # flow-mode splice state
        self._last_window = None
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
        """Absolute fader lean in σ units: holds until the fader moves."""
        with self.lock:
            if 0 <= macro < len(self.slider_knob):
                self.slider_knob[macro] = float(value)

    def set_grip(self, macro: int, on: bool, value: float = 0.0):
        with self.lock:
            if on:
                self.grip[macro] = value
            else:
                self.grip.pop(macro, None)

    def nudge_phase(self, mode_index: int, delta: float):
        # push the knob along the real part of that mode's eigenvector so the
        # orbit's projection onto it rotates (a coarse phase nudge for v0.1).
        with self.lock:
            v = np.real(self.eig_right[:, mode_index])
            proj = self.psi.T @ v                      # mode -> macro space
            n = np.linalg.norm(proj)
            if n > 1e-9:
                self.nudge_knob += delta * proj / n

    def set_meta(self, name: str, value: float):
        with self.lock:
            if name in ("beta", "gamma", "tau", "kappa"):
                setattr(self.orbit, name, float(value))
            elif name == "momentum":
                self.orbit.beta_p = float(value)

    # -- step + state -------------------------------------------------------

    def _apply_decay_and_grip(self):
        self.nudge_knob *= 0.9                          # transient leans decay
        self.knob = self.slider_knob + self.nudge_knob  # faders hold absolutely
        for macro, held in self.grip.items():
            # clamp: strong restoring bias toward the held coordinate value
            cur = self.orbit.history_a[-1][macro] if self.orbit.history_a else 0.0
            self.knob[macro] += 3.0 * (held - cur)

    def step_state(self) -> dict:
        with self.lock:
            self._apply_decay_and_grip()
            self.orbit.knob = self.knob
            st = self.orbit.step()
            # flow mode: corpus momentum + walk-as-field, closed loop —
            # the same dynamics as render_flow, live.
            w = self.reader.sample_flow(st.a)
            self.orbit.relocalize(self.reader.window_membership(w))
            self._last_window = w
        self._last_orbit_state = st                     # for audio_chunk()

        macros = []
        for k, mi in enumerate(self.macro_indices):
            macros.append({
                "index": int(mi),
                "name": self.names.get(f"macro:{mi}", f"macro {k+1}"),
                "position": float(st.a[k]),                    # absolute collar
                "innovation": float(st.a[k] - st.a_pred[k]),   # co-moving needle
                "lean": float(self.slider_knob[k]),            # fader position
                "gripped": k in self.grip,
            })

        grooves = []
        for mi in self.groove_modes:
            z = st.m @ np.real(self.eig_right[:, mi]) \
                + 1j * (st.m @ np.imag(self.eig_right[:, mi]))
            grooves.append({
                "index": int(mi),
                "name": self.names.get(f"groove:{mi}", f"groove {mi}"),
                "phase": float(np.angle(z)),
                "depth": float(np.abs(z)),
                "freq": float(self.classification[mi]["frequency"]),
                "damping": float(self.classification[mi]["damping"]),
            })

        toggles = []
        for mi in self.alt_modes:
            z = float(st.m @ np.real(self.eig_right[:, mi]))
            toggles.append({
                "index": int(mi),
                "name": self.names.get(f"alt:{mi}", f"alt {mi}"),
                "on": z > 0,
            })

        return {
            "type": "state",
            "macros": macros, "grooves": grooves, "toggles": toggles,
            "meta": {"beta": self.orbit.beta, "gamma": self.orbit.gamma,
                     "tau": self.orbit.tau, "kappa": self.orbit.kappa,
                     "momentum": self.orbit.beta_p},
        }

    def audio_chunk(self) -> bytes:
        """PCM (int16 LE) for one step of flow-mode audio.

        Mirrors render_flow's splicing statefully: each chunk is exactly one
        step long, crossfaded against the previous grain's tail (linear when
        the emission was the material's own continuation, equal-power on
        jumps), at natural amplitude so fades emerge from the material.
        """
        from basin.render import _equal_power_fades
        if self._last_window is None:
            return b""
        step = int(round(float(self.cfg["step_s"]) * self.sr))
        xfade = min(int(round(float(self.cfg["crossfade_s"]) * self.sr)), step)
        grain_len = step + xfade
        g = self.reader.grain_audio(self._last_window, grain_len)
        if self._prev_tail is not None and xfade > 0:
            if self.reader.last_jump:
                fi, fo = _equal_power_fades(xfade)
            else:
                t = np.linspace(0.0, 1.0, xfade, endpoint=False)
                fi, fo = t, 1.0 - t
            head = self._prev_tail * fo + g[:xfade] * fi
            chunk = np.concatenate([head, g[xfade:step]])
        else:
            chunk = g[:step]
        self._prev_tail = g[step:grain_len].copy()
        return np.clip(chunk * 0.9 * 32767, -32768, 32767).astype("<i2").tobytes()


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
