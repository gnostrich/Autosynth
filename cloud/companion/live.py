"""LIVE mode — the deck-playback tab's carrier math (Train B2, playable
milestone ONLY: straight play under a FULL FENCE; no bridge, no fence
release, no convergence arrival, no journey bar, no fidelity metric — those
are later trains per papers/PREREG-live-mode.md AMENDMENT 1 / AMENDMENT 2).

This module owns the PURE, engine-adjacent pieces that ``engine_bridge.
StreamPlayer`` wires into the produce loop:

  1. Resolve a (track, click-second) into the B-1 FULL FENCE: that track's
     own CONSECUTIVE slices from the clicked spot onward, using the SAME
     slice source the wavemap already reads (``engine_bridge.
     track_unit_slices``) — never re-derived (§2 of the prereg).

  2. Construct the carrier via the ONE locked construction point,
     ``ets.writer.clamp.clamp0`` — imported LAZILY here (Part A is a
     separate, parallel build; this module must not fail to import just
     because Part A hasn't landed yet in this process).

  3. Locate, by INTROSPECTION rather than a hardcoded guess, which keyword
     argument of ``StreamWriter.write_bar`` accepts the ClampTerms carrier.
     The locked interface fixes the carrier's CONSTRUCTOR and its TYPE NAME
     (``ClampTerms``) but not the parameter name Train A chooses on
     ``write_bar`` (a file this build does not own) — so the signature's
     annotations are searched for the string "ClampTerms" instead of
     guessing a literal kwarg.

Every entry point here fails LOUD (``LiveCarrierUnavailable``) rather than
ever falling back to unfenced (free-blend) play — AMENDMENT 2's B-0 forbids
the free blend from ever sounding in LIVE, so an unavailable/unwired carrier
must REFUSE the request, not degrade it silently.
"""
from __future__ import annotations

import bisect
import inspect
from typing import Optional, Sequence, Tuple


class LiveCarrierUnavailable(RuntimeError):
    """The Part-A clamp carrier (``ets.writer.clamp.clamp0`` / ``ClampTerms``)
    is not importable yet, or is importable but not yet wired into
    ``StreamWriter.write_bar`` — OR the track has no honest stored slice
    source to fence at all. Raised instead of ever silently proceeding
    without a real fence."""


# --- slice resolution (reuses engine_bridge.track_unit_slices verbatim) -----

def resolve_start_index(slices: Sequence[Sequence], t: float) -> int:
    """The ordinal index into ``slices`` (the track's OWN time-ordered
    ``track_unit_slices`` rows: ``[t0_s, t1_s, unit_id, mass, q]``) that
    click-second ``t`` lands in: the first slice whose span contains ``t``
    (``t0 <= t < t1``), the first slice starting at/after ``t`` if it falls
    in a gap, or the LAST slice if ``t`` is beyond the track's end. Never
    fabricates a slice — an empty ``slices`` is the caller's error to catch."""
    if not slices:
        raise LiveCarrierUnavailable(
            "track has no stored slices — cannot resolve a click into a fence")
    t = float(t)
    for idx, row in enumerate(slices):
        t0, t1 = float(row[0]), float(row[1])
        if t0 <= t < t1 or t < t0:
            return idx
    return len(slices) - 1


def pin_unit_ids(slices: Sequence[Sequence], start_index: int) -> Tuple[int, ...]:
    """That track's own CONSECUTIVE unit ids from ``start_index`` onward, in
    the SAME time order ``slices`` already carries (B-1: 'consecutive slices
    from position p'; B-1-amended: 'straight play begins there at once')."""
    return tuple(int(row[2]) for row in slices[start_index:])


def uid_index_map(slices: Sequence[Sequence]) -> dict:
    """unit_id -> its ordinal position in ``slices`` (time order). Lets
    ``StreamPlayer.live_state`` report ``slice_index`` for whichever unit is
    ACTUALLY placed (measured from produced-bar telemetry), never a timer or
    the originally-requested position."""
    return {int(row[2]): idx for idx, row in enumerate(slices)}


# --- the carrier itself -------------------------------------------------

# STRAIGHT PLAY IS A MOVING POINTER, NOT A BAG (measured fix, 2026-08-13), AND
# THE POINTER WALKS TATUMS, NOT ROWS (second measured fix, same day).
#
# First defect: the fence pinned a track's WHOLE remaining unit set, so the fiber
# choice roamed inside the track (measured live: 16593 -> 13281 -> 9945 -> 11664
# -> 3169 where consecutive ids were required). B-1 says "bars pinned to that
# track's CONSECUTIVE slices", so the pin must advance with the bar.
#
# Second defect, from the world's own grain: a unit is a (slot, band) CELL, so
# the n_bands units of one tatum SHARE that tatum's span (track_unit_slices'
# docstring: "the spans REPEAT by design"). A window of `s_phase` ROWS is
# therefore a fraction of one bar's tatums and carries only some bands — which
# is precisely why the bar's (role, band) demands starved. The core window is
# cut in TATUMS: one bar covers `s_phase` tatums, and every unit of those tatums
# is admitted. Nothing is dialled; both numbers are the world's own geometry.
#
# PER-ROLE WIDENING (AMENDMENT 4, operator-approved): a bar may still demand a
# role the core tatums do not carry. The fence then widens WITHIN THE SAME TRACK
# — the nearest unit of that role, by time — never to another track. That
# widening is the "fence-definition change" R1 permits; it is not an escape.
# Units admitted by widening rather than by the core window are counted as
# OFF-WINDOW for R2(b) and feed the B-5 fidelity verdict.

