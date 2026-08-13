"""PREREG-live-mode.md PART A — ClampTerms, the sanctioned SECOND carrier (CI
teeth for the two registered kill conditions and the LM-3 groundwork fixture).

  LM-1  carrier-neutral: a neutral/absent ClampTerms is BYTE-IDENTICAL to no
        carrier at all — same rows, same continuation flags, same audio bytes,
        same consumed rng stream (draw count/order, proven via the rng's own
        final bit-generator state, not merely equal outputs).
  LM-2  carrier-typing: a unit/time target through the LIVE tilt gate raises
        TypeError; the same target on ClampTerms passes; the single-
        construction-point static scan bites on a planted second site.

Plus a straight-fence sanity fixture (LM-3 groundwork, Train B's concern —
proven here only as "the mechanism is live and correct", not as the mode).

Out-of-process for anything that imports ``architecture-v6/ets`` (the arch-v6
engine is kept out of the cloud interpreter, exactly like
test_fast_realize.py / test_channel_bias.py — a synthetic hand-built world,
never a corpus render). The single-construction-point AST scan and the LM-11
no-timetable-constant scan (renumbered by Amendment 2 — see that test's
docstring) run IN-PROCESS (pure source-text parsing, no import), mirroring
test_h6_panel_exhaustive.py's C-3 idiom.
"""
from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ARCH_ETS = _ROOT / "architecture-v6" / "ets"
_CLAMP_PY = _ARCH_ETS / "writer" / "clamp.py"
_REALIZE_PY = _ARCH_ETS / "writer" / "realize.py"


# =============================================================================
# IN-PROCESS static checks (pure source text — no architecture-v6/ets import)
# =============================================================================

def _sources(pkg: str):
    for p in sorted((_ARCH_ETS / pkg).rglob("*.py")):
        yield p, p.read_text()


def _count_clampterms_calls(src: str) -> int:
    """The number of `ClampTerms(...)` CALL sites in `src` (any spelling:
    bare name or attribute access), mirroring
    test_h6_panel_exhaustive.py::test_c3_engine_constructs_tilt_only_via_layer0's
    `_direct_tilt_calls` scanner exactly."""
    n = 0
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            f = node.func
            name = (f.attr if isinstance(f, ast.Attribute) else
                    (f.id if isinstance(f, ast.Name) else ""))
            if name == "ClampTerms":
                n += 1
    return n


def test_lm2_single_construction_point_static_check():
    """A-1/LM-2: `ClampTerms(...)` is called nowhere in the `ets` tree except
    inside its own defining module, `clamp.py` (where `__post_init__`'s
    validation runs and `clamp0` is the sanctioned constructor). Any other
    call site — the engine, the writer's other modules, anywhere — is a rogue
    second construction point."""
    offenders = {}
    for pkg in ("writer", "engine", "render", "functional", "geometry",
               "ingestion", "panel", "instrument", "meters", "training"):
        pkg_dir = _ARCH_ETS / pkg
        if not pkg_dir.is_dir():
            continue
        for p, src in _sources(pkg):
            if p == _CLAMP_PY:
                continue
            n = _count_clampterms_calls(src)
            if n:
                offenders[str(p.relative_to(_ROOT))] = n
    assert not offenders, (
        f"ClampTerms constructed outside clamp.py (rogue second construction "
        f"point, A-1/LM-2): {offenders}")
    # BITE: a planted second construction site must be caught by the scanner.
    planted = "c = ClampTerms(track_mask={0: 1.0}, openness=1.0)\n"
    assert _count_clampterms_calls(planted) == 1, (
        "the ClampTerms single-construction-point scan is vacuous — it does "
        "not even catch a planted second call site")


_LM11_FORBIDDEN_EXACT = {"N_BRIDGE_BARS", "BRIDGE_BARS", "RAMP_SHAPE",
                         "RAMP_TABLE", "SCHEDULE_TABLE", "TIMEOUT",
                         "TIMEOUT_S", "TIMEOUT_BARS"}


