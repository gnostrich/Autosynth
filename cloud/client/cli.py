"""`ets-cloud train <corpus>` — the thin local client.

Flow (each step's locality is explicit):
  1. INGEST locally: corpus -> prototypes (cost + mass + the two histograms).
     Raw audio and stage-2 recipes stay on the device.
  2. WHITELIST-ENCODE only stage-3 (``cloud.common.encode_job``) — structurally
     incapable of putting raw audio / recipes on the wire.
  3. POST to the service (or the in-process stand-in).
  4. VERIFY the returned receipt locally against the SAME stage-3 input; abort on
     any mismatch (a tampered world is refused).
  5. WRITE the world file locally. Playback stays in the existing local app.
"""
from __future__ import annotations

import argparse
import glob
import io
import os
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cloud.common import (
    encode_job, decode_result, verify_receipt, Result, STAGE3_PROTO_FIELDS,
)


# ---------------------------------------------------------------------------
# 1. local ingest -> prototypes
# ---------------------------------------------------------------------------

def load_prototypes(corpus: str, seed: int = 0):
    """Local ingest: turn a corpus into ``roles.Prototypes`` (stage-3 source).

    Accepts either
      * a directory of cached ETS track npz (``track_*.npz``) -> loaded and
        quantised with the existing ``roles.extract_prototypes`` (needs the local
        ingest deps: scikit-learn), or
      * a ``.npz`` prototype bundle (a small fixture; see ``save_prototypes``).

    Full raw-audio ingestion (mp3/wav -> tracks) uses ``ets.ingestion.pipeline``
    and its heavy deps (librosa, beat_this); it is the same local step the engine
    already ships and is intentionally not re-implemented here.
    """
    from ets.geometry import roles

    p = Path(corpus)
    if p.is_file() and p.suffix == ".npz":
        return _load_proto_bundle(p)

    if p.is_dir():
        track_paths = sorted(glob.glob(str(p / "track_*.npz")))
        if not track_paths:
            raise SystemExit(
                f"no cached track_*.npz under {p}. Raw-audio ingest "
                f"(mp3/wav -> tracks) is a local step via ets.ingestion.pipeline; "
                f"run it on the device first, or pass a .npz prototype bundle.")
        from ets.ingestion.pipeline import load
        tracks = [load(tp) for tp in track_paths]
        return [roles.extract_prototypes(t, seed=seed) for t in tracks]

    raise SystemExit(f"corpus not found: {corpus}")


def save_prototypes(path: str, protos) -> None:
    """Write a stage-3 prototype bundle (fixture / offline handoff). Stores ONLY
    the four whitelisted fields — the same fields that cross the wire."""
    payload: Dict[str, np.ndarray] = {"n_protos": np.int64(len(protos))}
    for i, P in enumerate(protos):
        for name in STAGE3_PROTO_FIELDS:
            payload[f"p{i}.{name}"] = np.asarray(getattr(P, name), float)
    np.savez(path, **payload)


def _load_proto_bundle(path: Path):
    from ets.geometry import roles
    with np.load(path) as z:
        n = int(z["n_protos"])
        out = []
        for i in range(n):
            cost = np.asarray(z[f"p{i}.cost"], float)
            mass = np.asarray(z[f"p{i}.mass"], float)
            slot_hist = np.asarray(z[f"p{i}.slot_hist"], float)
            band_profile = np.asarray(z[f"p{i}.band_profile"], float)
            K = mass.shape[0]
            out.append(roles.Prototypes(
                track_id=i, cost=cost, mass=mass, slot_hist=slot_hist,
                band_profile=band_profile,
                timbre=np.zeros((K, 4)), chroma=np.zeros((K, 12))))
    return out


# ---------------------------------------------------------------------------
# 3. transport: POST the job (real HTTP or in-process stand-in)
# ---------------------------------------------------------------------------

