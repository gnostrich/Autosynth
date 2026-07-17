"""The local companion server (MVP-2, phase 1).

Endpoints (ALL bound to loopback — this is a local box, never 0.0.0.0):
  GET  /                 -> the browser instrument UI (static)
  GET  /api/health       -> liveness
  GET  /api/status       -> session state (ingested files, last world)
  POST /api/ingest       -> store dropped bytes in the local session dir.
                            LOCAL-ONLY: this handler NEVER contacts the cloud.
  POST /api/train        -> ingest the session -> stage-3 -> cloud anchor-fit ->
                            verify receipt -> write the world locally.

CS boundary (load-bearing, mirrors CS-1..CS-5):
  * The user's dropped audio lands in ``session_dir`` and stays there. /api/ingest
    has no code path to the network.
  * The ONLY cloud call is ``cloud.client.train`` -> ``cloud.client.post_job``,
    which whitelist-encodes ONLY stage-3 (cost/mass/slot_hist/band_profile). It is
    structurally incapable of putting raw audio / recipes on the wire.
  * No renderer/decoder is imported here on the cloud path (no cloud decoder). Any
    audio the user hears is rendered LOCALLY (phase 2), never in the cloud.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
# APPEND (never insert at 0): the ui-v5 engine tree (architecture-v6) must keep the
# front of sys.path so `import ets` resolves to it, not root engine-v1. Inserting
# repo-root at 0 here was the bug that let root ets shadow the arch-v6 engine (which
# alone carries the live cap + telemetry). Repo-root only needs to be reachable for
# cloud.* imports, so append is sufficient and never clobbers engine priority.
if str(_REPO_ROOT) not in sys.path:
    sys.path.append(str(_REPO_ROOT))

_STATIC = Path(__file__).resolve().parent / "static"


class Companion:
    """Holds the per-run config + session state. No engine/render import here;
    the cloud round-trip is delegated to ``cloud.client`` (the guarded path)."""

    def __init__(self, cloud_url: str = "inproc",
                 session_dir: Optional[str] = None,
                 play_world: Optional[str] = None, seed: int = 0) -> None:
        # ``cloud_url`` is the ONLY outbound target. "inproc" runs the service
        # in-process (offline / tests); otherwise an https base URL (Railway).
        self.cloud_url = cloud_url
        base = Path(session_dir) if session_dir else (_REPO_ROOT / "cache" / "companion_session")
        self.session_dir = base
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.world_path = self.session_dir / "world.npz"
        self.last_receipt: Optional[dict] = None
        # playable world for the INSTRUMENT (default: the repo's founding world).
        self.seed = int(seed)
        if play_world is None:
            cand = _REPO_ROOT / "corpus.etsworld"
            play_world = str(cand) if cand.exists() else None
        self.play_world = play_world
        self._player = None            # lazy StreamPlayer (the LOCAL decoder)

    def player(self):
        """Lazily construct the LOCAL render bridge. Import is deferred so the
        companion's cloud path never pulls a decoder (CS-4)."""
        if self._player is None:
            if not self.play_world or not Path(self.play_world).exists():
                return None
            from cloud.companion.engine_bridge import StreamPlayer
            self._player = StreamPlayer(self.play_world, seed=self.seed)
        return self._player

    # --- local-only ingest --------------------------------------------------
    def ingest_bytes(self, filename: str, data: bytes) -> dict:
        """Persist dropped bytes into the session dir. NO network. Returns a
        manifest entry. Filenames are basename-sanitised (no path traversal)."""
        name = os.path.basename(filename or "drop.bin").replace("\x00", "")
        if not name or name in (".", ".."):
            name = "drop.bin"
        dest = self.session_dir / name
        dest.write_bytes(data)
        return {"name": name, "bytes": len(data), "stored": str(dest)}

    def session_files(self):
        return sorted(p.name for p in self.session_dir.iterdir()
                      if p.is_file() and p.name != "world.npz")

    def reset(self) -> dict:
        """Clear the current corpus + world so a fresh corpus can be loaded — the
        MVP's account-free 'new corpus' action (one corpus at a time; whoever is at
        the machine resets and drops their own audio). Local-only: no network."""
        removed = 0
        for p in list(self.session_dir.iterdir()):
            if p.is_file():
                p.unlink(); removed += 1
        self.last_receipt = None
        return {"ok": True, "cleared": removed}

    # --- the guarded cloud round-trip --------------------------------------
    def run_train(self, seed: int = 0, sweeps: int = 8,
                  sigma: Optional[float] = None) -> dict:
        """Ingest the session -> stage-3 -> cloud anchor-fit -> verify -> write.

        Delegates entirely to ``cloud.client.train`` so the whitelist encoder is
        the single wire exit. Accepts a corpus dir of cached track_*.npz or a
        .npz prototype bundle in the session dir (raw-audio ingest is the same
        local ets.ingestion step, run on the device)."""
        from cloud.client.cli import train  # imported lazily; guarded path only

        # pick a .npz prototype bundle if present, else the session dir itself
        bundles = [p for p in self.session_dir.iterdir()
                   if p.is_file() and p.suffix == ".npz" and p.name != "world.npz"]
        corpus = str(bundles[0]) if bundles else str(self.session_dir)

        result = train(corpus, service=self.cloud_url, out=str(self.world_path),
                       seed=seed, sweeps=sweeps, sigma=sigma, verbose=False)
        r = {k: (float(v) if hasattr(v, "__float__") and not isinstance(v, bool)
                 else (bool(v) if isinstance(v, bool) else v.tolist()
                       if hasattr(v, "tolist") else v))
             for k, v in result.receipt.items()}
        self.last_receipt = r
        return {"ok": True, "receipt": r, "world": str(self.world_path)}


