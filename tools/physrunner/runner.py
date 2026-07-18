"""ETS PHYSICS RUNNER — an isolated, throwaway compute surface for heavy
conjugacy-physics ensembles (papers/DIRECTIVE-conjugacy-reconciliation.md §1B:
reciprocity P1, σ_φ=FDT P5, holonomy P3) at psytech scale.

WHY THIS EXISTS. The physics predictions in §1B are estimated over the writer's
T_s>0 sampling ensemble; at scale that is thousands of settles, far more than a
live web request should carry. This service runs those settles on Railway compute
in TEMPORARY projects, one job at a time per instance, so a heavy sweep can be
fanned out across many instances WITHOUT ever touching the live ets-web service.

WHAT IT IS — a THEORY INSTRUMENT on COMMITTED corpora, nothing more:
  * It loads a COMMITTED repo world (demo.etsworld, or a synthetic fixture shipped
    in-image) and runs the SAME streaming writer the live engine uses
    (ets.writer.stream.StreamWriter.write_bar), mirroring the T_s>0 sampling
    ensemble of architecture-v6/scripts/run_sigma_phi.py.
  * It returns NUMBERS ONLY — per-settle arrangement observables (φ statistics,
    committed occupancy O, gauge-frame reads). It returns NO audio, NO recipes,
    NO source-unit material.

CS / R POSTURE (cloud/COMPANION_INVARIANTS.md, ETS CS-1..CS-5):
  * NO USER-AUDIO PATH. There is no ingest endpoint and no way to feed audio in.
    The only worlds it can settle are committed repo worlds / in-image fixtures
    (privacy boundary preserved: user audio never reaches this box).
  * NO TRAINING. There is no anchor-fit / LAMBDA / σ_φ authoring here — the image
    deliberately omits torch/beat_this. Settlement reads a FROZEN world; it never
    writes one. σ_φ is only READ (embedded in the world), never fabricated.
  * NO DECODER CLAIMS beyond what settlement needs. No render, no bank build, no
    PCM. The runner exercises the arrangement side of the engine only.

ENGINE OWNERSHIP (mirrors cloud/companion/engine_bridge.py): architecture-v6 is
forced to the FRONT of sys.path so `import ets` resolves to the ui-v5 engine tree,
with a loud assert if the root engine-v1 shadowed it.

AUTH. Every /job request must carry `X-Runner-Token` equal to env RUNNER_TOKEN
(set at deploy). Missing/unset token ⇒ refused. /health is open (platform probe).

CONCURRENCY. Jobs run SYNCHRONOUSLY in-request; at most ONE job at a time per
instance (a second concurrent job gets 409). The CALLER parallelizes across
INSTANCES, not threads — this keeps each instance's memory bounded to one
settlement ensemble at a time.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Optional

import numpy as np

log = logging.getLogger("ets.physrunner")

# tools/physrunner/runner.py -> parents[2] is the repo root (the Docker build
# copies ets/, architecture-v6/, demo.etsworld, tools/physrunner/ under /app,
# so this resolves to /app in the image and the repo root in a checkout).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ARCH_V6 = str(_REPO_ROOT / "architecture-v6")

# canonical direction-lane names the runner accepts in a u-point, mapped to the
# LaneVector field they set (ets.panel.lanes: the exhaustive six).
_LANE_KEYS = frozenset(
    {"region", "density", "continuity", "gauge", "novelty", "temperature"})

# guardrail so an accidental huge request cannot exhaust an instance's memory
# (one job at a time is the primary bound; this backstops a fat-fingered n).
_MAX_TOTAL_SETTLES = 200_000


def _load_engine():
    """Force the ui-v5 engine tree to the FRONT of sys.path and import it, with a
    LOUD ownership assert (mirrors cloud/companion/engine_bridge.py). Membership is
    not enough — root engine-v1 must not shadow the arch-v6 engine, so we remove
    any stale entry then insert at 0, then verify the module we resolved actually
    lives under architecture-v6/. Returns the symbols the settle path needs."""
    while _ARCH_V6 in sys.path:
        sys.path.remove(_ARCH_V6)
    sys.path.insert(0, _ARCH_V6)
    import ets.engine.engine as _eng
    resolved = getattr(_eng, "__file__", "?")
    if not str(resolved).startswith(_ARCH_V6):
        raise RuntimeError(
            "physrunner resolved the WRONG engine tree: `import ets.engine.engine` "
            f"loaded {resolved!r}, not the ui-v5 engine under {_ARCH_V6!r}. The "
            "arch-v6 tree must own `import ets`; ensure no root-ets import precedes "
            "the runner.")
    from ets.engine.engine import Engine, resolve_sigma
    from ets.engine.worldfile import load_world
    from ets.panel.lanes import default_lane_vector
    return Engine, resolve_sigma, load_world, default_lane_vector


# --------------------------------------------------------------------------
# observable collection (numbers only — the whole privacy posture in one place)
# --------------------------------------------------------------------------

def _f(x) -> float:
    return float(np.asarray(x).reshape(-1)[0]) if np.ndim(x) else float(x)


def _collect(r, frame, names: List[str]) -> dict:
    """Reduce ONE settled bar (a BarResult `r` + the writer's current gauge
    `frame`) to the requested observables. Every value is plain float / list —
    no audio, no unit ids beyond the arrangement statistics the connector's
    Layer-0 φ already expose. Unknown names raise (fail loud, never silently
    drop a requested observable)."""
    phi = r.phi
    out = {"bar": int(r.bar)}
    for name in names:
        if name == "Phi_region":
            out[name] = [float(v) for v in np.asarray(phi["region"]).reshape(-1)]
        elif name == "Phi_density":
            out[name] = _f(phi["density"])
        elif name == "Phi_cont":
            out[name] = _f(phi["cont"])
        elif name == "Phi_gauge":
            out[name] = _f(phi["gauge"])
        elif name == "Phi_novelty":
            out[name] = _f(phi["novelty"])
        elif name == "phi":
            out[name] = {
                "region": [float(v) for v in np.asarray(phi["region"]).reshape(-1)],
                "density": _f(phi["density"]), "cont": _f(phi["cont"]),
                "gauge": _f(phi["gauge"]), "novelty": _f(phi["novelty"])}
        elif name == "O":
            out[name] = [[float(v) for v in row] for row in np.asarray(r.O)]
        elif name == "frame":
            out[name] = {"transpose": float(frame.transpose),
                         "phase": float(frame.phase)}
        else:
            raise ValueError(f"unknown observable {name!r}; known: Phi_region, "
                             "Phi_density, Phi_cont, Phi_gauge, Phi_novelty, "
                             "phi, O, frame")
    return out


class Runner:
    """Owns the loaded engine trees + a small committed-world cache + the single
    in-instance job lock. One job at a time; the caller fans out across instances."""

    def __init__(self, token: Optional[str]):
        self.token = token
        # The engine tree is loaded LAZILY on the first job (see _ensure_engine).
        # /health and every auth/validation refusal must answer WITHOUT importing
        # the engine — a compute box reports liveness and gates tokens even if the
        # engine tree were unavailable; the settle path is the only thing that
        # needs it. It also keeps the ownership assert on the settle path, where it
        # belongs. Loading is single-shot and, because at most one job runs per
        # instance (the busy lock), never races.
        self._Engine = self._resolve_sigma = None
        self._load_world = self._default_lane_vector = None
        # committed worlds are a small closed set (demo + in-image fixtures); cache
        # the load (~0.5s) + resolved σ_φ per path so a sweep of jobs on one world
        # doesn't reload it each time. Memory stays bounded — worlds are tiny frozen
        # objects (no bank materialized: the runner never renders audio).
        self._worlds: dict = {}
        self._busy = threading.Lock()

    def _ensure_engine(self):
        """Load + pin the arch-v6 engine on first job (idempotent)."""
        if self._Engine is None:
            (self._Engine, self._resolve_sigma, self._load_world,
             self._default_lane_vector) = _load_engine()

    # -- world resolution (committed corpora ONLY) --------------------------
    def _world(self, rel_path: str):
        self._ensure_engine()
        if rel_path in self._worlds:
            return self._worlds[rel_path]
        # resolve strictly INSIDE the repo/image root — no traversal to arbitrary
        # files. The image only contains committed worlds + fixtures anyway, but
        # this makes the "committed corpora only" posture structural, not incidental.
        candidate = (_REPO_ROOT / rel_path).resolve()
        if not str(candidate).startswith(str(_REPO_ROOT)):
            raise ValueError(f"world path escapes the repo root: {rel_path!r}")
        if not candidate.is_file():
            raise ValueError(f"no such committed world: {rel_path!r}")
        wf = self._load_world(str(candidate))
        sigma = self._resolve_sigma(wf)
        self._worlds[rel_path] = (wf, sigma)
        return self._worlds[rel_path]

    def _engine(self, rel_path: str, seed: int):
        wf, sigma = self._world(rel_path)
        return self._Engine(wf, profile="desktop", seed=int(seed), sigma=sigma), wf

    # -- u-point -> LaneVector ---------------------------------------------
    def _lane_vector(self, M: int, upoint: Optional[dict]):
        u = self._default_lane_vector(M)
        if not upoint:
            return u
        for k, v in upoint.items():
            if k not in _LANE_KEYS:
                raise ValueError(f"unknown lane {k!r}; lanes: {sorted(_LANE_KEYS)}")
            if k == "region":
                if np.ndim(v) == 0:
                    u.u_region = np.full(M, float(v), dtype=np.float32)
                else:
                    vec = np.zeros(M, dtype=np.float32)
                    src = np.asarray(v, dtype=np.float32).reshape(-1)
                    vec[:min(M, src.size)] = src[:M]
                    u.u_region = vec
            elif k == "density":
                u.u_density = float(v)
            elif k == "continuity":
                u.u_continuity = float(v)
            elif k == "gauge":
                u.u_gauge = float(v)
            elif k == "novelty":
                u.u_novelty = float(v)
            elif k == "temperature":
                u.T_s = float(v)
        return u

    # -- jobs ---------------------------------------------------------------
    def settle_ensemble(self, job: dict) -> dict:
        """Run the T_s>0 sampling ensemble on a committed world (mirrors
        run_sigma_phi's per-bar arrangement ensemble, streaming form). For each
        u-point, one writer seeded `seed0` produces `n` consecutive bars — the
        writer's genuine equilibrium output ensemble at that lean. A fixed seed0
        across u-points gives common random numbers, so d<Φ>/du finite differences
        are low-variance (a variance-reduction property, not a special case)."""
        world = job["world"]
        seed0 = int(job.get("seed0", 0))
        n = int(job.get("n", 1))
        if n < 1:
            raise ValueError("n must be >= 1")
        collect = list(job.get("collect")
                       or ["Phi_region", "Phi_cont", "Phi_novelty"])
        u_field = job.get("u", {})
        u_points = u_field if isinstance(u_field, list) else [u_field]
        if not u_points:
            u_points = [{}]
        if n * len(u_points) > _MAX_TOTAL_SETTLES:
            raise ValueError(
                f"n*|u_points| = {n * len(u_points)} exceeds the per-job settle "
                f"cap {_MAX_TOTAL_SETTLES}; split across more instances")

        results = []
        world_hash = None
        for upoint in u_points:
            eng, wf = self._engine(world, seed0)
            world_hash = wf.world_hash
            u = self._lane_vector(eng.world.M, upoint)
            settles = []
            for _ in range(n):
                tilt = eng._tilt_for(u)
                r = eng.writer.write_bar(tilt=tilt)
                settles.append(_collect(r, eng.writer.frame, collect))
            results.append({"u": upoint, "settles": settles})
        return {"kind": "settle_ensemble", "world": world, "world_hash": world_hash,
                "seed0": seed0, "n": n, "M": int(eng.world.M),
                "collect": collect, "results": results}

    def cycle(self, job: dict) -> dict:
        """Drive a lane-space cycle (a list of u-points) FORWARD then REVERSED and
        return the per-bar committed occupancy O + gauge-frame reads for each
        direction — the raw material for the holonomy P3 loop/slide computation,
        done CLIENT-side (the runner ships numbers, never a verdict). A fresh
        writer seeded `seed0` walks each direction, one settled bar per u-point."""
        world = job["world"]
        seed0 = int(job.get("seed0", 0))
        collect = list(job.get("collect") or ["O", "frame"])
        cyc = job.get("u") if job.get("u") is not None else job.get("cycle")
        if not isinstance(cyc, list) or not cyc:
            raise ValueError("cycle requires 'u' (or 'cycle') as a non-empty list "
                             "of u-points forming the cycle")

        def _walk(u_points):
            eng, wf = self._engine(world, seed0)
            bars = []
            for upoint in u_points:
                u = self._lane_vector(eng.world.M, upoint)
                tilt = eng._tilt_for(u)
                r = eng.writer.write_bar(tilt=tilt)
                bars.append(_collect(r, eng.writer.frame, collect))
            return bars, wf.world_hash, int(eng.world.M)

        forward, world_hash, M = _walk(cyc)
        reversed_bars, _, _ = _walk(list(reversed(cyc)))
        return {"kind": "cycle", "world": world, "world_hash": world_hash,
                "seed0": seed0, "M": M, "collect": collect,
                "forward": forward, "reversed": reversed_bars}

    def run(self, job: dict) -> dict:
        kind = job.get("kind")
        if kind == "settle_ensemble":
            return self.settle_ensemble(job)
        if kind == "cycle":
            return self.cycle(job)
        raise ValueError(f"unknown job kind {kind!r}; known: settle_ensemble, cycle")


class _Handler(BaseHTTPRequestHandler):
    runner: Runner = None  # bound on the server-specific subclass below

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        """Token gate: the deploy sets RUNNER_TOKEN; every /job must present it in
        X-Runner-Token. An UNSET token fails CLOSED (the runner refuses all jobs
        rather than serve open compute) — never a silent bypass."""
        expected = self.runner.token
        if not expected:
            return False
        return self.headers.get("X-Runner-Token", "") == expected

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        if path in ("", "/health"):
            self._json(200, {"ok": True, "service": "ets-physrunner",
                             "busy": self.runner._busy.locked(),
                             "worlds_cached": len(self.runner._worlds),
                             "token_configured": bool(self.runner.token)})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        if path != "/job":
            self._json(404, {"ok": False, "error": "not found"})
            return
        if not self._authorized():
            self._json(403, {"ok": False, "error": "missing or invalid "
                             "X-Runner-Token"})
            return
        # one job at a time per instance: refuse (409) rather than queue, so memory
        # stays bounded to a single ensemble and the caller retries on another box.
        if not self.runner._busy.acquire(blocking=False):
            self._json(409, {"ok": False, "error": "runner busy — one job per "
                             "instance; retry on another instance"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            try:
                job = json.loads(raw.decode()) if raw else {}
            except Exception as exc:
                self._json(400, {"ok": False, "error": f"bad JSON: {exc}"})
                return
            try:
                out = self.runner.run(job)
            except ValueError as exc:            # bad request shape / unknown kind
                self._json(400, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:             # settlement/engine failure — honest 500
                log.exception("job failed")
                self._json(500, {"ok": False,
                                 "error": f"{type(exc).__name__}: {exc}"})
                return
            self._json(200, {"ok": True, **out})
        finally:
            self.runner._busy.release()

    def log_message(self, *_a):  # quiet
        pass


def serve(token: Optional[str] = None, host: str = "0.0.0.0", port: int = 8790
          ) -> ThreadingHTTPServer:
    """Build a serving runner. `token` defaults to env RUNNER_TOKEN. ThreadingHTTP
    lets /health answer while a job runs; the busy lock still enforces one job at a
    time (409 otherwise). The caller starts/stops the returned server."""
    if token is None:
        token = os.environ.get("RUNNER_TOKEN") or None
    runner = Runner(token=token)
    handler = type("_BoundHandler", (_Handler,), {"runner": runner})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.runner = runner
    return httpd


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO)
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8790"))
    token = os.environ.get("RUNNER_TOKEN") or None
    if not token:
        # loud, honest: without a token the runner refuses every job. Surface it at
        # boot so a mis-deploy is obvious rather than mysteriously 403-ing.
        print("[physrunner] WARNING: RUNNER_TOKEN is unset — every /job will be "
              "refused (403). Set RUNNER_TOKEN at deploy.")
    httpd = serve(token=token, host=host, port=port)
    print(f"[physrunner] listening on http://{host}:{port}  "
          f"(token {'set' if token else 'UNSET'})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
