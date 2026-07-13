"""Canonical invariant manifest — the executable source of truth for spec §14.

Each invariant I-1..I-14 from ets-spec-v0.md §14 is registered here with its
spec text, an enforcement status, and (once the relevant feature exists) a
check function. This module is the single place the auditor and CI consult to
know which invariants are ENFORCED by an executable test and which are still
PENDING because the feature they guard has not been built yet.

Discipline (builder rule 3, auditor §2):
  - No invariant may be absent from this list.
  - PENDING means "the guarded feature does not exist yet", never "we chose
    not to check". When the feature lands, its invariant MUST move to ENFORCED
    in the same change, or the auditor rejects the diff.
  - An ENFORCED invariant's check function raises AssertionError on violation.
  - Nothing here may be satisfied by a vacuous pass; a PENDING invariant is
    reported as pending, not as passing.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class Status(Enum):
    ENFORCED = "enforced"   # an executable check exists and runs
    PENDING = "pending"     # guarded feature not built yet; check to come with it


@dataclass(frozen=True)
class Invariant:
    id: str                 # "I-1"
    title: str
    spec_text: str          # verbatim from §14
    status: Status
    check: Optional[Callable[[], None]] = None   # raises AssertionError on violation

    def __post_init__(self):
        if self.status is Status.ENFORCED and self.check is None:
            raise ValueError(f"{self.id} marked ENFORCED but has no check function")
        if self.status is Status.PENDING and self.check is not None:
            raise ValueError(f"{self.id} marked PENDING but ships a check function")


# The 14 invariants, verbatim titles from spec §14. All PENDING at skeleton
# stage (no guarded feature exists yet). Each moves to ENFORCED in the same
# diff that builds the feature it guards.
INVARIANTS = [
    Invariant("I-1", "single tilt jack",
              "no control path into the writer except h-transform tilt.",
              Status.PENDING),
    Invariant("I-2", "gauge law",
              "no coordinates cross a track boundary; only normalized intrinsic "
              "cost structure.",
              Status.PENDING),
    Invariant("I-3", "no duplicate smoothing",
              "no pressure accumulator or any duplicate smoothing mechanism.",
              Status.PENDING),
    Invariant("I-4", "one F",
              "no training loss distinct from F; no eta-KL tether or second "
              "authority over equilibrium gains.",
              Status.PENDING),
    Invariant("I-5", "meters out of the loss",
              "meters never in any objective/gradient/settlement decision.",
              Status.PENDING),
    Invariant("I-6", "no external negatives",
              "no external negative data; comparison class derived from good "
              "tracks only; scramble family fixed in PREREG.",
              Status.PENDING),
    Invariant("I-7", "clamped-cell interventions",
              "all interventions (past, human demands) are clamped cells; no "
              "exception paths, no recovery modes.",
              Status.PENDING),
    Invariant("I-8", "streaming stability",
              "streaming stability certificate; halt-and-report on state growth "
              "under stationary input.",
              Status.PENDING),
    Invariant("I-9", "frozen F weights",
              "run-time controls are tilt parameters only; F term-weights frozen "
              "after training.",
              Status.PENDING),
    Invariant("I-10", "thin planner",
              "planner stateless, external, thin; reads meters/map, writes lanes "
              "only.",
              Status.PENDING),
    Invariant("I-11", "render applies, never chooses",
              "rendering applies, never chooses.",
              Status.PENDING),
    Invariant("I-12", "provenance",
              "every output sample traceable to (track, unit, transform).",
              Status.PENDING),
    Invariant("I-13", "no web tech",
              "no browser/web tech in runtime.",
              Status.PENDING),
    Invariant("I-14", "Hankel/holonomy are instruments",
              "Hankel/holonomy quantities are instruments; event triggers must "
              "not fork decision authority from F.",
              Status.PENDING),
]

EXPECTED_IDS = [f"I-{n}" for n in range(1, 15)]


def by_id(iid: str) -> Invariant:
    for inv in INVARIANTS:
        if inv.id == iid:
            return inv
    raise KeyError(iid)
