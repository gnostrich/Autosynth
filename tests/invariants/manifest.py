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


# --- source-level structural helpers (AST, so docstrings/comments that merely
#     NAME a forbidden concept are ignored — only real code identifiers count) --

def _code_identifiers(src: str) -> set:
    """Every identifier USED IN CODE (names, attributes, defs, args, kwargs).
    String literals and comments are excluded, so a docstring saying 'holonomy
    appears NOWHERE' does not trip a forbidden-token scan; a variable named
    `holonomy` does."""
    import ast
    idents = set()
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            idents.add(n.id)
        elif isinstance(n, ast.Attribute):
            idents.add(n.attr)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            idents.add(n.name)
        elif isinstance(n, ast.arg):
            idents.add(n.arg)
        elif isinstance(n, ast.keyword) and n.arg:
            idents.add(n.arg)
    return idents


def _forbidden_hits(src: str, tokens) -> list:
    """Forbidden tokens that appear as a substring of any CODE identifier."""
    idents = _code_identifiers(src)
    return sorted({t for t in tokens for i in idents if t in i.lower()})


def _module_src(mod) -> str:
    import inspect
    return inspect.getsource(mod)


# Forbidden identifier substrings per invariant.
_FORBID_I3 = ["pressure", "accumulator", "accum", "ema", "momentum",
              "velocity", "smoother", "running_"]
_FORBID_I4 = ["tether", "eta_kl", "kl_tether", "aux_loss", "auxloss",
              "second_objective", "trainloss", "training_loss"]
_FORBID_I5 = ["holonomy", "drift", "meter", "novelty", "saturation",
              "hankel", "eoc"]


def _check_i3() -> None:
    """I-3 no pressure accumulator / no duplicate smoothing mechanism. The anchor
    state carries ONLY support+mass; no accumulator/EMA/momentum field or code
    identifier exists in the functional, solver, or anchor modules."""
    from ets.functional import f as ff, solver as sv, anchors as an
    from ets.functional.f import FState

    # (a) the anchor/solver state has ONLY the allowed fields — no accumulator.
    allowed = {"D", "a", "B", "theta", "pis", "phase_off", "transpose"}
    fields = set(FState.__dataclass_fields__)
    assert fields <= allowed, f"FState carries non-allowed (accumulator?) state: {fields - allowed}"

    # (b) no accumulator/smoothing identifier in the code of any F-side module.
    for mod in (ff, sv, an):
        hits = _forbidden_hits(_module_src(mod), _FORBID_I3)
        assert not hits, f"I-3: accumulator/smoothing identifier in {mod.__name__}: {hits}"

    # (c) NON-VACUITY: the scanner actually bites on an accumulator pattern.
    assert _forbidden_hits("def step(g):\n    self.pressure_accum = self.pressure_accum + g\n",
                           _FORBID_I3), "I-3 scanner is vacuous"