def _assigned_or_defined_names(src: str) -> set:
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def test_lm11_no_timetable_constants_defined_in_train_a_modules():
    """Amendment 1's no-timetable check, renumbered LM-11 by Amendment 2
    (§A2.2 — LM-9/LM-10 are now the operator's idle-silence / first-click-
    immediacy checks, both Train B/transport concerns outside this file's
    scope). Content unchanged: no bridge-length constant, ramp table,
    schedule array, or timeout may be DEFINED (an assignment or a def/class
    name) in clamp.py or realize.py. Prose that documents the retirement
    (this test's own docstrings, clamp.py's module docstring) is not a
    definition and is not scanned — only actual identifiers bound in the
    module."""
    for path in (_CLAMP_PY, _REALIZE_PY):
        names = _assigned_or_defined_names(path.read_text())
        hit = {n for n in names
              if n.upper() in _LM11_FORBIDDEN_EXACT
              or "RAMP" in n.upper() or "TIMEOUT" in n.upper()
              or "BRIDGE_BARS" in n.upper()}
        assert not hit, (
            f"{path.relative_to(_ROOT)} defines a retired/forbidden "
            f"timetable identifier (Amendment 1 / LM-11): {hit}")
    # BITE: a planted ramp-length constant must be caught.
    planted = _assigned_or_defined_names("N_BRIDGE_BARS = 8\n")
    assert any("BRIDGE_BARS" in n.upper() for n in planted), (
        "the LM-11 no-timetable scan is vacuous")


# =============================================================================
# OUT-OF-PROCESS: a synthetic, hand-built two-track world (no corpus render)
# =============================================================================

