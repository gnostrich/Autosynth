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
from typing import Mapping, Optional, Sequence, Tuple


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
    # STRICT FORWARD WINDOW. Widening to the surrounding tatums filled the silence
    # holes but stopped it being linear playback - the operator hears it smear
    # rather than play the passage ("not playing the track faithfully", "sort of
    # sidechained"). Faithfulness wins: this bar draws from THIS bar's tatums, and
    # the per-role widening below is the only relief, used solely where the core
    # carries nothing for a demanded role.

    # slot i plays tatum (start + i) and nothing else — the passage in order
    slot_pin = {}
    for j, g in enumerate(core_groups):
        slot_pin[j] = tuple(int(slices[i][2]) for i in g)

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
    return {"core": core, "widened": tuple(widened), "exhausted": False,
            "slot_pin": slot_pin}


def bar_window_unit_ids(unit_ids: Sequence[int], bars_elapsed: int,
                        s_phase: int) -> Tuple[int, ...]:
    """Row-cut window kept for the fixtures that pin the pointer's forward walk
    on a flat id list (no span/role information available there). The live path
    uses ``bar_window`` above, which cuts by tatum and widens per role."""
    w = max(1, int(s_phase))
    start = max(0, int(bars_elapsed)) * w
    return tuple(int(u) for u in unit_ids[start:start + w])


def build_full_fence(track: int, unit_ids: Sequence[int], slot_pin=None):
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
                      unit_pin=(int(track), tuple(int(u) for u in unit_ids)),
                      slot_pin=slot_pin)
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


# --- THE BRIDGE (papers/PREREG-live-mode.md AMENDMENTS 1, 3, 4, 5, and the
# operator's 2026-08-14 REFRAME superseding B-2..B-5 of Amendment 5) ---------
#
# STRAIGHT play (above) is Train B2. This section is the bridge: the second
# click, while a track is already playing straight, no longer starts a fresh
# full fence at once.
#
# THE REFRAME (binding; supersedes the corridor/ratchet as the DEFAULT path):
# the transition already exists in the object — the succession bridge (the
# KL tether to the propagated past) IS the transition operator. A musical
# transition is the system relaxing between two basins at finite temperature,
# winding between the past tether and the destination pull as they trade
# dominance, finding the cheap crossing. That winding is the physics, not
# meander — so the default bridge RELEASES the wall, APPLIES the pull, and
# does NOT intervene:
#
#   B-1 RELEASE — the source fence's openness walks 1 -> 0 on the adopted
#       RegionSlew law (unchanged from the original brief). ``release_step``.
#   B-2 PULL — the destination's stored column-share character latches as a
#       COLUMN lean on the EXISTING tilt jack (the region-tilt lane every
#       other view already drives through ``StreamPlayer.set_region`` / the
#       ONE ``_tilt_for(u)`` — I-1), sigma-clamped (the panel's own
#       ``clamp_region`` envelope) and slewed in (the SAME adopted law).
#       Nothing else is emitted: no clamp, no second channel.
#       ``pull_target`` / ``pull_step``.
#   B-3 TRAVERSE — once released (openness reaches 0) there is NO further
#       restriction: no corridor, no ratchet, no monotonicity requirement, no
#       profile-space arrival test. The path is whatever the tether makes
#       cheap given the committed past; excursions and back-and-forth are
#       EXPECTED and are never suppressed or smoothed.
#   B-4 ARRIVAL IS OBSERVED, NOT MEASURED — the destination fence closes when
#       the casting is ALREADY drawing predominantly from the destination
#       track: placement share >= ARRIVAL_SHARE sustained over ARRIVAL_BARS
#       consecutive bars, both REGISTERED verbatim, never per-corpus tuned.
#       ``dest_share`` / ``arrival_reached``.
#   B-5 STALL — share never rises: rendered honestly by the view (its own
#       copy/treatment), never a forced/faked arrival and never a timeout.
#   B-6 TEMPERATURE is the character knob already in the object (documented,
#       not built): cold -> direct crossing, few excursions; hot -> wider
#       excursions, more surprising connective material. No new parameter.
#   B-7 The profile-distance floor (``measure_floor``, the L2-column-share
#       wobble) is RETIRED from the arrival test — the corpus's own measured
#       diameter (~0.25 on the one fixture measured) covers too much of the
#       space (A5.2) to type as a reliable "have we arrived" signal. It is
#       kept as a DIAGNOSTIC readout only (reported, never gating).
#
# ONE METRIC FOR THE DIAGNOSTIC (Amendment 5 / A5.2, kept for the report):
# ``column_shares``/``char_gap``/``stored_character`` still compute the L2
# distance between COLUMN-SHARE vectors — an M-length vector that sums to 1 —
# so "achieved" and "target" live in the same space. This machinery now feeds
# the report's gap trajectory ONLY; it is never read by the arrival decision.
#
# THE RATCHET/CORRIDOR (Amendment 3) IS KEPT BUT DORMANT, FLAGGED, NON-
# DEFAULT (R-5): a measurement instrument for A/B comparison, never wired
# into ``engine_bridge.StreamPlayer``'s default bridge path. See the section
# below headed "RATCHET CORRIDOR — FLAGGED, NON-DEFAULT".
#
# THE MODE COMPUTES, THE CARRIER CARRIES (mirrors LM-4/BR-1): every function
# below is a PURE reduction over data already on hand (stored slices, or
# already-produced telemetry) or over its own small dict of state — none of
# it touches settlement/F/render, and the per-bar clamp it hands the writer
# is built through the SAME single construction point (clamp0) straight play
# already uses. No schedule/corridor/easing/monotonicity logic exists in
# architecture-v6/ets (BR-1; see cloud/tests/test_live_bridge.py's static
# scan).

