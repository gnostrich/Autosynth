"""Outbound region-control shaping (architecture-v5 B3) — a UX-LAYER backstop.

This module shapes the REGION lean vector *on its way out of the panel* and does
nothing else. It is OUTSIDE the trained object: it imports only numpy, reads
nothing from settlement / F / render / provenance, and — by construction —
cannot influence how the writer settles or what the render emits (that is proven
statically by the door test). Deleting it leaves main-out byte-identical (V5-A).

Two pieces, both purely on the outbound control value:

  * `clamp_region` — the SAFE-ENVELOPE CLAMP (B3.1). Caps the per-anchor region
    lean the panel is allowed to transmit at `SAFE_REGION_MAGNITUDE`, preserving
    direction. It is a backstop WALL on the control, not an engine limiter: the
    engine sees a smaller number, nothing about its dynamics changes.

  * `RegionSlew` — the SLEW LIMITER (B3.2). A bounded-rate follower: it chases a
    target region vector with a maximum per-step delta, so a sudden control JUMP
    (a pad arm-teleport, a MIDI CC slam, a mid-stream lane change) leaves the
    panel as a MONOTONE RAMP instead of a one-frame discontinuity.

Measured basis for the cap (scratch measurements, engine untouched — see
PREREG-v5-interaction §"Measured facts"): single-anchor region lean is stable
across the whole 0.20→1.00 range, and the exact reported multi-anchor combo
rendered healthy offline at 1.0 and even at 1.2. `SAFE_REGION_MAGNITUDE = 1.0`
is therefore a comfortably-inside-healthy backstop, with headroom above it still
proven safe offline. The panel's XY pad ring is drawn AT this cap, so the cap is
something the operator can see and never a silent surprise.

Scope note (disclosed): only the REGION vector is clamped here. The five scalar
"steering" lanes are already bounded by their declared per-lane range (lanes.py
lo/hi = ±3 for the directions, [1e-3, 4] for temperature); the reported healthy
combo sits inside those, so no new scalar cap is warranted or added. The measured
divergence driver is the region multi-anchor magnitude, which this module walls.
"""
from __future__ import annotations

import numpy as np

# The safe-envelope cap on any single anchor's transmitted region lean. Named,
# with the measured basis above; the pad ring is painted AT this value.
SAFE_REGION_MAGNITUDE: float = 1.0

# Maximum per-emit change of any region component in the slew follower. At the
# panel's ~30 Hz emit/tick rate a full-scale (0→cap) move takes ~cap/step ticks
# (~0.4 s here) — a short constant that removes one-frame jumps without feeling
# laggy. It is a per-STEP bound, not read from anything downstream.
SLEW_MAX_STEP: float = 0.08


def clamp_region(u_region, cap: float = SAFE_REGION_MAGNITUDE) -> np.ndarray:
    """Return a copy of `u_region` whose largest-magnitude component is at most
    `cap`, scaling the whole vector uniformly so the LEAN DIRECTION (which
    anchors, in what ratio) is preserved. A vector already inside the envelope is
    returned unchanged (up to the float32 copy). This is the emittable-magnitude
    wall: no reachable control state can push a per-anchor lean past `cap`."""
    u = np.asarray(u_region, dtype=np.float32).reshape(-1).copy()
    if u.size == 0:
        return u
    peak = float(np.max(np.abs(u)))
    if peak > cap:
        u *= np.float32(cap / peak)
    return u


class RegionSlew:
    """Bounded-rate follower for the OUTBOUND region lean vector.

    `step(target)` advances the internal current vector toward `target` by at
    most `max_step` per component and returns the new current — a monotone,
    per-step-bounded ramp. It holds only its own current vector; it reads nothing
    from the trained object. A JUMP in `target` therefore leaves the panel as a
    sequence of small steps, never a single discontinuity (B3.2)."""

    def __init__(self, max_step: float = SLEW_MAX_STEP, n: int = 0) -> None:
        self.max_step = float(max_step)
        self._cur = np.zeros(int(n), dtype=np.float32)

    def _fit(self, n: int) -> None:
        if self._cur.shape[0] != n:
            c = np.zeros(n, dtype=np.float32)
            m = min(n, self._cur.shape[0])
            c[:m] = self._cur[:m]
            self._cur = c

    def step(self, target) -> np.ndarray:
        t = np.asarray(target, dtype=np.float32).reshape(-1)
        self._fit(t.shape[0])
        delta = np.clip(t - self._cur, -self.max_step, self.max_step)
        self._cur = (self._cur + delta).astype(np.float32)
        return self._cur.copy()

    def at_target(self, target, tol: float = 1e-6) -> bool:
        t = np.asarray(target, dtype=np.float32).reshape(-1)
        self._fit(t.shape[0])
        return bool(np.all(np.abs(t - self._cur) <= tol))

    def reset(self, vec) -> None:
        self._cur = np.asarray(vec, dtype=np.float32).reshape(-1).copy()

    @property
    def current(self) -> np.ndarray:
        return self._cur.copy()