class _Handler(BaseHTTPRequestHandler):
    companion: Companion = None  # set on the server instance below

    def _send(self, code: int, body: bytes, ctype="application/octet-stream"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict):
        self._send(code, json.dumps(obj).encode(), "application/json")

    # --- GET ----------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        if path in ("", "/"):
            self._serve_static("index.html", "text/html; charset=utf-8")
            return
        if path == "/api/health":
            self._json(200, {"ok": True, "service": "ets-companion", "cloud": self.companion.cloud_url})
            return
        if path == "/api/status":
            self._json(200, {
                "session_dir": str(self.companion.session_dir),
                "files": self.companion.session_files(),
                "world": str(self.companion.world_path) if self.companion.world_path.exists() else None,
                "last_receipt": self.companion.last_receipt,
            })
            return
        if path == "/api/world":
            p = self.companion.player()
            self._json(200, p.world_info() if p is not None
                       else {"ready": False, "reason": "no playable world loaded"})
            return
        if path == "/api/stream":
            self._stream_audio()
            return
        if path == "/api/telemetry":
            self._stream_telemetry()
            return
        if path.startswith("/static/"):
            self._serve_static(path[len("/static/"):], self._ctype(path))
            return
        self._send(404, b"not found", "text/plain")

    def _serve_static(self, rel: str, ctype: str):
        # basename-guard: no traversal out of the static dir
        safe = os.path.normpath(rel).lstrip("/")
        if safe.startswith(".."):
            self._send(403, b"forbidden", "text/plain")
            return
        f = _STATIC / safe
        if not f.is_file():
            self._send(404, b"not found", "text/plain")
            return
        self._send(200, f.read_bytes(), ctype)

    @staticmethod
    def _ctype(path: str) -> str:
        if path.endswith(".html"):
            return "text/html; charset=utf-8"
        if path.endswith(".js"):
            return "text/javascript"
        if path.endswith(".css"):
            return "text/css"
        return "application/octet-stream"

    # --- POST ---------------------------------------------------------------
    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        if path == "/api/ingest":
            # LOCAL-ONLY: store bytes, never forward. Filename via X-Filename.
            fn = self.headers.get("X-Filename", "drop.bin")
            entry = self.companion.ingest_bytes(fn, body)
            self._json(200, {"ok": True, "ingested": entry,
                             "files": self.companion.session_files()})
            return

        if path == "/api/reset":
            # account-free "new corpus": clear session + world, LOCAL-ONLY
            out = self.companion.reset()
            self._json(200, {**out, "files": self.companion.session_files()})
            return

        # --- instrument control: region-tilt is the ONLY engine-bound gesture ---
        if path == "/api/steer":
            p = self.companion.player()
            if p is None:
                self._json(409, {"ok": False, "error": "no playable world"})
                return
            region = []
            if body:
                try:
                    region = json.loads(body.decode()).get("region", [])
                except Exception:
                    region = []
            p.set_region(region)         # the SINGLE settlement input
            self._json(200, {"ok": True})
            return
        if path == "/api/play":
            p = self.companion.player()
            if p is None:
                self._json(409, {"ok": False, "error": "no playable world"})
                return
            p.start()
            self._json(200, {"ok": True, "playing": True})
            return
        if path == "/api/stop":
            p = self.companion.player()
            if p is not None:
                p.stop()
            self._json(200, {"ok": True, "playing": False})
            return

        if path == "/api/train":
            params = {}
            if body:
                try:
                    params = json.loads(body.decode())
                except Exception:
                    params = {}
            try:
                out = self.companion.run_train(
                    seed=int(params.get("seed", 0)),
                    sweeps=int(params.get("sweeps", 8)),
                    sigma=params.get("sigma", None))
            except SystemExit as exc:      # ingest guidance (e.g. no protos)
                self._json(400, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:       # decode/verify/transport
                self._json(502, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return
            self._json(200, out)
            return

        self._send(404, b"not found", "text/plain")

    # --- streaming helpers (chunked; no Content-Length) ---------------------
    def _stream_audio(self):
        p = self.companion.player()
        if p is None:
            self._send(409, b"no playable world", "text/plain")
            return
        p.start()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            for chunk in p.stream_chunks():
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ValueError):
            pass  # client closed the audio stream

    def _stream_telemetry(self):
        import time
        p = self.companion.player()
        if p is None:
            self._send(409, b"no playable world", "text/plain")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while True:
                frame = json.dumps(p.telemetry)
                self.wfile.write(("data: " + frame + "\n\n").encode())
                self.wfile.flush()
                time.sleep(0.1)
        except (BrokenPipeError, ConnectionResetError, ValueError):
            pass  # client closed the telemetry stream

    def log_message(self, *_a):  # quiet
        pass


def _require_loopback(host: str) -> str:
    """Structurally enforce the sealed-box invariant: the companion binds LOOPBACK
    ONLY (matches the module contract, 'never 0.0.0.0'). A non-loopback host — e.g.
    0.0.0.0 — is refused, so the one localhost port cannot be widened into a public
    listener by a stray flag."""
    if host == "localhost":
        return host
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise SystemExit(f"[companion] refusing host {host!r}: bind loopback only "
                         f"(127.0.0.1 / ::1 / localhost)")
    if not ip.is_loopback:
        raise SystemExit(f"[companion] refusing non-loopback host {host!r}: "
                         f"bind loopback only — the box is local by design")
    return host


def serve(cloud_url: str = "inproc", host: str = "127.0.0.1", port: int = 8770,
          session_dir: Optional[str] = None) -> ThreadingHTTPServer:
    """Start the companion on loopback. Returns the (already-serving is caller's
    job) server; callers in tests use ``server_close`` to stop."""
    host = _require_loopback(host)
    comp = Companion(cloud_url=cloud_url, session_dir=session_dir)
    handler = type("_BoundHandler", (_Handler,), {"companion": comp})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.companion = comp
    return httpd


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m cloud.companion",
                                 description="ETS local companion (sealed on-device box)")
    ap.add_argument("--cloud-url", default=os.environ.get("ETS_CLOUD_URL", "inproc"),
                    help="cloud anchor-fit base URL (Railway), or 'inproc' for offline")
    ap.add_argument("--host", default="127.0.0.1", help="loopback only by design")
    ap.add_argument("--port", type=int, default=int(os.environ.get("ETS_COMPANION_PORT", "8770")))
    ap.add_argument("--session-dir", default=None)
    args = ap.parse_args(argv)

    httpd = serve(cloud_url=args.cloud_url, host=args.host, port=args.port,
                  session_dir=args.session_dir)
    print(f"[companion] UI + API on http://{args.host}:{args.port}  (cloud={args.cloud_url})")
    print(f"[companion] session dir: {httpd.companion.session_dir}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