from math import sqrt


def column_shares(track_role_map: Optional[Mapping], M: int) -> Tuple[float, ...]:
    """The ACHIEVED column-share vector: the SAME reduction the FE's role strip
    reads (``fieldColShares`` in static/index.html) over the SAME telemetry
    (``StreamPlayer.telemetry["nowplaying_track_role"]``, keys ``"tid,k"``).
    Sums placement mass by role k across every track, then normalizes to a
    share (sums to 1). An empty/all-zero map ⇒ an honest all-zero vector (no
    invented uniform fallback) — mirrors ``fieldColShares``'s own ``tot>0``
    guard exactly."""
    M = int(M)
    glow = [0.0] * M
    tot = 0.0
    for key, v in (track_role_map or {}).items():
        try:
            k = int(str(key).split(",")[1])
        except (ValueError, IndexError):
            continue
        v = float(v)
        if 0 <= k < M:
            glow[k] += v
            tot += v
    if tot <= 0.0:
        return tuple(0.0 for _ in range(M))
    return tuple(g / tot for g in glow)


def char_gap(a: Sequence[float], b: Sequence[float]) -> float:
    """L2 distance between two column-share vectors — the ONE metric (Amendment
    5): every arrival/corridor comparison in this module goes through this
    single function, so achieved and target are never compared in mismatched
    spaces."""
    return sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def stored_character(slices: Sequence[Sequence], t: float, M: int) -> Tuple[float, ...]:
    """The TARGET column-share vector for a destination click (track, t): the
    mass-weighted mixture of the STORED role indicator over the slice(s)
    whose span contains t — server-side mirror of static/index.html's
    ``fieldScrubWeights`` (WS-1/W-2), in the SAME column-share space
    ``column_shares`` produces (sums to 1). A click landing in a gap (no
    stored slice contains t) is honestly all-zero — no smoothing, no nearest-
    neighbour guess."""
    M = int(M)
    t = float(t)
    w = [0.0] * M
    tot = 0.0
    for row in slices:
        t0, t1 = float(row[0]), float(row[1])
        if not (t0 <= t < t1):
            continue
        m = float(row[3])
        q = row[4] if len(row) > 4 else ()
        for r in range(min(M, len(q))):
            v = m * float(q[r])
            w[r] += v
            tot += v
    if tot <= 0.0:
        return tuple(0.0 for _ in range(M))
    return tuple(x / tot for x in w)


def measure_floor(history: Sequence[Sequence[float]]) -> Optional[dict]:
    """The MEASURED noise floor (Amendment 1 A1.4 / Amendment 5 A5.2): mean +
    sd of the bar-to-bar L2 distance between consecutive achieved
    column-share vectors in ``history`` (time order). This is the SAME
    statistic A5.2 reports (mean, sd, floor=mean+sd) — computed HERE, at
    runtime, over THIS world's own recent telemetry, never hardcoded.

    B-7 (2026-08-14 reframe): this is now a DIAGNOSTIC readout ONLY — reported
    per journey (pinned at the journey's start, §A5.3 R-A), never consulted by
    the arrival decision (``arrival_reached`` below is the only gate).

    Returns ``None`` if fewer than 2 samples exist (a bar-to-bar wobble needs
    at least one consecutive pair) — an honest absence, never a fabricated
    floor from insufficient history."""
    hist = list(history)
    if len(hist) < 2:
        return None
    deltas = [char_gap(hist[i], hist[i + 1]) for i in range(len(hist) - 1)]
    n = len(deltas)
    mean = sum(deltas) / n
    var = sum((d - mean) ** 2 for d in deltas) / n     # population sd, matches A5.2's own report
    sd = sqrt(var)
    return {"mean": mean, "sd": sd, "floor": mean + sd, "n": n}


