"""The two declared TOLERANCE knobs (directive v1): LEASH and COMMA.

  LEASH — slide tolerance.
  COMMA — loop tolerance. DEFAULT = +infinity (displayed 'inf'), so shipped
          behavior is unchanged until the user turns it.

TYPING (why these are NOT lanes and NOT tilt inputs). Spec §8's six CV lanes
are the EXHAUSTIVE control set entering the writer through the single tilt
jack; that law stands untouched (ets.panel.lanes.assert_lanes_exhaustive).
LEASH and COMMA are TOLERANCES: declared bounds the operator sets on the
writer's slide/loop drift, the input side of the slide/loop meter jack pairs.
In v1 FEATURE 1 they exist, display, and TRANSMIT (/ets/tolerances) — and are
consumed by NOTHING. Stage-1 authority wiring (what enforcement of a finite
tolerance even means — it is boundary-condition-typed per the connector's
one-intervention-species law, not a new control channel) is a separate,
pre-registered feature. CI enforces the no-consumer state: no identifier of
these knobs may appear in ets/writer or ets/render
(tests/harness/test_h6_panel_exhaustive.py).

DEFAULTS, derived, not taste: both default to +inf — the tolerance that
constrains nothing — because v1 ships with zero enforcement authority; any
finite default would DECLARE a bound nothing enforces (a lie on the panel).
The directive pins comma's default = inf explicitly; leash inherits the same
logic and this is flagged in the session report (the directive's "wire to the
EXISTING budget mechanic" found no such mechanic in the tree — see report).

This mirrors lanes.py: a closed, typed, asserted set. Exactly TWO knobs; a
third tolerance is a spec/directive revision, and the guard bites on it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ToleranceSpec:
    id: str
    title: str
    meaning: str
    default: float          # +inf = unconstrained (see module docstring)
    lo: float = 0.0         # tolerances are magnitudes; negative is malformed


TOLERANCES: Tuple[ToleranceSpec, ...] = (
    ToleranceSpec("leash", "LEASH", "slide tolerance", default=math.inf),
    ToleranceSpec("comma", "COMMA", "loop tolerance", default=math.inf),
)

TOLERANCE_IDS: Tuple[str, ...] = tuple(t.id for t in TOLERANCES)
_CANONICAL = frozenset({"leash", "comma"})


def assert_tolerances_exhaustive(ids) -> None:
    """Exactly the two declared tolerance knobs — no third, none missing."""
    got = tuple(ids)
    assert len(got) == len(set(got)), f"duplicate tolerance ids: {got}"
    assert frozenset(got) == _CANONICAL, (
        "TOLERANCE KNOB SET IS NOT THE DECLARED TWO (LEASH, COMMA). "
        f"extra={sorted(frozenset(got) - _CANONICAL)} "
        f"missing={sorted(_CANONICAL - frozenset(got))}. Adding a tolerance "
        "requires a directive/spec revision.")


def display(value: float) -> str:
    """Panel display: 'inf' for the untouched (unconstraining) tolerance."""
    return "inf" if math.isinf(value) else f"{value:.3f}"


@dataclass
class Tolerances:
    """The transmitted tolerance pair. Finite values must be >= 0."""
    leash: float = math.inf
    comma: float = math.inf

    def __post_init__(self):
        for spec in TOLERANCES:
            v = float(getattr(self, spec.id))
            if math.isnan(v) or v < spec.lo:
                raise ValueError(f"{spec.title} must be >= {spec.lo} or inf, got {v}")
            setattr(self, spec.id, v)

    def as_dict(self) -> dict:
        return {"leash": self.leash, "comma": self.comma}
