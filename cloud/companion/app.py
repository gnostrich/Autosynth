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
import ipaddress
import json
import os
import secrets
import sys
import threading
import time
from collections import OrderedDict
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
                 play_world: Optional[str] = None, seed: int = 0,
                 registry: "Optional[WorldRegistry]" = None) -> None:
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
        # The process-wide engine registry (shared demo player + LRU-capped trained
        # players + single-train lock). When None (standalone / the existing test
        # constructions), player() builds its own engine exactly as before, so the
        # local + keyless behavior is byte-for-byte unchanged. When set (a Hub-owned
        # session), engines are shared/pooled through it — the OOM fix.
        self.registry = registry
        # PROG (design §4A): the REAL, ordered stage transitions run_train records as
        # it walks the seam. /api/status exposes these; the FE renders them. Empty
        # until a train runs; each entry is {"stage", "t"} in emission order.
        self.train_stages: list = []
        # Opt-in share (default OFF). set_id identifies THIS session's trained set in
        # the shared catalog; opened_set_id is the shared set (if any) this session
        # has loaded into its player (a visitor consuming someone else's set).
        self.set_id: Optional[str] = None
        self.set_name: Optional[str] = None
        self.owner_label: Optional[str] = None
        self.shared: bool = False
        self.opened_set_id: Optional[str] = None
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
        """Lazily construct/resolve the LOCAL render bridge. Import is deferred so the
        companion's cloud path never pulls a decoder (CS-4).

        Two modes, one control law (region-tilt only) either way:
          * registry is None (standalone / keyless local): build a per-session engine
            once and cache it — the unchanged original behavior.
          * registry is set (Hub-owned session): resolve through the process-wide
            registry — the SHARED demo singleton for the demo world, or an LRU-capped
            trained/shared player for any other world. This is the OOM fix: one demo
            engine for everyone, a bounded number of trained engines resident."""
        if not self.play_world or not Path(self.play_world).exists():
            return None
        if self.registry is None:
            if self._player is None:
                from cloud.companion.engine_bridge import StreamPlayer
                self._player = StreamPlayer(self.play_world, seed=self.seed,
                                            is_trained=self._is_trained)
            return self._player
        if self.play_world == self._demo_world:
            return self.registry.demo_player(self._demo_world, self.seed)
        return self.registry.trained_player(self.play_world, self.seed)

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
        """Public train entry: enforce the single-in-proc-train bound (the OOM fix's
        third leg) and record the REAL stage transitions for /api/status (PROG).

        Concurrency: at most ONE in-process training at a time. A second concurrent
        train is REFUSED honestly (``TrainBusy`` -> the handler returns 429/busy) —
        never queued behind a promise that pretends to run. When there is no registry
        (standalone / the existing tests), there is a single session and no lock, so
        the behavior is unchanged."""
        reg = self.registry
        if reg is not None and not reg.begin_train():
            raise TrainBusy("a training is already running — try again shortly")
        self.train_stages = []

        def _prog(stage: str) -> None:
            # honest, real stage boundary — appended in emission order (design §4A).
            self.train_stages.append({"stage": stage, "t": time.time()})

        try:
            return self._run_train(seed=seed, sweeps=sweeps, sigma=sigma, progress=_prog)
        finally:
            if reg is not None:
                reg.end_train()

    def _run_train(self, seed: int = 0, sweeps: int = 8,
                   sigma: Optional[float] = None, progress=None) -> dict:
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
                cloud_url=self.cloud_url, seed=seed, sweeps=sweeps, sigma=sigma,
                progress=progress)
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
            self.opened_set_id = None          # my own world is live, not a shared one
            self.set_id = self.set_id or ("set-" + secrets.token_hex(4))
            if self.registry is not None:
                # hand the freshly-built engine to the LRU so it counts against the
                # cap and is shared/evicted with every other trained engine (rather
                # than pinned per-session forever — the OOM fix).
                self.registry.adopt(trained, player)
                self._player = None
            else:
                self._player = player          # reuse the already-loaded player
            return {"ok": True, "built": True, "receipt": out["receipt"],
                    "world": trained, "is_trained": True, "playback": "live",
                    "set_id": self.set_id,
                    "sigma_phi_disarmed": out.get("sigma_phi_disarmed", [])}

        from cloud.client.cli import train  # imported lazily; guarded path only

        # pick a .npz prototype bundle if present, else the session dir itself
        bundles = [p for p in self.session_dir.iterdir()
                   if p.is_file() and p.suffix == ".npz" and p.name != "world.npz"]
        corpus = str(bundles[0]) if bundles else str(self.session_dir)

        # Honest coarse stages for the geometry-only path: train() does ingest+fit+
        # verify+write as one guarded call, so we emit only the boundaries we can
        # truthfully observe (never inventing per-stage detail this path doesn't run).
        if progress is not None:
            progress("cloud_fit")
        result = train(corpus, service=self.cloud_url, out=str(self.world_path),
                       seed=seed, sweeps=sweeps, sigma=sigma, verbose=False)
        if progress is not None:
            progress("save")
        r = {k: (float(v) if hasattr(v, "__float__") and not isinstance(v, bool)
                 else (bool(v) if isinstance(v, bool) else v.tolist()
                       if hasattr(v, "tolist") else v))
             for k, v in result.receipt.items()}
        self.last_receipt = r
        return {"ok": True, "receipt": r, "world": str(self.world_path),
                "is_trained": False}