# =============================================================================
# DEFAULT BRIDGE v0 — release + pull, no intervention (the 2026-08-14 reframe)
# =============================================================================

def release_step(openness_cur: float) -> float:
    """One bar's RELEASE step (B-1 / A1.3, unchanged by the reframe): the
    source fence's openness follows ``ets.panel.envelope.RegionSlew`` — the
    REGISTERED slew law and its REGISTERED ``SLEW_MAX_STEP`` — ADOPTED at
    LIVE's own per-bar emit cadence rather than the panel's 30 Hz timer
    (A1.3's disclosed consequence: wall-clock release time differs; no new
    rate is invented). A fresh ``RegionSlew`` is used as a pure one-shot
    stepper (n=1, target 0) so this function stays a pure value->value call,
    while the underlying step math is the SAME imported law, not a
    reimplementation of it."""
    from ets.panel.envelope import RegionSlew, SLEW_MAX_STEP
    rs = RegionSlew(max_step=SLEW_MAX_STEP, n=1)
    rs.reset([float(openness_cur)])
    nxt = rs.step([0.0])
    return float(max(0.0, nxt[0]))


def release_clamp(openness_cur: float, source_track: int, pin_units=None, slot_pin=None):
    """B-1/B-3's ONLY carrier restriction: while ``openness_cur > 0`` a
    single-track fence to ``source_track`` at the CURRENT (decaying) openness
    — the source's own forward-walking window (``pin_units``/``slot_pin``,
    straight play's existing mechanism) continues exactly as it does in
    straight play. Once fully released (``openness_cur <= 0``) this returns
    ``None`` — clamp0's OWN neutral-carrier law (A-2/LM-1), not a special
    case invented here: the traverse (B-3) has no restriction beyond that, by
    construction (BR-1 — there is nothing left in this function to be a
    corridor/ratchet)."""
    if openness_cur <= 0.0:
        return None
    try:
        from ets.writer.clamp import clamp0
    except ImportError as exc:
        raise LiveCarrierUnavailable(
            "ets.writer.clamp.clamp0 is not importable yet: "
            f"{type(exc).__name__}: {exc}") from exc
    try:
        return clamp0(
            track_mask={int(source_track): float(openness_cur)},
            openness=float(openness_cur),
            unit_pin=((int(source_track), tuple(int(u) for u in pin_units))
                      if pin_units else None),
            slot_pin=slot_pin)
    except Exception as exc:
        raise LiveCarrierUnavailable(
            f"clamp0(...) failed to construct the release fence: "
            f"{type(exc).__name__}: {exc}") from exc


def pull_target(stored_char: Sequence[float]) -> Tuple[float, ...]:
    """B-2's sigma-clamped latch: the destination's STORED column-share
    character, passed through the SAME safe-envelope wall
    (``ets.panel.envelope.clamp_region`` / ``SAFE_REGION_MAGNITUDE``) the
    panel's own region lane uses. A column-share vector's components already
    sum to <= 1 (never exceeding the cap on their own), so this is a genuine
    reuse of the registered wall, not a no-op dressed up as one — it is the
    SAME call, on the SAME cap, that would fire if a component ever did
    exceed it. Computed ONCE at click time and PINNED for the whole journey
    ("latches")."""
    from ets.panel.envelope import clamp_region
    return tuple(float(x) for x in clamp_region(stored_char))


def pull_step(cur_vec: Sequence[float], target_vec: Sequence[float]) -> Tuple[float, ...]:
    """One bar's SLEWED step of the latched region lean toward ``target_vec``
    — the SAME adopted ``RegionSlew`` law/constant as ``release_step``,
    applied here to the FULL region vector (length ``len(target_vec)``)
    instead of a single scalar. This is the ONLY lean the bridge ever emits
    (B-2: "nothing else is emitted") — it rides the EXISTING region-tilt lane
    (``StreamPlayer.set_region`` -> the ONE ``_tilt_for(u)``), never a second
    control channel."""
    n = len(target_vec)
    from ets.panel.envelope import RegionSlew, SLEW_MAX_STEP
    rs = RegionSlew(max_step=SLEW_MAX_STEP, n=n)
    rs.reset(list(cur_vec) if cur_vec is not None else [0.0] * n)
    return tuple(float(x) for x in rs.step(list(target_vec)))


