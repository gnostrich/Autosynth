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
import logging
import os
import secrets
import sys
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

log = logging.getLogger("ets.companion")

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
                 registry: "Optional[WorldRegistry]" = None,
                 surface_demo: bool = True) -> None:
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
        # VISITOR TIER (OPEN_ENDS #16): in a KEYED deploy an unauthenticated request
        # resolves to a read/play visitor session (is_visitor=True). A visitor may
        # read + play + steer + open shared sets, but is NOT an owner: ingest / train
        # / reset / share stay key-gated (401, so the in-app "unlock training"
        # affordance can upgrade the page). The Hub flips this on the shared session
        # it hands to keyless requests in keyed mode; every keyed-authenticated /
        # keyless-local / legacy-public session leaves it False.
        self.is_visitor: bool = False
        # playable world for the INSTRUMENT (default: the repo's founding world).
        self.seed = int(seed)
        if play_world is None and surface_demo:
            # LOCAL / fresh-clone path (R5): prefer the COMMITTED self-contained demo
            # (embedded audio, no external files) so a fresh clone plays out of the
            # box; fall back to a local corpus.etsworld if present (dev machines).
            #
            # HOSTED path (surface_demo=False, set by the Hub for public deploys per
            # OPEN_ENDS #16(c)): the founding demo is NOT surfaced on the site — the
            # initial Play state is EMPTY until the user opens a shared set from
            # Explore or (keyed) trains their own world. play_world stays None so the
            # demo engine never even spins up (a memory win too — no boot-time load).
            for _name in ("demo.etsworld", "corpus.etsworld"):
                cand = _REPO_ROOT / _name
                if cand.exists():
                    play_world = str(cand)
                    break
        # remember the demo/founding world so reset() can revert to it. On the hosted
        # path this is None -> reset reverts to the honest EMPTY state, not the demo.
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

    def ingested_track_names(self):
        """The REAL ingested audio filenames of this session's corpus, in the same
        sorted order the train seam consumes them — so index i IS track id i (the
        T0,T1,... order the Source Library shows). The single source both the
        /api/world name override and the share-catalog snapshot read; never an
        invented name (empty when no audio was ingested)."""
        return [f for f in self.session_files()
                if os.path.splitext(f)[1].lower() in _AUDIO_EXTS]

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
            # PRE-WARM on train-complete (OPEN_ENDS #21d): the world just went
            # live — build its bank + first bars NOW, before any listener.
            _prewarm_engine(self.registry, trained, player)
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