class TrainBusy(Exception):
    """Raised when a second concurrent in-proc train is refused (honest 429/busy)."""


def _build_stream_player(world_path: str, seed: int, is_trained: bool):
    """The SINGLE engine-build boundary (kept out of the class so it is one
    injectable seam). The decoder import is deferred here so the companion's cloud
    path stays provably decoder-free (CS-4); nothing above this line pulls a
    renderer. Tests inject a lightweight fake here to exercise the registry's
    sharing/eviction without loading the real engine."""
    from cloud.companion.engine_bridge import StreamPlayer
    return StreamPlayer(world_path, seed=seed, is_trained=bool(is_trained))


class WorldRegistry:
    """Process-wide engine pool — the OOM fix, one place, one policy.

    * ONE shared demo-world engine for every session (built once, reused). A fresh
      visitor never rebuilds the ~GB demo bank; they attach to the singleton.
    * Trained / shared-set engines live in an LRU capped at ``max_loaded``
      (``ETS_MAX_LOADED_WORLDS``, default 2). Loading past the cap EVICTS the
      least-recently-used engine: its StreamPlayer is stopped and dropped (engine +
      bank released to the GC). The world FILE stays on disk, so a later request
      reloads it on demand. Idle worlds thus cost only disk, not RAM.

    The lock makes get-or-build atomic so two simultaneous first-requests cannot
    each build the demo (which would defeat the singleton and the memory bound)."""

    def __init__(self, max_loaded: int = 2) -> None:
        self.max_loaded = max(1, int(max_loaded))
        self._demo = None
        self._demo_path: Optional[str] = None
        self._lru: "OrderedDict[str, object]" = OrderedDict()
        self._training = False
        self._lock = threading.Lock()

    def demo_player(self, demo_path: str, seed: int):
        with self._lock:
            if self._demo is None:
                self._demo = _build_stream_player(demo_path, seed, False)
                self._demo_path = demo_path
            return self._demo

    def trained_player(self, world_path: str, seed: int, is_trained: bool = True):
        with self._lock:
            p = self._lru.get(world_path)
            if p is None:
                p = _build_stream_player(world_path, seed, is_trained)
                self._lru[world_path] = p
            self._lru.move_to_end(world_path)
            self._evict_locked()
            return p

    def adopt(self, world_path: str, player) -> None:
        """Place an already-built trained engine into the LRU (used right after a
        train builds one) so it counts against the cap like any other."""
        with self._lock:
            self._lru[world_path] = player
            self._lru.move_to_end(world_path)
            self._evict_locked()

    def _evict_locked(self) -> None:
        while len(self._lru) > self.max_loaded:
            _old_path, old = self._lru.popitem(last=False)
            try:
                old.stop()                      # release engine + bank
            except Exception:
                pass

    def loaded_worlds(self):
        with self._lock:
            return list(self._lru.keys())

    # single-in-proc-train gate ---------------------------------------------
    def begin_train(self) -> bool:
        with self._lock:
            if self._training:
                return False
            self._training = True
            return True

    def end_train(self) -> None:
        with self._lock:
            self._training = False


