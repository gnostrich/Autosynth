"""ClampTerms — the sanctioned SECOND carrier into the writer (prereg
PREREG-live-mode.md, PART A; mirrors I-1's single-construction-point law).

TiltTerms (``tilt.py``) reshapes the MEASURE over a fiber choice set (a soft
Doob h-transform: every candidate stays reachable, some are leaned toward).
ClampTerms reshapes the SET ITSELF (a feasible-set restriction, T4 in the
prereg's vocabulary): before the SAME measure runs, some candidates are simply
not admitted this bar. Nothing about F, the settlement solver, or the casting
measure changes (A-5) — ClampTerms only narrows `choices` in
``realize.FiberThreader._choose`` before energies are ever computed over it.

    p(a) ∝ exp( −F(a)/T_s + Σ_i λ_i · φ_i(a) )     restricted to a ⊂ FEASIBLE(clamp)

ONE CONSTRUCTION POINT (A-1, mirrors C-3/I-1): ``clamp0`` is the only function
in this codebase meant to build a live restriction from control values. There
is no other legitimate call site for ``ClampTerms(...)`` anywhere in the
engine; ``tests/test_clamp_carrier.py`` statically scans the tree for a rogue
second constructor and fails the build if one appears (mirror of
``test_c3_engine_constructs_tilt_only_via_layer0``).

CONTENT (A-3). Per bar, upstream hands the writer:
  track_mask : {track_id -> m in [0,1]}   per-track admission level
  openness   : scalar in [0,1]            the fence's current strength
  unit_pin   : optional (track_id, (unit_id, ...))  an ordered admissible-unit
               range on ONE track (the "(track, slice-range) pin" of A-3,
               expressed as the ordered real units that range covers — for a
               straight, phase-locked track this ordered-unit sequence IS the
               slice range, so no separate slice-index field is needed: a real
               unit already carries its position in its source track).

THE FENCE RULE (prereg §2.1 — the only engine logic this carrier adds; lives
in realize.py, not here): a candidate c = (track_id, unit_id) survives iff

    track_mask.get(track_of(c), 0.0) >= openness

and, when ``unit_pin`` names c's track, iff c's unit_id is in the pinned
range. Openness=1 with mask={i:1.0} is a FULL FENCE (only track i survives);
openness=0 is NO RESTRICTION (every mask value is >= 0 trivially). Between the
two, a rising `openness` admits a widening ring of tracks in mask order. This
carrier does not decide *when* openness moves — that is upstream data (LM-4);
no schedule, ramp, bar-count, or timeout constant lives in this module or in
realize.py (prereg Amendment 1, LM-9: the N-bar timetable is retired — the
prior draft's ``N_BRIDGE_BARS``/ramp-shape constants never landed here and
must not reappear).

NEUTRAL LAW (A-2, KILL CONDITION LM-1). Exactly like ``TiltTerms.__post_init__``
canonicalizing an all-zero ``channel_logbias`` to ``None``, a ClampTerms whose
restriction is vacuous canonicalizes to ``None`` — not an object that happens
to restrict nothing, but the literal absent-carrier sentinel ``realize.py``
already treats as "no clamp at all" (``self.clamp is None`` skips the fence
branch entirely: zero extra computation, zero extra rng draws). Three
independent conditions each trigger this, matching the prereg's wording
exactly:

  * ``openness == 0.0``        — the fence rule admits every track regardless
                                  of what the mask says (m >= 0 always holds),
                                  so a mask paired with openness=0 is inert.
  * an empty ``track_mask``    — with NO per-track entries at all, `openness`
                                  has nothing to threshold: treating "no data"
                                  as "restrict everything" would be inventing
                                  a restriction from absence (the same honesty
                                  principle as WorldNotCalibrated refusing to
                                  invent a λ scale). Note this is deliberately
                                  NOT the same as an all-EXPLICIT-zero mask
                                  (e.g. {0: 0.0, 1: 0.0}) with openness > 0:
                                  that IS real (if extreme) restriction data —
                                  it starves on purpose and is reported via
                                  STARVED, never silently reinterpreted as
                                  neutral. Zero-valued mask entries are
                                  therefore NOT dropped during canonicalization
                                  (unlike TiltTerms.channel_logbias, which
                                  drops zero weights); doing so here would
                                  collapse that legitimate all-zero-explicit
                                  state into the empty-mask neutral bucket.
  * an absent carrier          — ``clamp=None`` (the parameter's own default
                                  everywhere it is threaded) or ``no_clamp()``.

``clamp0`` always validates first (so a malformed ``openness``/mask still
raises even when the result would be neutral) and only THEN collapses a
neutral result to ``None`` — the same order TiltTerms follows: build the
canonical object, then let ``is_untilted``/``is_neutral`` decide whether the
tilt/clamp block of the settlement sees it at all.

TYPING SPLIT (A-4, KILL CONDITION LM-2, prereg §4's operator-flagged reading,
restated here verbatim):

    "No unit or time target may leave the LIVE path on the tilt carrier.
     LIVE's tilt payload carries ['col', r] column leans and nothing else; a
     unit/time target offered to the tilt carrier from the LIVE path raises
     TypeError."

``live_tilt_target`` below is that gate: the ONLY function through which the
(not-yet-built) LIVE bridge may address ``TiltTerms`` at all. It accepts
nothing but a "col" (column = REGION anchor) target and raises ``TypeError``
for "unit"/"time" — because unit/time content is exactly what ``unit_pin``
above is FOR: unit and time (ordered-unit-range) targets are LEGAL on
ClampTerms, always. This split is scoped strictly to the LIVE path; it does
NOT touch ``tilt.py`` at all (this module imports nothing from it and
``tilt.py`` is not edited by this build), so the pre-existing, shipped,
operator-ratified GRID field-bias UNIT grain
(``TiltTerms.channel_logbias["unit"]``, PREREG-field-bias-REV3) is completely
untouched — GRID keeps leaning individual units exactly as it does today
(LM-0/LM-8: that grain never calls this gate and never will).

POLARITY (stated so nobody misreads it, prereg §2.1's own note): the
operator's word is `openness` and the operator's definition is INVERTED
against the English word — **1 = fully fenced, 0 = no restriction**. Both the
name and the polarity are kept verbatim; a "1 -> 0 -> 1" openness trajectory
therefore means *fenced -> free -> fenced*, exactly as the directive
describes it. This carrier does not decide the trajectory (Amendment 1: it
arrives as upstream release/convergence-close EVENTS, not a schedule this
carrier or the engine computes) — it only ever holds one bar's already-decided
(mask, openness, pin) snapshot, which is why every ClampTerms instance is
frozen and per-bar-immutable, constructed upstream and handed to the writer
exactly as one TiltTerms per bar already is.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class ClampTerms:
    """The feasible-set restriction (T4) the writer's fiber choice consumes
    alongside TiltTerms. See the module docstring for content (A-3), the
    neutral law (A-2/LM-1), and the typing split (A-4/LM-2). Construct ONLY
    via ``clamp0``/``no_clamp`` (A-1) — never directly outside this module."""

    track_mask: Mapping[int, float]
    openness: float
    unit_pin: Optional[Tuple[int, Tuple[int, ...]]] = None
    # PER-SLOT PIN (straight-play faithfulness). `unit_pin` admits a bar's worth of
    # material as ONE pool, which lets any slot play any of it: measured, a single
    # bar drew tatums 0, 8, 15, 16 and 23 at once — the track layered over itself.
    # This maps slot-in-bar -> the units that slot alone may play, so the bar walks
    # the passage in order. None ⇒ unchanged behaviour (neutral law untouched).
    slot_pin: Optional[Mapping[int, Tuple[int, ...]]] = None

    def __post_init__(self):
        mask = {}
        for k, v in dict(self.track_mask).items():
            k = int(k)
            v = float(v)
            if not (isfinite(v) and 0.0 <= v <= 1.0):
                raise ValueError(
                    f"track_mask[{k}]={v} must be finite and in [0,1]")
            mask[k] = v
        object.__setattr__(self, "track_mask", mask)

        o = float(self.openness)
        if not (isfinite(o) and 0.0 <= o <= 1.0):
            raise ValueError(f"openness={o} must be finite and in [0,1]")
        object.__setattr__(self, "openness", o)

        if self.unit_pin is not None:
            tid, units = self.unit_pin
            tid = int(tid)
            ordered: list = []
            for u in units:
                u = int(u)
                if u not in ordered:
                    ordered.append(u)
            if not ordered:
                raise ValueError(
                    "unit_pin's admissible unit range must be non-empty "
                    "(a pin naming zero units is not a pin — express 'admit "
                    "nothing from this track' via track_mask instead)")
            object.__setattr__(self, "unit_pin", (tid, tuple(ordered)))

    @property
    def is_neutral(self) -> bool:
        """True iff this restriction is vacuous under the fence rule
        (prereg §2.1): `openness == 0` makes every mask entry satisfy
        `m >= openness` regardless of value, and an empty mask has no data
        for `openness` to threshold against. See the module docstring's
        NEUTRAL LAW for why these two conditions collapse to neutral while an
        explicit all-zero-valued mask with openness > 0 deliberately does
        NOT (it starves on purpose, disclosed via STARVED).

        This is a CONSTRUCTION-TIME judgment, consumed by `clamp0` (below) to
        decide whether to return this object or `None`. `realize._admits` —
        the engine's fence rule itself — implements prereg §2.1 LITERALLY,
        with no special case for an empty mask (an empty mask and an
        explicit all-zero mask are indistinguishable to a plain
        `dict.get(tid, 0.0)` lookup, by construction). The empty-mask branch
        of the neutral law therefore holds only for objects that passed
        through `clamp0`; a raw `ClampTerms(track_mask={}, openness=...>0)`
        built by bypassing `clamp0` is a misuse (exactly what LM-2's
        single-construction-point check exists to catch) and, if it somehow
        reached the engine anyway, would starve — not silently pass as
        neutral. `openness == 0` needs no such caveat: it is neutral by the
        engine's fence formula unconditionally, regardless of construction
        path, because `m >= 0` holds for EVERY valid mask value."""
        return self.openness == 0.0 or not self.track_mask


def clamp0(track_mask: Mapping[int, float], openness: float,
           unit_pin: Optional[Tuple[int, Tuple[int, ...]]] = None,
           slot_pin: Optional[Mapping[int, Tuple[int, ...]]] = None
          ) -> Optional[ClampTerms]:
    """THE single construction point (A-1) for a live ClampTerms restriction.

    Validates and canonicalizes exactly like ``ClampTerms.__post_init__``
    (so malformed input still raises even in the neutral case — validate
    first, canonicalize-to-None second, the same order ``layer0`` follows),
    then applies the NEUTRAL LAW (A-2/LM-1): a vacuous restriction collapses
    to ``None``, byte-identical to no carrier at all, because
    ``realize.FiberThreader`` treats ``clamp is None`` as "skip the fence
    branch entirely" — no extra computation, no extra rng draw, ever."""
    terms = ClampTerms(track_mask=dict(track_mask), openness=float(openness),
                       slot_pin=(dict(slot_pin) if slot_pin else None),
                       unit_pin=unit_pin)
    return None if terms.is_neutral else terms


