"""The frozen-world artifact the engine loads (`--world <file>`).

A world file is a pickle of a header + payload:

  payload["world"]   : ets.writer.World (frozen anchors, prototypes, tracks,
                       realization index) — the world-freeze object.
  payload["sources"] : how to materialize the REAL source-unit audio the
                       schedule references (I-12: every sample is a real unit):
                         {"kind": "corpus",   "paths": {track_id: mp3_path}}
                         {"kind": "embedded", "bank":  SourceUnitBank}
                       "corpus" re-derives unit audio deterministically from
                       the source files (ets.render.load_source_units — the
                       G0-style reconstruction, no choices); "embedded" carries
                       the bank inline (synthetic/test worlds).
  payload["sigma_phi"] : optional mapping for ets.writer.tilt.SigmaPhi (the σ_φ
                       calibration MAY be embedded at world-freeze; the
                       registered corpus artifact lives in ets/calibration/ and
                       is loaded by the ets.calibration loader — see
                       engine.resolve_sigma for the documented precedence).

WORLD HASH (the H-8 determinism key): sha256 over the pickled payload bytes.
Same file content ⇔ same hash; the offline render receipt records it together
with the live f.LAMBDA, the knob trajectory, and the seed — the full H-8 tuple.

Pickle is the v0 container (internal artifact, native desktop, no wire
exposure); the loader refuses files without the ETS header.
"""
from __future__ import annotations
import hashlib
import io
import pickle
from dataclasses import dataclass
from typing import Optional

MAGIC = "ets-world-v1"


@dataclass
class WorldFile:
    world: object                    # ets.writer.World
    sources: dict                    # see module docstring
    sigma_phi: Optional[dict]        # raw mapping (SigmaPhi.from_mapping input)
    world_hash: str                  # sha256 hex of the payload bytes
    path: Optional[str] = None


def _payload_bytes(world, sources, sigma_phi) -> bytes:
    buf = io.BytesIO()
    pickle.dump({"world": world, "sources": sources, "sigma_phi": sigma_phi},
                buf, protocol=4)
    return buf.getvalue()


def save_world(path: str, world, sources: dict,
               sigma_phi: Optional[dict] = None) -> str:
    """Write the world artifact; returns its content hash."""
    if not isinstance(sources, dict) or sources.get("kind") not in (
            "corpus", "embedded"):
        raise ValueError("sources must be {'kind': 'corpus'|'embedded', ...}")
    payload = _payload_bytes(world, sources, sigma_phi)
    digest = hashlib.sha256(payload).hexdigest()
    with open(path, "wb") as fh:
        pickle.dump({"magic": MAGIC, "sha256": digest}, fh, protocol=4)
        fh.write(payload)
    return digest


def load_world(path: str) -> WorldFile:
    with open(path, "rb") as fh:
        header = pickle.load(fh)
        if not (isinstance(header, dict) and header.get("magic") == MAGIC):
            raise ValueError(f"{path}: not an ETS world file")
        payload = fh.read()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != header.get("sha256"):
        raise ValueError(f"{path}: payload hash mismatch (corrupt world file)")
    data = pickle.loads(payload)
    return WorldFile(world=data["world"], sources=data["sources"],
                     sigma_phi=data.get("sigma_phi"), world_hash=digest,
                     path=path)
