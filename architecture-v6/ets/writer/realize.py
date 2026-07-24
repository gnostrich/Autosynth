"""Realization: the settled tape occupancy -> the render's ``Schedule`` (spec §11
contract), with NO decoder and NO static keymap (connector: THE TAPE PORT).

The settlement produced ``O_tape : (M, S_out)`` — role occupancy per output slot.
Realization reads that coupling OUT as unit->slot placements. Two pieces:

  1. The ROLE MATERIALIZATION INDEX (built once, settlement-independent): for each
     anchor role k and band b, a representative REAL source unit (track, unit).
     This is "what role k sounds like in band b" — the analogue of the render
     materializing a source unit from its identity. It is a READ of the frozen
     world (each track's coupling to the shared anchors); it grants the tape ZERO
     structural authority and spawns nothing (connector NO SELF-INGESTION).

  2. The PER-SLOT PLACEMENT: for each output slot, the SETTLED column O_tape[:,s]
     (with the frozen band gains B) decides WHICH roles sound in WHICH bands here,
     HOW LOUD (each placement carries its cell's settled mass), and thus which
     real unit is laid. This is decided by the settlement, per slot — never a
     fixed table (connector NO STATIC KEYMAP). Change the anchors or LAMBDA
     (step d) or, later, the tilt, and O_tape changes, so the placements change.
     The choice of unit is a WRITER decision (spec §8 temperature lives in the
     writer); the render only applies it (I-11). There is NO threshold anywhere:
     every band the settlement put energy into sounds, at its settled mass — the
     continuous settled field reaches the tape untruncated (registry finding
     writer-settled-field-truncation; I-15 pattern class).

Clamped cells (I-7) pass through verbatim: a ``unit_demands`` clamp forces its
exact unit at its slot; a ``role_columns`` clamp already shaped O_tape and thus
its realization. There is no exception path — a clamp is just a cell.

The emitted gauge is IDENTITY (u=0, lanes constant): one section, no transpose,
no phase shift, unit gauge loudness. Loudness STRUCTURE is not gauge: it rides on
each placement as its settled mass (settlement output; see ``realize``). The
tape's coupling IS the provenance record (connector (i)) — the render then
discharges I-12 sample-by-sample.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple
import numpy as np

from ..functional import f as ff
from ..functional import solver as sv
from ..render.schedule import Schedule, Section, IDENTITY, PLACEMENT_DTYPE
from .tilt import fiber_choice_logits as fiber_logits


# ---- role materialization index -------------------------------------------

def _track_membership(fstate, proto, n_settle: int = 4) -> np.ndarray:
    """Row-normalized coupling of ONE track's prototypes to the FROZEN anchors.

    Settles just this track's coupling in the frozen anchor field (the same
    ``solver.update_pi`` I-projection, anchors held fixed). Returns g:(K, M) with
    rows summing to 1 — prototype k's membership across anchors. Cross-track
    traffic factors through the shared anchors only (I-2)."""
    M = fstate.a.shape[0]
    K = proto.mass.shape[0]
    st = replace(fstate, pis=[np.outer(proto.mass, fstate.a)])
    for _ in range(n_settle):
        st = sv.update_pi(st, [proto])
    g = st.pis[0]
    g = g / (g.sum(1, keepdims=True) + 1e-12)
    return g


@dataclass
class RealizationIndex:
    """(anchor k, band b) -> representative real source unit (track_id, unit_id),
    plus the SOURCE-RUN structure the unit-successor T4 threads at write time
    (spec §5 rev-r1: run-continuation is a fiber term).

    successor : (track_id, unit_id) -> the source-consecutive real unit in the SAME
                band of the same track (the real run one step on), or absent at a
                track/band boundary. Threading it makes the tape PLAY real runs
                rather than re-lay one fixed unit per role every bar.
    unit_role : (track_id, unit_id) -> the unit's dominant anchor role.
    candidates: (anchor k, band b) -> [(track_id, unit_id, intrinsic_phase)] real
                units of role k in band b, used to SEED a new run (phase-matched).
    These carry defaults so a minimal index (unit_of only) still realizes — with no
    runs available the writer falls back to the representative unit (old behavior)."""
    unit_of: Dict[Tuple[int, int], Tuple[int, int]]
    role_track: Dict[int, int]     # anchor k -> the track that best carries it
    M: int
    n_bands: int
    successor: Dict[Tuple[int, int], Tuple[int, int]] = field(default_factory=dict)
    unit_role: Dict[Tuple[int, int], int] = field(default_factory=dict)
    candidates: Dict[Tuple[int, int], list] = field(default_factory=dict)
    unit_phase: Dict[Tuple[int, int], float] = field(default_factory=dict)


def build_index(fstate, protos, tracks) -> RealizationIndex:
    """Build the role materialization index from the frozen world.

    For each (anchor k, band b): the (track, prototype) that best carries role k
    AND has real band-b material — scored by ``membership_to_k * band_affinity_b``.
    Because different tracks are strong in different bands, this spreads the
    materialization across the corpus (a role's low end may come from one track,
    its top end from another) rather than collapsing to a single track. Then the
    concrete unit is the real band-b unit in that track whose timbre is closest to
    the prototype's centroid (salience-weighted tie-break). Choices here are WRITER
    role-materialization (allowed); the render only applies (I-11)."""
    M = int(fstate.a.shape[0])
    n_bands = int(fstate.B.shape[1])

    # membership of every prototype (across tracks) to every anchor, and each
    # prototype's per-band affinity (band_profile normalized by its own mass).
    memb = [_track_membership(fstate, P) for P in protos]     # list of (K_t, M)
    band_aff = []
    for P in protos:
        m = P.mass[:, None] + 1e-12
        band_aff.append(P.band_profile / m)                   # (K_t, n_bands), in [0,1]

    unit_of: Dict[Tuple[int, int], Tuple[int, int]] = {}
    role_track: Dict[int, int] = {}
    role_track_votes = {k: {} for k in range(M)}
    for k in range(M):
        for b in range(n_bands):
            best_ti, best_pi, best_val = 0, 0, -np.inf
            for ti, (g, ba) in enumerate(zip(memb, band_aff)):
                score = g[:, k] * (ba[:, b] + 1e-6)           # role AND band material
                pj = int(np.argmax(score))
                if score[pj] > best_val:
                    best_ti, best_pi, best_val = ti, pj, float(score[pj])
            P = protos[best_ti]
            tr = tracks[best_ti]
            role_track_votes[k][int(tr.track_id)] = \
                role_track_votes[k].get(int(tr.track_id), 0) + 1

            centroid = P.timbre[best_pi]                       # (4,) role timbre
            u = tr.units
            desc = tr.C_timbre.desc                            # (n,4) standardized
            masses = np.asarray(tr.masses, float)
            in_band = np.where(u["band"] == b)[0]
            if in_band.size == 0:
                pick = int(np.argmax(masses))                 # unreachable in practice
            else:
                d = np.linalg.norm(desc[in_band] - centroid[None, :], axis=1)
                d = d / (masses[in_band] + 1e-9)              # prefer salient units
                pick = int(in_band[int(np.argmin(d))])
            unit_of[(k, b)] = (int(tr.track_id), int(u["unit_id"][pick]))
    for k in range(M):
        role_track[k] = int(max(role_track_votes[k], key=role_track_votes[k].get))

    # ---- source-run structure the unit-successor T4 threads (spec §5 rev-r1) ----
    # successor: within each track+band, the source-consecutive real unit (a real
    # run one step on). unit_role: each unit's dominant anchor (nearest prototype in
    # timbre -> that prototype's anchor membership). candidates[(k,b)]: real role-k,
    # band-b units with their intrinsic (arrangement == source) phase, to seed runs.
    successor: Dict[Tuple[int, int], Tuple[int, int]] = {}
    unit_role: Dict[Tuple[int, int], int] = {}
    unit_phase: Dict[Tuple[int, int], float] = {}
    candidates: Dict[Tuple[int, int], list] = {(k, b): [] for k in range(M)
                                               for b in range(n_bands)}
    for ti, (P, tr) in enumerate(zip(protos, tracks)):
        u = tr.units
        tid = int(tr.track_id)
        desc = tr.C_timbre.desc                                # (n,4)
        g = memb[ti]                                           # (K,M) membership
        # nearest prototype per unit (timbre), then its dominant anchor
        dp = np.linalg.norm(desc[:, None, :] - P.timbre[None, :, :], axis=2)
        proto_of = dp.argmin(1)
        role_of = g.argmax(1)[proto_of]                       # (n,) unit -> anchor
        band = u["band"].astype(int)
        uid = u["unit_id"].astype(int)
        phase = u["phase"].astype(float)
        src = tr.provenance_index["src_start"].astype(np.int64)
        for j in range(len(uid)):
            key = (tid, int(uid[j]))
            unit_role[key] = int(role_of[j])
            unit_phase[key] = float(phase[j])
            candidates[(int(role_of[j]), int(band[j]))].append(
                (tid, int(uid[j]), float(phase[j])))
        # source-successor within each band (by source order)
        for b in np.unique(band):
            idx = np.where(band == b)[0]
            srt = idx[np.argsort(src[idx])]
            for a, c in zip(srt[:-1], srt[1:]):
                successor[(tid, int(uid[a]))] = (tid, int(uid[c]))
    # total deterministic order on each pool: (intrinsic phase, track, unit) —
    # a fixed enumeration of the choice set, NOT a preference (the choice is
    # made by the fiber measure in FiberThreader).
    for key in candidates:
        candidates[key].sort(key=lambda z: (z[2], z[0], z[1]))
    return RealizationIndex(unit_of=unit_of, role_track=role_track,
                            M=M, n_bands=n_bands, successor=successor,
                            unit_role=unit_role, candidates=candidates,
                            unit_phase=unit_phase)


# ---- implementation selection for the fiber choice (NO semantic content) ----
#
# The per-(slot, band) fiber choice below has TWO implementations of the SAME
# mathematics: `_choose_original` (the reference, kept verbatim) and
# `_choose_fast` (the same expressions evaluated on precomputed numpy arrays
# instead of per-candidate Python loops). They are not alternatives in any
# musical sense — they are proven BIT-IDENTICAL (identical candidate order,
# identical energies, identical reuse weights, identical field addends,
# identical rng consumption, identical argmax), so which one runs is invisible
# to the tape. `ETS_FAST_REALIZE=0|false|off` selects the reference path at CALL
# time (no rebuild, no restart of anything but the process's env read); the
# default is the fast one. Gates: cloud/tools/fast_realize_verify.py (G1 row
# identity, G2 PCM byte identity) and cloud/tests/test_fast_realize.py.
_FAST_OFF = ("0", "false", "off", "no")


def fast_realize_enabled() -> bool:
    """True iff the vectorized fiber-choice implementation is selected (default).

    Read from the environment at call time so the kill-switch is live for a
    running process's next choice; it selects an IMPLEMENTATION only."""
    return os.environ.get("ETS_FAST_REALIZE", "1").strip().lower() not in _FAST_OFF