def no_clamp() -> None:
    """The explicit neutral carrier (A-2). Always ``None`` — passing this,
    passing nothing (every clamp-accepting parameter in this codebase
    defaults to ``None``), or passing ``clamp0`` a vacuous restriction are
    the SAME value reaching the writer, hence byte-identical output (LM-1)."""
    return None


_LIVE_TILT_LEGAL_KINDS = ("col",)


def live_tilt_target(kind: str, ref: int) -> Tuple[str, int]:
    """THE LIVE path's sole gate onto the tilt carrier (A-4 TYPING SPLIT;
    prereg §4 / Amendment 1's carried-over wording, LM-2's kill condition).

    `kind` is the vocabulary A-4 uses for what a control value targets:
    "col" addresses a REGION anchor r (the w_r column lean TiltTerms already
    carries via `lam_region[r]`); "unit"/"time" address a specific source
    unit or an output-slot position. Only "col" is legal through this gate —
    "unit"/"time" raise TypeError, because that content belongs on
    ClampTerms.unit_pin instead (construct it via `clamp0`, which accepts it
    without complaint; see test_clamp_carrier.py::LM-2 for the paired proof).

    This function is NOT a restriction on TiltTerms itself — it is the LIVE
    bridge's own narrow front door, scoped to the (not-yet-built) LIVE mode.
    The pre-existing, ratified GRID field-bias UNIT grain
    (`TiltTerms.channel_logbias["unit"]`) does not call this gate, is not
    reachable through it, and is untouched by this build (LM-0/LM-8)."""
    if kind not in _LIVE_TILT_LEGAL_KINDS:
        raise TypeError(
            f"LIVE tilt path forbids a {kind!r} target (ref={ref!r}) — "
            "unit/time content may not reach the tilt carrier from LIVE "
            "(A-4/LM-2); express it as ClampTerms.unit_pin instead")
    return ("col", int(ref))
