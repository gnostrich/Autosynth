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
    four are scalars. `meta` carries the calibration provenance (instrument id,
    n_bars, seed, world hash) and is never read by the map itself."""
    region: np.ndarray            # (M,) fluctuation of φ_region per anchor
    density: float
    cont: float
    gauge: float
    novelty: float
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

    @classmethod
    def from_mapping(cls, m: Mapping) -> "SigmaPhi":
        """Build from the calibration artifact's mapping (the ets.calibration
        loader's output): keys = the five φ ids; region is a per-anchor list."""
        missing = [k for k in PHI_IDS if k not in m]
        if missing:
            raise ValueError(f"sigma_phi artifact missing observables: {missing}")
        return cls(region=np.asarray(m["region"], float),
                   density=float(m["density"]), cont=float(m["cont"]),
                   gauge=float(m["gauge"]), novelty=float(m["novelty"]),
                   meta=dict(m.get("meta", {})))


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
    degenerate: Tuple[str, ...] = ()   # lanes whose φ was σ=0-degenerate

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

    @property
    def is_untilted(self) -> bool:
        return (not np.any(self.lam_region) and self.lam_density == 0.0
                and self.lam_cont == 0.0 and self.lam_gauge == 0.0
                and self.lam_novelty == 0.0)


def untilted(n_anchors: int, T_s: float = 1.0) -> TiltTerms:
    """The identity tilt at temperature T_s (u = 0). This is the untilted
    writer the σ_φ calibration instrument runs."""
    return TiltTerms(lam_region=np.zeros(int(n_anchors)), lam_density=0.0,
                     lam_cont=0.0, lam_gauge=0.0, lam_novelty=0.0,
                     T_s=float(T_s))


class WorldNotCalibrated(RuntimeError):
    """Raised when a nonzero lean arrives for a world with no registered σ_φ
    calibration. Leaning without a derived scale would require inventing λ —
    forbidden (connector: 'No hand-set λ scales exist anywhere'). Halt and
    report; do not guess."""


def _lam(u: float, sigma: float, lane: str, degenerate: list) -> float:
    if sigma == 0.0:
        if u != 0.0:
            degenerate.append(lane)
        return 0.0                    # exact identity tilt (see module docstring)
    return float(u) / float(sigma)


def layer0(u, sigma: Optional[SigmaPhi]) -> TiltTerms:
    """The Layer-0 map: lane vector u (+ T_s) → TiltTerms via λ_i = u_i/σ_φi.

    `u` is an ets.panel.lanes.LaneVector-typed object (duck-typed here so the
    writer package does not import the panel package: the wire decodes to it,
    the engine hands it over). `sigma` is the registered calibration; None is
    accepted ONLY for an all-zero lean (the untilted writer needs no scale) —
    a nonzero lean on an uncalibrated world raises WorldNotCalibrated."""
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
        return untilted(r.shape[0], T_s=float(u.T_s))

    sr = np.asarray(sigma.region, float).reshape(-1)
    if sr.shape[0] != r.shape[0]:
        raise ValueError(
            f"region lean has {r.shape[0]} anchors but calibration has "
            f"{sr.shape[0]} — σ_φ must be re-run on anchor spawn/prune")
    degenerate: list = []
    lam_region = np.zeros_like(r)
    for k in range(r.shape[0]):
        lam_region[k] = _lam(float(r[k]), float(sr[k]), f"region[{k}]", degenerate)
    terms = TiltTerms(
        lam_region=lam_region,
        lam_density=_lam(float(u.u_density), sigma.density, "density", degenerate),
        lam_cont=_lam(float(u.u_continuity), sigma.cont, "cont", degenerate),
        lam_gauge=_lam(float(u.u_gauge), sigma.gauge, "gauge", degenerate),
        lam_novelty=_lam(float(u.u_novelty), sigma.novelty, "novelty", degenerate),
        T_s=float(u.T_s),
        degenerate=tuple(degenerate),
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
                        reuse: np.ndarray, tilt: TiltTerms) -> np.ndarray:
    """Per-choice log-weights of the Layer-0 measure over a fiber choice set.

    `energies` are the F-side energies of each candidate placement (computed by
    the writer from f.py's own T1p/T4 term math — see realize.FiberThreader);
    `is_continuation` marks the choices that continue a source run (Δφ_cont=1);
    `reuse` is each candidate's recency weight (Δφ_novelty contribution).

        log w(c) = −E_F(c)/T_s + λ_cont·1[cont](c) + λ_novelty·reuse(c)

    φ_region/φ_density are fixed by the already-settled O at this point and
    contribute an equal constant to every choice (dropped); φ_gauge does not
    read the fiber."""
    e = np.asarray(energies, float)
    return (-e / tilt.T_s
            + tilt.lam_cont * np.asarray(is_continuation, float)
            + tilt.lam_novelty * np.asarray(reuse, float))