@dataclass
class _Pool:
    """The frozen (role k, band b) candidate pool, in ARRAY form.

    Exactly ``index.candidates[(k, b)]`` in its fixed enumeration order — the
    same order `_choose_original` builds its `choices` list in — with the three
    per-candidate reads that loop performs hoisted into arrays:

      keys   : the (track_id, unit_id) of each candidate — what a choice
               returns, and the field-bias grains' lookup keys
      phase  : each candidate's intrinsic phase (``index.unit_phase``)
      missing: positions with NO intrinsic phase — `_choose_original` falls back
               to the SLOT phase there, which is psi-dependent, so those entries
               are filled per call (empty for any index built by ``build_index``)
      gidx   : each candidate's row in the recency mirror ``_last_bar``
      cont0/cont1: the continuation indicator of this choice set with (cont1) and
               without (cont0) a run-continuation head — constants of the pool

    Derived ONLY from the frozen index (never from elapsed time): a memo of the
    world, not writer state (I-8; see FiberThreader._fast_tables)."""
    keys: List[Tuple[int, int]]
    phase: np.ndarray
    missing: np.ndarray
    gidx: np.ndarray
    cont0: np.ndarray
    cont1: np.ndarray
    # the field-bias addends of THIS pool under the field map of the bar being
    # written: (that map object, the vector). One slot — the live tilt is
    # rebound per bar, so at most the current bar's map is referenced.
    cbias: Optional[Tuple[object, np.ndarray]] = None

    @property
    def size(self) -> int:
        return len(self.keys)


