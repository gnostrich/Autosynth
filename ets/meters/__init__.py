"""Output jacks (spec §9): drift/holonomy, phrase EOC, novelty saturation.

Read-only instrumentation. Every meter here is a PURE FUNCTION of an
arrangement / gauge-frame trajectory (or, for the loop-defect survey, of the
frozen world's role geometry) -> CV/gate. A meter takes NO F-weights and feeds
NOTHING back into any objective, gradient, or settlement decision (spec §9,
invariants I-5 and I-14). The sanctioned consumers are the planner (§10) and
CV-lane feedback patching (§10 mode 3b).

This package imports ONLY numpy — it has ZERO dependency on ets.functional
(f / solver / ot / anchors), which the I-14 manifest check enforces
structurally, proving the meters cannot fork decision authority from F.
"""
from .holonomy import (
    signed_increment, circular_holonomy, barycentric_map, loop_defect,
)
from .drift_cv import (
    DriftCV, DriftReadout, drift_cv, key_drift, phase_drift, timbre_drift,
    KEY_MODULUS, TIMBRE_MODULUS,
)
from .gauge_slide import (
    GaugeSlide, SlideReadout, gauge_slide, slide_key, slide_phase,
    displacement_from_home, KEY_CARDINALITY,
)
from .gauge_loop import loop_g, bar_blocks, star_edge, metrical_cost
from .phrase import PhraseEOC, phrase_eoc, dominant_period
from .novelty import NoveltySaturation, novelty_saturation

__all__ = [
    "signed_increment", "circular_holonomy", "barycentric_map", "loop_defect",
    "DriftCV", "DriftReadout", "drift_cv", "key_drift", "phase_drift",
    "timbre_drift", "KEY_MODULUS", "TIMBRE_MODULUS",
    "GaugeSlide", "SlideReadout", "gauge_slide", "slide_key", "slide_phase",
    "displacement_from_home", "KEY_CARDINALITY",
    "loop_g", "bar_blocks", "star_edge", "metrical_cost",
    "PhraseEOC", "phrase_eoc", "dominant_period",
    "NoveltySaturation", "novelty_saturation",
]
