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


# --- executable invariant checks (raise AssertionError on violation) ---------
# Checks import their guarded feature lazily so the manifest stays cheap to load
# and PENDING invariants pull in no heavy deps.

def _check_i2() -> None:
    """I-2 gauge law: no coordinate crosses a track boundary; only normalized,
    quotiented, within-track cost structure exists."""
    import numpy as np
    from ets.ingestion.pipeline import synthetic_track
    from ets.ingestion.track import require_within_track

    t1 = synthetic_track(track_id=1, seed=1)
    t2 = synthetic_track(track_id=2, seed=2)

    # (a) descriptor arrays are private, never shared across tracks
    for a, b in [(t1.C_timbre, t2.C_timbre),
                 (t1.C_pitchclass, t2.C_pitchclass),
                 (t1.C_metrical, t2.C_metrical)]:
        assert a.desc is not b.desc, f"{a.kind}: descriptor array shared across tracks"
        assert not np.shares_memory(a.desc, b.desc), \
            f"{a.kind}: descriptor memory aliased across tracks"
        assert a.track_id != b.track_id

    # (b) the ONLY sanctioned combiner refuses to bridge a track boundary
    for kind in ("C_timbre", "C_pitchclass", "C_metrical"):
        require_within_track(getattr(t1, kind), getattr(t1, kind))  # same track ok
        try:
            require_within_track(getattr(t1, kind), getattr(t2, kind))
        except ValueError:
            pass
        else:
            raise AssertionError(f"{kind}: cross-track cost was NOT forbidden")

    # (c) each cost is normalized within-track (dimensionless O(1)); self-cost 0
    for C in (t1.C_timbre, t1.C_pitchclass, t1.C_metrical):
        assert C.cost(3, 3) == 0.0, f"{C.kind}: nonzero self-cost"
        vals = [C.cost(i, j) for i in range(0, C.n, 7) for j in range(1, C.n, 5)]
        vals = np.array(vals)
        assert np.all(np.isfinite(vals)) and np.all(vals >= 0), \
            f"{C.kind}: non-finite/negative cost"
        rms = float(np.sqrt(np.mean(vals ** 2)))
        assert 0.2 < rms < 5.0, f"{C.kind}: not within-track normalized (rms={rms})"

    # (d) pitch-class cost is transposition-quotiented (invariant to chroma roll)
    Cp = t1.C_pitchclass
    base = Cp.cost(0, 5)
    Cp.desc[5] = np.roll(Cp.desc[5], 3)
    assert abs(Cp.cost(0, 5) - base) < 1e-9, "pitchclass cost not transposition-quotiented"

    # (e) metrical cost is circular (phase 0.0 ~ phase 1.0)
    Cm = t1.C_metrical
    Cm.desc[0, 0] = 0.0
    Cm.desc[1, 0] = 1.0
    assert Cm.cost(0, 1) < 1e-9, "metrical cost not circular"


def _check_i12() -> None:
    """I-12 provenance: every unit resolves to (track, unit, source-span); the
    check is not vacuous — a corrupted provenance must be caught."""
    import numpy as np
    from ets.ingestion.pipeline import synthetic_track
    from ets.ingestion.track import assert_provenance_complete

    t = synthetic_track(track_id=7, seed=7)
    assert_provenance_complete(t)  # a well-formed track passes

    # the guard actually catches violations (drop a provenance row)
    t.provenance_index = t.provenance_index[:-1].copy()
    try:
        assert_provenance_complete(t)
    except AssertionError:
        pass
    else:
        raise AssertionError("provenance check passed on an INCOMPLETE index")

    # and catches an out-of-source span
    t2 = synthetic_track(track_id=8, seed=8)
    t2.provenance_index["src_end"][0] = t2.n_samples + 10_000
    try:
        assert_provenance_complete(t2)
    except AssertionError:
        pass
    else:
        raise AssertionError("provenance check passed on an out-of-bounds span")


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
              Status.ENFORCED, _check_i2),
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
              Status.ENFORCED, _check_i12),
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
