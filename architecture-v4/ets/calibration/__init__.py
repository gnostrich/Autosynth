"""sigma_phi calibration artifact: loader + world hash [INSTRUMENT plumbing].

The connector's Layer-0 knob scaling is lambda_i = u_i / sigma_phi_i, with
sigma_phi_i the equilibrium fluctuation of phi_i under the UNTILTED writer,
measured by the registered calibration pass (REGISTRY: sigma-phi-untilted-*;
regenerate: ``python3 scripts/run_sigma_phi.py``). This package is the
artifact's single home and the engine's single way to consume it:

    from ets.calibration import load_sigma_phi, world_content_hash
    cal = load_sigma_phi()                      # ets/calibration/sigma_phi.json
    cal.sigma["region"]        # (M,) ndarray — per-anchor sigma (lane 1)
    cal.sigma["continuity"]    # float                        (lane 3)
    cal.identifiable["density"]  # False => NO calibrated scale exists at u=0
    cal.lane_phi               # {1:"region", ..., 6:None}
    cal.world_hash == world_content_hash(world.fstate)   # instrument validity

HONESTY LAW (no invented floors): an observable whose untilted fluctuation is
exactly 0.0 is recorded ``identifiable: false`` with its R3-style note. The
loader exposes that fact verbatim; it never substitutes a floor, a default
sigma, or an infinity. An engine asked to tilt a non-identifiable lane must
surface the wall, not divide by an invented number.

The instrument is bound to ONE frozen world: ``world_hash`` is the sha256 of
the frozen anchor content (D, a, B, theta) plus the live LAMBDA. Any anchor
spawn/prune or weight change alters the hash, invalidating the artifact —
the connector mandates re-running the calibration pass then (re-run on
resize). ``world_content_hash`` recomputes it from a live FState so the
engine can assert validity at load time.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional
import hashlib
import json
import os

import numpy as np

SIGMA_PHI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "sigma_phi.json")

_PHI_NAMES = ("region", "density", "continuity", "gauge", "novelty")


def world_content_hash(fstate, lam: Optional[dict] = None) -> str:
    """sha256 of the frozen world content the calibration instruments: anchor
    support/mass/gains/profile (D, a, B, theta) and the frozen F weights LAMBDA
    (read live from ets.functional.f unless given). Shapes are hashed with the
    bytes so a reshape cannot collide."""
    if lam is None:
        from ets.functional.f import LAMBDA as lam  # live frozen weights (I-9)
    h = hashlib.sha256()
    for name in ("D", "a", "B", "theta"):
        arr = np.ascontiguousarray(getattr(fstate, name), dtype=np.float64)
        h.update(name.encode())
        h.update(str(arr.shape).encode())
        h.update(arr.tobytes())
    h.update(json.dumps({k: float(v) for k, v in sorted(lam.items())},
                        sort_keys=True).encode())
    return h.hexdigest()


@dataclass(frozen=True)
class SigmaPhi:
    """The loaded calibration artifact (values + provenance metadata).

    sigma / mean : per-observable equilibrium statistics under the untilted
                   writer. "region" entries are (M,) ndarrays; the four scalar
                   observables are floats.
    identifiable : sigma > 0.0 exactly (per component for "region"). False
                   means: not identifiable at u=0, see notes — no floor exists.
    notes        : per-observable honesty notes (present for non-identifiable
                   entries; R3-style).
    lane_phi     : lane number -> phi name (lane 6 TEMPERATURE -> None).
    world_hash   : sha256 binding the instrument to its frozen world + LAMBDA.
    n_bars       : ensemble size (bars of the untilted settlement measured).
    meta         : the full artifact dict (estimator text, ensemble spec,
                   autocorrelations, regeneration command, registry id, ...).
    """
    sigma: Dict[str, object]
    mean: Dict[str, object]
    identifiable: Dict[str, object]
    notes: Dict[str, str]
    lane_phi: Dict[int, Optional[str]]
    world_hash: str
    n_bars: int
    meta: dict

    @property
    def M(self) -> int:
        return int(np.asarray(self.sigma["region"]).shape[0])


def load_sigma_phi(path: Optional[str] = None) -> SigmaPhi:
    """Load and validate the calibration artifact. Raises (never defaults) on a
    missing file, a missing observable, or an identifiability flag inconsistent
    with its recorded sigma — a broken instrument is a wall, not a fallback."""
    p = path or SIGMA_PHI_PATH
    with open(p, "r", encoding="utf-8") as fh:
        doc = json.load(fh)

    phi = doc["phi"]
    missing = [n for n in _PHI_NAMES if n not in phi]
    if missing:
        raise ValueError(f"sigma_phi artifact lacks observables: {missing}")

    sigma: Dict[str, object] = {}
    mean: Dict[str, object] = {}
    identifiable: Dict[str, object] = {}
    notes: Dict[str, str] = {}
    for name in _PHI_NAMES:
        e = phi[name]
        s = np.asarray(e["sigma"], dtype=float)
        m = np.asarray(e["mean"], dtype=float)
        ident = np.asarray(e["identifiable"], dtype=bool)
        if not np.all(s >= 0.0):
            raise ValueError(f"phi_{name}: negative sigma in artifact")
        if not np.array_equal(ident, s > 0.0):
            raise ValueError(
                f"phi_{name}: identifiable flag inconsistent with sigma "
                f"(flags must be exactly sigma > 0; no floors, no overrides)")
        if name == "region":
            if s.ndim != 1 or s.shape != m.shape:
                raise ValueError("phi_region sigma/mean must be (M,) vectors")
            sigma[name], mean[name], identifiable[name] = s, m, ident
        else:
            if s.ndim != 0:
                raise ValueError(f"phi_{name} sigma must be a scalar")
            sigma[name] = float(s)
            mean[name] = float(m)
            identifiable[name] = bool(ident)
        if not bool(np.all(ident)):
            note = e.get("note", "")
            if not (isinstance(note, str) and note.strip()):
                raise ValueError(
                    f"phi_{name}: non-identifiable entry lacks its honesty note")
            notes[name] = note

    lane_phi = {int(k): v for k, v in doc["lanes"].items()}
    if sorted(lane_phi) != [1, 2, 3, 4, 5, 6] or lane_phi[6] is not None:
        raise ValueError("artifact lane map must cover lanes 1..6 with "
                         "TEMPERATURE (6) mapped to no phi")

    wh = doc["world"]["hash"]
    if not (isinstance(wh, str) and len(wh) == 64):
        raise ValueError("artifact world hash malformed")

    return SigmaPhi(sigma=sigma, mean=mean, identifiable=identifiable,
                    notes=notes, lane_phi=lane_phi, world_hash=wh,
                    n_bars=int(doc["ensemble"]["n_bars"]), meta=doc)
