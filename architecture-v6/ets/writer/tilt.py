"""Layer-0 exact tilt map (ets-connector-v0, Layer 0) — THE single control entry
into the writer (spec §1, §8; invariant I-1).

    p(a) ∝ exp( −F(a)/T_s + Σ_i λ_i · φ_i(a) ),      λ_i = u_i / σ_{φ_i}

The panel's lane vector u (five direction leans + temperature T_s) reaches the
settlement ONLY through `layer0(u, sigma)` below, which produces the one
control-typed object the writer accepts: `TiltTerms`. There is no other
constructor path from control values to the settlement (C-3); the writer's
settle/stream entry points take a `TiltTerms` and nothing lane-shaped (I-1).

SCALING — the only would-be constant, derived (connector Layer 0): λ_i =
u_i / σ_{φ_i}, where σ_{φ_i} is the equilibrium fluctuation of φ_i under the
UNTILTED writer, measured by the registered calibration instrument at
world-freeze (artifact: ets/calibration/sigma_phi.json, loaded via
ets.calibration — a separate registered instrument; re-run on any anchor
spawn/prune). Knobs therefore read in natural units: standard fluctuations of
lean. NO hand-set λ scale exists here; this module contains no numeric scale at
all beyond the exact mathematics of the map.

DEGENERATE STATISTICS (exact, not a fallback). If the calibration measured
σ_{φ_i} = 0, then φ_i was constant along the untilted equilibrium trajectory.
For a statistic that is constant over the candidate set, the exponential tilt
exp(λ·φ) = exp(λ·c) is an arrangement-independent factor that normalizes away:
the tilted measure is IDENTICAL for every finite λ. The map therefore assigns
the identity tilt (λ_i = 0 — one representative of the equivalence class in
which all λ act identically) and RECORDS the lane as degenerate so the engine
reports it loudly. This is a theorem about degenerate exponential families, not
an error-hiding branch; the v0 wall it currently surfaces is φ_gauge: the v0
writer's gauge frame is frozen at the identity (no live gauge block exists in
the tape settlement), so the GAUGE STIFFNESS lane is degenerate on any v0
world. Reported, not patched (see the session report / REGISTRY).

Temperature T_s is typed separately (connector): it scales settlement
sharpness, carries no φ, and enters only at the settlement step (the mode of
exp(−F/T_s + Σλφ) is argmin F − T_s·Σλφ; the looseness of the sample around
that mode scales with T_s).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple

import numpy as np

from .phi import PHI_IDS


@dataclass(frozen=True)
class SigmaPhi:
    """The registered σ_φ calibration numbers for ONE frozen world.

    region is per-anchor (the REGION lane is a vector over anchors); the other
    four are scalars. `identifiable[lane]` = False marks a lane whose scale the
    registered instrument could NOT identify on this world (e.g. σ_density
    under a MAP-settling untilted writer, where the observable has zero
    untilted fluctuation): such a lane is DISARMED — λ is UNDEFINED, not zero
    and not huge — and the map applies no tilt while the panel still transmits
    u (honest state, surfaced by engine log + /ets/welcome). This is distinct
    from an identifiable σ=0 (a statistic PROVEN constant over the candidate
    set, e.g. φ_gauge on a frozen-frame world), whose identity tilt is exact.
    `meta` carries calibration provenance and is never read by the map."""
    region: np.ndarray            # (M,) fluctuation of φ_region per anchor
    density: float
    cont: float
    gauge: float
    novelty: float
    identifiable: Mapping = field(default_factory=dict)   # lane -> bool (default True)
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "region",
                           np.asarray(self.region, float).reshape(-1))
        vals = np.concatenate([self.region,
                               [self.density, self.cont, self.gauge, self.novelty]])
        if not np.all(np.isfinite(vals)) or np.any(vals < 0.0):
            raise ValueError(
                "sigma_phi must be finite and >= 0 (a negative or NaN "
                "fluctuation is a broken calibration, not a scale)")

    def is_identifiable(self, lane: str) -> bool:
        return bool(self.identifiable.get(lane, True))

    @classmethod
    def from_mapping(cls, m: Mapping) -> "SigmaPhi":
        """Build from a mapping artifact (embedded world sigma / --sigma-phi
        JSON): keys = the five φ ids; region is a per-anchor list; optional
        'identifiable' dict of lane -> bool."""
        missing = [k for k in PHI_IDS if k not in m]
        if missing:
            raise ValueError(f"sigma_phi artifact missing observables: {missing}")
        return cls(region=np.asarray(m["region"], float),
                   density=float(m["density"]), cont=float(m["cont"]),
                   gauge=float(m["gauge"]), novelty=float(m["novelty"]),
                   identifiable=dict(m.get("identifiable", {})),
                   meta=dict(m.get("meta", {})))


# SECOND-MOMENT SHAPE (covariance-shape XY, PREREG-sampler-covariance-xy). The
# per-eigendirection anisotropy `a` (below) rescales the ALREADY-EXISTING Laplace
# draw's variance along each Hessian eigendirection; it never touches F, the
# settled mode, or the λ tilt. It is clamped to this safe band at the single
# control boundary (TiltTerms.__post_init__) so no path can drive an unclamped
# over-/under-dispersion into the writer. a=None ⇒ exactly the current draw.
A_SHAPE_LO: float = 0.25
A_SHAPE_HI: float = 4.0

# FIELD-BIAS GRAINS (PREREG-field-bias-REV3 + track_role prototype). The per-
# candidate soft fiber lean resolves ADDITIVELY over exactly the candidate
# attributes that VARY within a fiber choice set: the source track (roll-up), the
# unit (the ultimate "channel"), and the (track, slot-role) SUB-TRACK cell. A PURE
# role is deliberately NOT a fiber grain — within a choice set every candidate
# shares the settled role, so a pure-role addend is a softmax constant that cancels
# (the measured role wall); it steers through the O-block region lane instead. But
# (track, role) varies via track, so it DOES steer (PREREG-track-role-bias). Order
# is fixed for a stable carrier. Each grain's sub-map key is coerced by _grain_key.
FIELD_GRAINS: Tuple[str, ...] = ("track", "unit", "track_role")


def _grain_key(grain: str, k):
    """Canonical sub-map key per field grain: track/unit key on an int id; the
    track_role SUB-TRACK grain keys on a (track_id, role_k) int pair."""
    if grain == "track_role":
        return (int(k[0]), int(k[1]))
    return int(k)


@dataclass(frozen=True)
class TiltTerms:
    """The h-transform tilt, in F's units — the ONE control object the writer
    consumes (I-1). Produced ONLY by `layer0` (or `untilted`); nothing else in
    the runtime constructs it from control values (C-3 static check)."""
    lam_region: np.ndarray        # (M,) λ per anchor
    lam_density: float
    lam_cont: float
    lam_gauge: float
    lam_novelty: float
    T_s: float
    degenerate: Tuple[str, ...] = ()   # lanes whose φ was σ=0-degenerate (exact identity)
    disarmed: Tuple[str, ...] = ()     # lanes the instrument could not identify
                                       # (λ undefined; NO tilt applied; honest state)
    a: Optional[np.ndarray] = None     # (M,) per-Hessian-eigendirection variance scale
                                       # for the Laplace draw (SECOND moment only; None
                                       # ⇒ ones ⇒ byte-identical current draw). Ordered
                                       # stiffest-first (a[0] scales the largest-curvature
                                       # direction); the writer aligns it to eigh order.
    channel_logbias: Optional[Mapping] = None
                                       # SOFT multi-grain FIELD-bias lean (PREREG-
                                       # field-bias-REV3, extends channel-bias-squares
                                       # REV2). The ONE datum {"track": {tid->β},
                                       # "unit": {uid->β}} folded into the FIBER choice
                                       # measure (fiber_choice_logits); the writer
                                       # resolves each candidate's addend ADDITIVELY,
                                       # β_track[tid] + β_unit[uid] (track = the roll-up,
                                       # unit = the operator's ultimate "channel"). A
                                       # bare {tid->β} map (the ratified REV2 track
                                       # projection) is lifted to {"track": ...} at the
                                       # single construction boundary below. NOT a φ
                                       # lane, no σ scale, NO effect on the settled O
                                       # mode — it up-weights candidate units in the
                                       # SOFT Gibbs draw, so the settlement perceives
                                       # the lean and accommodates it (nothing pinned;
                                       # the writer stays generative). None/empty at
                                       # EVERY grain ⇒ no addend ⇒ byte-identical draw.

    def __post_init__(self):
        object.__setattr__(self, "lam_region",
                           np.asarray(self.lam_region, float).reshape(-1))
        if not (np.isfinite(self.T_s) and self.T_s > 0.0):
            raise ValueError(f"temperature T_s must be finite and > 0, got {self.T_s}")
        vals = np.concatenate([self.lam_region,
                               [self.lam_density, self.lam_cont,
                                self.lam_gauge, self.lam_novelty]])
        if not np.all(np.isfinite(vals)):
            raise ValueError("tilt λ must be finite")
        if self.a is not None:
            a = np.asarray(self.a, float).reshape(-1)
            if a.shape[0] != self.lam_region.shape[0]:
                raise ValueError(
                    f"anisotropy `a` has length {a.shape[0]} but the tilt has "
                    f"{self.lam_region.shape[0]} eigendirections (one per anchor)")
            if not np.all(np.isfinite(a)):
                raise ValueError("anisotropy `a` must be finite")
            # CLAMP at the boundary (the coherence guard's safe band): no writer
            # path ever sees an `a` outside [A_SHAPE_LO, A_SHAPE_HI].
            object.__setattr__(self, "a", np.clip(a, A_SHAPE_LO, A_SHAPE_HI))
        if self.channel_logbias is not None:
            # Canonical carrier is the tagged multi-grain field bias
            # {grain -> {key: β}} over the grains that VARY within a fiber choice
            # set (FIELD_GRAINS = track, unit). A bare int-keyed map is the ratified
            # REV2 track projection (what channel_logbias() and the frozen track gate
            # emit) — lifted to {"track": ...} here at this single construction
            # boundary (one canonical form downstream; realize reads only the tagged
            # form). Zero-valued weights are dropped, so an all-zero field ⇒ None ⇒
            # byte-identical (the hard invariant).
            raw = dict(self.channel_logbias)
            if raw and all(isinstance(g, str) for g in raw):
                tagged = raw
            else:
                tagged = {"track": raw}
            norm: dict = {}
            for g in FIELD_GRAINS:
                m = tagged.get(g)
                if not m:
                    continue
                mm = {_grain_key(g, k): float(v) for k, v in dict(m).items()}
                if not all(np.isfinite(v) for v in mm.values()):
                    raise ValueError("channel_logbias weights must be finite")
                mm = {k: v for k, v in mm.items() if v != 0.0}
                if mm:
                    norm[g] = mm
            object.__setattr__(self, "channel_logbias", (norm or None))

    @property
    def is_untilted(self) -> bool:
        # `a` is deliberately EXCLUDED: it modulates only the draw's second
        # moment (spread), never the settled mode F descends to. A tilt carrying
        # only an anisotropy still settles to the untilted mode (settle.py reads
        # this property to skip the O-block tilt potential — correct, since `a`
        # adds no O-block potential).
        return (not np.any(self.lam_region) and self.lam_density == 0.0
                and self.lam_cont == 0.0 and self.lam_gauge == 0.0
                and self.lam_novelty == 0.0)


def untilted(n_anchors: int, T_s: float = 1.0,
             a: Optional[np.ndarray] = None,
             channel_logbias: Optional[Mapping] = None) -> TiltTerms:
    """The identity tilt at temperature T_s (u = 0). This is the untilted
    writer the σ_φ calibration instrument runs. `a` (default None) is the
    optional second-moment anisotropy; None keeps the draw byte-identical.
    `channel_logbias` (default None) is the optional SOFT per-channel fiber
    lean (PREREG-channel-bias-squares) — None/empty keeps the draw byte-
    identical; it never touches the settled O mode (fiber block only)."""
    return TiltTerms(lam_region=np.zeros(int(n_anchors)), lam_density=0.0,
                     lam_cont=0.0, lam_gauge=0.0, lam_novelty=0.0,
                     T_s=float(T_s), a=a, channel_logbias=channel_logbias)


class WorldNotCalibrated(RuntimeError):
    """Raised when a nonzero lean arrives for a world with no registered σ_φ
    calibration. Leaning without a derived scale would require inventing λ —
    forbidden (connector: 'No hand-set λ scales exist anywhere'). Halt and
    report; do not guess."""


def _lam(u: float, sigma: float, lane: str, identifiable: bool,
         degenerate: list, disarmed: list) -> float:
    if not identifiable:
        # the registered instrument could NOT identify this lane's scale on
        # this world/writer: λ is UNDEFINED (≠ 0-as-value, ≠ huge). The lane is
        # DISARMED: u still transmits, no tilt is applied, and the state is
        # surfaced (engine log + /ets/welcome). Never invent a scale.
        if u != 0.0:
            disarmed.append(lane)
        return 0.0
    if sigma == 0.0:
        if u != 0.0:
            degenerate.append(lane)
        return 0.0                    # exact identity tilt (see module docstring)
    return float(u) / float(sigma)


def layer0(u, sigma: Optional[SigmaPhi],
           a: Optional[np.ndarray] = None,
           channel_logbias: Optional[Mapping] = None) -> TiltTerms:
    """The Layer-0 map: lane vector u (+ T_s) → TiltTerms via λ_i = u_i/σ_φi.

    `u` is an ets.panel.lanes.LaneVector-typed object (duck-typed here so the
    writer package does not import the panel package: the wire decodes to it,
    the engine hands it over). `sigma` is the registered calibration; None is
    accepted ONLY for an all-zero lean (the untilted writer needs no scale) —
    a nonzero lean on an uncalibrated world raises WorldNotCalibrated.

    `a` (default None) is the optional per-eigendirection second-moment
    anisotropy (PREREG-sampler-covariance-xy). It is NOT a φ lane and carries no
    σ scale — it rescales the draw's spread, not the settled mode — so it is
    copied verbatim onto the ONE TiltTerms the writer consumes (clamped there),
    keeping this the single tilt-construction point (C-3) with no new lane and no
    second channel. None ⇒ ones ⇒ byte-identical draw."""
    r = np.asarray(u.u_region, float).reshape(-1)
    leans_zero = (not np.any(r) and float(u.u_density) == 0.0
                  and float(u.u_continuity) == 0.0 and float(u.u_gauge) == 0.0
                  and float(u.u_novelty) == 0.0)
    if sigma is None:
        if not leans_zero:
            raise WorldNotCalibrated(
                "nonzero lane lean received but this world carries no σ_φ "
                "calibration (ets/calibration/sigma_phi.json). Run the "
                "calibration instrument at world-freeze; λ will not be invented.")
        return untilted(r.shape[0], T_s=float(u.T_s), a=a,
                        channel_logbias=channel_logbias)

    sr = np.asarray(sigma.region, float).reshape(-1)
    if sr.shape[0] != r.shape[0]:
        raise ValueError(
            f"region lean has {r.shape[0]} anchors but calibration has "
            f"{sr.shape[0]} — σ_φ must be re-run on anchor spawn/prune")
    degenerate: list = []
    disarmed: list = []
    reg_ok = sigma.is_identifiable("region")
    lam_region = np.zeros_like(r)
    for k in range(r.shape[0]):
        lam_region[k] = _lam(float(r[k]), float(sr[k]), f"region[{k}]", reg_ok,
                             degenerate, disarmed)
    terms = TiltTerms(
        lam_region=lam_region,
        lam_density=_lam(float(u.u_density), sigma.density, "density",
                         sigma.is_identifiable("density"), degenerate, disarmed),
        lam_cont=_lam(float(u.u_continuity), sigma.cont, "cont",
                      sigma.is_identifiable("cont"), degenerate, disarmed),
        lam_gauge=_lam(float(u.u_gauge), sigma.gauge, "gauge",
                       sigma.is_identifiable("gauge"), degenerate, disarmed),
        lam_novelty=_lam(float(u.u_novelty), sigma.novelty, "novelty",
                         sigma.is_identifiable("novelty"), degenerate, disarmed),
        T_s=float(u.T_s),
        degenerate=tuple(degenerate),
        disarmed=tuple(disarmed),
        a=a,
        channel_logbias=channel_logbias,
    )
    return terms


# ---------------------------------------------------------------------------
# How the tilt enters the two free blocks of the tape settlement. These are the
# EXACT consequences of the Layer-0 measure — mechanism, zero learned content.
# ---------------------------------------------------------------------------

def o_block_potential(O: np.ndarray, tilt: TiltTerms) -> float:
    """The tilt's O-block potential added to the settled objective.

    Mode of p ∝ exp(−F/T_s + Σλφ)  ⇔  argmin_O [ F(O) − T_s·Σ_i λ_i φ_i(O) ].
    Of the five φ, exactly two factor through the O-block (φ_region = row sums,
    φ_density = total mass — both linear in O); φ_cont/φ_novelty live on the
    fiber block and φ_gauge on the (v0-frozen) gauge block."""
    O = np.asarray(O, float)
    return float(-tilt.T_s * (tilt.lam_region @ O.sum(axis=1)
                              + tilt.lam_density * O.sum()))


def o_block_gradient(tilt: TiltTerms, M: int, n_slots: int) -> np.ndarray:
    """d(o_block_potential)/dO — constant, because both O-block φ are linear."""
    g = np.full((int(M), int(n_slots)), -tilt.T_s * tilt.lam_density)
    g += (-tilt.T_s * tilt.lam_region)[:, None]
    return g


def fiber_choice_logits(energies: np.ndarray, is_continuation: np.ndarray,
                        reuse: np.ndarray, tilt: TiltTerms,
                        channel_bias: Optional[np.ndarray] = None) -> np.ndarray:
    """Per-choice log-weights of the Layer-0 measure over a fiber choice set.

    `energies` are the F-side energies of each candidate placement (computed by
    the writer from f.py's own T1p/T4 term math — see realize.FiberThreader);
    `is_continuation` marks the choices that continue a source run (Δφ_cont=1);
    `reuse` is each candidate's recency weight (Δφ_novelty contribution);
    `channel_bias` (optional, per-choice) is the SOFT field lean β(c) — the
    candidate's ADDITIVE log-weight resolved from `tilt.channel_logbias` across the
    field grains, β(c) = β_track[c.track_id] + β_unit[c.unit_id] (PREREG-field-bias-
    REV3; track = roll-up, unit = the ultimate "channel", summed). None ⇒ zero addend.

        log w(c) = −E_F(c)/T_s + λ_cont·1[cont](c) + λ_novelty·reuse(c) + β(c)

    The field lean is inside the SAME measure — it does not pin any choice; a unit
    (or track) with no candidate in this (role,band) set gets no term, so the pull is
    contingent on the settled O and the grain's coverage (soft, generative).
    φ_region/φ_density are fixed by the already-settled O at this point and
    contribute an equal constant to every choice (dropped); φ_gauge does not
    read the fiber."""
    e = np.asarray(energies, float)
    logits = (-e / tilt.T_s
              + tilt.lam_cont * np.asarray(is_continuation, float)
              + tilt.lam_novelty * np.asarray(reuse, float))
    if channel_bias is not None:
        logits = logits + np.asarray(channel_bias, float)
    return logits