def _check_i4() -> None:
    """I-4 one F: no training loss distinct from F; no eta-KL tether / second
    authority. The solver's accept/reject decision reads the single functional
    f.F and nothing else."""
    import ast
    from ets.functional import f as ff, solver as sv, anchors as an
    assert callable(ff.F), "the single objective f.F must exist"

    ssrc = _module_src(sv)
    # (a) no second-objective / tether identifier anywhere on the F side.
    for mod in (sv, an, ff):
        hits = _forbidden_hits(_module_src(mod), _FORBID_I4)
        assert not hits, f"I-4: second-objective identifier in {mod.__name__}: {hits}"

    # (b) STRUCTURAL: the acceptance scalar in batch_solve is produced by f.F and
    #     the accept guard compares those F values — no parallel objective.
    tree = ast.parse(ssrc)
    bs = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "batch_solve"), None)
    assert bs is not None, "batch_solve not found"
    f_assigned = set()      # variables assigned from a call to ff.F / f.F
    for n in ast.walk(bs):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            fn = n.value.func
            is_F = isinstance(fn, ast.Attribute) and fn.attr == "F"
            if is_F:
                for tgt in n.targets:
                    if isinstance(tgt, ast.Tuple):
                        for e in tgt.elts:
                            if isinstance(e, ast.Name):
                                f_assigned.add(e.id)
                    elif isinstance(tgt, ast.Name):
                        f_assigned.add(tgt.id)
    assert "F_cand" in f_assigned and "F_cur" in f_assigned, \
        "acceptance scalars F_cand/F_cur are not both produced by f.F"
    # the accept guard must be a comparison between those F values.
    guards = [n for n in ast.walk(bs) if isinstance(n, ast.Compare)]
    names_in_guards = {x.id for g in guards for x in ast.walk(g) if isinstance(x, ast.Name)}
    assert "F_cand" in names_in_guards and "F_cur" in names_in_guards, \
        "accept guard does not compare the F values"

    # (c) NON-VACUITY: the second-objective scanner bites.
    assert _forbidden_hits("aux = eta_kl_tether(x)\naccept = aux < 0\n",
                           _FORBID_I4), "I-4 scanner is vacuous"


def _check_i5() -> None:
    """I-5 meters/holonomy never in any objective/gradient/settlement decision.
    The functional module f.py contains NO holonomy/drift/meter/novelty/hankel/eoc
    identifier — those quantities are instruments (spec §9, I-14), never in F."""
    from ets.functional import f as ff
    hits = _forbidden_hits(_module_src(ff), _FORBID_I5)
    assert not hits, f"I-5: meter/holonomy identifier appears in F (f.py): {hits}"

    # NON-VACUITY: the scanner bites on a holonomy/meter term in an F-like source.
    bad = "def F(state):\n    return transport(state) + holonomy_drift(state)\n"
    assert _forbidden_hits(bad, _FORBID_I5), "I-5 scanner is vacuous"


_DECISION_NAMES = frozenset({
    "argmax", "argmin", "argsort", "argpartition", "partition",
    "sort", "sorted", "lexsort",
    "choice", "shuffle", "permutation", "sample", "multinomial",
    "rand", "randn", "randint", "random", "default_rng",
    "rank", "argwhere_best", "score",
})


def _decision_names_in_source(src: str) -> set:
    """AST-scan a module's source; return which decision identifiers it uses.

    Robust to comments/strings (those are ast.Constant, not Name/Attribute), so a
    module may *describe* argmax in prose without tripping. A genuine call like
    ``np.argmax(...)`` or ``random.choice(...)`` is caught."""
    import ast
    found = set()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _DECISION_NAMES:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in _DECISION_NAMES:
            found.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None)
            names = [mod] if mod else []
            names += [a.name for a in getattr(node, "names", [])]
            for nm in names:
                if nm and nm.split(".")[-1] == "random":
                    found.add("random")
    return found


def _mutant_render_source_that_chooses() -> str:
    """A render that MAKES A CHOICE — keeps only the loudest unit per slot. Used
    solely to prove the I-11 checks bite (structural + behavioral)."""
    return (
        "import numpy as np\n"
        "def render(schedule, sources):\n"
        "    n = int(schedule.slot_boundaries[-1])\n"
        "    audio = np.zeros(n)\n"
        "    P = schedule.placements\n"
        "    best = np.argmax([abs(sources.get(int(p['src_track']), int(p['src_unit'])).audio).sum() for p in P])\n"
        "    p = P[int(best)]\n"
        "    return audio, p\n"
    )