def _tatum_groups(slices: Sequence[Sequence]) -> list:
    """`slices` grouped into consecutive same-span runs — the world's tatums, in
    time order. Each group is the list of that tatum's row indices (its n_bands
    (slot, band) cells)."""
    groups: list = []
    last = None
    for idx, row in enumerate(slices):
        span = (float(row[0]), float(row[1]))
        if span != last:
            groups.append([])
            last = span
        groups[-1].append(idx)
    return groups


def _role_of(row: Sequence) -> Optional[int]:
    """The stored role of one slice row: argmax of its stored q indicator. None
    when the row carries no usable indicator — never a guessed role."""
    q = row[4] if len(row) > 4 else None
    try:
        q = list(q)
    except TypeError:
        return None
    if not q:
        return None
    best, best_v = 0, float(q[0])
    for k in range(1, len(q)):
        if float(q[k]) > best_v:
            best, best_v = k, float(q[k])
    return int(best)


def group_of_index(slices: Sequence[Sequence], start_index: int) -> int:
    """Which tatum group the clicked slice row falls in. Straight play starts at
    the CLICKED spot, so the cursor is measured from this group — not from the
    top of the track."""
    for gi, g in enumerate(_tatum_groups(slices)):
        if start_index in g:
            return gi
    return 0


def build_plan(slices: Sequence[Sequence]) -> dict:
    """Everything the per-bar fence needs, computed ONCE per click: the tatum
    grouping and, per role, that role's (group index, row index) pairs in time
    order so the nearest carrier is a bisect rather than a full rescan."""
    groups = _tatum_groups(slices)
    role_groups: dict = {}
    for gi, g in enumerate(groups):
        for i in g:
            role_groups.setdefault(_role_of(slices[i]), []).append((gi, i))
    return {"groups": groups, "role_groups": role_groups}


def bar_window(slices: Sequence[Sequence], bars_elapsed: int, s_phase: int,
               demanded_roles: Optional[Sequence[int]] = None,
               start_group: int = 0, plan: Optional[dict] = None) -> dict:
    """This bar's fence content, as ``{"core": (...), "widened": (...),
    "exhausted": bool}``.

    ``core``    — every unit of this bar's `s_phase` tatums, walking forward.
    ``widened`` — for each demanded role the core does not carry, that track's
                  OWN nearest unit of the role (by tatum distance). Empty when
                  the core already covers every demanded role.
    ``exhausted`` — the cursor has walked past the end of the track; the caller
                  returns to idle silence rather than wrapping or repeating.
    """
    # PRECOMPUTED (measured fix): grouping 17k rows and scanning every group per
    # missing role ONCE PER BAR is O(track) per bar — on an 8-minute track that
    # is slow enough that the produce loop composed ZERO bars in 45s (measured
    # live: bars_elapsed stuck at 0, no audio). `plan` carries the grouping and
    # the per-role nearest-tatum index, built ONCE at click time, so the per-bar
    # cost is a list slice and a dict lookup.
    if plan is None:
        plan = build_plan(slices)
    groups = plan["groups"]
    w = max(1, int(s_phase))
    start = max(0, int(start_group)) + max(0, int(bars_elapsed)) * w
    core_groups = groups[start:start + w]
    if not core_groups:
        return {"core": (), "widened": (), "exhausted": True}

    # NEIGHBOURHOOD (measured fix): a single bar's worth of tatums often carries no
    # unit at all for some role the settlement demands, so the fence starved on
    # nearly every bar and — under the hard-fence law, correctly — those slots fell
    # silent. The result was audible as thin, skeletal playback. Admitting the
    # surrounding tatums OF THE SAME TRACK gives the bar enough material to fill its
    # roles while staying inside the fence: same track, still walking forward, no
    # cast outside ClampTerms. The forward-walking CORE still starts every bar
    # (LM-3(a)); this only widens what is admissible around it.
    lo = max(0, start - w)
    hi = min(len(groups), start + 2 * w)
    core_groups = groups[lo:hi]

    core_idx = [i for g in core_groups for i in g]
    core = tuple(int(slices[i][2]) for i in core_idx)

    widened: list = []
    if demanded_roles:
        have = {_role_of(slices[i]) for i in core_idx}
        centre = start + len(core_groups) // 2
        for k in demanded_roles:
            k = int(k)
            if k in have:
                continue
            # nearest tatum carrying role k — a bisect over that role's own
            # precomputed, time-ordered group list (was a full rescan per bar)
            by_role = plan["role_groups"].get(k)
            if not by_role:
                continue                      # the track has no role-k material
            pos = bisect.bisect_left(by_role, (centre,))
            best_i, best_d = None, None
            for cand in by_role[max(0, pos - 1):pos + 2]:
                d = abs(cand[0] - centre)
                if best_d is None or d < best_d:
                    best_i, best_d = cand[1], d
            if best_i is not None:
                widened.append(int(slices[best_i][2]))
    return {"core": core, "widened": tuple(widened), "exhausted": False}