class CatalogEntry:
    """One shared (published) set in the Explore catalog. Metadata only — the audio
    is never held here; playing a shared set loads its world through the SAME LRU
    path a session's own trained world uses (no separate render surface)."""

    def __init__(self, set_id, name, owner, world_path, region_armed, disarmed,
                 owner_token):
        self.set_id = set_id
        self.name = name
        self.owner = owner
        self.world_path = world_path
        self.region_armed = bool(region_armed)
        self.disarmed = list(disarmed or [])
        self.owner_token = owner_token           # only the owner may unshare

    def available(self) -> bool:
        # honest availability: the world file must still be on disk to play it.
        try:
            return bool(self.world_path) and Path(self.world_path).exists()
        except Exception:
            return False

    def public_view(self, mine: bool = False) -> dict:
        return {"id": self.set_id, "name": self.name, "owner": self.owner,
                "availability": "available" if self.available() else "unavailable",
                "region_armed": self.region_armed, "disarmed": self.disarmed,
                "mine": bool(mine)}


class Hub:
    """Per-server owner of sessions, the shared engine registry, the access-key gate,
    and the shared-set catalog. In KEYLESS mode (no ``ETS_ACCESS_KEYS``) there is a
    single default session and NO gate — today's behavior, unchanged. In KEYED mode
    each authenticated visitor gets its own session (its own ingest dir + trained
    world), and every /api route except health + auth requires a session token."""

    def __init__(self, cloud_url="inproc", session_dir=None, play_world=None,
                 seed=0, public=False, access_keys=None, max_loaded=None) -> None:
        self.cloud_url = cloud_url
        self._base = Path(session_dir) if session_dir else (_REPO_ROOT / "cache" / "companion_session")
        self._play_world = play_world
        self.seed = int(seed)
        self.public = bool(public)
        self.access_keys = set(k for k in (access_keys or []) if k)
        if max_loaded is None:
            max_loaded = int(os.environ.get("ETS_MAX_LOADED_WORLDS", "2"))
        self.registry = WorldRegistry(max_loaded=max_loaded)
        self.sessions: "dict[str, Companion]" = {}
        self.catalog: "dict[str, CatalogEntry]" = {}
        self._lock = threading.Lock()
        # the keyless / local single session shares the base dir so its on-disk
        # layout (and the existing tests' expectations) are exactly unchanged.
        self.default_session = self._make_session(self._base)
        self.default_session.public = self.public

    @property
    def keyed(self) -> bool:
        return bool(self.access_keys)

    def _make_session(self, session_dir) -> "Companion":
        comp = Companion(cloud_url=self.cloud_url, session_dir=str(session_dir),
                         play_world=self._play_world, seed=self.seed,
                         registry=self.registry)
        comp.public = self.public
        return comp

    def authenticate(self, key: str):
        """Validate a key against ETS_ACCESS_KEYS; on success mint a token and a
        fresh per-visitor session. Returns the token, or None for a bad key."""
        if not key or key not in self.access_keys:
            return None
        token = secrets.token_urlsafe(24)
        sess = self._make_session(self._base / ("visitor_" + token[:12]))
        sess.set_id = "set-" + token[:10]
        sess.owner_label = "you"
        with self._lock:
            self.sessions[token] = sess
        return token

    def session_for_token(self, token):
        if not token:
            return None
        with self._lock:
            return self.sessions.get(token)

    def playable_for(self, session):
        """Resolve the engine a session should be playing NOW, honoring revocation:
        if the session had opened a shared set that has since been unshared (or whose
        file vanished), silently revert it to the demo world (EXP-B: revocation
        actually revokes — a held handle stops resolving)."""
        sid = getattr(session, "opened_set_id", None)
        if sid is not None:
            entry = self.catalog.get(sid)
            if entry is None or not entry.available():
                session.opened_set_id = None
                session.play_world = session._demo_world
            else:
                session.play_world = entry.world_path
        return session.player()

    # --- shared-set catalog ------------------------------------------------
    def share(self, session, on: bool, name=None):
        """Toggle sharing of a session's OWN trained set. Opt-in, default OFF; only
        the owning session can list/delist its set (EXP: a stranger cannot publish
        or revoke someone else's set)."""
        if not session._is_trained or session.set_id is None:
            return {"ok": False, "error": "no trained set to share — train first"}
        sid = session.set_id
        if on:
            info = {}
            try:
                p = self.registry.trained_player(session.play_world, session.seed)
                info = p.world_info()
            except Exception:
                info = {"region_armed": False, "disarmed": []}
            entry = CatalogEntry(
                set_id=sid, name=(name or session.set_name or "shared set"),
                owner=(session.owner_label or "owner"),
                world_path=session.play_world,
                region_armed=info.get("region_armed", False),
                disarmed=info.get("disarmed", []),
                owner_token=session.set_id)
            with self._lock:
                self.catalog[sid] = entry
            session.shared = True
        else:
            with self._lock:
                self.catalog.pop(sid, None)
            session.shared = False
        return {"ok": True, "shared": session.shared, "set_id": sid}

    def explore(self, session):
        with self._lock:
            entries = list(self.catalog.values())
        mine = getattr(session, "set_id", None)
        return [e.public_view(mine=(e.set_id == mine)) for e in entries]

    def open_set(self, session, set_id):
        """Load a shared set into a session's player (reuses the LRU path). Refuses
        an unknown/unshared/unavailable id (EXP-A: unlisted is unreachable)."""
        entry = self.catalog.get(set_id)
        if entry is None or not entry.available():
            return None
        session.opened_set_id = set_id
        session.play_world = entry.world_path
        return entry


