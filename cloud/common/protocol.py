"""The stage-3 wire protocol: the ONE definition of what crosses device->cloud.

CS-1..CS-5 are compiled in here structurally, not by convention:

* ``Stage3Proto`` is a frozen dataclass with EXACTLY the four gauge-invariant
  prototype fields the anchor-fit (``ets.functional.anchors.build_world``)
  consumes: ``cost``, ``mass``, ``slot_hist``, ``band_profile``. It has NO field
  for raw audio, provenance, unit coordinates, source spans, or the private
  timbre/chroma descriptors — so it is structurally incapable of carrying them.
  Attaching any such field raises at construction (``TypeError``: unexpected
  keyword).

* ``encode_job`` converts prototypes to ``Stage3Proto`` (reading ONLY the four
  attributes; a ``Track`` or a raw-audio array has no ``.cost`` and raises), packs
  a closed grammar of npz keys, and runs ``assert_wire_whitelisted`` on the exact
  bytes it is about to emit. Any key outside the closed grammar (e.g. ``audio``,
  ``src_start``, ``provenance``) makes the encoder refuse to serialize.

* ``verify_receipt`` re-derives the returned world's F-descent value and anchor
  count from the SAME stage-3 prototypes, using root ``ets``'s own ``f.F`` /
  ``anchors.effective_rank`` (no re-implementation) — a device-verifiable receipt
  that is cheap (one F evaluation + one eigendecomposition) versus the full
  block-coordinate solve it certifies.

Nothing here adds training logic or a learned object; it only marshals stage-3 and
verifies receipts.
"""
from __future__ import annotations

import io
import re
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

# Make root `ets` importable when this package is used from anywhere. The repo
# root is three parents up: cloud/common/protocol.py -> common -> cloud -> root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Root ETS training code, imported UNCHANGED. These are the ONLY entry points the
# cloud layer reuses; it neither wraps nor alters them.
from ets.geometry import roles          # Prototypes type + role distances
from ets.functional import anchors as an  # build_world (anchor-fit), effective_rank
from ets.functional import f as ff        # the single functional F (receipt check)


# ---------------------------------------------------------------------------
# THE STAGE-3 WHITELIST (closed sets — the seam)
# ---------------------------------------------------------------------------

# Exactly the prototype fields ``anchors.build_world`` reads (gauge-invariant,
# dimensionless). NOT timbre/chroma (private, content-adjacent), NOT track_id,
# and — by construction — nothing from stage 1 (raw audio) or stage 2 (recipes:
# provenance, source spans, unit coordinates).
STAGE3_PROTO_FIELDS = ("cost", "mass", "slot_hist", "band_profile")

# The only training params that may be declared. A closed set: an unknown param
# key is refused (no smuggling a payload through the params channel).
STAGE3_PARAM_FIELDS = ("seed", "sweeps", "sigma")
PARAM_DEFAULTS: Dict[str, object] = {"seed": 0, "sweeps": 8, "sigma": None}

# Self-describing marker embedded in every job, and the closed key grammar the
# encoder/decoder both enforce on the exact wire bytes.
WHITELIST_TAG = "ets-stage3:" + ",".join(STAGE3_PROTO_FIELDS)
_PROTO_KEY = re.compile(r"^p(\d+)\.(" + "|".join(STAGE3_PROTO_FIELDS) + r")$")
_PARAM_KEY = re.compile(r"^param\.(" + "|".join(STAGE3_PARAM_FIELDS) + r")$")
_META_KEYS = {"__ets_stage3__", "n_protos"}


class WhitelistViolation(Exception):
    """Raised when a payload attempts to put a non-stage-3 field on the wire."""


class ReceiptError(Exception):
    """Raised when a returned world's receipt does not verify against the job."""


# ---------------------------------------------------------------------------
# Stage-3 prototype: structurally can hold ONLY the four whitelisted fields
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Stage3Proto:
    """A prototype reduced to exactly the stage-3 fields. Frozen and closed: there
    is no slot for audio, provenance, or private descriptors, so none can ride
    along. Constructing with any other field raises ``TypeError``."""
    cost: np.ndarray          # (K,K) within-track gauge-quotiented cost, RMS~1
    mass: np.ndarray          # (K,)  prototype masses, sum 1
    slot_hist: np.ndarray     # (K,S) metrical-slot mass profile
    band_profile: np.ndarray  # (K,N) band mass profile

    @classmethod
    def from_prototype(cls, P) -> "Stage3Proto":
        """Read ONLY the four whitelisted attributes off a prototype-like object.

        A ``Track`` (no ``.cost``), a raw-audio ndarray, or a stage-2 recipe object
        lacks these attributes and raises ``AttributeError`` here — the encoder can
        never be handed one and silently succeed."""
        vals = {}
        for name in STAGE3_PROTO_FIELDS:
            v = getattr(P, name)   # AttributeError if not a real prototype
            vals[name] = np.ascontiguousarray(np.asarray(v, dtype=np.float64))
        s = cls(**vals)
        s.validate()
        return s

    def validate(self) -> None:
        K = self.mass.shape[0]
        S = self.slot_hist.shape[1]
        N = self.band_profile.shape[1]
        if self.cost.shape != (K, K):
            raise WhitelistViolation(f"cost must be ({K},{K}), got {self.cost.shape}")
        if self.mass.shape != (K,):
            raise WhitelistViolation(f"mass must be ({K},), got {self.mass.shape}")
        if self.slot_hist.shape != (K, S):
            raise WhitelistViolation("slot_hist first axis must equal K")
        if self.band_profile.shape != (K, N):
            raise WhitelistViolation("band_profile first axis must equal K")
        for name in STAGE3_PROTO_FIELDS:
            if not np.all(np.isfinite(getattr(self, name))):
                raise WhitelistViolation(f"{name} has non-finite entries")