def _check_i11() -> None:
    """I-11: rendering applies, never chooses.

    Three teeth, each proven non-vacuous by construction:
      (A) STRUCTURAL — the render module carries no scoring/selection/sampling
          identifier (AST scan). Proven to bite against a choosing mutant.
      (B) DETERMINISM — same (schedule, sources) -> identical output, twice.
          Proven to bite against a nondeterministic reference.
      (C) ORDER-INDEPENDENCE — permuting the placement order leaves the output
          unchanged (overlap-add is commutative). A render that SELECTED (e.g.
          "keep the loudest, drop the rest") would depend on order; pure
          application does not. Proven to bite against the choosing mutant."""
    import inspect
    import numpy as np
    import ets.render.render as R
    import ets.render.schedule as SCH
    import ets.render.sources as SRC
    import ets.render.provenance as PRV
    from ets.render.schedule import Schedule, Section, Gauge, PLACEMENT_DTYPE
    from ets.render.sources import SourceUnit, SourceUnitBank
    from ets.render.render import render

    # (A) structural: the whole render package's active code is decision-free.
    for mod in (R, SCH, SRC, PRV):
        used = _decision_names_in_source(inspect.getsource(mod))
        assert not used, (
            f"{mod.__name__} uses decision primitive(s) {sorted(used)} — the "
            f"render path must apply, never choose (I-11)")
    # ...and the scanner BITES: the choosing mutant is flagged.
    mutant_used = _decision_names_in_source(_mutant_render_source_that_chooses())
    assert "argmax" in mutant_used, (
        "I-11 structural scan is vacuous: it did not flag an argmax-selecting render")

    # Build a tiny, audio-free schedule+sources (equal-length units -> no phase
    # vocoder; keeps this check fast and dependency-light). Overlapping slots +
    # a loudness gauge make order genuinely observable.
    rng = np.random.default_rng(1111)
    L = 64
    bounds = np.array([0, L, 2 * L, 3 * L], dtype=np.int64)  # 3 output slots
    bank = SourceUnitBank(sr=44100)
    # 6 units; several share slots so contributions overlap-add.
    placement_rows = []
    uid = 0
    for slot in range(3):
        for _ in range(2):
            aud = rng.standard_normal(L)
            bank.add(SourceUnit(track_id=0, unit_id=uid, band=0,
                                src_start=0, src_end=L, audio=aud, sr=44100))
            placement_rows.append((slot, 0, uid, 0))
            uid += 1
    placements = np.array(placement_rows, dtype=PLACEMENT_DTYPE)
    sections = (Section(0, 0, 3, Gauge(loudness_scale=0.7)),)  # non-identity gauge
    sched = Schedule(sr=44100, slot_boundaries=bounds,
                     placements=placements, sections=sections)

    a1, prov1 = render(sched, bank)
    a2, prov2 = render(sched, bank)

    # (B) determinism: bit-identical on repeat.
    assert np.array_equal(a1, a2), "render is not deterministic (I-11)"
    assert np.array_equal(prov1.segments, prov2.segments), \
        "render provenance is not deterministic (I-11)"
    # bite: a nondeterministic reference would fail array_equal.
    assert not np.array_equal(a1, a1 + rng.standard_normal(len(a1)) * 1e-6), \
        "determinism check is vacuous"

    # (C) order-independence: permuted placements -> same audio (allclose; FP
    # summation reorders at ~1e-15). Selection logic would break this.
    perm = rng.permutation(len(placements))
    sched_perm = Schedule(sr=44100, slot_boundaries=bounds,
                          placements=placements[perm], sections=sections)
    a_perm, _ = render(sched_perm, bank)
    assert np.allclose(a1, a_perm, atol=1e-9), \
        "render output depends on placement order — it is selecting, not applying (I-11)"

    # bite: a SELECTING reference (keep only the first placement seen per slot,
    # drop the rest) genuinely depends on order, so it FAILS allclose under the
    # same permutation. This proves the order-independence tooth is non-vacuous.
    def _first_wins(sched_):
        n = int(sched_.slot_boundaries[-1])
        out = np.zeros(n)
        seen = set()
        for row in sched_.placements:
            s = int(row["out_slot"])
            if s in seen:
                continue          # a CHOICE: drop later placements on this slot
            seen.add(s)
            a = int(sched_.slot_boundaries[s]); b = int(sched_.slot_boundaries[s + 1])
            out[a:b] += bank.get(int(row["src_track"]), int(row["src_unit"])).audio
        return out
    assert not np.allclose(_first_wins(sched), _first_wins(sched_perm), atol=1e-9), \
        "order-independence check is vacuous: a selecting render was not distinguished"