_DUMP = r"""
import hashlib, json, os, sys
sys.path.insert(0, r"%s")
sys.path.insert(0, r"%s/architecture-v6")
import numpy as np
from types import SimpleNamespace

from ets.writer.clamp import ClampTerms, clamp0, no_clamp, live_tilt_target
from ets.writer.realize import FiberThreader, RealizationIndex, realize as realize_batch
from ets.writer.tilt import untilted
from ets.writer.tape import OutputGrid, TapeNode, ClampSet
from ets.render import render, SourceUnit, SourceUnitBank
from cloud.companion.channel_bias import field_logbias

S_PHASE = 8
SR = 44100
TATUM = 4410

# ---- a synthetic two-track world sharing ONE (role=0, band=0) pool --------
# Track 0 ("home"): units 0..7, real successor chain 0->1->...->7, intrinsic
#   phase i/8 (exactly the 8 slot-phase bins -- it always has a phase-exact
#   seed candidate, so it dominates the UNRESTRICTED deterministic choice).
# Track 1 ("other"): units 100..102, real successor chain 100->101->102,
#   phase i/3 (never phase-exact -- naturally disfavored, so fencing IT IN
#   is a clean, unambiguous "the fence moved the output" positive control).
TRACK0 = list(range(8))
TRACK1 = [100, 101, 102]

successor = {}
for a, b in zip(TRACK0[:-1], TRACK0[1:]):
    successor[(0, a)] = (0, b)
for a, b in zip(TRACK1[:-1], TRACK1[1:]):
    successor[(1, a)] = (1, b)

unit_phase = {}
for i, u in enumerate(TRACK0):
    unit_phase[(0, u)] = i / 8.0
for i, u in enumerate(TRACK1):
    unit_phase[(1, u)] = i / 3.0

cand_list = ([(0, u, unit_phase[(0, u)]) for u in TRACK0]
            + [(1, u, unit_phase[(1, u)]) for u in TRACK1])
cand_list.sort(key=lambda z: (z[2], z[0], z[1]))
candidates = {(0, 0): cand_list}
unit_of = {(0, 0): (0, TRACK0[0])}

index = RealizationIndex(unit_of=unit_of, role_track={0: 0}, M=1, n_bands=1,
                         successor=successor, unit_role={}, candidates=candidates,
                         unit_phase=unit_phase)
fstate = SimpleNamespace(B=np.array([[1.0]]))


def _drive(threader, n_slots):
    rows, cont = [], []
    bar_prev = 0
    for s in range(n_slots):
        bar = s // S_PHASE
        if bar != bar_prev:
            threader.commit_bar(bar_prev)
            bar_prev = bar
        r, c = threader.place_slot(s, np.array([1.0]))
        rows.extend(r); cont.extend(c)
    threader.commit_bar(bar_prev)
    return rows, cont


def _run_stream(clamp_obj, seed=0, n_slots=40, tilt_obj=None):
    th = FiberThreader(index, fstate, S_PHASE,
                       tilt=(tilt_obj if tilt_obj is not None else untilted(1)),
                       rng=np.random.default_rng(seed), clamp=clamp_obj)
    rows, cont = _drive(th, n_slots)
    return rows, cont, th.rng.bit_generator.state, list(th.starved)


# ---- LM-1: neutral/absent ClampTerms is byte-identical (streaming, rng) ---
# a/b/c/d are all GENUINELY neutral by construction: b is clamp0's own
# canonicalization (openness=0); c is a raw ClampTerms bypass with openness=0
# -- mathematically neutral UNCONDITIONALLY, since `m >= 0` holds for every
# valid mask value, with no dependence on construction path; d is no_clamp().
rows_a, cont_a, state_a, starv_a = _run_stream(None)
rows_b, cont_b, state_b, starv_b = _run_stream(clamp0({0: 1.0, 1: 1.0}, 0.0))
rows_c, cont_c, state_c, starv_c = _run_stream(
    ClampTerms(track_mask={0: 1.0, 1: 1.0}, openness=0.0))       # raw bypass
rows_d, cont_d, state_d, starv_d = _run_stream(no_clamp())

lm1_stream = {
    "nonvacuous": len(rows_a) > 10,
    "no_starvation_baseline": (not starv_a and not starv_b and not starv_c
                               and not starv_d),
    "rows_ab": rows_a == rows_b, "cont_ab": cont_a == cont_b,
    "rng_ab": state_a == state_b,
    "rows_ac": rows_a == rows_c, "cont_ac": cont_a == cont_c,
    "rng_ac": state_a == state_c,
    "rows_ad": rows_a == rows_d, "cont_ad": cont_a == cont_d,
    "rng_ad": state_a == state_d,
}

# ---- NOT part of the neutral law: a raw ClampTerms(track_mask={}, openness>0)
# bypass is a REAL (if degenerate) restriction, not a neutral one -- clamp.py's
# docstring says so explicitly (empty mask and explicit all-zero mask are
# mathematically indistinguishable to `_admits`'s literal dict.get lookup; only
# `clamp0` treats a truly-empty mask as "no data, don't restrict", and only at
# construction time). Both bypasses below MUST record STARVED on every choice
# -- and, because starvation always falls back to the unrestricted set, the
# resulting OUTPUT still coincides with the unclamped baseline (a worked
# example of "never a silent no-op", not a second neutral-law path).
rows_f, cont_f, state_f, starv_f = _run_stream(
    ClampTerms(track_mask={}, openness=0.7))                     # empty-mask bypass
rows_g, cont_g, state_g, starv_g = _run_stream(
    ClampTerms(track_mask={0: 0.0, 1: 0.0}, openness=0.7))       # explicit all-zero

starvation_fallback_coincidence = {
    "empty_mask_bypass_starves_every_choice": len(starv_f) > 0,
    "explicit_zero_bypass_starves_every_choice": len(starv_g) > 0,
    "starved_sets_identical_fg": starv_f == starv_g,
    "rows_identical_fg": rows_f == rows_g,
    "rows_coincide_with_unclamped_baseline_f": rows_a == rows_f,
    "rows_coincide_with_unclamped_baseline_g": rows_a == rows_g,
}

# ---- LM-2: the LIVE tilt gate vs ClampTerms (typing split, A-4) -----------
def _typeerror(fn, *a, **k):
    try:
        fn(*a, **k)
        return False
    except TypeError:
        return True

lm2 = {
    "col_ok": live_tilt_target("col", 3) == ("col", 3),
    "unit_raises": _typeerror(live_tilt_target, "unit", 42),
    "time_raises": _typeerror(live_tilt_target, "time", 7),
    "unit_pin_passes_on_clamp": (
        clamp0({0: 1.0}, 1.0, unit_pin=(0, (42,))) is not None
        and clamp0({0: 1.0}, 1.0, unit_pin=(0, (42,))).unit_pin == (0, (42,))
    ),
}

# ---- neutral-law construction-time canonicalization / validation ----------
def _raises(exc, fn, *a, **k):
    try:
        fn(*a, **k)
        return False
    except exc:
        return True

neutral_law = {
    "openness_zero_is_none": clamp0({0: 1.0, 1: 1.0}, 0.0) is None,
    "empty_mask_is_none": clamp0({}, 0.7) is None,
    "no_clamp_is_none": no_clamp() is None,
    "nonneutral_is_object": clamp0({0: 1.0}, 0.5) is not None,
    "explicit_all_zero_mask_openness_positive_NOT_neutral":
        clamp0({0: 0.0, 1: 0.0}, 0.5) is not None,
    "bad_openness_raises": _raises(ValueError, ClampTerms,
                                   track_mask={}, openness=1.5),
    "bad_mask_value_raises": _raises(ValueError, ClampTerms,
                                     track_mask={0: 2.0}, openness=0.5),
    "empty_pin_raises": _raises(ValueError, ClampTerms, track_mask={0: 1.0},
                                openness=1.0, unit_pin=(0, ())),
}

# ---- LM-1: a REAL render (batch realize -> Schedule -> audio) -------------
def _bank_for(sched, seed=0):
    rng = np.random.default_rng(seed)
    bank = SourceUnitBank(sr=SR)
    for r in sched.placements:
        key = (int(r["src_track"]), int(r["src_unit"]))
        if key not in bank:
            bank.add(SourceUnit(track_id=key[0], unit_id=key[1], band=0,
                                src_start=0, src_end=TATUM,
                                audio=rng.standard_normal(TATUM), sr=SR))
    return bank


def _render_with(clamp_obj, n_slots=32):
    grid = OutputGrid(sr=SR, tatum_len=TATUM, n_slots=n_slots, s_phase=S_PHASE)
    tape = TapeNode(grid=grid, M=1, clamps=ClampSet())
    O = np.ones((1, n_slots))
    sched, meta = realize_batch(O, tape, fstate, index, clamp=clamp_obj)
    bank = _bank_for(sched)
    audio, prov = render(sched, bank)
    audio = np.ascontiguousarray(np.asarray(audio, dtype=np.float32))
    sha = hashlib.sha256(audio.tobytes()).hexdigest()
    tracks = sorted({int(x["src_track"]) for x in sched.placements})
    return sched.placements, sha, meta, tracks


p_none, sha_none, meta_none, tr_none = _render_with(None)
p_neut, sha_neut, meta_neut, tr_neut = _render_with(clamp0({0: 1.0}, 0.0))
# raw bypass, openness=0 -- neutral UNCONDITIONALLY (see lm1_stream's case c).
p_neut2, sha_neut2, meta_neut2, tr_neut2 = _render_with(
    ClampTerms(track_mask={0: 1.0, 1: 1.0}, openness=0.0))

lm1_render = {
    "n_placements": int(len(p_none)),
    "placements_equal_neutral": bool(np.array_equal(p_none, p_neut)),
    "sha_equal_neutral": sha_none == sha_neut,
    "placements_equal_neutral2": bool(np.array_equal(p_none, p_neut2)),
    "sha_equal_neutral2": sha_none == sha_neut2,
    "baseline_never_picks_track1_naturally": 1 not in tr_none,   # sets up the
                                                                  # positive control below
    "starved_none_baseline": meta_none["starved"] == [],
}

# ---- POSITIVE CONTROL: fencing to the naturally-disfavored track MOVES ----
p_t1, sha_t1, meta_t1, tr_t1 = _render_with(clamp0({1: 1.0}, 1.0))
lm_moves = {
    "fenced_tracks_are_exactly_track1": tr_t1 == [1],
    "differs_from_baseline_sha": sha_t1 != sha_none,
    "starved_false_positive_control": meta_t1["starved"] == [],
}

# ---- STARVATION: an unsatisfiable fence never silently no-ops -------------
p_sv, sha_sv, meta_sv, tr_sv = _render_with(clamp0({99: 1.0}, 1.0))
starvation = {
    "starved_nonempty": len(meta_sv["starved"]) > 0,
    "rows_still_emitted": len(p_sv) > 0,
    "starved_events_are_bar_k_b_triples":
        all(len(e) == 3 for e in meta_sv["starved"]),
}

# ---- straight-fence sanity (LM-3 groundwork): full fence + pin ------------
th_pin = FiberThreader(index, fstate, S_PHASE, tilt=untilted(1),
                       rng=np.random.default_rng(3),
                       clamp=clamp0({0: 1.0}, 1.0, unit_pin=(0, (2, 3, 4))))
rows_pin, cont_pin = _drive(th_pin, 48)
seen_pin = sorted({(int(t), int(u)) for (_s, t, u, _sec, _m) in rows_pin})
straight_fence = {
    "nonvacuous": len(rows_pin) > 5,
    "all_within_pin": all(tu in {(0, 2), (0, 3), (0, 4)} for tu in seen_pin),
    "more_than_one_unit_used": len(seen_pin) > 1,
    "no_starvation": th_pin.starved == [],
}

# ---- fast vs original bit-identity UNDER an active, nontrivial clamp ------
field = field_logbias(track={0: 0.3, 1: -0.2}, unit={2: 0.5, 100: -0.4})
tilt_field = untilted(1, channel_logbias=field)
clamp_partial = clamp0({0: 1.0, 1: 0.6}, 0.6, unit_pin=(0, (1, 2, 3, 4, 5, 6)))

def _run_impl(fast, clamp_obj, seed=11, n_slots=64):
    os.environ["ETS_FAST_REALIZE"] = "1" if fast else "0"
    th = FiberThreader(index, fstate, S_PHASE, tilt=tilt_field,
                       rng=np.random.default_rng(seed), clamp=clamp_obj)
    rows, cont = _drive(th, n_slots)
    return rows, cont, list(th.starved)

rows_fast, cont_fast, starv_fast = _run_impl(True, clamp_partial)
rows_orig, cont_orig, starv_orig = _run_impl(False, clamp_partial)
os.environ.pop("ETS_FAST_REALIZE", None)

fast_orig_under_clamp = {
    "nonvacuous": len(rows_fast) > 10,
    "rows_identical": rows_fast == rows_orig,
    "cont_identical": cont_fast == cont_orig,
    "starved_identical": starv_fast == starv_orig,
}

# ---- fast vs original bit-identity UNDER clamp, BATCH (tilt=None) path ----
def _run_batch_impl(fast, clamp_obj, n_slots=32):
    os.environ["ETS_FAST_REALIZE"] = "1" if fast else "0"
    grid = OutputGrid(sr=SR, tatum_len=TATUM, n_slots=n_slots, s_phase=S_PHASE)
    tape = TapeNode(grid=grid, M=1, clamps=ClampSet())
    O = np.ones((1, n_slots))
    sched, meta = realize_batch(O, tape, fstate, index, clamp=clamp_obj)
    return [[int(x["out_slot"]), int(x["src_track"]), int(x["src_unit"]),
             int(x["section"]), float(x["mass"])] for x in sched.placements], meta["starved"]

batch_fast, batch_starv_fast = _run_batch_impl(True, clamp_partial)
batch_orig, batch_starv_orig = _run_batch_impl(False, clamp_partial)
os.environ.pop("ETS_FAST_REALIZE", None)

batch_fast_orig_under_clamp = {
    "nonvacuous": len(batch_fast) > 5,
    "rows_identical": batch_fast == batch_orig,
    "starved_identical": batch_starv_fast == batch_starv_orig,
}

print(json.dumps({
    "lm1_stream": lm1_stream, "lm2": lm2, "neutral_law": neutral_law,
    "lm1_render": lm1_render, "lm_moves": lm_moves, "starvation": starvation,
    "straight_fence": straight_fence,
    "fast_orig_under_clamp": fast_orig_under_clamp,
    "batch_fast_orig_under_clamp": batch_fast_orig_under_clamp,
    "starvation_fallback_coincidence": starvation_fallback_coincidence,
}))
""" % (str(_ROOT), str(_ROOT))