# The dataclass has exactly the whitelisted fields — asserted at import so a future
# edit that adds an off-whitelist field to Stage3Proto is caught immediately.
assert tuple(f.name for f in fields(Stage3Proto)) == STAGE3_PROTO_FIELDS, (
    "Stage3Proto fields drifted from the stage-3 whitelist")


# ---------------------------------------------------------------------------
# The closed wire-key grammar — the structural gate against smuggling
# ---------------------------------------------------------------------------

def assert_wire_whitelisted(payload: Dict[str, np.ndarray]) -> None:
    """Every key in an outgoing/incoming JOB must match the closed grammar:

        __ets_stage3__ | n_protos | p{i}.{cost|mass|slot_hist|band_profile}
                                  | param.{seed|sweeps|sigma}

    Any other key (audio, raw, src_start, provenance, unit, recipe, ...) raises.
    This runs on the EXACT bytes the client is about to send and the service is
    about to accept, so it bites on both ends."""
    for key in payload:
        if key in _META_KEYS:
            continue
        if _PROTO_KEY.match(key) or _PARAM_KEY.match(key):
            continue
        raise WhitelistViolation(
            f"wire key {key!r} is not in the stage-3 whitelist "
            f"(raw audio / stage-2 recipe fields can never cross CS-1)")


# ---------------------------------------------------------------------------
# JOB encode / decode  (client -> service)
# ---------------------------------------------------------------------------

def encode_job(protos, params: Optional[Dict[str, object]] = None) -> bytes:
    """Serialize a stage-3 JOB. Reads ONLY the whitelisted prototype fields and
    the whitelisted params; refuses any unknown param key; and self-checks the
    exact bytes against the wire grammar before emitting them."""
    params = dict(params or {})
    unknown = set(params) - set(STAGE3_PARAM_FIELDS)
    if unknown:
        raise WhitelistViolation(
            f"param(s) {sorted(unknown)} not in stage-3 whitelist "
            f"{list(STAGE3_PARAM_FIELDS)}")

    s3 = [p if isinstance(p, Stage3Proto) else Stage3Proto.from_prototype(p)
          for p in protos]
    if not s3:
        raise WhitelistViolation("a job must contain at least one prototype")

    payload: Dict[str, np.ndarray] = {
        "__ets_stage3__": np.frombuffer(WHITELIST_TAG.encode("utf-8"), dtype=np.uint8),
        "n_protos": np.int64(len(s3)),
    }
    for i, p in enumerate(s3):
        for name in STAGE3_PROTO_FIELDS:
            payload[f"p{i}.{name}"] = getattr(p, name)
    for name in STAGE3_PARAM_FIELDS:
        v = params.get(name, PARAM_DEFAULTS[name])
        payload[f"param.{name}"] = np.float64(np.nan if v is None else float(v))

    assert_wire_whitelisted(payload)          # gate the EXACT bytes
    buf = io.BytesIO()
    np.savez(buf, **payload)
    return buf.getvalue()


def decode_job(job_bytes: bytes):
    """Inverse of ``encode_job`` (service side). Verifies the whitelist tag and the
    wire grammar, then reconstructs the real ``roles.Prototypes`` type with the two
    UNUSED private fields (timbre/chroma) filled with zeros — they never cross and
    ``anchors.build_world`` never reads them, so this is faithful, not a shim."""
    with np.load(io.BytesIO(job_bytes)) as z:
        payload = {k: z[k] for k in z.files}
    assert_wire_whitelisted(payload)

    tag = bytes(payload["__ets_stage3__"].tobytes()).decode("utf-8")
    if tag != WHITELIST_TAG:
        raise WhitelistViolation(f"job whitelist tag mismatch: {tag!r}")

    n = int(payload["n_protos"])
    protos = []
    for i in range(n):
        cost = np.asarray(payload[f"p{i}.cost"], float)
        mass = np.asarray(payload[f"p{i}.mass"], float)
        slot_hist = np.asarray(payload[f"p{i}.slot_hist"], float)
        band_profile = np.asarray(payload[f"p{i}.band_profile"], float)
        Stage3Proto(cost, mass, slot_hist, band_profile).validate()
        K = mass.shape[0]
        protos.append(roles.Prototypes(
            track_id=i, cost=cost, mass=mass,
            slot_hist=slot_hist, band_profile=band_profile,
            timbre=np.zeros((K, 4)), chroma=np.zeros((K, 12))))

    params = {}
    for name in STAGE3_PARAM_FIELDS:
        v = float(payload[f"param.{name}"])
        params[name] = None if np.isnan(v) else v
    return protos, params