def _prewarm_engine(registry, world_path: str, player) -> None:
    """PRE-WARM (OPEN_ENDS #21d): start a world's produce loop the moment it goes
    LIVE (train completes / a set is shared), instead of waiting for the first
    listener. ``player.start()`` returns immediately — it spawns the daemon
    produce-loop thread, and THAT background thread pays the bank build + first
    renders (the observed ~6-9 min post-deploy cold window), so the first
    listener connects to an already-warm stream.

    DISCLOSED TRADEOFF (operator-accepted): this spends CPU rendering bars for a
    world nobody may ever listen to, in exchange for first-listen latency.

    GUARD: only the ONE world involved is ever warmed, and only while it is
    still resident in the registry LRU (within ETS_MAX_LOADED_WORLDS) — a
    pre-warm never loads or pins an engine past the memory cap, and an LRU
    eviction stops a warming loop like any other (``stop()`` on evict).

    A pre-warm failure must not fail the already-completed train/share: it is
    logged LOUDLY (never swallowed) and the first listener will hit the same
    error honestly via the bridge's last_error readout."""
    if registry is not None and world_path not in registry.loaded_worlds():
        return                       # evicted already — the memory bound wins
    try:
        player.start()
    except Exception:
        log.exception("pre-warm failed for %s", world_path)


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
                 owner_token, track_names=None):
        self.set_id = set_id
        self.name = name
        self.owner = owner
        self.world_path = world_path
        self.region_armed = bool(region_armed)
        self.disarmed = list(disarmed or [])
        self.owner_token = owner_token           # only the owner may unshare
        # HONEST attribution the owner OPTED to publish with the set: the real
        # ingested filenames by track id ({int tid: name}), snapshotted at share
        # time. Served only via /api/world to sessions that OPENED this set (the
        # legend/labels), never invented — empty means "keep the generic labels".
        self.track_names = dict(track_names or {})

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
    and the shared-set catalog.

    Session model (one rule): whoever is NOT the machine's owner gets their OWN
    session. Concretely:
      * KEYLESS-LOCAL — the single default session (the person at the machine IS
        the owner; one corpus at a time, R4). Unchanged.
      * KEYED — a valid token resolves to that visitor's OWNER session; every
        keyless request resolves to a PER-VISITOR anonymous session (minted with an
        ``ets_session`` cookie on first API contact). Anonymous visitors are
        ISOLATED from each other: one visitor's opened set never appears on
        another's Play page.
      * KEYLESS-PUBLIC (legacy) — same per-visitor anonymous sessions; the R6
        demo-only 503 gate on owner surfaces is unchanged.
    Sessions are POINTERS (opened set, ingest dir, flags) — engines stay shared and
    bounded through the ONE WorldRegistry LRU, so per-visitor sessions add no
    engine memory. Anonymous sessions live in a capped in-memory LRU (known #17:
    in-memory, reset on redeploy; an evicted visitor honestly re-lands on the empty
    state and can re-open a set)."""

    def __init__(self, cloud_url="inproc", session_dir=None, play_world=None,
                 seed=0, public=False, access_keys=None, max_loaded=None) -> None:
        self.cloud_url = cloud_url
        self._base = Path(session_dir) if session_dir else (_REPO_ROOT / "cache" / "companion_session")
        self._play_world = play_world
        self.seed = int(seed)
        self.public = bool(public)
        # HOSTED-surface demo policy (OPEN_ENDS #16(c)): the founding demo is surfaced
        # ONLY on non-public (local / fresh-clone, R5) runs. On the PUBLIC hosted site
        # no session auto-loads the demo — the initial Play state is empty until a
        # shared set is opened or a keyed user trains. An explicit ``play_world``
        # (tests / a pinned deploy) always wins, so this only governs the default.
        self._surface_demo = not self.public
        self.access_keys = set(k for k in (access_keys or []) if k)
        if max_loaded is None:
            max_loaded = int(os.environ.get("ETS_MAX_LOADED_WORLDS", "2"))
        self.registry = WorldRegistry(max_loaded=max_loaded)
        self.sessions: "dict[str, Companion]" = {}
        # PER-VISITOR anonymous sessions (keyless requests on keyed/public deploys),
        # token -> Companion, LRU-capped. Pointers only — engines stay in the shared
        # registry, so the cap is about not accreting session objects forever
        # (in-memory, known #17), not about engine RAM.
        self.max_anon = int(os.environ.get("ETS_MAX_ANON_SESSIONS", "1024"))
        self.anon_sessions: "OrderedDict[str, Companion]" = OrderedDict()
        self.catalog: "dict[str, CatalogEntry]" = {}
        self._lock = threading.Lock()
        # the keyless / local single session shares the base dir so its on-disk
        # layout (and the existing tests' expectations) are exactly unchanged. It
        # serves ONLY keyless-LOCAL requests now; on keyed/public deploys keyless
        # requests get per-visitor anonymous sessions instead (never this shared
        # object — the cross-visitor leak fix). is_visitor mirrors the deploy mode
        # for back-compat with direct constructions in tests.
        self.default_session = self._make_session(self._base)
        self.default_session.public = self.public
        self.default_session.is_visitor = self.keyed

    @property
    def keyed(self) -> bool:
        return bool(self.access_keys)

    def _make_session(self, session_dir) -> "Companion":
        comp = Companion(cloud_url=self.cloud_url, session_dir=str(session_dir),
                         play_world=self._play_world, seed=self.seed,
                         registry=self.registry, surface_demo=self._surface_demo)
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

    # --- per-visitor ANONYMOUS sessions (shared deploys only) ----------------
    def anon_session(self, token):
        """Resolve an existing anonymous visitor session by its cookie token, or
        None (unknown / evicted / restarted server -> the caller mints afresh)."""
        if not token:
            return None
        with self._lock:
            sess = self.anon_sessions.get(token)
            if sess is not None:
                self.anon_sessions.move_to_end(token)
            return sess

    def new_anon_session(self):
        """Mint a fresh anonymous visitor session + token (set as the visitor's
        ``ets_session`` cookie by the handler). Same Companion construction as every
        other session; is_visitor marks it a non-owner on keyed deploys (the same
        single owner predicate — no second decision channel)."""
        token = secrets.token_urlsafe(24)
        sess = self._make_session(self._base / ("anon_" + token[:12]))
        sess.is_visitor = self.keyed
        evicted = []
        with self._lock:
            self.anon_sessions[token] = sess
            while len(self.anon_sessions) > self.max_anon:
                evicted.append(self.anon_sessions.popitem(last=False)[1])
        # Disk-side of the LRU (auditor note, 2026-07-18): eviction must also
        # remove the session's (empty) directory, or crawler traffic accretes
        # dirs without bound. Visitor sessions cannot ingest, so rmdir — which
        # refuses non-empty dirs — is the safe form; anything non-empty is left
        # in place rather than destroyed.
        for old in evicted:
            try:
                os.rmdir(old.session_dir)
            except OSError:
                pass
        return token, sess

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
            p = None
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
                owner_token=session.set_id,
                # sharing is the owner's opt-in: publish the REAL ingested track
                # names with the set (index i = track id i, the train-seam order),
                # so openers see honest attribution instead of "track N".
                track_names={i: n for i, n in
                             enumerate(session.ingested_track_names())})
            with self._lock:
                self.catalog[sid] = entry
            session.shared = True
            # PRE-WARM on share (OPEN_ENDS #21d): a just-listed set will draw its
            # first stranger-listener cold; warm the ONE shared world now.
            if p is not None:
                _prewarm_engine(self.registry, session.play_world, p)
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
    _mint = None                 # anon token minted for THIS request (reset per request)

    # canonical unauthorized body — matches the deployed ets-web probe exactly.
    _UNAUTH = {"ok": False, "error": "unauthorized — enter your access key",
               "auth_required": True}

    def _send(self, code: int, body: bytes, ctype="application/octet-stream"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # no-store: without it, browsers heuristically cache the HTML/JS and
        # keep showing a STALE app after a deploy (observed live 2026-07-18:
        # a phone kept rendering the retired founding-demo page). The app is
        # one small page; always-fresh beats cache here.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict, cookie: Optional[str] = None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")   # API state is live, never cacheable
        if cookie is None:
            # a session token minted while resolving THIS request (an anonymous
            # visitor's first API contact) rides out on the same response.
            cookie = getattr(self, "_mint", None)
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
        """The session for THIS request — never None on the serving path (OPEN_ENDS
        #16: no access wall). Resolution order:
          * KEYLESS-LOCAL -> the single default session (the person at the machine
            is the owner; one corpus at a time). Unchanged.
          * KEYED, valid token -> that visitor's OWNER session.
          * otherwise (keyless request on a keyed or public deploy) -> that
            visitor's OWN anonymous session, resolved by the ``ets_session`` cookie
            or minted now (the cookie rides out on this response via _json). Two
            anonymous visitors NEVER share a session, so one visitor's opened set
            cannot appear on another's Play page. A cookie-less client simply gets
            a fresh session per request — honest statelessness, never a shared one."""
        token = self._token()
        if self.hub.keyed:
            sess = self.hub.session_for_token(token)
            if sess is not None:
                return sess
        elif not self.hub.public:
            return self.hub.default_session
        sess = self.hub.anon_session(token)
        if sess is None:
            self._mint, sess = self.hub.new_anon_session()
        return sess

    def _can_train(self, session) -> bool:
        """The single OWNER predicate that pins every (public × keyed × visitor)
        combo. A session may ingest/train/reset/share iff it is an OWNER:
          * KEYED deploy  -> owner iff it is NOT a visitor session (i.e. it was
            reached with a valid token). A keyless (anonymous) visitor is not an
            owner.
          * KEYLESS deploy -> owner iff not public (local run). The legacy
            keyless-public session is the demo-only consumer.
        This is the ONE channel both the POST gate and the FE branch on."""
        if self.hub.keyed:
            return not getattr(session, "is_visitor", False)
        return not getattr(session, "public", False)

    # --- GET ----------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        self._mint = None            # per-request (handlers persist across keep-alive)
        path = self.path.split("?", 1)[0].rstrip("/")
        if path in ("", "/"):
            # NO ACCESS WALL (OPEN_ENDS #16): GET / always serves the app. A keyless
            # visitor gets the read/play visitor session; the access-key entry is now
            # an in-app "unlock training" affordance, not a gate page.
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

        # The read/play /api routes below serve OWNERS and VISITORS alike (OPEN_ENDS
        # #16). _session() never returns None on the serving path (keyless-local ->
        # default; keyed -> owner-by-token; otherwise the visitor's own anonymous
        # session); the None guard stays as a defensive backstop only.
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
            if p is None:
                # HONEST EMPTY STATE (OPEN_ENDS #16(c)): no world is loaded. The demo
                # is not surfaced on the hosted site, so a fresh session plays nothing
                # until it opens a shared set from Explore or (keyed) trains its own.
                # The reason is tailored to what THIS session can do so the FE can
                # point the right way; ``loaded:false`` distinguishes this from a world
                # that exists but is still warming up (never conflated with "loading").
                reason = ("no set loaded — train your own, or open a shared set "
                          "from Explore" if self._can_train(session)
                          else "no set loaded — open a shared set from Explore")
                info = {"ready": False, "loaded": False, "reason": reason}
            else:
                info = p.world_info()
            info["public"] = getattr(session, "public", False)
            info["opened_set_id"] = session.opened_set_id
            # KEYED-TRAIN: expose the owner predicate so the FE shows Train for keyed
            # sessions (read-only state; no new authority — the gate stays server-side).
            info["can_train"] = self._can_train(session)
            # VISITOR TIER (OPEN_ENDS #16): whether the deploy is keyed decides if the
            # in-app "unlock training" affordance is offered. A keyless visitor on a
            # KEYED deploy can upgrade with a key; on a keyless deploy there is no key
            # to enter, so the FE shows no unlock affordance.
            info["keyed"] = self.hub.keyed
            # STATIC per-world FIELD telemetry (read-only, once-per-world): the
            # per-track anchor-mass profiles + per-role unit pools that carry the
            # field's TRACK and UNIT grains. Same reductions the desktop emits over
            # /ets/profiles + /ets/unitpool; folded into /api/world so the FE gets
            # them with the world. No new route, no new authority.
            if p is not None:
                try:
                    info.update(p.static_field())
                except Exception as exc:
                    # HONEST degradation, not a silent dodge (auditor note 1):
                    # a world without provenance legitimately stays role-grain-
                    # only (prereg wall #1), but the fault is SURFACED in the
                    # log + payload so a genuine reduction bug cannot hide
                    # behind the degradation path.
                    log.warning("static_field unavailable -> role-grain-only "
                                "field: %s", exc)
                    info["field_degraded"] = f"{type(exc).__name__}: {exc}"
                # HONEST track NAMES: the world carries no source filenames, but two
                # honest sources exist beyond the bridge's generic "track N":
                #   * a session's OWN trained world -> the SESSION's real ingested
                #     filenames by track index (the same T0,T1… order the Source
                #     Library shows);
                #   * an OPENED shared set -> the names its OWNER opted to publish
                #     with it at share time (the catalog snapshot).
                # Everything else (demo / no shared names) keeps the honest generic
                # label — never an invented name.
                names = dict(info.get("track_names", {}))
                if session._is_trained and session.opened_set_id is None:
                    audio = session.ingested_track_names()
                    for tid_str in list(names.keys()):
                        i = int(tid_str)
                        if 0 <= i < len(audio):
                            names[tid_str] = audio[i]
                elif session.opened_set_id is not None:
                    entry = self.hub.catalog.get(session.opened_set_id)
                    shared = entry.track_names if entry is not None else {}
                    for tid_str in list(names.keys()):
                        n = shared.get(int(tid_str))
                        if n:
                            names[tid_str] = n
                info["track_names"] = names
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
        self._mint = None            # per-request (handlers persist across keep-alive)
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

        # Resolve the session (never None on the serving path: keyless-local ->
        # default; keyed -> owner-by-token; otherwise the visitor's own anon session).
        session = self._session()

        # OWNER GATE (OPEN_ENDS #16): the corpus surfaces (ingest/train/reset/share)
        # are OWNER-only. A non-owner hitting one is refused by the SINGLE owner
        # predicate — no second decision channel:
        #   * KEYED deploy -> a keyless VISITOR gets 401 auth_required, so the in-app
        #     "unlock training" affordance can enter a key and upgrade the page. (This
        #     replaces the old access wall; it is NOT the legacy 503.)
        #   * KEYLESS-public (legacy, no keys configured) -> the R6 demo-only 503
        #     stays exactly as before (there is no key to enter).
        # Owners (keyed-authenticated, or keyless-local) fall through and proceed.
        if path in ("/api/ingest", "/api/train", "/api/reset", "/api/share") \
                and not self._can_train(session):
            if self.hub.keyed:
                self._json(401, dict(self._UNAUTH))
            else:
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