def _check_i6() -> None:
    """I-6 no external negatives: the comparison class is derived from GOOD
    tracks only (re-arrangements of real units, never external "bad music"), and
    the scramble family is EXACTLY the fixed pre-registered set. Non-vacuous:
    every branch below is shown to bite.
    """
    import numpy as np
    from ets.ingestion.pipeline import synthetic_track
    from ets.ingestion.track import assert_provenance_complete
    from ets.training import scramble as S

    t = synthetic_track(track_id=3, seed=3)
    inp_keys = S.content_keys(t)

    # (b) the family is EXACTLY the fixed pre-registered set (enumerated, closed)
    assert set(S.registry_names()) == set(S.PREREGISTERED_FAMILY), \
        "scramble registry != fixed PREREG family"
    assert set(S.PREREGISTERED_FAMILY) == {
        "grid-shuffle", "role-permute", "phase-rotate", "cross-track-swap"}, \
        "PREREG family names drifted from spec §6"
    S.assert_family_fixed()  # holds on the clean registry

    # ...and it BITES: an unregistered scrambler must fail the closed-set check.
    S._REGISTRY["__bogus_scrambler__"] = S.ScrambleOp(
        "__bogus_scrambler__", "track", "(none)", "implemented",
        lambda tr, seed=0: tr)
    try:
        bit = False
        try:
            S.assert_family_fixed()
        except AssertionError:
            bit = True
        assert bit, "family-fixed check did NOT bite on an unregistered scrambler"
    finally:
        del S._REGISTRY["__bogus_scrambler__"]

    # All four members are now IMPLEMENTED (step c activated the two role-level
    # ops through the anchor channel). Track-level ops return Tracks; role-level
    # ops return role-space Arrangements. The family is split by arity.
    from ets.training.world import WorldFreeze, _occ
    from ets.geometry import roles as _roles
    track_ops = {op.name for op in S.family() if op.arity == "track"}
    role_ops = {op.name for op in S.family() if op.arity in ("role", "role_pair")}
    assert track_ops == {"grid-shuffle", "phase-rotate"}, track_ops
    assert role_ops == {"role-permute", "cross-track-swap"}, role_ops
    assert all(op.status == "implemented" for op in S.family()), \
        "every family member must be implemented after step c"

    # (a) TRACK-level ops: real units only + inventory preserved + honest single-
    # source provenance (I-12) — this certifies 'good tracks only'.
    for name in track_ops:
        op = S._REGISTRY[name]
        out = op.fn(t, seed=11)
        assert_provenance_complete(out)
        S.assert_inventory_preserved([t], out)          # (a) ⊆ real + (c) equal
        out2 = op.fn(t, seed=11)
        assert np.array_equal(out.provenance_index["src_start"],
                              out2.provenance_index["src_start"])
        assert np.array_equal(out.units["phase"], out2.units["phase"])
        assert S.content_keys(t) == inp_keys, f"{name} mutated its input"
        disarranged = (
            not np.array_equal(out.provenance_index["src_start"],
                               t.provenance_index["src_start"])
            or not np.array_equal(out.units["phase"], t.units["phase"]))
        assert disarranged, f"{name} was a no-op (did not disarrange)"

    # (b) ROLE-level ops: draw ONLY through the gauge-invariant anchor channel; the
    # arrangement is assembled from REAL couplings (no fabrication, I-6). A minimal
    # frozen world suffices to exercise the anchor coupling.
    t2b = synthetic_track(track_id=4, seed=4)
    rng = np.random.default_rng(0)
    Dw = rng.random((3, 3)); Dw = 0.5 * (Dw + Dw.T); np.fill_diagonal(Dw, 0.0)
    world = WorldFreeze(D=Dw, a=np.full(3, 1 / 3),
                        B=np.full((3, 8), 1 / 8), theta=np.full((3, 8), 1 / 8),
                        sigma=1.0, M=3)
    real_ids = [t.track_id, t2b.track_id]
    _Preal = _roles.extract_prototypes(t, seed=0)
    O_real = _occ(world.couple(_Preal), _Preal)
    for name in role_ops:
        op = S._REGISTRY[name]
        if op.arity == "role":
            arr = op.fn(t, world, seed=11); arr2 = op.fn(t, world, seed=11)
        else:
            arr = op.fn([t, t2b], world, seed=11); arr2 = op.fn([t, t2b], world, seed=11)
        S.assert_arrangement_real(arr, real_ids)        # (a)/(c) real-only, no fab
        assert np.array_equal(arr.O, arr2.O), f"{name} not deterministic"
        assert S.content_keys(t) == inp_keys, f"{name} mutated its input"
        assert not np.allclose(arr.O, O_real, atol=1e-9), \
            f"{name} was a no-op (did not disarrange the occupancy)"

    # ...and the role-space guard BITES on a non-real (fabricated) source.
    bogus = S.Arrangement(O=O_real.copy(), t1=0.0, mass_sources=(9999,))
    bit = False
    try:
        S.assert_arrangement_real(bogus, real_ids)
    except AssertionError:
        bit = True
    assert bit, "assert_arrangement_real did NOT catch a fabricated source (I-6)"

    # Prove the inventory guard is NON-VACUOUS.
    good = S.grid_shuffle(t, seed=1)

    # (i) FABRICATION / external data: point one unit at a source span that
    #     exists in NO real track — the ⊆ branch must bite.
    import dataclasses
    tampered = dataclasses.replace(good,
                                   provenance_index=good.provenance_index.copy())
    tampered.provenance_index["src_start"][0] = t.n_samples + 10_000
    tampered.provenance_index["src_end"][0] = t.n_samples + 20_000
    bit = False
    try:
        S.assert_inventory_preserved([t], tampered)
    except AssertionError:
        bit = True
    assert bit, "inventory guard did NOT catch a fabricated (external) unit"

    # (ii) INVENTORY LOSS: drop one real unit consistently — the equality branch
    #      must bite even though every remaining unit is still real (⊆ holds).
    n = len(good.units)
    sl = slice(0, n - 1)
    dropped = dataclasses.replace(
        good,
        units=good.units[sl].copy(), masses=good.masses[sl].copy(),
        provenance_index=good.provenance_index[sl].copy(),
        C_timbre=dataclasses.replace(good.C_timbre, desc=good.C_timbre.desc[sl].copy()),
        C_pitchclass=dataclasses.replace(good.C_pitchclass,
                                         desc=good.C_pitchclass.desc[sl].copy()))
    bit = False
    try:
        S.assert_inventory_preserved([t], dropped)
    except AssertionError:
        bit = True
    assert bit, "inventory guard did NOT catch a dropped unit (lost inventory)"


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
              Status.ENFORCED, _check_i3),
    Invariant("I-4", "one F",
              "no training loss distinct from F; no eta-KL tether or second "
              "authority over equilibrium gains.",
              Status.ENFORCED, _check_i4),
    Invariant("I-5", "meters out of the loss",
              "meters never in any objective/gradient/settlement decision.",
              Status.ENFORCED, _check_i5),
    Invariant("I-6", "no external negatives",
              "no external negative data; comparison class derived from good "
              "tracks only; scramble family fixed in PREREG.",
              Status.ENFORCED, _check_i6),
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
              Status.ENFORCED, _check_i11),
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