# Recency mirror sentinel for "this unit was never committed": a bar so far in
# the future that bar − NEVER is negative, hence Δ < 1, hence weight 0 — the
# `last is None` branch of `_reuse`, expressed in the same comparison as the
# Δ < 1 branch (one mask, no second condition).
_NEVER = 1 << 62


def _frozen(a: np.ndarray) -> np.ndarray:
    """Mark a cached array read-only: caches are inputs to the choice measure,
    never scratch (nothing downstream of `fiber_choice_logits` writes them)."""
    a.flags.writeable = False
    return a


# ---- the fiber block: one threading mechanism for batch AND stream ---------

class FiberThreader:
    """Realizes the fiber block slot-by-slot under the Layer-0 measure.

    At each (slot, band) with settled energy the choice set is
        { continue the band's run (source successor of its last unit) }
        ∪ { seed candidates: real units of the settled role in this band }.
    Every choice is scored by F's OWN fiber terms (f.unit_phase_charge_at for
    T1's phase-displacement integrand, f.LAMBDA['T4'] for the run-continuation
    reward — the term math lives in f.py, single source), and the selection is
    a draw from the Layer-0 tilted measure

        p(c) ∝ exp( −E_F(c)/T_s + λ_cont·1[cont](c) + λ_novelty·reuse(c) )

    (ets.writer.tilt.fiber_choice_logits). With ``tilt=None`` and ``rng=None``
    this reduces to the deterministic minimum-F choice (the batch T→0 mode);
    with an rng it is an exact categorical draw via Gumbel-max (deterministic
    given the seed — spec §8 TEMPERATURE = sampling looseness in the WRITER;
    the render never samples, I-11).

    This object carries the fiber STATE (runs in flight, last committed use per
    unit) — the run/recency half of the working tape (spec §7). Its size is
    bounded by material heard (≤ corpus units + bands), never by elapsed time
    (I-8; see StreamWriter.state_size).

    Note (declared, carried over): this remains a per-slot sequential
    materialization of the fiber block, not a certified joint fiber settlement
    (REGISTRY 'realize-greedy-fiber'). What CHANGED here: the choice energy is
    now F's own T1p/T4 (the underived min(8,·) seed window and its rotation
    cursor are DELETED — the full candidate pool is scored), and the Layer-0
    tilt/temperature act on the same measure instead of beside it.
    """

    def __init__(self, index: RealizationIndex, fstate, s_phase: int,
                 tilt=None, rng=None):
        self.index = index
        self.B = fstate.B
        self.s_phase = int(s_phase)
        self.tilt = tilt
        self.rng = rng
        self.run_head: Dict[int, Tuple[int, int]] = {}    # band -> unit in flight
        self.last_used: Dict[Tuple[int, int], int] = {}   # unit -> last COMMITTED bar
        self._pending: Dict[Tuple[int, int], int] = {}    # placed this (uncommitted) bar
        # --- fast-path memos (implementation only; see fast_realize_enabled) ---
        # `_unit_row` + `_last_bar` are an ARRAY MIRROR of `last_used` (which is
        # written in exactly one place, commit_bar); `_pools` and `_energy` memo
        # pure functions of the FROZEN index (and, for `_energy`, of the grid's
        # finitely many slot phases). None of them is new working state: their
        # size is bounded by the material + the grid, never by elapsed time
        # (I-8; cloud/tests/test_fast_realize.py::test_fast_memos_are_bounded).
        self._unit_row: Optional[Dict[Tuple[int, int], int]] = None
        self._last_bar: Optional[np.ndarray] = None
        self._pools: Dict[Tuple[int, int], _Pool] = {}
        self._energy: Dict[Tuple[int, int, float], np.ndarray] = {}

    # -- fiber state (the run/recency half of the working tape, spec §7) ------
    def state_size(self) -> int:
        return len(self.run_head) + len(self.last_used) + len(self._pending)

    def commit_bar(self, bar: int) -> None:
        """Commit the bar's placements into the recency state (the committed
        tape is what φ_novelty reads — connector Layer 0)."""
        for key, b in self._pending.items():
            self.last_used[key] = b
            if self._unit_row is not None:                # keep the mirror exact
                row = self._unit_row.get(key)             # (a key with no row is
                if row is not None:                       # in no pool, so it is
                    self._last_bar[row] = b               # never read back)
        self._pending.clear()

    def _reuse(self, key: Tuple[int, int], bar: int) -> float:
        """Recency weight r(Δ)=1/Δ vs the COMMITTED tape (see phi.py note)."""
        last = self.last_used.get(key)
        if last is None or bar - last < 1:
            return 0.0
        return 1.0 / float(bar - last)

    def recency_snapshot(self, keys, bar: int) -> Dict[Tuple[int, int], int]:
        """Δbars since last committed use, for the given keys (φ input)."""
        out: Dict[Tuple[int, int], int] = {}
        for key in keys:
            last = self.last_used.get(key)
            if last is not None and bar - last >= 1:
                out[key] = bar - last
        return out

    def _choose(self, k: int, b: int, psi: float, bar: int):
        """One (slot, band) fiber choice. Returns ((tid, uid), is_continuation)
        or None if no material exists for (k, b).

        THE single fiber-choice entry point: both implementations live behind
        it, so every observer of the choice (and every caller) still sees
        exactly one `_choose` per (slot, band). Which implementation evaluates
        the measure is selected at call time by ``fast_realize_enabled()`` and
        is bit-identical either way (see that function's note)."""
        if fast_realize_enabled():
            return self._choose_fast(k, b, psi, bar)
        return self._choose_original(k, b, psi, bar)

    def _choose_original(self, k: int, b: int, psi: float, bar: int):
        """The reference implementation of the fiber choice — the measure
        written out candidate-by-candidate. Kept verbatim as the definition the
        vectorized path is verified against (ETS_FAST_REALIZE=0 runs it)."""
        idx = self.index
        choices: List[Tuple[int, int]] = []
        is_cont: List[bool] = []
        cur = self.run_head.get(b)
        nxt = idx.successor.get(cur) if cur is not None else None
        if nxt is not None:
            choices.append(nxt)
            is_cont.append(True)
        for (tid, uid, _ph) in idx.candidates.get((k, b), ()):
            choices.append((int(tid), int(uid)))
            is_cont.append(False)
        if not choices:
            fallback = idx.unit_of.get((k, b))    # minimal index / degenerate
            return (fallback, False) if fallback is not None else None

        # F's own fiber energies (LAMBDA live; term math from f.py).
        phases = np.array([idx.unit_phase.get(c, psi) for c in choices])
        charge = ff.unit_phase_charge_at(phases, psi)
        cont = np.asarray(is_cont, float)
        energies = ff.LAMBDA["T1p"] * charge - ff.LAMBDA["T4"] * cont

        if self.tilt is None:
            logits = -energies                     # T→0 deterministic reduction
        else:
            reuse = np.array([self._reuse(c, bar) for c in choices])
            # SOFT multi-grain field lean (PREREG-field-bias-REV3 + track_role): each
            # candidate's addend is the SUM of its grains under tilt.channel_logbias —
            # the source TRACK (roll-up, c[0]=track_id), the UNIT (the ultimate
            # "channel", c[1]=unit_id), and the (TRACK, slot-ROLE) SUB-TRACK cell
            # (c[0], k) where k is THIS slot's settled role (the _choose arg that made
            # this the "role-k units in band b" set — same k from place_slot). All
            # three VARY across this choice set (track/unit vary per candidate; (track,
            # k) varies via track, k fixed), so all three steer. A PURE role is fixed
            # across the set and would be a softmax constant that cancels — it is NOT a
            # grain (the measured role wall); (track, role) dodges it via the track key.
            # None/empty at every grain ⇒ no addend (byte-identical); the array length
            # matches `choices`, so the rng draw size below is unchanged — a zero field
            # never perturbs the stream.
            fb = getattr(self.tilt, "channel_logbias", None)
            cbias = None
            if fb:
                tw = fb.get("track") or {}
                uw = fb.get("unit") or {}
                trw = fb.get("track_role") or {}
                if tw or uw or trw:
                    cbias = np.array([tw.get(int(c[0]), 0.0) + uw.get(int(c[1]), 0.0)
                                      + trw.get((int(c[0]), int(k)), 0.0)
                                      for c in choices])
            logits = fiber_logits(energies, cont, reuse, self.tilt,
                                  channel_bias=cbias)

        if self.rng is None:
            j = int(np.argmax(logits))             # first-max: fixed enumeration order
        else:
            gumbel = -np.log(-np.log(self.rng.uniform(size=len(logits))))
            j = int(np.argmax(logits + gumbel))    # exact categorical draw
        return (choices[j], bool(is_cont[j]))

    # -- the same measure, evaluated on arrays instead of per candidate -------
    #
    # Term by term this is `_choose_original` with its four per-candidate Python
    # loops (phase read, reuse lookup, field-grain lookup, choice-tuple build)
    # replaced by array reads over the SAME candidate order. Every arithmetic
    # expression is kept in its original form and order: the choice-set arrays
    # are elementwise-identical to the lists they replace, and the reductions
    # (argmax, and the rng draw's size and order) are untouched — so the logits,
    # the consumed random stream and the index picked are bit-identical.

    def _fast_tables(self) -> None:
        """Build, once, the array mirror of the recency state `last_used`.

        Every real unit of the frozen world gets a row; the mirror is seeded
        from the recency committed SO FAR and thereafter maintained by the one
        writer of `last_used` (commit_bar). Bounded by corpus units."""
        if self._unit_row is not None:
            return
        rows: Dict[Tuple[int, int], int] = {}
        for pool in self.index.candidates.values():
            for (tid, uid, _ph) in pool:
                key = (int(tid), int(uid))
                if key not in rows:
                    rows[key] = len(rows)
        for succ in self.index.successor.values():
            key = (int(succ[0]), int(succ[1]))
            if key not in rows:
                rows[key] = len(rows)
        last = np.full(len(rows), _NEVER, dtype=np.int64)
        for key, bar in self.last_used.items():
            row = rows.get(key)
            if row is not None:
                last[row] = int(bar)
        self._unit_row = rows
        self._last_bar = last

    def _pool_of(self, k: int, b: int) -> _Pool:
        """The (k, b) candidate pool in array form (built once per pool)."""
        pool = self._pools.get((k, b))
        if pool is not None:
            return pool
        idx = self.index
        cands = idx.candidates.get((k, b), ())
        keys = [(int(tid), int(uid)) for (tid, uid, _ph) in cands]
        n = len(keys)
        phase = np.zeros(n)
        missing: List[int] = []
        for j, key in enumerate(keys):
            ph = idx.unit_phase.get(key)
            if ph is None:
                missing.append(j)                  # slot-phase fallback, per call
            else:
                phase[j] = float(ph)
        cont1 = np.zeros(n + 1)
        cont1[0] = 1.0                             # the run-continuation head
        pool = _Pool(
            keys=keys,
            phase=_frozen(phase),
            missing=np.array(missing, dtype=np.intp),
            gidx=np.array([self._unit_row[key] for key in keys], dtype=np.intp),
            cont0=_frozen(np.zeros(n)),
            cont1=_frozen(cont1),
        )
        self._pools[(k, b)] = pool
        return pool

    def _pool_energies(self, pool: _Pool, k: int, b: int, psi: float) -> np.ndarray:
        """F's fiber energies of the pool's candidates at slot phase psi.

        `ff.LAMBDA["T1p"] * charge - ff.LAMBDA["T4"] * cont` with cont = 0 (a
        seed candidate never continues a run) — the candidate block of
        `_choose_original`'s `energies`, elementwise identical to it. Memoized
        on (pool, slot phase): the grid has exactly `s_phase` slot phases, so
        this table is bounded by pools x s_phase (material x grid, not time)."""
        key = (k, b, psi)
        e = self._energy.get(key)
        if e is not None:
            return e
        phase = pool.phase
        if pool.missing.size:
            phase = phase.copy()
            phase[pool.missing] = psi              # `unit_phase.get(c, psi)`
        charge = ff.unit_phase_charge_at(phase, psi)
        e = _frozen(ff.LAMBDA["T1p"] * charge - ff.LAMBDA["T4"] * pool.cont0)
        self._energy[key] = e
        return e

    def _pool_cbias(self, pool: _Pool, k: int, fb, tw, uw, trw) -> np.ndarray:
        """The pool's field-bias addends β(c) = β_track + β_unit + β_(track,k).

        Same sum, same order, same grains as `_choose_original`; k is fixed
        across the pool (it IS the pool's role), so the whole vector is a
        function of (pool, the tilt's field map) and is memoized on that map
        object — recomputed exactly once per pool per rebound tilt."""
        cached = pool.cbias
        if cached is not None and cached[0] is fb:
            return cached[1]
        arr = _frozen(np.array(
            [tw.get(tid, 0.0) + uw.get(uid, 0.0) + trw.get((tid, k), 0.0)
             for (tid, uid) in pool.keys]))
        pool.cbias = (fb, arr)
        return arr

    def _choose_fast(self, k: int, b: int, psi: float, bar: int):
        """The vectorized fiber choice (see `_choose`; bit-identical to
        `_choose_original`)."""
        idx = self.index
        if self._unit_row is None:
            self._fast_tables()
        cur = self.run_head.get(b)
        nxt = idx.successor.get(cur) if cur is not None else None
        pool = self._pool_of(k, b)
        n = pool.size
        h = 1 if nxt is not None else 0            # the continuation head, if any
        if n + h == 0:
            fallback = idx.unit_of.get((k, b))     # minimal index / degenerate
            return (fallback, False) if fallback is not None else None

        # F's own fiber energies (LAMBDA live; term math from f.py).
        base = self._pool_energies(pool, k, b, psi)
        if h:
            energies = np.empty(n + 1)
            energies[0] = (ff.LAMBDA["T1p"]
                           * ff.unit_phase_charge_at(idx.unit_phase.get(nxt, psi), psi)
                           - ff.LAMBDA["T4"] * 1.0)
            energies[1:] = base
            cont = pool.cont1
        else:
            energies = base
            cont = pool.cont0

        if self.tilt is None:
            logits = -energies                     # T→0 deterministic reduction
        else:
            reuse = np.empty(n + h)
            if h:
                reuse[0] = self._reuse(nxt, bar)
            if n:
                delta = bar - self._last_bar[pool.gidx]
                # r(Δ)=1/Δ against the COMMITTED tape; never-used (Δ<0 by the
                # _NEVER sentinel) and same-bar (Δ<1) units weigh 0 — `_reuse`,
                # elementwise.
                reuse[h:] = np.where(delta >= 1,
                                     1.0 / np.maximum(delta, 1), 0.0)
            # SOFT multi-grain field lean: identical grains, sum and order to
            # `_choose_original` (see the note there); the array length matches
            # the choice set, so the rng draw size below is unchanged.
            fb = getattr(self.tilt, "channel_logbias", None)
            cbias = None
            if fb:
                tw = fb.get("track") or {}
                uw = fb.get("unit") or {}
                trw = fb.get("track_role") or {}
                if tw or uw or trw:
                    pc = self._pool_cbias(pool, k, fb, tw, uw, trw)
                    if h:
                        cbias = np.empty(n + 1)
                        cbias[0] = (tw.get(int(nxt[0]), 0.0) + uw.get(int(nxt[1]), 0.0)
                                    + trw.get((int(nxt[0]), int(k)), 0.0))
                        cbias[1:] = pc
                    else:
                        cbias = pc
            logits = fiber_logits(energies, cont, reuse, self.tilt,
                                  channel_bias=cbias)

        if self.rng is None:
            j = int(np.argmax(logits))             # first-max: fixed enumeration order
        else:
            gumbel = -np.log(-np.log(self.rng.uniform(size=len(logits))))
            j = int(np.argmax(logits + gumbel))    # exact categorical draw
        if h and j == 0:
            return (nxt, True)
        return (pool.keys[j - h], False)

    def place_slot(self, s: int, col: np.ndarray, clamp_unit=None):
        """Realize output slot ``s`` from its settled column ``col`` (M,).

        Returns (rows, continues): rows = [(slot, tid, uid, section, mass)],
        continues = [bool] per row (the φ_cont events). A unit-demand clamp
        (I-7) passes through verbatim with neutral mass 1.0."""
        bar = int(s) // self.s_phase
        if clamp_unit is not None:
            tid, uid, _b = clamp_unit
            key = (int(tid), int(uid))
            self._pending[key] = bar
            return [(int(s), int(tid), int(uid), 0, 1.0)], [False]

        B = self.B
        e = np.asarray(col, float) @ B                 # (n_bands,) settled energy
        psi = (int(s) % self.s_phase) / float(self.s_phase)
        rows: List[Tuple[int, int, int, int, float]] = []
        continues: List[bool] = []
        for b in range(B.shape[1]):
            if e[b] <= 0:
                continue                               # no settled energy: nothing
            k = int(np.argmax(col * B[:, b]))          # role carrying band b here
            got = self._choose(k, b, psi, bar)
            if got is None:
                continue
            (place, cont) = got
            self.run_head[b] = place
            self._pending[place] = bar
            # settled mass -> amplitude: sqrt(e[b]) conserves the slot's settled
            # mass sum_b e[b] as rendered energy (see realize docstring).
            rows.append((int(s), int(place[0]), int(place[1]), 0,
                         float(np.sqrt(e[b]))))
            continues.append(bool(cont))
        return rows, continues