# B-4's two REGISTERED constants (operator, 2026-08-14 reframe) — verbatim,
# never per-corpus tuned, never exposed as a UI knob.
# ARRIVAL IS SETTLING, NOT A TARGET (correction, 2026-08-14). The previous gate
# compared the destination share to 0.75 — a level nobody had measured or shown
# to be reachable, and the first real journey peaked at 0.63 against it. That was
# the same error as the retired profile-distance floor, in a different quantity.
# There is now NO TARGET ANYWHERE on the arrival path: the share is watched only
# through its HIGH-WATER DYNAMICS. When the pull stops producing new highs for a
# settling window, the system has settled into whatever basin it reached, and the
# fence closes THERE, at the share it actually attained.
#
# W IS DERIVED, NOT PICKED: it is the SAME bar count over which the world's
# wobble floor is measured (`StreamPlayer._METER_WINDOW`, the registered
# I-8 meter window). No other constant enters the bridge.

def settling(shares, window: int):
    """The ONE observation that ends every journey (A-2): has the destination
    share stopped setting new highs for `window` bars?

    Returns ``{"settled", "high", "bars_since_high", "attained"}``.

    * `settled` — no new high-water mark within the last `window` bars.
    * `high` — the high-water mark reached, reported never judged.
    * `attained` — the share at the moment of the observation: WHERE it landed,
      which is the whole result. A high attained share is the destination basin;
      a low one is the corpus's honest limit toward that destination. Both are
      the same event and neither is a success or a failure.

    Reversibility (A-3) is inherent: a new high resets `bars_since_high` to 0, so
    a journey that looks finished can find more road and continue.

    No level is compared against anything (A-5): the only comparison here is a
    share against the highest share THIS journey has itself produced."""
    h = [float(x) for x in (shares or ())]
    if not h:
        return {"settled": False, "high": 0.0, "bars_since_high": 0, "attained": 0.0}
    high = h[0]
    since = 0
    for x in h[1:]:
        if x > high:
            high = x
            since = 0
        else:
            since += 1
    w = max(1, int(window))
    return {"settled": since >= w, "high": high,
            "bars_since_high": since, "attained": h[-1]}


def settled_render(track_name, attained: float) -> str:
    """End-of-journey copy (A-5): descriptive, never success/failure, never the
    word stalled. It reports WHERE the journey settled, because where it settled
    is the result."""
    return "settled — drawing %d%% from %s" % (round(100.0 * float(attained)),
                                               track_name)


# =============================================================================
# RATCHET CORRIDOR — FLAGGED, NON-DEFAULT, MEASUREMENT-ONLY (Amendment 3 R-5)
# =============================================================================
# The 2026-08-14 reframe retires the corridor as the DEFAULT bridge mechanism
# (BR-1: the default path above has no schedule/corridor/easing/monotonicity
# logic at all). Amendment 3 R-5 keeps a ratcheted-corridor alternative
# available "as a registered mode flag for comparison/measurement, not
# exposed in UI v0" — this section IS that flag: a complete, independently
# testable implementation that NOTHING in ``engine_bridge.StreamPlayer``'s
# default bridge path calls (see cloud/tests/test_live_bridge.py's
# ``test_br1_default_engine_bridge_path_never_calls_the_ratchet`` static
# scan). It exists for an explicit, opt-in A/B run, never for a listener.
#
# It also demonstrates WHY B-7 retired the profile-distance floor from the
# arrival test (A5.2): ``corridor_mask`` below can legitimately compute an
# EMPTY admissible set on bar 1 of a corridor phase (the blended ACHIEVED
# telemetry can sit closer to target than any SINGLE track's own static
# character), which is exactly the honest-stall risk the reframe's B-4
# (observed placement share, no profile distance) sidesteps by construction.

def track_character(slices: Sequence[Sequence], M: int) -> Tuple[float, ...]:
    """A TRACK'S OWN static column-share vector: the SAME mass-weighted q
    reduction as ``stored_character``, but over the WHOLE track's stored
    slices rather than one clicked window — the corridor's per-track ranking
    input (a buildable proxy for "material whose [own] character" — computed
    once from stored data, never a prediction of a future settlement outcome,
    which is not knowable before the draw). DORMANT: only the ratchet
    functions below call this."""
    M = int(M)
    w = [0.0] * M
    tot = 0.0
    for row in slices:
        m = float(row[3])
        q = row[4] if len(row) > 4 else ()
        for r in range(min(M, len(q))):
            v = m * float(q[r])
            w[r] += v
            tot += v
    if tot <= 0.0:
        return tuple(0.0 for _ in range(M))
    return tuple(x / tot for x in w)