# ---------------------------------------------------------------------------
# RESULT encode / decode  (service -> client)
# ---------------------------------------------------------------------------

@dataclass
class Result:
    """The returned world (gauge-invariant FState fields) + the device-verifiable
    receipt. ``fstate`` is the reconstructed ``ff.FState`` so the client can score
    it with root ETS's own F."""
    fstate: object
    receipt: Dict[str, float]


def encode_result(state, info: Dict[str, object]) -> bytes:
    payload: Dict[str, np.ndarray] = {
        "world.D": np.asarray(state.D, float),
        "world.a": np.asarray(state.a, float),
        "world.B": np.asarray(state.B, float),
        "world.theta": np.asarray(state.theta, float),
        "world.phase_off": np.asarray(state.phase_off, np.int64),
        "world.transpose": np.asarray(state.transpose, np.int64),
        "world.n_tracks": np.int64(len(state.pis)),
    }
    for i, pi in enumerate(state.pis):
        payload[f"world.pi{i}"] = np.asarray(pi, float)
    for k, v in info.items():
        payload[f"receipt.{k}"] = np.asarray(v)
    buf = io.BytesIO()
    np.savez(buf, **payload)
    return buf.getvalue()


def reconstruct_fstate(payload: Dict[str, np.ndarray]):
    """Rebuild the root-ETS ``FState`` from a decoded result payload."""
    n = int(payload["world.n_tracks"])
    pis = [np.asarray(payload[f"world.pi{i}"], float) for i in range(n)]
    return ff.FState(
        D=np.asarray(payload["world.D"], float),
        a=np.asarray(payload["world.a"], float),
        B=np.asarray(payload["world.B"], float),
        theta=np.asarray(payload["world.theta"], float),
        pis=pis,
        phase_off=np.asarray(payload["world.phase_off"], np.int64),
        transpose=np.asarray(payload["world.transpose"], np.int64))


def decode_result(result_bytes: bytes) -> Result:
    with np.load(io.BytesIO(result_bytes)) as z:
        payload = {k: z[k] for k in z.files}
    fstate = reconstruct_fstate(payload)
    receipt = {k[len("receipt."):]: payload[k].item()
               if payload[k].ndim == 0 else payload[k]
               for k in payload if k.startswith("receipt.")}
    return Result(fstate=fstate, receipt=receipt)


# ---------------------------------------------------------------------------
# DEVICE-VERIFIABLE RECEIPT CHECK
# ---------------------------------------------------------------------------

def verify_receipt(protos, result: Result, atol: float = 1e-6) -> bool:
    """Re-derive the returned world's certificate from the SAME stage-3 protos,
    using root ETS's own functional/anchors code. Raises ``ReceiptError`` on any
    mismatch; returns True on success.

    Checks (each bites on a tampered world or receipt):
      * anchor count == number of returned anchor masses, and <= round(effective
        rank of the traffic operator) (pruning only removes anchors);
      * the traffic effective rank matches the receipt (re-derived, cheap);
      * F(returned world, protos) equals the receipt's F_final (the block solve's
        settled value) — the tightest check: perturbing any of D/a/B/theta/pi
        moves F off the certified value.
    """
    r = result.receipt
    state = result.fstate

    for key in ("effective_rank", "n_anchors", "sigma", "F_final"):
        if key not in r:
            raise ReceiptError(f"receipt missing required field {key!r}")

    sigma = float(r["sigma"])
    A, _D_role, _sigma = an.traffic_affinity(protos, sigma=sigma)
    er = float(an.effective_rank(A))
    if abs(er - float(r["effective_rank"])) > max(atol, 1e-6 * abs(er)):
        raise ReceiptError(
            f"effective rank mismatch: recomputed {er} vs receipt "
            f"{float(r['effective_rank'])}")

    n_anchors = int(state.a.shape[0])
    if n_anchors != int(r["n_anchors"]):
        raise ReceiptError(
            f"anchor count mismatch: world has {n_anchors} vs receipt "
            f"{int(r['n_anchors'])}")
    if n_anchors > int(round(er)):
        raise ReceiptError(
            f"anchor count {n_anchors} exceeds round(effective_rank)={round(er)}")

    F_val, _terms = ff.F(state, protos)
    if abs(float(F_val) - float(r["F_final"])) > max(atol, 1e-6 * abs(float(F_val))):
        raise ReceiptError(
            f"F-descent value mismatch: recomputed {float(F_val)} vs certified "
            f"F_final {float(r['F_final'])} (world does not settle where claimed)")
    return True