# ---- settled occupancy -> Schedule ----------------------------------------

def realize(O: np.ndarray, tape, fstate, index: RealizationIndex
            ) -> Tuple[Schedule, dict]:
    """Turn the settled tape occupancy into a Schedule (unit->slot+mass + gauge).

    THE SETTLED FIELD IS CARRIED WHOLE — no threshold, no flat gain. At slot s
    the settlement routed energy e[b] = (O[:,s] @ B)[b] to band b; every band
    with e[b] > 0 places a unit, and the placement carries mass sqrt(e[b]).

    Mass derivation (conservation, no free constant). B's rows are simplex
    (frozen band gains sum to 1 per role), so the slot's settled mass is
    E_s = sum_b e[b] = sum_k O[k,s]. The render overlap-adds; band-disjoint
    units are energy-orthogonal, so the slot's rendered energy is
    sum_b mass_b^2 * (unit energy), with unit energies comparable by
    unitization. Requiring (i) band shares follow the settled field,
    mass_b^2 proportional to e[b]/E_s, and (ii) the slot total follow the
    settled slot mass, sum_b mass_b^2 = E_s, forces mass_b = sqrt(e[b])
    uniquely. Fewer active bands never get louder: one active band carrying
    all of E_s renders at energy E_s, the same total as E_s spread over
    eight — the flat-unit-gain behavior this replaces scaled with the COUNT
    of surviving bands, which was the deleted structure.

    A unit-demand clamp (I-7) passes through verbatim with neutral mass 1.0:
    the demand names an exact unit for the whole slot; its loudness is the
    demand's, not a settled (slot, band) cell's.
    """
    n_slots = int(tape.grid.n_slots)
    clamps = tape.clamps
    S_phase = int(tape.grid.s_phase)

    # unit-successor run-continuation (spec §5 rev-r1 T4, at write time): each band
    # carries a REAL source run; at each active slot the fiber measure chooses to
    # continue the source successor of its last unit or to seed a new run — the
    # choice scored by F's OWN fiber terms (FiberThreader; the term math lives in
    # f.py). This threads long real runs across bar boundaries, so bar N and bar
    # N+1 hold DIFFERENT real content even though the settled role occupancy O is
    # bar-periodic — the static bar-loop vanishes while groove (which roles/bands
    # sound where) stays stable. Choosing which unit continues a run is a WRITER
    # decision (spec §8); the render only applies it (I-11). Batch mode is the
    # deterministic T→0 reduction (tilt=None, rng=None); the streaming writer
    # drives this SAME mechanism with the Layer-0 tilt and temperature.
    threader = FiberThreader(index, fstate, S_phase)

    rows: List[Tuple[int, int, int, int, float]] = []
    bar_prev = 0
    for s in range(n_slots):
        bar = s // S_phase
        if bar != bar_prev:
            threader.commit_bar(bar_prev)                     # recency reads committed bars
            bar_prev = bar
        r, _cont = threader.place_slot(
            s, O[:, s], clamp_unit=clamps.unit_demands.get(s))
        rows.extend(r)
    threader.commit_bar(bar_prev)

    p = np.zeros(len(rows), dtype=PLACEMENT_DTYPE)
    for i, (s, tid, uid, sec, mass) in enumerate(rows):
        p[i]["out_slot"] = s
        p[i]["src_track"] = tid
        p[i]["src_unit"] = uid
        p[i]["section"] = sec
        p[i]["mass"] = mass

    sections = (Section(0, 0, n_slots, IDENTITY),)            # identity gauge (u=0)
    sched = Schedule(sr=int(tape.grid.sr),
                     slot_boundaries=tape.grid.slot_boundaries,
                     placements=p, sections=sections)
    meta = {
        "n_placements": int(len(rows)),
        "n_slots": n_slots,
        "n_tracks_used": int(len({r[1] for r in rows})),
        "clamped_unit_slots": sorted(clamps.unit_demands),
    }
    return sched, meta