def corridor_mask(track_chars: Mapping[int, Sequence[float]], target: Sequence[float],
                  best_gap: float, floor: float,
                  prev_mask: Optional[Mapping[int, float]]) -> dict:
    """R-1/R-3 — one bar's admissible-TRACK set: every track whose OWN static
    column-share character (``track_chars``) sits within ``best_gap + floor``
    of ``target``, each admitted at mask value 1.0 (a genuine binary hard
    set — Amendment 4's hard fence, not a soft ring).

    R-3 NO-SPLICE: if that set is EMPTY (no road within the current corridor)
    the corridor "simply stops tightening" — ``prev_mask`` is returned
    UNCHANGED rather than collapsed to nothing. DORMANT (see section header)."""
    bound = float(best_gap) + float(floor)
    admissible = {int(tid): 1.0 for tid, ch in track_chars.items()
                 if char_gap(ch, target) <= bound}
    if admissible:
        return admissible
    return dict(prev_mask) if prev_mask else {}


def ratchet_bridge_step(state: dict, achieved: Sequence[float]) -> dict:
    """ONE bar's pure state transition for the FLAGGED ratchet corridor
    (release then corridor phase). Never mutates ``state``; returns a NEW
    dict. DORMANT (see section header) — kept for A/B measurement only.

    ``achieved`` is this bar's measured column-share vector. R-2: ``best_gap``
    moves ONLY from this achieved sample, monotone non-increasing, NEVER from
    elapsed bars or a clock — repeated calls with the SAME ``achieved``
    (frozen telemetry) leave ``best_gap``/the corridor mask BYTE-IDENTICAL
    (RG-1), by construction: nothing here reads a bar counter or wall clock.

    Fields consumed/produced in ``state``: target, floor (pinned), best_gap,
    phase ("release"|"corridor"), openness_cur, track_chars, mask (current
    admissible set), stalled, arrived, gap (last-measured, diagnostic)."""
    st = dict(state)
    g = char_gap(achieved, st["target"])
    st["gap"] = g
    prev_best = st.get("best_gap")
    st["best_gap"] = g if prev_best is None else min(float(prev_best), g)
    st["arrived"] = bool(g < float(st["floor"]))

    if st["phase"] == "release":
        nxt = release_step(st["openness_cur"])
        st["openness_cur"] = nxt
        if nxt <= 0.0:
            st["phase"] = "corridor"

    if st["phase"] == "corridor":
        prev_mask = st.get("mask")
        new_mask = corridor_mask(st["track_chars"], st["target"], st["best_gap"],
                                 st["floor"], prev_mask)
        # R-3: "stalled" iff the FRESH computation this bar found no road (the
        # corridor had to fall back to the frozen prior mask) — never sticky
        # past a bar that genuinely widens again.
        fresh = corridor_mask(st["track_chars"], st["target"], st["best_gap"],
                              st["floor"], None)
        st["stalled"] = (not fresh) and bool(prev_mask)
        st["mask"] = new_mask
    return st


def ratchet_bridge_clamp(state: dict, source_track: int, pin_units=None, slot_pin=None):
    """Build one bar's ClampTerms from ratchet ``state`` (release or corridor
    phase). Lazy-imports ``clamp0`` exactly like ``release_clamp``; raises
    ``LiveCarrierUnavailable`` under the same conditions. DORMANT (see
    section header) — kept for A/B measurement only."""
    try:
        from ets.writer.clamp import clamp0
    except ImportError as exc:
        raise LiveCarrierUnavailable(
            "ets.writer.clamp.clamp0 is not importable yet: "
            f"{type(exc).__name__}: {exc}") from exc
    try:
        if state["phase"] == "release":
            return clamp0(
                track_mask={int(source_track): float(state["openness_cur"])},
                openness=float(state["openness_cur"]),
                unit_pin=((int(source_track), tuple(int(u) for u in pin_units))
                          if pin_units else None),
                slot_pin=slot_pin)
        mask = state.get("mask") or {}
        return clamp0(track_mask={int(t): 1.0 for t in mask}, openness=1.0)
    except Exception as exc:
        raise LiveCarrierUnavailable(
            f"clamp0(...) failed to construct the ratchet bridge fence: "
            f"{type(exc).__name__}: {exc}") from exc


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