def _dump():
    r = subprocess.run([sys.executable, "-c", _DUMP], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"subprocess failed:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


_D = None


def _d():
    global _D
    if _D is None:
        _D = _dump()
    return _D


# =============================================================================
# LM-1 — carrier-neutral (KILL CONDITION)
# =============================================================================

def test_lm1_neutral_or_absent_clamp_is_byte_identical_streaming():
    """A neutral ClampTerms (openness=0, or empty mask, via clamp0 OR a raw
    direct-construction bypass), `no_clamp()`, and an omitted/`None` clamp all
    produce the SAME rows, the SAME continuation flags, and leave the rng in
    the SAME final state (proving the draw count/order is untouched — a
    neutral clamp must not add or remove a single `rng.uniform` call)."""
    d = _d()["lm1_stream"]
    assert d["nonvacuous"], "the streaming fixture produced too few rows to test"
    assert d["no_starvation_baseline"], "the neutral-law baseline runs must not starve"
    for suffix in ("ab", "ac", "ad"):
        assert d[f"rows_{suffix}"], f"rows differ for case {suffix}"
        assert d[f"cont_{suffix}"], f"continuation flags differ for case {suffix}"
        assert d[f"rng_{suffix}"], (
            f"rng final state differs for case {suffix} — a neutral clamp "
            f"perturbed the consumed random stream")


def test_starvation_fallback_coincides_with_baseline_but_is_not_the_neutral_law():
    """NOT part of the LM-1 kill condition: an all-EXPLICIT-zero mask, and a
    raw ClampTerms(track_mask={}, openness>0) bypass of clamp0, both
    legitimately STARVE on every single choice (they are real, if degenerate,
    restrictions — clamp.py's docstring says so explicitly; `_admits`
    implements prereg §2.1 literally, with no empty-mask special case).
    Because starvation always falls back to the unrestricted set, the
    resulting rows happen to coincide with the unclamped baseline here — an
    honest side-effect of "never a silent no-op", not a second, competing
    neutral-law implementation living in the engine."""
    d = _d()["starvation_fallback_coincidence"]
    assert d["empty_mask_bypass_starves_every_choice"], (
        "a raw empty-mask ClampTerms bypass (openness>0) must starve — it "
        "is not neutral by the engine's literal fence formula")
    assert d["explicit_zero_bypass_starves_every_choice"], (
        "an explicit all-zero-valued mask (openness>0) must starve")
    assert d["starved_sets_identical_fg"], (
        "an empty mask and an explicit all-zero mask must starve identically "
        "-- they are indistinguishable to _admits's dict.get lookup")
    assert d["rows_identical_fg"], "the two starving bypasses must agree with each other"
    assert d["rows_coincide_with_unclamped_baseline_f"], (
        "starvation fallback must reproduce the unrestricted baseline exactly")
    assert d["rows_coincide_with_unclamped_baseline_g"], (
        "starvation fallback must reproduce the unrestricted baseline exactly")


def test_lm1_neutral_clamp_construction_canonicalizes_to_none():
    d = _d()["neutral_law"]
    assert d["openness_zero_is_none"], "openness=0 must canonicalize to None"
    assert d["empty_mask_is_none"], "an empty track_mask must canonicalize to None"
    assert d["no_clamp_is_none"], "no_clamp() must be None"
    assert d["nonneutral_is_object"], (
        "clamp0 must still build a real object for a genuine restriction — "
        "this is not a vacuous always-None constructor")
    assert d["explicit_all_zero_mask_openness_positive_NOT_neutral"], (
        "an EXPLICIT all-zero-valued mask with openness>0 is real (if "
        "extreme) restriction data and must NOT be folded into the empty-"
        "mask neutral bucket")
    assert d["bad_openness_raises"], "openness outside [0,1] must raise ValueError"
    assert d["bad_mask_value_raises"], "a mask value outside [0,1] must raise ValueError"
    assert d["empty_pin_raises"], "a unit_pin naming zero units must raise ValueError"


def test_lm1_neutral_clamp_real_render_byte_identical_audio():
    """A real batch render (Schedule -> audio) with clamp=None vs a
    neutral-canonicalizing clamp0 call vs a raw neutral-bypass ClampTerms:
    identical placement rows AND identical sha256 audio bytes."""
    d = _d()["lm1_render"]
    assert d["n_placements"] > 10, "the render fixture produced too few placements"
    assert d["placements_equal_neutral"], "placement rows differ under a neutral clamp"
    assert d["sha_equal_neutral"], "rendered audio bytes differ under a neutral clamp"
    assert d["placements_equal_neutral2"], (
        "placement rows differ under a raw empty-mask ClampTerms bypass")
    assert d["sha_equal_neutral2"], (
        "rendered audio bytes differ under a raw empty-mask ClampTerms bypass")
    assert d["starved_none_baseline"], "the unclamped baseline must never starve"


def test_positive_control_a_real_fence_measurably_moves_the_output():
    """Non-vacuity check paired with LM-1: this is NOT a mechanism that is
    always a no-op. Fencing to the track the unrestricted measure naturally
    disfavors forces every placement onto it and changes the rendered audio —
    proof the fence is live, not merely proof it is inert at zero."""
    r = _d()["lm1_render"]
    assert r["baseline_never_picks_track1_naturally"], (
        "test fixture assumption broken: the synthetic world must naturally "
        "prefer track 0 unrestricted, or this positive control is meaningless")
    m = _d()["lm_moves"]
    assert m["fenced_tracks_are_exactly_track1"], (
        "a full fence to track 1 must emit ONLY track-1 placements")
    assert m["differs_from_baseline_sha"], (
        "a real, active fence must change the rendered audio — the mechanism "
        "must not be vacuous")
    assert m["starved_false_positive_control"], (
        "track 1 has real candidates in the pool; this fence must not starve")


# =============================================================================
# LM-2 — carrier-typing (KILL CONDITION)
# =============================================================================

def test_lm2_live_tilt_path_rejects_unit_and_time_targets():
    d = _d()["lm2"]
    assert d["col_ok"], "the LIVE tilt gate must accept a 'col' (region) target"
    assert d["unit_raises"], "the LIVE tilt gate must raise TypeError for a 'unit' target"
    assert d["time_raises"], "the LIVE tilt gate must raise TypeError for a 'time' target"


def test_lm2_the_same_unit_target_is_legal_on_clamp_terms():
    d = _d()["lm2"]
    assert d["unit_pin_passes_on_clamp"], (
        "the SAME unit target that raises TypeError on the LIVE tilt path "
        "must be constructible without error on ClampTerms (A-4 typing split)")


# =============================================================================
# Starvation — disclosed, never a silent no-op
# =============================================================================

def test_starvation_is_recorded_and_never_a_silent_no_op():
    d = _d()["starvation"]
    assert d["starved_nonempty"], (
        "an unsatisfiable fence must record STARVED (bar, k, b) events")
    assert d["rows_still_emitted"], (
        "a starved bar must still use the unrestricted set — never a silent "
        "no-op and never empty output")
    assert d["starved_events_are_bar_k_b_triples"], (
        "starvation events must be observable (bar, k, b) triples, not opaque")


# =============================================================================
# Straight-fence sanity (LM-3 groundwork — Train B builds the mode)
# =============================================================================

def test_straight_fence_sanity_full_fence_plus_pin_emits_only_the_pinned_units():
    d = _d()["straight_fence"]
    assert d["nonvacuous"], "the straight-fence fixture produced too few rows"
    assert d["all_within_pin"], (
        "a full fence (openness=1, mask={i:1.0}) with a unit_pin must emit "
        "ONLY units inside the pinned range — including through the "
        "continuation entry, which must be fenced too")
    assert d["more_than_one_unit_used"], (
        "the fixture should exercise more than one pinned unit (weak test "
        "otherwise)")
    assert d["no_starvation"], "a satisfiable full fence must never starve"


# =============================================================================
# Fast/original bit-identity under an ACTIVE clamp (extends the existing
# fast-realize equivalence fixture to the clamped case)
# =============================================================================

def test_choose_fast_and_original_are_bit_identical_under_an_active_clamp():
    d = _d()["fast_orig_under_clamp"]
    assert d["nonvacuous"], "the fast/original clamp comparison produced too few rows"
    assert d["rows_identical"], (
        "_choose_fast and _choose_original diverge under a partial clamp "
        "(mask + pin + field bias)")
    assert d["cont_identical"], (
        "_choose_fast and _choose_original produce different continuation "
        "flags under a partial clamp")
    assert d["starved_identical"], (
        "_choose_fast and _choose_original disagree on which (bar, k, b) "
        "starved under a partial clamp")


def test_batch_realize_fast_and_original_are_bit_identical_under_clamp():
    d = _d()["batch_fast_orig_under_clamp"]
    assert d["nonvacuous"], "the batch clamp comparison produced too few rows"
    assert d["rows_identical"], (
        "the batch (tilt=None) T->0 reduction diverges fast-vs-original "
        "under a partial clamp")
    assert d["starved_identical"], (
        "the batch reduction's starvation events diverge fast-vs-original "
        "under a partial clamp")