def post_job(job_bytes: bytes, service: str) -> bytes:
    """Send the stage-3 job to the service and return the raw result bytes.

    ``service == "inproc"`` runs the same service code in-process (offline / parity
    tests); otherwise it is an HTTP base URL and the job is POSTed to ``/train``."""
    if service == "inproc":
        from cloud.service import run_job_inprocess
        return run_job_inprocess(job_bytes)
    url = service.rstrip("/") + "/train"
    headers = {"Content-Type": "application/octet-stream"}
    # Single-user bearer secret: attach it if the local env carries one. The
    # service enforces only when it too has ETS_TRAIN_TOKEN set, so an unset
    # env leaves both sides open (local dev) and a set env gates production.
    token = os.environ.get("ETS_TRAIN_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=job_bytes, headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        return resp.read()


# ---------------------------------------------------------------------------
# 5. write the returned world locally
# ---------------------------------------------------------------------------

def write_world(out: str, result: Result) -> None:
    """Persist the cloud-computed anchor geometry + receipt locally.

    This is the offloaded artifact (the world's gauge-invariant intrinsic
    structure). Attaching the realization index (``ets.writer.build_index``, which
    needs the local tracks) and saving the playable ``.etsworld`` is the existing
    local step — it consumes this file and stays entirely on the device."""
    s = result.fstate
    payload: Dict[str, np.ndarray] = {
        "world.D": s.D, "world.a": s.a, "world.B": s.B, "world.theta": s.theta,
        "world.phase_off": np.asarray(s.phase_off, np.int64),
        "world.transpose": np.asarray(s.transpose, np.int64),
        "world.n_tracks": np.int64(len(s.pis)),
    }
    for i, pi in enumerate(s.pis):
        payload[f"world.pi{i}"] = np.asarray(pi, float)
    for k, v in result.receipt.items():
        payload[f"receipt.{k}"] = np.asarray(v)
    np.savez(out, **payload)


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def train(corpus, service: str = "inproc", out: Optional[str] = None,
          seed: int = 0, sweeps: int = 8, sigma: Optional[float] = None,
          verbose: bool = True) -> Result:
    """Run the full device-side flow. ``corpus`` may be a path or a ready list of
    prototypes (used by tests). Returns the verified ``Result``."""
    if isinstance(corpus, (str, os.PathLike)):
        protos = load_prototypes(str(corpus), seed=seed)
    else:
        protos = list(corpus)          # already-ingested prototypes

    params = {"seed": seed, "sweeps": sweeps, "sigma": sigma}
    job_bytes = encode_job(protos, params)      # whitelist-encode ONLY stage-3
    if verbose:
        print(f"[client] stage-3 job: {len(protos)} prototypes, "
              f"{len(job_bytes)} bytes -> {service}")

    result_bytes = post_job(job_bytes, service)
    result = decode_result(result_bytes)

    verify_receipt(protos, result)              # raises on a tampered world
    if verbose:
        r = result.receipt
        print(f"[client] receipt VERIFIED: M={int(r['n_anchors'])} anchors, "
              f"F_final={float(r['F_final']):.6g}, "
              f"F_monotone={bool(r['F_monotone'])}")

    if out:
        write_world(out, result)
        if verbose:
            print(f"[client] world written locally: {out}")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ets-cloud",
                                 description="ETS cloud training client")
    sub = ap.add_subparsers(dest="cmd", required=True)
    tr = sub.add_parser("train", help="ingest -> upload stage-3 -> verify -> write")
    tr.add_argument("corpus", help="dir of cached track_*.npz or a .npz prototype bundle")
    tr.add_argument("--service", default="inproc",
                    help="service base URL, or 'inproc' for the local stand-in")
    tr.add_argument("--out", default=None, help="output world npz path")
    tr.add_argument("--seed", type=int, default=0)
    tr.add_argument("--sweeps", type=int, default=8)
    tr.add_argument("--sigma", type=float, default=None)
    args = ap.parse_args(argv)

    if args.cmd == "train":
        train(args.corpus, service=args.service, out=args.out,
              seed=args.seed, sweeps=args.sweeps, sigma=args.sigma)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
