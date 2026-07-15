"""slide[g] — gauge-frame SLIDE meter (directive-v1 feature 2, STAGE 0 shadow).

THE SPLIT. The existing DRIFT CV jack (``drift_cv``) reports one conflated
number per gauge component: the accumulated signed winding of the running
frame. That winding mixes two physically distinct quantities:

  (1) the frame SLIDING along its gauge orbit (a displacement-from-home of the
      section gauge itself — key modulation, groove shift), and
  (2) genuine HOLONOMY of the coupling traffic (curvature: loops that fail to
      close). That half lives in ``gauge_loop`` (loop[g]).

This module is half (1): a READ-ONLY functional of the settled per-section
gauge fields the machine already produces — at corpus time the per-track
sections ``FState.transpose`` / ``FState.phase_off``; at the writer the
realized Schedule's per-section ``Gauge`` (transpose_semitones, phase_shift),
sampled per bar. The caller passes those already-produced values as plain
arrays (same contract as ``drift_cv``); this module imports ONLY numpy and its
sibling ``holonomy`` primitives — never ``ets.functional`` (I-5, I-14; the
I-14 manifest check enforces this structurally).

PER BAR: compose the frame's increments (the discrete connection 1-form,
gauge-invariant by construction: a global re-referencing v -> v + c cancels in
every difference) into the running displacement-from-home, and report that
displacement per gauge component IN F'S OWN QUOTIENT:

  * TRANSPOSITION on Z_12: the displacement is a group element of Z_12,
    reported as its minimal signed representative in [-6, 6). Absolute key is
    gauge; only the composed relative displacement is meaningful.

  * METRICAL PHASE via the SAME estimator as F's T1 phase-displacement charge:

        charge[t] = 1 - | sum_{tau<=t} m_tau e^{i 2 pi x_tau} | / sum m_tau

    where x_tau is bar tau's displacement-from-home as a fraction of the
    metrical circle and m_tau its settled mass. This is the closed-form gauge
    quotient: one GLOBAL phase re-referencing delta is free (it multiplies
    every e^{i 2 pi x} by the same unit phasor and drops out of |.|); per-bar
    differing displacement is charged. charge = 0 exactly when every bar sits
    at one common displacement (the frame never slid, up to a re-choice of
    home); incoherent per-bar slide drives it toward 1. The formula is
    RE-STATED here in numpy rather than imported from ets.functional.f —
    meters have ZERO dependency on the F side (I-14 dependency law); f.py's
    ``phase_displacement_charge`` is the single AUTHORITY for the formula in F
    and this restatement is checked against the same algebra by the meter
    tests (H-4 gauge-scramble invariance).

No constants exist here beyond gauge-group cardinalities: Z_12 (spec §3
pitch-class circle) and the metrical circle's S slots (passed in by the
caller from the world's grid — never hardcoded).

Read-only instrumentation (spec §9): takes no F-weights, feeds nothing back
into any objective/gradient/settlement decision. Sanctioned consumers: the
planner and CV-lane feedback patching, plus the STAGE-0 shadow trace sidecar.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple
import numpy as np

from .holonomy import signed_increment

# Gauge-group cardinality (spec §3): transposition acts on the pitch-class
# circle Z_12. The metrical circle's cardinality S is a property of the world's
# grid and is passed in by the caller (never hardcoded here).
KEY_CARDINALITY = 12.0


def displacement_from_home(values: Sequence[float], modulus: float) -> np.ndarray:
    """Per-bar displacement-from-home of a gauge frame: the COMPOSED increments.

    ``values`` is the per-bar gauge-section value on a circle of circumference
    ``modulus``. The increments are the frame's consecutive differences mapped
    to their minimal signed representatives (the discrete connection 1-form);
    their cumulative sum is the displacement on the covering space, with
    displacement[0] = 0 (bar 0 IS home). Built from differences only, so a
    global re-referencing v -> v + c leaves it unchanged to machine precision.
    """
    v = np.asarray(values, float)
    if v.ndim != 1:
        raise ValueError("frame trajectory must be 1-D (one value per bar)")
    if len(v) == 0:
        return np.zeros(0)
    incr = signed_increment(np.diff(v), modulus)
    return np.concatenate([[0.0], np.cumsum(incr)])


@dataclass(frozen=True)
class SlideReadout:
    """One slide jack's output over a bar trajectory."""
    component: str
    per_bar: np.ndarray        # (T,) the jack's per-bar CV (see slide_key/slide_phase)
    modulus: float


def slide_key(transpose: Sequence[float]) -> SlideReadout:
    """Key-slide jack: per-bar displacement-from-home of the transposition
    section, as the Z_12 group element (minimal signed representative in
    [-6, 6)). The quotient by Z_12 is the gauge law itself: which absolute key
    is "home" is gauge; the composed relative displacement is intrinsic."""
    disp = displacement_from_home(transpose, KEY_CARDINALITY)
    return SlideReadout("key", signed_increment(disp, KEY_CARDINALITY),
                        KEY_CARDINALITY)


def slide_phase(phase: Sequence[float], phase_modulus: float,
                mass: Optional[Sequence[float]] = None) -> SlideReadout:
    """Phase-slide jack: per-bar F-quotient slide charge of the beat-phase
    section (modulus = the world's metrical-slot count S, in the same units as
    ``phase``).

    charge[t] = 1 - |sum_{tau<=t} m_tau e^{i 2 pi x_tau}| / sum_{tau<=t} m_tau,
    with x_tau = displacement_from_home[tau] / S and m_tau the bar's settled
    mass (uniform when None). See module docstring: the |.| quotients exactly
    one global phase re-referencing — F's own quotient, restated in numpy."""
    disp = displacement_from_home(phase, float(phase_modulus))
    T = len(disp)
    m = np.ones(T) if mass is None else np.asarray(mass, float)
    if m.shape != (T,):
        raise ValueError("mass must give one settled mass per bar")
    if np.any(m < 0.0):
        raise ValueError("bar masses must be >= 0")
    x = disp / float(phase_modulus)
    z = np.cumsum(m * np.exp(1j * 2.0 * np.pi * x))
    w = np.cumsum(m)
    charge = np.zeros(T)
    live = w > 0.0
    charge[live] = 1.0 - np.abs(z[live]) / w[live]
    return SlideReadout("phase", np.maximum(charge, 0.0), float(phase_modulus))


@dataclass(frozen=True)
class GaugeSlide:
    """The slide[g] jack bank: one jack per live v0 gauge component. The
    timbre-basis component is absent-by-construction on any v0 world (the
    same WALL recorded in ``drift_cv``; nothing is fabricated here)."""
    key: SlideReadout
    phase: SlideReadout

    def as_dict(self):
        return {"slide_key_disp": self.key.per_bar.tolist(),
                "slide_phase_charge": self.phase.per_bar.tolist()}


def gauge_slide(transpose: Sequence[float], phase: Sequence[float],
                phase_modulus: float,
                mass: Optional[Sequence[float]] = None) -> GaugeSlide:
    """Compute both slide jacks from a per-bar gauge-frame trajectory.

    ``transpose`` / ``phase`` are the settled per-section gauge values sampled
    per bar (FState.transpose / FState.phase_off at corpus time; the realized
    Schedule's per-section Gauge at the writer). ``mass`` is the per-bar
    settled mass (schedule-side; uniform when None)."""
    return GaugeSlide(key=slide_key(transpose),
                      phase=slide_phase(phase, phase_modulus, mass))
