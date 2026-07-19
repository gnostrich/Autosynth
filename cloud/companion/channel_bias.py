"""Per-channel SOFT bias (PREREG-channel-bias-squares, Phase 1 — soft revision).

A "channel" is a source track. Amplifying channel T applies a SOFT lean toward
track-T material: an additive log-weight on track-T's candidate units inside the
Layer-0 FIBER choice measure — the distribution over the pooled channels at each
beat (``ets.writer.tilt.fiber_choice_logits``). The Gibbs settlement PERCEIVES the
lean and accommodates it (it draws track-T units more often where they are
candidates, and the run-continuation / other bands settle around that); NOTHING is
pinned, no slot is forced, the writer stays fully generative. This is the operator
mechanism correction: a soft prior the settlement reads, not a hard I-7 clamp.

The lean rides the ONE ``TiltTerms`` the writer already consumes (I-1) via a new
``channel_logbias`` field ({track_id -> additive log-weight}); there is no second
control channel, no new lane, no clamp. amplify ∈ [0,1] is the bias STRENGTH
(continuous); zero / empty ⇒ no addend ⇒ the fiber draw is byte-identical.

STRENGTH SCALE (derived, not hand-set): the per-unit-amplify log-weight is F's own
metrical phase-charge weight ``LAMBDA['T1p']`` (read live), so amplify=1 leans a
channel by one natural "unit of preference" on the same log-odds scale the fiber
energies live on — strong but soft (F's phase / continuation terms still compete,
and a channel with no candidate at a beat gets no lean there). No magic constant.

DEGENERACY IS THE OPEN QUESTION (measured, Phase-1 gate). A soft lean can COLLAPSE
if the channels overlap in the pooled candidate set or F's energies dominate. The
verifier measures the provenance pull curve; if it is mushy, that is the honest H0
(keep the XY pad; disarm the squares) — we do NOT fall back to the hard clamp.
"""
from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np


def channel_tids(world) -> List[int]:
    """Channel ordering: channel i is the i-th track_id in ascending order —
    stable and world-independent, so a bias vector's component i always addresses
    the same channel."""
    return sorted(int(t.track_id) for t in world.tracks)


def default_strength() -> float:
    """The per-unit-amplify log-weight = F's own metrical phase-charge weight
    (read live, so it tracks calibration). Derived scale, no hand-set constant."""
    from ets.functional.f import LAMBDA
    return float(LAMBDA["T1p"])


def channel_logbias(bias, tids: List[int], strength: Optional[float] = None
                    ) -> Optional[Dict[int, float]]:
    """Assemble the {track_id -> additive log-weight} soft-lean map for a
    per-channel amplify vector. Returns ``None`` when nothing is biased (⇒ the
    writer's default fiber draw ⇒ byte-identical)."""
    b = np.asarray(bias, dtype=np.float64).reshape(-1)
    if b.size == 0 or not np.any(b > 0.0):
        return None
    if strength is None:
        strength = default_strength()
    out: Dict[int, float] = {}
    for ch in range(min(b.size, len(tids))):
        a = float(b[ch])
        if a > 0.0:
            out[int(tids[ch])] = float(strength) * a
    return out or None
