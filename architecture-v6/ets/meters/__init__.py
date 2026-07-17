"""Output jacks (spec §9): slide/loop gauge-drift pair, phrase EOC, novelty
saturation.

Read-only instrumentation. Every meter here is a PURE FUNCTION of an
arrangement / gauge-frame trajectory (or, for the loop-defect survey, of the
frozen world's role geometry) -> CV/gate. A meter takes NO F-weights and feeds
NOTHING back into any objective, gradient, or settlement decision (spec §9,
invariants I-5 and I-14). The sanctioned consumers are the planner (§10) and
CV-lane feedback patching (§10 mode 3b); ``contract`` types those consumers
(directive-v1 Feature 2 Stage 1).

This package imports ONLY numpy — it has ZERO dependency on ets.functional
(f / solver / ot / anchors), which the I-14 manifest check enforces
structurally, proving the meters cannot fork decision authority from F.

NOTE (directive-v1 Feature 2 Stage 1): the prior conflated DRIFT CV jack
(``drift_cv``, one number per gauge component mixing frame-slide with traffic
curvature) was DELETED outright — code, panel element, OSC address, registry
field — per the merged evidence (REGISTRY conflation-regression-stage1-
2026-07-15: residual exactly 0.0 at machine precision on every producible
trace). ``slide``/``loop`` below are the two jacks that replaced it.
"""
from .holonomy import signed_increment, barycentric_map, loop_defect
from .gauge_slide import (
    GaugeSlide, SlideReadout, gauge_slide, slide_key, slide_phase,
    displacement_from_home, KEY_CARDINALITY,
)
from .gauge_loop import loop_g, bar_blocks, star_edge, metrical_cost
from .phrase import PhraseEOC, phrase_eoc, dominant_period
from .novelty import NoveltySaturation, novelty_saturation
from . import contract

__all__ = [
    "signed_increment", "barycentric_map", "loop_defect",
    "GaugeSlide", "SlideReadout", "gauge_slide", "slide_key", "slide_phase",
    "displacement_from_home", "KEY_CARDINALITY",
    "loop_g", "bar_blocks", "star_edge", "metrical_cost",
    "PhraseEOC", "phrase_eoc", "dominant_period",
    "NoveltySaturation", "novelty_saturation",
    "contract",
]