class _Handler(BaseHTTPRequestHandler):
    companion: Companion = None  # set on the server instance below
    hub: "Hub" = None            # the per-server session/registry/catalog owner

    # canonical unauthorized body — matches the deployed ets-web probe exactly.
    _UNAUTH = {"ok": False, "error": "unauthorized — enter your access key",
               "auth_required": True}

    def _send(self, code: int, body: bytes, ctype="application/octet-stream"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict, cookie: Optional[str] = None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if cookie is not None:
            self.send_header("Set-Cookie",
                             f"ets_session={cookie}; Path=/; SameSite=Strict")
        self.end_headers()
        self.wfile.write(body)

    # --- auth / session resolution -----------------------------------------
    def _token(self) -> Optional[str]:
        """Session token from an ``Authorization: Bearer`` header (API clients) or the
        ``ets_session`` cookie (the browser, set at /api/auth). Either transport is
        equivalent; the cookie lets same-origin GET / and streams carry auth with no
        per-request header wiring."""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip() or None
        for part in self.headers.get("Cookie", "").split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                if k == "ets_session":
                    return v or None
        return None

    def _session(self):
        """The authenticated session, or None. In KEYLESS mode (no ETS_ACCESS_KEYS)
        there is no gate and the single default session is always returned — today's
        behavior, untouched. In KEYED mode a valid token is required."""
        if not self.hub.keyed:
            return self.hub.default_session
        return self.hub.session_for_token(self._token())

    def _can_train(self, session) -> bool:
        """The single owner predicate that fixes all four (public × keyed) combos:
        a session may train/ingest/reset iff it is an OWNER, i.e. the deploy is keyed
        (reaching any session required a valid token) OR the session is not public.
        Only a KEYLESS-public visitor is the demo-only consumer."""
        return bool(self.hub.keyed or not getattr(session, "public", False))

    # --- GET ----------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        if path in ("", "/"):
            # KEYED + unauthenticated -> the access page. Otherwise the instrument.
            if self.hub.keyed and self._session() is None:
                self._serve_static("access.html", "text/html; charset=utf-8")
            else:
                self._serve_static("index.html", "text/html; charset=utf-8")
            return
        if path == "/api/health":
            # liveness stays UNGATED (platform probe + the FE's dead-vs-loading
            # signal must work before/without a token). It carries no session data.
            self._json(200, {"ok": True, "service": "ets-companion",
                             "cloud": self.hub.cloud_url})
            return
        if path.startswith("/static/"):
            self._serve_static(path[len("/static/"):], self._ctype(path))
            return

        # everything below is a gated /api route in KEYED mode.
        session = self._session()
        if session is None:
            self._json(401, dict(self._UNAUTH))
            return

        if path == "/api/status":
            self._json(200, {
                "session_dir": str(session.session_dir),
                "files": session.session_files(),
                "world": str(session.world_path) if session.world_path.exists() else None,
                "last_receipt": session.last_receipt,
                "is_trained": session._is_trained,
                "shared": session.shared,
                "set_id": session.set_id,
                "opened_set_id": session.opened_set_id,
                # KEYED-TRAIN (R6 reading): a keyed session is an owner (reaching the
                # session at all required a valid token), so it keeps full owner
                # powers even under ETS_PUBLIC. Only KEYLESS public is the demo-only
                # visitor. can_train is the ONE predicate both layers branch on.
                "keyed": self.hub.keyed,
                "can_train": self._can_train(session),
                # PROG (design §4A): the REAL ordered stage transitions of the last/
                # running train — the FE renders the staged indicator from THESE only.
                "train_stages": list(session.train_stages),
            })
            return
        if path == "/api/world":
            p = self.hub.playable_for(session)
            info = p.world_info() if p is not None else {
                "ready": False, "reason": "no playable world loaded"}
            info["public"] = getattr(session, "public", False)
            info["opened_set_id"] = session.opened_set_id
            # KEYED-TRAIN: expose the owner predicate so the FE shows Train for keyed
            # sessions (read-only state; no new authority — the gate stays server-side).
            info["can_train"] = self._can_train(session)
            self._json(200, info)
            return
        if path == "/api/explore":
            self._json(200, {"ok": True, "sets": self.hub.explore(session)})
            return
        if path == "/api/stream":
            self._stream_audio(session)
            return
        if path == "/api/telemetry":
            self._stream_telemetry(session)
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

        # /api/auth is the ONE ungated POST — it is how a keyed visitor obtains a
        # token. A good key mints a token (returned in JSON AND set as a cookie for
        # the browser); a bad/missing key is refused honestly.
        if path == "/api/auth":
            key = ""
            if body:
                try:
                    key = str(json.loads(body.decode()).get("key", ""))
                except Exception:
                    key = ""
            if not self.hub.keyed:
                # keyless deployment: no gate at all — auth is a no-op success.
                self._json(200, {"ok": True, "token": None, "keyed": False})
                return
            token = self.hub.authenticate(key)
            if token is None:
                self._json(401, {"ok": False, "error": "invalid access key",
                                 "auth_required": True})
                return
            self._json(200, {"ok": True, "token": token, "keyed": True}, cookie=token)
            return

        # every other /api POST is gated in KEYED mode.
        session = self._session()
        if session is None:
            self._json(401, dict(self._UNAUTH))
            return

        # PUBLIC (hosted, keyless-R6) mode is a play/steer-the-demo deployment only.
        # The corpus surfaces (upload, train, reset) write session state and need the
        # ingest deps that aren't in the hosted image — refuse them cleanly (503)
        # rather than expose a broken surface. KEYED sessions are OWNERS (a valid token
        # was required to reach this session), so the key gate SUPERSEDES the R6 demo
        # restriction: the 503 fires only for KEYLESS public visitors. The FE hides
        # these when !can_train.
        if getattr(session, "public", False) and not self.hub.keyed and path in (
                "/api/ingest", "/api/train", "/api/reset", "/api/share"):
            self._json(503, {"ok": False, "error": "not available in the hosted "
                             "demo — run the companion locally to train your own "
                             "audio", "public": True})
            return

        if path == "/api/ingest":
            # LOCAL-ONLY: store bytes, never forward. Filename via X-Filename.
            fn = self.headers.get("X-Filename", "drop.bin")
            entry = session.ingest_bytes(fn, body)
            self._json(200, {"ok": True, "ingested": entry,
                             "files": session.session_files()})
            return

        if path == "/api/reset":
            # account-free "new corpus": clear session + world, LOCAL-ONLY
            out = session.reset()
            self._json(200, {**out, "files": session.session_files()})
            return

        # --- instrument control: region-tilt is the ONLY engine-bound gesture ---
        if path == "/api/steer":
            p = self.hub.playable_for(session)
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
            p = self.hub.playable_for(session)
            if p is None:
                self._json(409, {"ok": False, "error": "no playable world"})
                return
            p.start()
            self._json(200, {"ok": True, "playing": True})
            return
        if path == "/api/stop":
            p = self.hub.playable_for(session)
            if p is not None:
                p.stop()
            self._json(200, {"ok": True, "playing": False})
            return

        # --- shared-set catalog (opt-in, per set; region-tilt only for visitors) ---
        if path == "/api/share":
            on = True
            name = None
            if body:
                try:
                    j = json.loads(body.decode())
                    on = bool(j.get("on", True))
                    name = j.get("name")
                    sid = j.get("set_id")
                    if sid is not None and sid != session.set_id:
                        # you may only share/unshare YOUR OWN set.
                        self._json(403, {"ok": False, "error": "not your set"})
                        return
                except Exception:
                    pass
            self._json(200, self.hub.share(session, on, name=name))
            return
        if path == "/api/open":
            sid = None
            if body:
                try:
                    sid = json.loads(body.decode()).get("set_id")
                except Exception:
                    sid = None
            entry = self.hub.open_set(session, sid)
            if entry is None:
                self._json(404, {"ok": False, "error": "set not available"})
                return
            self._json(200, {"ok": True, "set_id": entry.set_id,
                             "name": entry.name, "owner": entry.owner})
            return

        if path == "/api/train":
            params = {}
            if body:
                try:
                    params = json.loads(body.decode())
                except Exception:
                    params = {}
            try:
                out = session.run_train(
                    seed=int(params.get("seed", 0)),
                    sweeps=int(params.get("sweeps", 8)),
                    sigma=params.get("sigma", None))
            except TrainBusy as exc:       # a second concurrent train — honest 429
                self._json(429, {"ok": False, "error": str(exc), "busy": True})
                return
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
    def _stream_audio(self, session):
        p = self.hub.playable_for(session)
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

    def _stream_telemetry(self, session):
        p = self.hub.playable_for(session)
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
          session_dir: Optional[str] = None, public: bool = False) -> ThreadingHTTPServer:
    """Start the companion. Returns the (already-serving is caller's job) server;
    callers in tests use ``server_close`` to stop.

    ``public`` selects the bind policy. When False (default), the host is passed
    through ``_require_loopback`` — loopback only, the unchanged local default.
    When True (public mode, Railway deploy only), a non-loopback host such as
    0.0.0.0 is allowed as-is; the guard is not weakened, it is a separate path
    reached only by the explicit opt-in."""
    host = host if public else _require_loopback(host)
    access_keys = _access_keys()
    hub = Hub(cloud_url=cloud_url, session_dir=session_dir, public=bool(public),
              access_keys=access_keys)
    # The default (keyless) session preserves the exact single-session on-disk layout
    # + public gating; httpd.companion stays pointed at it for back-compat.
    comp = hub.default_session
    handler = type("_BoundHandler", (_Handler,), {"companion": comp, "hub": hub})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.companion = comp
    httpd.hub = hub
    return httpd


def _access_keys():
    """Parse ``ETS_ACCESS_KEYS`` (comma-separated). Empty/unset -> KEYLESS mode (no
    gate; today's behavior exactly). The gate ARMS only when at least one key is
    configured — it is never on by default."""
    raw = os.environ.get("ETS_ACCESS_KEYS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


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

    httpd = serve(cloud_url=args.cloud_url, host=host, port=port,
                  session_dir=args.session_dir, public=public)
    args.host, args.port = host, port  # for the log line below
    if public:
        print("[companion] PUBLIC MODE (Railway deploy) — binding a non-loopback listener")
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