def bar_window_unit_ids(unit_ids: Sequence[int], bars_elapsed: int,
                        s_phase: int) -> Tuple[int, ...]:
    """Row-cut window kept for the fixtures that pin the pointer's forward walk
    on a flat id list (no span/role information available there). The live path
    uses ``bar_window`` above, which cuts by tatum and widens per role."""
    w = max(1, int(s_phase))
    start = max(0, int(bars_elapsed)) * w
    return tuple(int(u) for u in unit_ids[start:start + w])


def build_full_fence(track: int, unit_ids: Sequence[int]):
    """Construct the B-1 FULL FENCE for straight play: fully fenced to
    ``track`` (``track_mask={track: 1.0}, openness=1.0``), pinned to
    ``unit_ids`` — which for straight play is ONE BAR's consecutive window
    (see ``bar_window_unit_ids``), rebuilt each bar so the tape walks the
    track forward instead of roaming inside it. Lazy import — Part A may land
    seconds after this module does; raises ``LiveCarrierUnavailable`` rather
    than ever proceeding without a real fence."""
    try:
        from ets.writer.clamp import clamp0
    except ImportError as exc:
        raise LiveCarrierUnavailable(
            "ets.writer.clamp.clamp0 is not importable yet (Part A / Train A "
            f"of PREREG-live-mode.md has not landed in this process): "
            f"{type(exc).__name__}: {exc}") from exc
    try:
        return clamp0(track_mask={int(track): 1.0}, openness=1.0,
                      unit_pin=(int(track), tuple(int(u) for u in unit_ids)))
    except Exception as exc:
        raise LiveCarrierUnavailable(
            f"clamp0(...) failed to construct the full fence: "
            f"{type(exc).__name__}: {exc}") from exc


def clamp_kwarg_name(write_bar_fn) -> Optional[str]:
    """Which keyword of ``write_bar`` accepts the ClampTerms carrier, found
    by reading the signature's annotations for the carrier's TYPE NAME
    (``ClampTerms`` — the one thing §2 of the prereg locks) rather than
    guessing a parameter name (this build does not own ``realize.py`` /
    ``stream.py`` and cannot know what Train A calls it). ``None`` if no such
    parameter exists yet (the carrier isn't wired into the writer)."""
    try:
        sig = inspect.signature(write_bar_fn)
    except (TypeError, ValueError):
        return None
    for name, param in sig.parameters.items():
        if name in ("self", "tilt", "clamps"):     # "clamps" = the pre-existing
            continue                               # I-7 ClampSet — a different carrier
        if "ClampTerms" in str(param.annotation):
            return name
    return None


def clamp_call_kwargs(write_bar_fn, clamp_terms) -> dict:
    """The ``{kwarg_name: clamp_terms}`` to splat into ``write_bar(tilt=...,
    **kwargs)``. ``clamp_terms is None`` (GRID/TRACKS — LIVE never touched,
    or LIVE idle) returns ``{}`` WITHOUT introspecting anything, so an
    un-fenced call stays the exact ``write_bar(tilt=tilt)`` call it is today
    (byte-identical; LM-0/LM-1). A non-None ``clamp_terms`` with no matching
    writer parameter raises ``LiveCarrierUnavailable`` — never a silent skip,
    which would emit the free blend under a fence request (exactly what B-0
    forbids)."""
    if clamp_terms is None:
        return {}
    name = clamp_kwarg_name(write_bar_fn)
    if name is None:
        raise LiveCarrierUnavailable(
            "StreamWriter.write_bar has no ClampTerms-typed parameter yet — "
            "the carrier module imports, but is not wired into the writer. "
            "LIVE refuses rather than emit unfenced audio under a fence.")
    return {name: clamp_terms}


# --- measured placement (the live-state feed) --------------------------

def current_placement(rows, track: int, uid_index: dict):
    """The unit ACTUALLY placed for ``track`` in one produced bar's rows
    (tuples ``(slot, tid, uid, sec, mass)``), by highest mass (ties: the
    later slot) — 'measured, not asserted': reads produced rows only, the
    same reduction family as ``engine_bridge.nowplaying_unit_activity``.
    Returns ``(unit_id, slice_index_or_None)``, or ``None`` if the fenced
    track placed nothing this bar."""
    best_key = None
    best_uid = None
    for (slot, tid, uid, _sec, mass) in rows:
        if int(tid) != int(track):
            continue
        key = (float(mass), int(slot))
        if best_key is None or key >= best_key:
            best_key, best_uid = key, int(uid)
    if best_uid is None:
        return None
    return best_uid, uid_index.get(best_uid)
