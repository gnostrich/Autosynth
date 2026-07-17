"""The companion server (MVP-2, phase 1).

Bind policy (two modes, one code path):
  * DEFAULT (local): loopback only (127.0.0.1 / ::1 / localhost). ``_require_loopback``
    refuses any non-loopback host, so the local box can never be widened into a
    public listener by a stray flag. This is the unchanged local default.
  * PUBLIC (``ETS_PUBLIC=1`` or ``--public``): the SINGLE sanctioned public mode,
    which exists ONLY for the hosted Railway deploy (R6: cloud-served interface,
    no repo clone). It allows binding 0.0.0.0 and reads ``$PORT`` (Railway injects
    it). It is an explicit, honest opt-in — never on by default, never a silent
    widening of the loopback guard.

Endpoints:
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
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import sys
import threading
import time
from http.cookies import SimpleCookie
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

# Extensions that route /api/train to the train->play seam (raw audio -> a playable
# trained world). Kept inline so app.py's ROUTING pulls no engine/decoder import; the
# seam module (cloud.companion.train_local) owns the authoritative AUDIO_EXTS and is
# imported lazily only once audio is actually present (CS-4: no decoder on this path).
_AUDIO_EXTS = frozenset({".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aif", ".aiff", ".aac"})


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
        # the user's freshly cloud-trained playable world (built by the train->play
        # seam; distinct from world.npz, which is the geometry-only offline artifact).
        self.trained_world_path = self.session_dir / "trained.etsworld"
        self.last_receipt: Optional[dict] = None
        # playable world for the INSTRUMENT (default: the repo's founding world).
        self.seed = int(seed)
        if play_world is None:
            # prefer the COMMITTED self-contained demo (embedded audio, no external
            # files) so a fresh clone plays out of the box; fall back to a local
            # corpus.etsworld if present (dev machines).
            for _name in ("demo.etsworld", "corpus.etsworld"):
                cand = _REPO_ROOT / _name
                if cand.exists():
                    play_world = str(cand)
                    break
        # remember the demo/founding world so reset() can revert to it.
        self._demo_world = play_world
        self.play_world = play_world
        self._is_trained = False       # True once the seam repoints to the user's world
        self._player = None            # lazy StreamPlayer (the LOCAL decoder)

    def player(self):
        """Lazily construct the LOCAL render bridge. Import is deferred so the
        companion's cloud path never pulls a decoder (CS-4)."""
        if self._player is None:
            if not self.play_world or not Path(self.play_world).exists():
                return None
            from cloud.companion.engine_bridge import StreamPlayer
            self._player = StreamPlayer(self.play_world, seed=self.seed,
                                        is_trained=self._is_trained)
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
        the machine resets and drops their own audio). Local-only: no network.

        Full revert (the operator's "reset button and all"): drops the session
        files AND the trained world, repoints the instrument back to the founding
        demo world, drops the cached player, and clears the trained flag. After a
        reset the instrument plays the demo again and reports is_trained:false."""
        removed = 0
        for p in list(self.session_dir.iterdir()):
            if p.is_file():
                p.unlink(); removed += 1
        self.last_receipt = None
        # revert the instrument to the founding demo world
        self.play_world = self._demo_world
        self._is_trained = False
        self._player = None
        return {"ok": True, "cleared": removed}

    # --- the guarded cloud round-trip --------------------------------------
    def run_train(self, seed: int = 0, sweeps: int = 8,
                  sigma: Optional[float] = None) -> dict:
        """Ingest the session -> stage-3 -> cloud anchor-fit -> verify -> write.

        The whitelist encoder is the SINGLE wire exit in both branches; only
        stage-3 ever crosses (CS-1). Two branches, distinguished by extension:

        * RAW AUDIO in the session (wav/mp3/flac/...): run the full train->play
          seam (local ingest -> stage-3 -> cloud fit -> local build_index ->
          playable .etsworld) and REPOINT the instrument at the user's trained
          world (is_trained -> True). The renderer/build_index imports live in the
          lazily-loaded ``train_local`` module, never on this cloud path (CS-4).

        * A .npz prototype bundle / dir of cached track_*.npz (the offline/test
          path): keep the geometry-only behavior — verify + write world.npz. The
          instrument keeps playing the demo world (is_trained stays False)."""
        # route by content: raw audio -> the train->play seam
        audio = sorted(p for p in self.session_dir.iterdir()
                       if p.is_file() and p.suffix.lower() in _AUDIO_EXTS)
        if audio:
            # lazy import: only pulls the local decoder/build_index when audio is
            # present, so app.py's top level stays provably decoder-free (CS-4).
            from cloud.companion.train_local import build_trained_world
            out = build_trained_world(
                [str(p) for p in audio], out_path=str(self.trained_world_path),
                cloud_url=self.cloud_url, seed=seed, sweeps=sweeps, sigma=sigma)
            self.last_receipt = out["receipt"]
            # Bring the trained world LIVE. The BUILD seam embedded THIS corpus's own
            # measured σ_φ in the world file, so loading it constructs the engine via
            # the EMBEDDED σ_φ precedence — the demo world's registered artifact is
            # never consulted (no staleness raise). The player plays AND steers the
            # trained world (region/continuity/novelty armed; density/gauge disarmed
            # at u=0, a measured fact — same as the founding world).
            trained = str(self.trained_world_path)
            from cloud.companion.engine_bridge import StreamPlayer
            try:
                player = StreamPlayer(trained, seed=self.seed, is_trained=True)
            except Exception as exc:
                # BUILD + verify + σ_φ succeeded and the world file is on disk; a
                # genuine UNEXPECTED failure bringing it live is surfaced (not
                # hidden) and we keep the calibrated demo world playing rather than
                # crash the instrument. This is not the old σ_φ wall (resolved above).
                return {"ok": True, "built": True, "is_trained": False,
                        "world": trained, "receipt": out["receipt"],
                        "playback": "error",
                        "playback_error": f"{type(exc).__name__}: {exc}"}
            # go live: repoint the instrument at the user's trained world
            self.play_world = trained
            self._is_trained = True
            self._player = player             # reuse the already-loaded player
            return {"ok": True, "built": True, "receipt": out["receipt"],
                    "world": trained, "is_trained": True, "playback": "live",
                    "sigma_phi_disarmed": out.get("sigma_phi_disarmed", [])}

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
        return {"ok": True, "receipt": r, "world": str(self.world_path),
                "is_trained": False}


# --- PUBLIC-mode per-visitor session policy (bounds + access gate) -----------
# These apply ONLY in public (hosted) mode. Local loopback mode keeps the single
# shared Companion with no cookies, no caps, no key gate (the local user is trusted).
_SID_COOKIE = "ets_sid"                     # opaque per-visitor session id (cookie)
_SID_RE = re.compile(r"\A[0-9a-f]{32}\Z")   # sids are 16-byte hex; anything else is foreign
_COOKIE_MAX_AGE = 86400                     # cookie lifetime (s); server TTL below is separate
_SESSION_TTL_SEC = 30 * 60                  # evict a session idle this long (bounds disk+mem)
_MAX_SESSION_BYTES = 100 * 1024 * 1024      # total upload bytes per session (100 MB)
_MAX_SESSION_FILES = 12                     # file-count cap per session
_MAX_GLOBAL_TRAINS = 2                      # concurrent trainings across the whole box


def _gate_html(configured: bool) -> str:
    """The MINIMAL public 'enter your access key' page (served by GET / to a caller
    with no key-authorized session). It is NOT the instrument. When the box has no
    keys configured it fails CLOSED with an honest 'access not configured' message
    and no working form. Same-origin POST /api/auth only; no external calls."""
    body = ('<p class="msg">Access is not configured on this server.</p>'
            '<p class="sub">The operator must set <code>ETS_ACCESS_KEYS</code>.</p>'
            if not configured else
            '<form id="f" autocomplete="off">'
            '<input id="k" type="password" placeholder="access key" aria-label="access key" '
            'autocomplete="off" spellcheck="false">'
            '<button id="go" type="submit">Enter</button>'
            '<p class="err" id="e"></p></form>'
            '<script>'
            'var f=document.getElementById("f"),k=document.getElementById("k"),'
            'e=document.getElementById("e");'
            'f.addEventListener("submit",function(ev){ev.preventDefault();e.textContent="";'
            'fetch("/api/auth",{method:"POST",headers:{"Content-Type":"application/json"},'
            'body:JSON.stringify({key:k.value})}).then(function(r){return r.json().then('
            'function(j){return{s:r.status,j:j};});}).then(function(res){'
            'if(res.j&&res.j.ok){location.href="/";}else{e.textContent=(res.j&&res.j.error)'
            '||("rejected ("+res.s+")");}}).catch(function(){e.textContent="network error";});'
            '});</script>')
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>ETS — access</title><style>'
        'html,body{margin:0;height:100%;background:#0E1214;color:#EAF1EF;'
        'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}'
        '.wrap{min-height:100%;display:flex;align-items:center;justify-content:center;padding:24px;}'
        '.card{width:min(360px,100%);background:linear-gradient(180deg,#151C1F,#1A2225);'
        'border:1px solid #253230;border-radius:16px;padding:28px;box-shadow:0 18px 40px -18px #000;}'
        'h1{font-size:17px;margin:0 0 4px;}h1 b{color:#4FE0AE;}'
        '.tag{font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:#5E6B68;'
        'font-weight:600;margin-bottom:20px;}'
        'input{width:100%;box-sizing:border-box;padding:11px 12px;border-radius:9px;'
        'background:#0F1517;border:1px solid #253230;color:#EAF1EF;font:inherit;margin-bottom:12px;}'
        'input:focus{outline:none;border-color:#1EB98A;}'
        'button{width:100%;padding:11px;border-radius:10px;border:1px solid #4FE0AE;'
        'background:#4FE0AE;color:#06110d;font:inherit;font-weight:650;cursor:pointer;}'
        '.err{color:#E86A6A;font-size:12px;min-height:16px;margin:10px 0 0;}'
        '.msg{color:#EAF1EF;font-size:14px;}.sub{color:#8A9794;font-size:12px;}'
        'code{color:#E8A24C;}</style></head><body><div class="wrap"><div class="card">'
        '<h1><b>ETS</b> — Equilibrium Tape Synth</h1>'
        '<div class="tag">hosted · access required</div>' + body +
        '</div></div></body></html>')


class SessionRegistry:
    """PUBLIC-mode per-visitor Companion registry. Each browser session (keyed by
    the ``ets_sid`` cookie) gets its OWN Companion with its OWN ``session_dir`` under
    ``base_dir/<sid>/`` and its OWN player state — no cross-visitor collision. Idle
    sessions are evicted on a TTL (deleting their dir + dropping their player) to
    bound disk + memory. This object exists ONLY in public mode; local loopback mode
    keeps the single shared Companion with no cookies and no registry.

    Access gate: a session is usable only once it is KEY-AUTHORIZED against
    ``access_keys`` (from ``ETS_ACCESS_KEYS``). Empty keys => fail CLOSED (nobody is
    authorized). A new key is minted by adding it to the ``ETS_ACCESS_KEYS`` env var
    — no code change is needed to add or revoke keys."""

    def __init__(self, cloud_url: str = "inproc", base_dir: Optional[str] = None,
                 seed: int = 0, access_keys=(), ttl: float = _SESSION_TTL_SEC,
                 max_global_trains: int = _MAX_GLOBAL_TRAINS) -> None:
        self.cloud_url = cloud_url
        self.base_dir = Path(base_dir) if base_dir else (_REPO_ROOT / "cache" / "companion_sessions")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.seed = int(seed)
        self.access_keys = tuple(k for k in (access_keys or ()) if k)
        self.ttl = float(ttl)
        self.max_global_trains = int(max_global_trains)
        self._sessions: dict = {}      # sid -> {"comp", "seen", "training", "auth"}
        self._active_trains = 0
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        """True iff at least one access key is set. False => the gate is CLOSED."""
        return bool(self.access_keys)

    # --- session resolution + TTL eviction ---------------------------------
    def get_or_create(self, sid: Optional[str]):
        """Return ``(companion, new_sid_or_None, authorized)`` for ``sid``. Mints a
        fresh session (dir + Companion) when the caller has no valid one. Sweeps and
        evicts idle sessions on every call so disk + memory stay bounded."""
        now = time.monotonic()
        with self._lock:
            self._evict_locked(now)
            rec = self._sessions.get(sid) if sid else None
            if rec is not None:
                rec["seen"] = now
                return rec["comp"], None, bool(rec["auth"])
            new_sid = secrets.token_hex(16)
            comp = Companion(cloud_url=self.cloud_url,
                             session_dir=str(self.base_dir / new_sid), seed=self.seed)
            comp.public = True
            self._sessions[new_sid] = {"comp": comp, "seen": now,
                                       "training": False, "auth": False}
            return comp, new_sid, False

    def _evict_locked(self, now: float) -> None:
        dead = []
        for sid, rec in self._sessions.items():
            if rec["training"]:
                continue                       # never evict a session mid-train
            player = getattr(rec["comp"], "_player", None)
            if player is not None and player.is_playing():
                rec["seen"] = now              # actively streaming: keep alive
                continue
            if now - rec["seen"] > self.ttl:
                dead.append(sid)
        for sid in dead:
            self._drop(self._sessions.pop(sid)["comp"])

    @staticmethod
    def _drop(comp: "Companion") -> None:
        player = getattr(comp, "_player", None)
        if player is not None:
            try:
                player.stop()
            except Exception:
                pass
        shutil.rmtree(comp.session_dir, ignore_errors=True)

    # --- access gate (public mode; constant-time key compare) --------------
    def key_valid(self, key) -> bool:
        """Constant-time membership test of ``key`` in the configured keys. Iterates
        ALL keys (no early-out) so timing never leaks which key matched. Keys are
        opaque strings and are NEVER logged."""
        if not key or not self.access_keys:
            return False
        ok = False
        for k in self.access_keys:
            if hmac.compare_digest(str(key), k):
                ok = True
        return ok

    def authorize(self, sid: Optional[str], key) -> bool:
        """Bind ``sid`` to authorized iff ``key`` is valid. Returns success."""
        if not self.key_valid(key):
            return False
        with self._lock:
            rec = self._sessions.get(sid)
            if rec is None:
                return False
            rec["auth"] = True
        return True

    # --- training caps (per-session single + small global cap) -------------
    def acquire_train(self, sid: Optional[str]):
        """Reserve a training slot: at most ONE per session and ``max_global_trains``
        across the box. Returns ``(ok, http_code, error_or_None)``."""
        with self._lock:
            rec = self._sessions.get(sid)
            if rec is None:
                return False, 409, "session expired — reload the page"
            if rec["training"]:
                return False, 409, "a training is already running for your session"
            if self._active_trains >= self.max_global_trains:
                return False, 429, "the box is busy training other sessions — try again shortly"
            rec["training"] = True
            self._active_trains += 1
            return True, 200, None

    def release_train(self, sid: Optional[str]) -> None:
        with self._lock:
            rec = self._sessions.get(sid)
            if rec is not None:
                rec["training"] = False
            if self._active_trains > 0:
                self._active_trains -= 1

    # --- per-session upload caps -------------------------------------------
    def check_ingest(self, comp: "Companion", incoming_len: int):
        """Enforce the per-session upload caps (byte total + file count). Returns
        ``(ok, http_code, error_or_None)``."""
        names = comp.session_files()
        if len(names) >= _MAX_SESSION_FILES:
            return False, 409, f"file limit reached ({_MAX_SESSION_FILES} files max per session)"
        used = 0
        for n in names:
            p = comp.session_dir / n
            if p.exists():
                used += p.stat().st_size
        if used + int(incoming_len or 0) > _MAX_SESSION_BYTES:
            mb = _MAX_SESSION_BYTES // (1024 * 1024)
            return False, 413, f"upload limit reached ({mb} MB max per session)"
        return True, 200, None


class _Handler(BaseHTTPRequestHandler):
    # Bound per server via ``type(...)`` in ``serve``. Exactly ONE is set:
    #   * LOCAL  mode: ``single_companion`` (the shared, trusted, uncapped box).
    #   * PUBLIC mode: ``registry`` (per-visitor sessions + caps + access gate).
    registry: "SessionRegistry" = None
    single_companion: Companion = None

    # --- per-request session resolution (public) / single companion (local) --
    def _resolve(self) -> None:
        """Bind ``self._comp`` (the Companion for THIS request), ``self._sid`` and
        ``self._authorized``. LOCAL mode: the single shared companion, no cookie, no
        gate (the local user is trusted). PUBLIC mode: the caller's per-visitor
        session (minted + Set-Cookie on first contact), plus its key-auth state."""
        self._pending_cookie = None
        self._sid = None
        self._authorized = True             # local mode: always allowed
        if self.registry is None:
            self._comp = self.single_companion
            return
        sid = self._read_sid()
        comp, new_sid, authorized = self.registry.get_or_create(sid)
        self._sid = new_sid or sid
        self._authorized = bool(authorized)
        if new_sid is not None:
            self._pending_cookie = new_sid
        self._comp = comp

    def _read_sid(self) -> Optional[str]:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return None
        try:
            jar = SimpleCookie(raw)
        except Exception:
            return None
        m = jar.get(_SID_COOKIE)
        val = m.value if m is not None else None
        return val if (val and _SID_RE.match(val)) else None

    def _emit_cookie(self) -> None:
        sid = getattr(self, "_pending_cookie", None)
        if sid:
            self.send_header(
                "Set-Cookie",
                f"{_SID_COOKIE}={sid}; Path=/; HttpOnly; SameSite=Lax; Max-Age={_COOKIE_MAX_AGE}")

    def _public_gate_ok(self, path: str) -> bool:
        """PUBLIC-mode key gate. Everything under /api/* requires a key-authorized
        session EXCEPT the platform liveness probe ``/api/health`` (no data, no
        compute — Railway's healthcheckPath must answer un-authed or the deploy
        restart-loops; mirrors the cloud service's 'health never gated' invariant)
        and the ``/api/auth`` handshake itself. Returns True if the request may
        proceed, else emits a 401 and returns False."""
        if self.registry is None:
            return True
        if path in ("/api/health", "/api/auth"):
            return True
        if self._authorized:
            return True
        self._json(401, {"ok": False, "error": "unauthorized — enter your access key",
                         "auth_required": True})
        return False

    def _send(self, code: int, body: bytes, ctype="application/octet-stream",
              no_store: bool = False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if no_store:
            self.send_header("Cache-Control", "no-store")
        self._emit_cookie()
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict):
        # no-store so per-session API responses are never served from a stale cache.
        self._send(code, json.dumps(obj).encode(), "application/json", no_store=True)

    # --- GET ----------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        self._resolve()
        path = self.path.split("?", 1)[0].rstrip("/")
        if path in ("", "/"):
            # PUBLIC: an un-authorized visitor gets the minimal access-key gate, not
            # the instrument. LOCAL: always the instrument (no gate).
            if self.registry is not None and not self._authorized:
                self._send(200, _gate_html(self.registry.configured).encode(),
                           "text/html; charset=utf-8", no_store=True)
                return
            self._serve_static("index.html", "text/html; charset=utf-8")
            return
        if path == "/api/health":
            cloud = self._comp.cloud_url if self._comp is not None else self.registry.cloud_url
            self._json(200, {"ok": True, "service": "ets-companion", "cloud": cloud})
            return
        if not self._public_gate_ok(path):
            return
        if path == "/api/status":
            self._json(200, {
                "session_dir": str(self._comp.session_dir),
                "files": self._comp.session_files(),
                "world": str(self._comp.world_path) if self._comp.world_path.exists() else None,
                "last_receipt": self._comp.last_receipt,
            })
            return
        if path == "/api/world":
            p = self._comp.player()
            info = p.world_info() if p is not None else {
                "ready": False, "reason": "no playable world loaded"}
            info["public"] = getattr(self._comp, "public", False)
            self._json(200, info)
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

    def _reject(self, code: int, obj: dict) -> None:
        """Reject a POST WITHOUT reading its (possibly large / not-yet-sent) body:
        send the response and mark the connection to close so the unread body is
        discarded by TCP. Used for the size caps and the un-authorized gate, where
        the whole point is to refuse before buffering the upload."""
        self.close_connection = True
        self._json(code, obj)

    # --- POST ---------------------------------------------------------------
    def do_POST(self):  # noqa: N802
        self._resolve()
        path = self.path.split("?", 1)[0].rstrip("/")
        comp = self._comp
        length = int(self.headers.get("Content-Length", 0) or 0)
        pub = self.registry is not None

        # PUBLIC access handshake: validate the access key (constant-time) and bind
        # THIS session to authorized. Fails CLOSED when no keys are configured. The
        # session cookie is set here (or was already set on the gate page load).
        if pub and path == "/api/auth":
            body = self.rfile.read(length) if length else b""
            key = None
            if body:
                try:
                    key = json.loads(body.decode()).get("key")
                except Exception:
                    key = None
            if not self.registry.configured:
                self._json(503, {"ok": False, "error": "access not configured on this server"})
                return
            if self.registry.authorize(self._sid, key):
                self._json(200, {"ok": True, "authorized": True})
            else:
                self._json(401, {"ok": False, "error": "invalid access key"})
            return

        # PUBLIC key gate on every other POST (auth-required). LOCAL: always passes.
        # A rejected POST may carry a large body we never read -> close, don't drain.
        if pub and path not in ("/api/health",) and not self._authorized:
            self._reject(401, {"ok": False, "error": "unauthorized — enter your access key",
                               "auth_required": True})
            return

        if path == "/api/ingest":
            # Store the dropped bytes in THIS session's dir; never forward (CS-1).
            # PUBLIC: enforce the per-session upload caps on the DECLARED length BEFORE
            # buffering the body, so an oversized/too-many upload is rejected without
            # ever reading it into RAM (reject + close, never drain).
            if pub:
                ok, code, err = self.registry.check_ingest(comp, length)
                if not ok:
                    self._reject(code, {"ok": False, "error": err})
                    return
            body = self.rfile.read(length) if length else b""
            fn = self.headers.get("X-Filename", "drop.bin")
            entry = comp.ingest_bytes(fn, body)
            self._json(200, {"ok": True, "ingested": entry, "files": comp.session_files()})
            return

        body = self.rfile.read(length) if length else b""

        if path == "/api/reset":
            # account-free "new corpus": clear THIS session + revert to the demo.
            out = comp.reset()
            self._json(200, {**out, "files": comp.session_files()})
            return

        # --- instrument control: region-tilt is the ONLY engine-bound gesture ---
        if path == "/api/steer":
            p = comp.player()
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
            p = comp.player()
            if p is None:
                self._json(409, {"ok": False, "error": "no playable world"})
                return
            p.start()
            self._json(200, {"ok": True, "playing": True})
            return
        if path == "/api/stop":
            p = comp.player()
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
            # PUBLIC: reserve a training slot (1 per session, small global cap) so a
            # single box can't be swamped; a clean 4xx when the cap bites.
            if pub:
                ok, code, err = self.registry.acquire_train(self._sid)
                if not ok:
                    self._json(code, {"ok": False, "error": err})
                    return
            try:
                out = comp.run_train(
                    seed=int(params.get("seed", 0)),
                    sweeps=int(params.get("sweeps", 8)),
                    sigma=params.get("sigma", None))
            except SystemExit as exc:      # ingest guidance (e.g. no protos)
                self._json(400, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:       # decode/verify/transport
                self._json(502, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return
            finally:
                if pub:
                    self.registry.release_train(self._sid)
            self._json(200, out)
            return

        self._send(404, b"not found", "text/plain")

    # --- streaming helpers (chunked; no Content-Length) ---------------------
    def _stream_audio(self):
        p = self._comp.player()
        if p is None:
            self._send(409, b"no playable world", "text/plain")
            return
        p.start()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Cache-Control", "no-store")
        self._emit_cookie()
        self.end_headers()
        try:
            for chunk in p.stream_chunks():
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ValueError):
            pass  # client closed the audio stream

    def _stream_telemetry(self):
        p = self._comp.player()
        if p is None:
            self._send(409, b"no playable world", "text/plain")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self._emit_cookie()
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


def _is_public(cli_public: bool = False) -> bool:
    """The public-bind switch. True ONLY when explicitly opted in via ``ETS_PUBLIC``
    (truthy env) or the ``--public`` CLI flag. This is the single sanctioned public
    mode and exists ONLY for the hosted Railway deploy (R6); the local default stays
    loopback. It is not a flag that bypasses the loopback guard silently — public
    mode is a distinct, explicit code path (see ``serve``)."""
    env = os.environ.get("ETS_PUBLIC", "").strip().lower()
    return bool(cli_public) or env in ("1", "true", "yes", "on")


def _require_loopback(host: str) -> str:
    """Structurally enforce the LOCAL-DEFAULT invariant: outside public mode the
    companion binds LOOPBACK ONLY (127.0.0.1 / ::1 / localhost). A non-loopback host
    — e.g. 0.0.0.0 — is refused here, so the local box cannot be widened into a
    public listener by a stray flag. The ONLY way to bind publicly is the explicit
    opt-in public mode (``ETS_PUBLIC=1`` / ``--public``), which is for the hosted
    Railway deploy only and takes a separate path that never calls this function."""
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
          session_dir: Optional[str] = None, public: bool = False,
          access_keys=()) -> ThreadingHTTPServer:
    """Start the companion. Returns the (already-serving is caller's job) server;
    callers in tests use ``server_close`` to stop.

    ``public`` selects both the bind policy AND the access model:

    * LOCAL (``public=False``, default): the host is passed through
      ``_require_loopback`` (loopback only, unchanged) and a SINGLE shared
      ``Companion`` serves the trusted local user — no cookies, no caps, no key gate.
    * PUBLIC (``public=True``, Railway deploy only): 0.0.0.0 is allowed as-is (the
      guard is a separate path, not weakened) and a ``SessionRegistry`` gives each
      key-authorized visitor an isolated per-session Companion with upload/training
      caps. ``access_keys`` (from ``ETS_ACCESS_KEYS``) are the only credentials that
      can open a session; empty => the gate is CLOSED (nobody gets in)."""
    host = host if public else _require_loopback(host)
    if public:
        reg = SessionRegistry(cloud_url=cloud_url, base_dir=session_dir,
                              access_keys=access_keys)
        handler = type("_BoundHandler", (_Handler,),
                       {"registry": reg, "single_companion": None})
        httpd = ThreadingHTTPServer((host, port), handler)
        httpd.registry = reg
        httpd.companion = None
        return httpd
    comp = Companion(cloud_url=cloud_url, session_dir=session_dir)
    comp.public = False
    handler = type("_BoundHandler", (_Handler,),
                   {"registry": None, "single_companion": comp})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.companion = comp
    return httpd


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m cloud.companion",
                                 description="ETS local companion (sealed on-device box)")
    ap.add_argument("--cloud-url", default=os.environ.get("ETS_CLOUD_URL", "inproc"),
                    help="cloud anchor-fit base URL (Railway), or 'inproc' for offline")
    ap.add_argument("--host", default=None,
                    help="bind host (default: 127.0.0.1 local; 0.0.0.0 in public mode)")
    ap.add_argument("--port", type=int, default=None,
                    help="bind port (default: 8770 local; $PORT in public mode)")
    ap.add_argument("--public", action="store_true",
                    help="PUBLIC bind for the hosted Railway deploy ONLY (allow 0.0.0.0, "
                         "read $PORT). Local default stays loopback; do not use locally.")
    ap.add_argument("--session-dir", default=None)
    args = ap.parse_args(argv)

    public = _is_public(args.public)
    # Bind defaults differ by mode. Public mode reads $HOST/$PORT (Railway injects
    # $PORT); local mode stays on loopback:8770. Explicit --host/--port always win.
    if args.host is not None:
        host = args.host
    elif public:
        host = os.environ.get("HOST", "0.0.0.0")
    else:
        host = "127.0.0.1"
    if args.port is not None:
        port = args.port
    elif public:
        port = int(os.environ.get("PORT", os.environ.get("ETS_COMPANION_PORT", "8770")))
    else:
        port = int(os.environ.get("ETS_COMPANION_PORT", "8770"))

    # Access keys (PUBLIC mode only): comma-separated opaque strings in
    # ETS_ACCESS_KEYS. A new key is minted simply by ADDING it to this env var and
    # restarting — no code change. Empty/unset in public mode => the gate is CLOSED
    # (fail closed: nobody is authorized). Keys are never logged.
    access_keys = [k.strip() for k in os.environ.get("ETS_ACCESS_KEYS", "").split(",")
                   if k.strip()]

    httpd = serve(cloud_url=args.cloud_url, host=host, port=port,
                  session_dir=args.session_dir, public=public, access_keys=access_keys)
    args.host, args.port = host, port  # for the log line below
    if public:
        print("[companion] PUBLIC MODE (Railway deploy) — binding a non-loopback listener")
        n = len(access_keys)
        print(f"[companion] access gate: {'CLOSED (no ETS_ACCESS_KEYS set)' if n == 0 else f'{n} key(s) configured'}")
    print(f"[companion] UI + API on http://{args.host}:{args.port}  (cloud={args.cloud_url})")
    if httpd.companion is not None:
        print(f"[companion] session dir: {httpd.companion.session_dir}")
    else:
        print(f"[companion] per-visitor session base: {httpd.registry.base_dir}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
