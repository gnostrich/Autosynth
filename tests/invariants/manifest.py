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
    The whole F/settlement PATH — the functional f.py AND the solver.py that
    settles it — contains NO holonomy/drift/meter/novelty/saturation/hankel/eoc
    identifier and IMPORTS no meter module. Those quantities are instruments
    (spec §9, I-14), never in F or in any settlement step."""
    from ets.functional import f as ff, solver as sv

    # (a) no meter/holonomy identifier is USED IN CODE anywhere on the F path.
    for mod in (ff, sv):
        hits = _forbidden_hits(_module_src(mod), _FORBID_I5)
        assert not hits, \
            f"I-5: meter/holonomy identifier appears on the F path ({mod.__name__}): {hits}"

    # (b) neither module IMPORTS the meters package (a meter could be referenced
    #     via an import alias that is not itself a forbidden token).
    for mod in (ff, sv):
        imps = _imported_modules(_module_src(mod))
        leaked = sorted(m for m in imps if "meter" in m.lower())
        assert not leaked, f"I-5: {mod.__name__} imports a meter module: {leaked}"

    # NON-VACUITY: the identifier scanner bites on a holonomy/meter term in an
    # F-like source, and the import scanner bites on a meters import.
    bad = "def F(state):\n    return transport(state) + holonomy_drift(state)\n"
    assert _forbidden_hits(bad, _FORBID_I5), "I-5 identifier scanner is vacuous"
    bad_imp = "from ets.meters import drift_cv\ndef step(x):\n    return x\n"
    assert any("meter" in m.lower() for m in _imported_modules(bad_imp)), \
        "I-5 import scanner is vacuous"


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
    # a loudness gauge make order genuinely observable, and DISTINCT per-placement
    # settled masses make the mass field participate in every tooth below: a
    # render that mis-bound masses to placements (e.g. applied them positionally)
    # would break order-independence.
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
            placement_rows.append((slot, 0, uid, 0, 0.3 + 0.2 * uid))  # distinct mass
            uid += 1
    placements = np.array(placement_rows, dtype=PLACEMENT_DTYPE)
    assert len(set(placements["mass"])) == len(placements), \
        "masses must be distinct for the order-independence tooth to cover them"
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
    # summation reorders at ~1e-15). Selection logic would break this. The rows
    # carry DISTINCT masses, so each placement's settled mass participates: the
    # permutation moves whole rows, and a render that bound mass to POSITION
    # rather than to its placement would fail this.
    perm = rng.permutation(len(placements))
    sched_perm = Schedule(sr=44100, slot_boundaries=bounds,
                          placements=placements[perm], sections=sections)
    a_perm, _ = render(sched_perm, bank)
    assert np.allclose(a1, a_perm, atol=1e-9), \
        "render output depends on placement order — it is selecting, not applying (I-11)"
    # ...and mass participation is NON-VACUOUS: neutralizing the masses changes
    # the audio, so the order-independence above genuinely covered them.
    placements_unit = placements.copy()
    placements_unit["mass"] = 1.0
    a_unit, _ = render(Schedule(sr=44100, slot_boundaries=bounds,
                                placements=placements_unit, sections=sections), bank)
    assert not np.allclose(a1, a_unit, atol=1e-9), \
        "mass coverage is vacuous: distinct masses did not change the render"

    # (D) MASS FAITHFULNESS / LINEARITY (retro-audit guard amendment): render is
    # exactly HOMOGENEOUS in each placement's mass — scaling one placement's mass
    # by c scales exactly that placement's contribution by c, for c large AND for
    # c small enough that any threshold-in-render would zero it. This closes the
    # demonstrated hole: a silent `if mass < t: continue` in render() survived
    # every prior tooth (determinism, order-independence, neutralize-bite are all
    # threshold-blind). Faithful application has no threshold; linearity proves it.
    j = 3                                    # an arbitrary placement under test
    solo = placements[j:j + 1].copy()
    a_solo, _ = render(Schedule(sr=44100, slot_boundaries=bounds,
                                placements=solo, sections=sections), bank)
    for c in (2.0, 1e-9):
        scaled = placements.copy()
        scaled["mass"] = placements["mass"]  # copy() of structured arr shares nothing
        scaled["mass"][j] = placements["mass"][j] * c
        a_c, _ = render(Schedule(sr=44100, slot_boundaries=bounds,
                                 placements=scaled, sections=sections), bank)
        # a_c - a1 must equal (c-1) * (j's solo contribution), machine precision.
        # rtol=0: the comparison must stay absolute, or a dropped tiny-c
        # contribution (~1e-9) hides inside the default relative tolerance.
        expect = (c - 1.0) * a_solo
        assert np.allclose(a_c - a1, expect, rtol=0, atol=1e-12 * max(1.0, abs(c))), (
            f"I-11 mass linearity violated at c={c}: render is not a pure "
            f"application of the settled mass (threshold or nonlinearity present)")
    # ...and the linearity tooth BITES: a thresholding render (drop mass < 0.5)
    # violates it at small c, exactly the mutant that survived the older teeth.
    def _thresholding(sched_):
        n = int(sched_.slot_boundaries[-1])
        out = np.zeros(n)
        for row in sched_.placements:
            if float(row["mass"]) < 0.5:
                continue                     # the silent-truncation failure mode
            s = int(row["out_slot"])
            a = int(sched_.slot_boundaries[s]); b = int(sched_.slot_boundaries[s + 1])
            out[a:b] += (bank.get(int(row["src_track"]), int(row["src_unit"])).audio
                         * float(row["mass"]) * 0.7)
        return out
    t_base = _thresholding(sched)
    tiny = placements.copy(); tiny["mass"][j] = placements["mass"][j] * 1e-9
    t_tiny = _thresholding(Schedule(sr=44100, slot_boundaries=bounds,
                                    placements=tiny, sections=sections))
    # linear expectation for the mutant, built from ITS OWN solo contribution:
    t_solo = np.zeros(int(bounds[-1]))
    slot_j = int(placements["out_slot"][j])
    aa = int(bounds[slot_j]); bb = int(bounds[slot_j + 1])
    t_solo[aa:bb] = (bank.get(0, int(placements["src_unit"][j])).audio
                     * float(placements["mass"][j]) * 0.7)
    t_expect = (1e-9 - 1.0) * t_solo
    assert not np.allclose(t_tiny - t_base, t_expect, rtol=0, atol=1e-12), (
        "I-11 mass-linearity bite is vacuous: the thresholding mutant was not "
        "distinguished")

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


def _check_i7() -> None:
    """I-7 clamped-cell interventions: all interventions (committed past, human
    demands) are CLAMPED CELLS of the SAME TYPE as history; there is ONE
    intervention channel and NO exception path / recovery mode.

    Guarded feature: the batch writer's tape node + clamp interface
    (ets/writer/tape.py, settle.py, realize.py). The check is non-vacuous — every
    branch is shown to bite.
    """
    import inspect
    import numpy as np
    from ets.ingestion.pipeline import synthetic_track
    from ets import writer as W
    from ets.writer import ClampSet, TapeNode

    # (a) SINGLE ENTRY / NO EXCEPTION PATH (structural). The tape node's only
    # intervention surface is its ClampSet; ClampSet carries exactly the two
    # same-species demand kinds (role columns, unit demands) and nothing else; and
    # the public generate/settle entry points expose no second placement-injection
    # or recovery/override parameter.
    tape_fields = set(TapeNode.__dataclass_fields__)
    assert "clamps" in tape_fields, "tape node lacks the clamp channel"
    clamp_fields = set(ClampSet.__dataclass_fields__)
    assert clamp_fields == {"role_columns", "unit_demands"}, \
        f"ClampSet grew a non-clamp intervention field: {clamp_fields}"
    forbidden = {"force", "override", "inject", "bypass", "recovery", "mode",
                 "special", "fallback"}
    for fn in (W.generate_batch, W.settle_tape, W.realize):
        params = set(inspect.signature(fn).parameters)
        bad = params & forbidden
        assert not bad, f"{fn.__name__} exposes a non-clamp intervention param: {bad}"
        # the ONLY intervention channel is the clamp-bearing tape/ClampSet.
        assert ("clamps" in params) or ("tape" in params), \
            f"{fn.__name__} has no clamp/tape channel"

    # Build a tiny frozen world to exercise the interface behaviorally.
    tracks = [synthetic_track(track_id=t, n_slots=24, seed=t) for t in range(4)]
    world = W.build_world_from_tracks(tracks, sigma=0.5)
    M = world.M

    # (b) A CLAMPED CELL IS THE SAME TYPE AS A SETTLED CELL. A settled column is an
    # (M,) float role-occupancy vector; a clamp column is exactly that shape/dtype.
    base = W.generate_batch(world, seconds=3.0)
    settled_col = base["settle"].O[:, 3]
    assert settled_col.shape == (M,) and settled_col.dtype == np.float64

    demand_col = np.zeros(M); demand_col[0] = 1.0
    assert demand_col.shape == settled_col.shape, "clamp column type != settled column"

    # role-column clamp: the settlement pins that exact cell (boundary condition),
    # same mechanism as every other cell — no special path.
    s_role = 5
    clamped = W.generate_batch(world, seconds=3.0,
                               clamps=ClampSet(role_columns={s_role: demand_col.copy()}))
    assert np.allclose(clamped["settle"].O[:, s_role], demand_col), \
        "role clamp was not honored as a boundary condition on the settlement"
    # bite: an unclamped run does NOT pin that column to the demand.
    assert not np.allclose(base["settle"].O[:, s_role], demand_col), \
        "I-7 role-clamp check is vacuous (column already equaled the demand)"

    # unit-demand clamp: the exact source unit appears VERBATIM at its slot.
    s_unit = 7
    tid, uid = int(tracks[1].track_id), int(tracks[1].units["unit_id"][10])
    demanded = W.generate_batch(
        world, seconds=3.0,
        clamps=ClampSet(unit_demands={s_unit: (tid, uid, 0)}))
    p = demanded["schedule"].placements
    at_slot = p[p["out_slot"] == s_unit]
    hit = any(int(r["src_track"]) == tid and int(r["src_unit"]) == uid for r in at_slot)
    assert hit, "unit demand was not placed verbatim at its clamped slot"
    # bite: without the clamp, that exact unit is not forced onto that slot.
    p0 = base["schedule"].placements
    at0 = p0[p0["out_slot"] == s_unit]
    forced_anyway = any(int(r["src_track"]) == tid and int(r["src_unit"]) == uid
                        for r in at0)
    assert not forced_anyway, \
        "I-7 unit-demand check is vacuous (unit appears without being clamped)"

    # (c) the demand raises loudly if it addresses a cell outside the tape (a
    # malformed intervention is rejected, not silently dropped / recovered).
    bit = False
    try:
        W.generate_batch(world, seconds=3.0,
                         clamps=ClampSet(role_columns={10_000: demand_col.copy()}))
    except ValueError:
        bit = True
    assert bit, "out-of-bounds clamp was not rejected (silent recovery path?)"


def _iter_runtime_sources():
    """Yield (path, source) for every .py file in the ets/ runtime package."""
    import os
    import ets
    root = os.path.dirname(os.path.abspath(ets.__file__))
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if fn.endswith(".py"):
                p = os.path.join(dirpath, fn)
                with open(p, "r", encoding="utf-8") as fh:
                    yield p, fh.read()


def _module_strings_in_source(src: str) -> set:
    """Every module reference an AST import makes, plus any dynamic-import string
    constant. Returns dotted strings with HONEST PROVENANCE:

      import panel                  -> 'panel'                 (top-level root)
      import ets.panel              -> 'ets.panel'
      from ets import panel         -> 'ets', 'ets.panel'      (submodule position)
      from . import panel           -> '.panel'                (relative: leading dot)
      from .panel import widget     -> '.panel', '.panel.widget'
      importlib.import_module('x')  -> 'x'

    A from-import target or relative import is NEVER emitted as a bare top-level
    name, so a forbidden-ROOT check on parts[0] cannot confuse the runtime's own
    ets.panel with the HoloViz 'panel' framework, while Qt-component matching
    (any dotted part) is unchanged. String literals in docstrings/comments do
    NOT count unless passed to importlib.import_module/__import__."""
    import ast
    mods: set = set()
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                mods.add(a.name)
        elif isinstance(n, ast.ImportFrom):
            base = ("." * n.level) + (n.module or "")   # relative keeps its dots
            if n.module:
                mods.add(base)
            sep = "." if n.module else ""               # `from . import x` -> '.x'
            for a in n.names:                       # `from PySide6 import QtWebEngineWidgets`
                mods.add(base + sep + a.name)
        elif isinstance(n, ast.Call):
            fn = n.func
            is_dyn = ((isinstance(fn, ast.Attribute) and fn.attr == "import_module")
                      or (isinstance(fn, ast.Name) and fn.id == "__import__"))
            if is_dyn and n.args and isinstance(n.args[0], ast.Constant) \
                    and isinstance(n.args[0].value, str):
                mods.add(n.args[0].value)
    return mods


# Forbidden import ROOTS (matched against parts[0] of a module string only).
_WEB_TOP = frozenset({
    "electron", "tauri", "webview", "pywebview", "cef", "cefpython3",
    "flask", "django", "aiohttp", "bottle", "tornado", "cherrypy", "werkzeug",
    "wsgiref", "gunicorn", "uvicorn", "starlette", "fastapi", "sanic", "quart",
    "dash", "streamlit", "gradio", "nicegui", "eel", "remi",
    # streamlit-kin / browser-rendered app-framework long tail. 'panel' is the
    # HoloViz framework: as a ROOT it can only be a genuine top-level import —
    # the runtime's own ets.panel appears as 'ets.panel' / '.panel' (never as
    # root 'panel') under _module_strings_in_source's provenance rules. 'anvil'
    # covers anvil-uplink (imports as `anvil`); anvil-app-server imports as
    # `anvil_app_server`. 'bokeh' includes its server (BokehJS = browser tech).
    # plotly-dash variants all import as `dash` (already listed above).
    "flet", "reflex", "anvil", "anvil_app_server", "justpy", "pywebio",
    "taipy", "solara", "marimo", "panel", "bokeh",
    "selenium", "playwright", "pyppeteer", "webbrowser",
})


_WEB_FULL = frozenset({"http.server", "wsgiref.simple_server"})


_WEB_QT = frozenset({
    "QtWebEngineWidgets", "QtWebEngineCore", "QtWebEngineQuick",
    "QtWebEngine", "QtWebView", "QtWebChannel", "QtWebSockets", "QtHttpServer",
})


def _web_hits(mod_strings) -> list:
    """Which of the given module strings are forbidden web/browser tech.

    _WEB_TOP entries are forbidden import ROOTS: they match parts[0] only, so a
    relative ('.panel') or submodule ('ets.panel') reference never matches.
    _WEB_QT entries match ANY dotted component (Qt web modules are reachable
    from several PySide6 bases). _WEB_FULL entries match the exact dotted path
    or a subpath."""
    hits = set()
    for m in mod_strings:
        parts = m.split(".")
        if parts[0].lower() in _WEB_TOP:
            hits.add(m)
        if any(p in _WEB_QT for p in parts):
            hits.add(m)
        if m in _WEB_FULL or any(m.startswith(f + ".") for f in _WEB_FULL):
            hits.add(m)
    return sorted(hits)


def _check_i13() -> None:
    """I-13 no browser/web tech in the runtime.

    Structural: every .py file in the ets/ package is AST-scanned for imports;
    NONE may reference web/browser/UI-server tech (Electron/Tauri/WebView/CEF,
    Flask/Django/aiohttp/FastAPI/…, Qt WebEngine, http.server). The runtime's UI
    stack is native Qt (PySide6) + OSC (python-osc) and nothing web.

    Non-vacuous in three independent ways:
      (i) the scanner BITES on planted web imports — one mutant per forbidden
          framework family, including the streamlit-kin long tail (flet, reflex,
          anvil, justpy, pywebio, taipy, solara, marimo, HoloViz panel, bokeh),
          Qt WebEngine, http.server, and a dynamic import of tauri;
     (ii) it is demonstrably reading real code — the sanctioned native stack
          (PySide6 + pythonosc) is actually present in the scanned tree, so an
          empty/no-op scan cannot masquerade as a pass; and
    (iii) it is PRECISE — the runtime's own ets.panel package (same leaf name as
          the forbidden HoloViz 'panel') is proven to never false-positive in
          any import form the runtime can use, while every acquisition channel
          for the HoloViz framework still bites.
    """
    # (a) the real runtime is clean.
    sanctioned_seen = {"PySide6": False, "pythonosc": False}
    for path, src in _iter_runtime_sources():
        mods = _module_strings_in_source(src)
        hits = _web_hits(mods)
        assert not hits, f"I-13: web/browser import in runtime file {path}: {hits}"
        for m in mods:
            top = m.split(".")[0]
            if top in sanctioned_seen:
                sanctioned_seen[top] = True

    # (b) NON-VACUITY (ii): the scan actually saw the native Qt + OSC stack, so
    #     it is genuinely parsing imports, not passing on an empty set.
    assert sanctioned_seen["PySide6"], \
        "I-13 scan saw no PySide6 import — the native panel stack is missing or unscanned"
    assert sanctioned_seen["pythonosc"], \
        "I-13 scan saw no pythonosc import — the OSC transport is missing or unscanned"

    # (c) NON-VACUITY (i): the scanner BITES on each web-tech pattern — one
    #     planted mutant per forbidden framework in the long-tail extension.
    mutants = {
        "flask server": "import flask\napp = flask.Flask(__name__)\n",
        "qt webengine": "from PySide6 import QtWebEngineWidgets\n",
        "qt webengine submodule": "from PySide6.QtWebEngineWidgets import QWebEngineView\n",
        "stdlib http server": "import http.server\n",
        "dynamic tauri": "import importlib\nimportlib.import_module('tauri')\n",
        "electron": "import electron\n",
        "flet": "import flet\nflet.app(lambda page: None)\n",
        "reflex": "import reflex as rx\n",
        "anvil uplink": "import anvil.server\n",
        "anvil app server": "import anvil_app_server\n",
        "justpy": "import justpy as jp\n",
        "pywebio": "from pywebio.output import put_text\n",
        "taipy": "from taipy.gui import Gui\n",
        "solara": "import solara\n",
        "marimo": "import marimo\n",
        "holoviz panel": "import panel as pn\n",
        "bokeh server": "from bokeh.server.server import Server\n",
    }
    for name, src in mutants.items():
        assert _web_hits(_module_strings_in_source(src)), \
            f"I-13 scanner is vacuous: did not flag web tech in mutant {name!r}"

    # ...and it does NOT false-positive on the sanctioned native stack.
    clean = ("import numpy as np\n"
             "from PySide6.QtWidgets import QWidget, QSlider\n"
             "from PySide6.QtCore import Qt, Signal\n"
             "from pythonosc import udp_client, osc_server, dispatcher\n")
    assert not _web_hits(_module_strings_in_source(clean)), \
        "I-13 scanner false-positives on native Qt widgets + OSC"

    # (d) NON-VACUITY (iii) — PRECISION PROOF for ets.panel vs HoloViz panel.
    #     Our runtime package ets.panel shares its leaf name with the forbidden
    #     framework. Every import form the runtime can use to reach OUR panel
    #     must scan clean...
    ours = {
        "absolute import": "import ets.panel\n",
        "absolute from": "from ets.panel import lanes, meters, osc_schema\n",
        "absolute deep from": "from ets.panel.lanes import LaneVector\n",
        "from ets import panel": "from ets import panel\n",
        "relative from-dot": "from . import panel\n",
        "relative from .panel": "from .panel import widget\n",
        "relative deep": "from ..panel.lanes import LaneVector\n",
        "dynamic relative": ("import importlib\n"
                             "importlib.import_module('.panel', 'ets')\n"),
    }
    for name, src in ours.items():
        fp = _web_hits(_module_strings_in_source(src))
        assert not fp, \
            f"I-13 false-positives on the runtime's own ets.panel ({name}): {fp}"
    # ...while every acquisition channel for the HoloViz framework still bites
    # (this is the mutant pair that makes the precision claim two-sided).
    theirs = {
        "import panel": "import panel as pn\n",
        "import panel submodule": "import panel.widgets\n",
        "from panel import": "from panel import Row\n",
        "from panel.io import": "from panel.io.server import serve\n",
        "dynamic top-level panel": ("import importlib\n"
                                    "importlib.import_module('panel')\n"),
    }
    for name, src in theirs.items():
        assert _web_hits(_module_strings_in_source(src)), \
            f"I-13 precision cut too deep: HoloViz panel not flagged via {name!r}"


def _imported_modules(src: str) -> set:
    """Every module string a source IMPORTS (absolute or relative), including the
    `from X import Y` targets as `X.Y`. Used to prove one package has ZERO
    dependency on another regardless of whether the imported names are then used
    as bare identifiers (which `_code_identifiers` would catch)."""
    import ast
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            for a in n.names:
                mods.add(a.name)
        elif isinstance(n, ast.ImportFrom):
            base = ("." * n.level) + (n.module or "")
            mods.add(base)
            for a in n.names:
                mods.add(base + "." + a.name)
    return mods


def _check_i14() -> None:
    """I-14 Hankel/holonomy are INSTRUMENTS; event triggers must not fork
    decision authority from F.

    Two structural teeth, each proven non-vacuous:

      (A) VALUES ONLY / NO BACK-EDGE INTO A SOLVE. Every module of the meters
          package imports nothing from the F/settlement side (ets.functional:
          f / solver / ot / anchors) nor from ets.training. A meter therefore
          cannot call into a settlement, so it produces values only and feeds
          nothing back — the holonomy/EOC/novelty jacks are instruments.

      (B) THE SETTLEMENT DECISION READS ONLY F. The solver's accept/reject guard
          in batch_solve compares F values and nothing else: no meter / EOC /
          gate / comparator identifier appears in that branch. An event trigger
          (e.g. an EOC gate) cannot fork the settlement decision away from F."""
    import ast
    import importlib
    from ets.functional import solver as sv

    # (A) meters package has ZERO dependency on the F/settlement side. Match
    #     whole dotted-path COMPONENTS (so "annotations" does not accidentally
    #     match "ot"); the entire F path lives under ets.functional, training
    #     under ets.training.
    # ets.meters.drift_cv was DELETED outright (directive-v1 Feature 2 Stage
    # 1, operator amendment stage1-delete-conflated-jack): the conflated jack
    # carried zero bits the slide/loop pair below does not already carry, on
    # every producible trace (REGISTRY conflation-regression-stage1-
    # 2026-07-15). ets.meters.contract is the typed consumer registry added
    # in the same stage; it is meters-side (reads only slide/loop readings)
    # and is swept here too.
    meter_mods = ["ets.meters", "ets.meters.holonomy",
                  "ets.meters.gauge_slide", "ets.meters.gauge_loop",
                  "ets.meters.phrase", "ets.meters.novelty",
                  "ets.meters.contract"]
    forbidden_pkg = {"functional", "training"}

    def _leaks(imports):
        return sorted(m for m in imports
                      if forbidden_pkg & set(m.lower().split(".")))

    for name in meter_mods:
        mod = importlib.import_module(name)
        leaked = _leaks(_imported_modules(_module_src(mod)))
        assert not leaked, \
            f"I-14: meter module {name} imports the F/settlement side: {leaked}"

    # ...and the dependency scan BITES: a meter that imported the solver is caught.
    mutant_meter = ("from ets.functional import solver as sv\n"
                    "def drift(x):\n    return sv.batch_solve(x)\n")
    assert _leaks(_imported_modules(mutant_meter)), \
        "I-14 (A) dependency scan is vacuous"

    # (B) the settlement accept guard reads ONLY F (no meter/EOC/comparator fork).
    #     Scan the FULL test expression of every `if` in batch_solve (not just
    #     Compare nodes), so an event trigger that forks via `if eoc_gate and
    #     F_cand <= F_cur:` (a BoolOp, not a bare Compare) is still caught.
    ssrc = _module_src(sv)
    tree = ast.parse(ssrc)
    bs = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "batch_solve"), None)
    assert bs is not None, "batch_solve not found"
    guard_names = {x.id for node in ast.walk(bs) if isinstance(node, ast.If)
                   for x in ast.walk(node.test) if isinstance(x, ast.Name)}
    assert "F_cand" in guard_names and "F_cur" in guard_names, \
        "I-14: the settlement guard does not compare F values"
    forked = _forbidden_hits("\n".join(f"{n} = 0" for n in guard_names), _FORBID_I5)
    assert not forked, \
        f"I-14: a meter/EOC identifier appears in the settlement guard: {forked}"

    # ...and it BITES: a guard that forks on an EOC gate is caught. (Mirror the
    # real scan: parse an if-guard, collect its test Names, run the token scan.)
    mguard = ast.parse("if eoc_gate and F_cand <= F_cur:\n    pass\n")
    mnames = {x.id for node in ast.walk(mguard) if isinstance(node, ast.If)
              for x in ast.walk(node.test) if isinstance(x, ast.Name)}
    assert _forbidden_hits("\n".join(f"{n} = 0" for n in mnames), _FORBID_I5), \
        "I-14 (B) settlement-guard scan is vacuous"


# --- I-15 no premature aggregation / structure-deleting projection -----------
# rev-r1 §5 fixes the authoritative per-term input partition. A term is legal iff
# it (a) consumes the full unit-resolved coupling pi, or (b) is a marginal of pi
# that PROVABLY factors through the occupancy O and carries a written proof, or
# (c) is a per-section gauge charge. T1 (transport + circular metrical phase-
# displacement charge) and T4 (unit-successor continuity) are spec-mandated on
# FULL pi and have NO proof route. Posing an F objective on the marginal alone —
# the fidelity breach this invariant remediates — is forbidden.
_SPEC_TERM_CONTRACT = {
    "T1": "full-pi", "T2": "marginal", "T3": "marginal",
    "T4": "full-pi", "T5": "gauge",
}


def _o_preserving_twin(protos):
    """Two FStates over the same protos with IDENTICAL occupancy O but DIFFERENT
    unit-resolved coupling pi. Constructed by moving coupling mass between two
    prototypes of track 0 whose (gauge-rolled, normalized) slot histograms are
    identical: O = sum_t pis[t].T @ q_t is invariant to that transfer (it cancels
    in the two equal q-rows), while pis itself changes. A term that factors
    through O is equal on both; a term that reads pi is free to differ."""
    import numpy as np
    from ets.functional import f as ff, anchors as an

    st_a = an.init_state(protos, M=4, seed=0)
    # force protos[0]'s first two prototypes to share a slot histogram so a mass
    # transfer between their coupling rows leaves O untouched.
    P0 = protos[0]
    P0.slot_hist[1] = P0.slot_hist[0].copy()
    st_a = an.init_state(protos, M=4, seed=0)  # rebuild against the edited protos
    st_b = ff.FState(
        D=st_a.D.copy(), a=st_a.a.copy(), B=st_a.B.copy(), theta=st_a.theta.copy(),
        pis=[p.copy() for p in st_a.pis],
        phase_off=st_a.phase_off.copy(), transpose=st_a.transpose.copy())
    pi0 = st_b.pis[0]
    m = 0
    delta = 0.4 * float(min(pi0[0, m], pi0[1, m]) + 1e-9)
    pi0[0, m] += delta
    pi0[1, m] -= delta
    # verify the twin really is O-preserving and pi-distinct.
    Oa = ff.occupancy(st_a, protos)
    Ob = ff.occupancy(st_b, protos)
    assert np.allclose(Oa, Ob, atol=1e-9), "twin construction did not preserve O"
    assert not np.allclose(st_a.pis[0], st_b.pis[0]), "twin did not perturb pi"
    return st_a, st_b


def _check_i15() -> None:
    """I-15: no premature aggregation / structure-deleting projection.

    Every F term either (a) consumes the full unit-resolved pi, or (b) carries a
    WRITTEN factorization proof (a justification string + this behavioral test).
    No proof, no merge.

    Tooth A (term contract, f.py): the declared TERM_INPUT_CONTRACT equals the
    spec partition; every 'marginal' term ships a non-trivial written proof AND
    is behaviorally invariant under an O-preserving pi rearrangement (its
    factorization claim is TRUE). Non-vacuous: the same rearrangement changes pi,
    so a mislabeled term that secretly read pi would be caught.

    Tooth B (referee non-degeneracy, nce): the corpus-time feature the estimator
    scores must NOT be posed on the marginal (O, t1) alone — a unit-resolved
    fiber (the T1 metrical phase charge / T4 unit-successor of rev-r1) must
    participate. A feature computed solely from (O, t1) is the exact structure-
    deleting projection that produced the KILL; it is a violation until a
    unit-resolved fiber enters the scored objective."""
    import inspect
    import numpy as np
    from ets.functional import f as ff

    # ---- Tooth A: term-input contract + marginal factorization proofs --------
    contract = getattr(ff, "TERM_INPUT_CONTRACT", None)
    assert isinstance(contract, dict), \
        "f.py declares no TERM_INPUT_CONTRACT (I-15: every term must declare its pi/marginal class)"
    assert contract == _SPEC_TERM_CONTRACT, (
        f"I-15: TERM_INPUT_CONTRACT {contract} != spec rev-r1 partition "
        f"{_SPEC_TERM_CONTRACT} (relabeling a full-pi term as marginal is forbidden)")
    proofs = getattr(ff, "FACTORIZATION_PROOFS", {})
    for term, cls in contract.items():
        if cls == "marginal":
            p = proofs.get(term, "")
            assert isinstance(p, str) and len(p.strip()) >= 80, \
                f"I-15: marginal term {term} lacks a written factorization proof (docstring)"

    # behavioral proof: build O-preserving pi-distinct twins; marginal terms MUST
    # be equal on both (they factor through O); and the twin must genuinely differ
    # in pi (non-vacuity — otherwise the invariance claim is empty).
    protos = [_synth_proto_i15(t, seed=t + 21) for t in range(3)]
    st_a, st_b = _o_preserving_twin(protos)
    _, da = ff.F(st_a, protos)
    _, db = ff.F(st_b, protos)
    for term, cls in contract.items():
        if cls == "marginal":
            assert abs(da[term] - db[term]) < 1e-9, (
                f"I-15: term {term} declared 'marginal' but is NOT invariant under an "
                f"O-preserving pi rearrangement — it secretly reads unit structure "
                f"(da={da[term]}, db={db[term]})")
    # non-vacuity: pi genuinely differs on the twin (the transfer preserves the
    # role column-sum but moves mass between two prototype rows), proving the
    # O-preserving move is a real pi perturbation, so the invariance above has bite.
    assert float(np.abs(st_a.pis[0] - st_b.pis[0]).max()) > 1e-6, \
        "I-15 twin is vacuous: pi did not actually change"

    # ---- Tooth B: the referee objective is not posed on the marginal alone ----
    # rev-r1 §5: T1 gains a circular metrical phase-displacement charge and T4 a
    # unit-successor continuation; both are UNIT-RESOLVED fiber terms. The scored
    # corpus-time feature must consume that fiber. A feature built only from
    # (O, t1) is the structure-deleting projection that KILLED step d.
    from ets.training import nce
    nce_src = inspect.getsource(nce)
    imports = _imported_modules(nce_src)
    fiber_participates = (
        any("fiber" in m.lower() for m in imports)
        or "fiber" in _code_identifiers(nce_src))
    assert fiber_participates, (
        "I-15 VIOLATION (structure-deleting projection): the corpus-time feature "
        "scored by ets.training.nce is posed on the marginal (O, t1) alone — no "
        "unit-resolved fiber (rev-r1 T1 metrical phase charge / T4 unit-successor) "
        "participates. This is the fidelity breach; the winning racer's F must wire "
        "the unit-resolved fiber into the scored objective before it can merge.")
    # non-vacuity: the fiber-participation scan bites on a marginal-only stub.
    assert not (
        any("fiber" in m.lower() for m in _imported_modules(
            "from ets.functional import f as ff\ndef feature(O, t1, world):\n    return ff.raw_terms_O(O, world.D, world.a, world.B, world.theta)\n"))), \
        "I-15 Tooth-B scan is vacuous (flagged a marginal-only feature as fiber-aware)"


def _synth_proto_i15(track_id, K=6, S=8, n_bands=8, seed=0):
    """Local prototype builder for the I-15 behavioral test (mirrors the feature
    test's synthetic prototypes; kept here so the manifest is self-contained)."""
    import numpy as np
    from ets.geometry.roles import Prototypes
    rng = np.random.default_rng(seed)
    pts = rng.standard_normal((K, 3))
    cost = np.sqrt(((pts[:, None] - pts[None]) ** 2).sum(-1))
    off = cost[~np.eye(K, dtype=bool)]
    cost = cost / (np.sqrt(np.mean(off ** 2)) + 1e-12)
    mass = rng.random(K) + 0.1; mass /= mass.sum()
    slot = rng.random((K, S)); slot /= slot.sum()
    band = rng.random((K, n_bands)); band = band / band.sum(1, keepdims=True) * mass[:, None]
    chroma = rng.random((K, 12)); chroma /= chroma.sum(1, keepdims=True)
    timbre = rng.standard_normal((K, 4))
    return Prototypes(track_id=track_id, cost=cost, mass=mass, slot_hist=slot,
                      band_profile=band, timbre=timbre, chroma=chroma)


def _check_i1() -> None:
    """I-1 single tilt jack: the writer's ONLY control type is TiltTerms built by
    the Layer-0 map; a non-tilt control object is refused with TypeError at
    runtime (behavioral tooth), and no runtime code constructs TiltTerms outside
    ets.writer.tilt's layer0/untilted (structural tooth lives in the H-6/C-3
    suite; here we run the behavioral refusal, which is non-vacuous by
    construction — the same call with the sanctioned object settles)."""
    from tests.harness.test_i1_i9_engine import test_i1_nontilt_control_is_refused_at_runtime
    test_i1_nontilt_control_is_refused_at_runtime()


def _check_i8() -> None:
    """I-8 streaming stability: state bounded by material heard on stationary
    input AND the guard BITES on injected growth (StreamHalt) — both teeth, per
    the no-vacuous-pass rule."""
    from tests.harness.worldtools import build_synthetic_world
    from tests.writer.test_stream import (
        test_i8_state_bounded_by_material_on_stationary_input,
        test_i8_guard_bites_on_injected_growth,
    )
    w = build_synthetic_world()
    test_i8_state_bounded_by_material_on_stationary_input(w)
    test_i8_guard_bites_on_injected_growth(w)


def _check_i9() -> None:
    """I-9 frozen F weights: live LAMBDA equals the registered training artifact,
    and an AST write-scan proves nothing under ets/ (engine/panel included)
    assigns to LAMBDA at runtime."""
    from tests.harness.test_i1_i9_engine import (
        test_i9_live_lambda_equals_registered_training_artifact,
        test_i9_engine_and_panel_never_write_lambda,
    )
    test_i9_live_lambda_equals_registered_training_artifact()
    test_i9_engine_and_panel_never_write_lambda()


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
              Status.ENFORCED, _check_i1),
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
              Status.ENFORCED, _check_i7),
    Invariant("I-8", "streaming stability",
              "streaming stability certificate; halt-and-report on state growth "
              "under stationary input.",
              Status.ENFORCED, _check_i8),
    Invariant("I-9", "frozen F weights",
              "run-time controls are tilt parameters only; F term-weights frozen "
              "after training.",
              Status.ENFORCED, _check_i9),
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
              Status.ENFORCED, _check_i13),
    Invariant("I-14", "Hankel/holonomy are instruments",
              "Hankel/holonomy quantities are instruments; event triggers must "
              "not fork decision authority from F.",
              Status.ENFORCED, _check_i14),
    Invariant("I-15", "no premature aggregation",
              "every F term consumes the full unit-resolved pi or carries a "
              "written factorization proof; no objective posed on a marginal.",
              Status.ENFORCED, _check_i15),
]

EXPECTED_IDS = [f"I-{n}" for n in range(1, 16)]


def by_id(iid: str) -> Invariant:
    for inv in INVARIANTS:
        if inv.id == iid:
            return inv
    raise KeyError(iid)
