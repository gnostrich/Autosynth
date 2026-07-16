"""STAGE-0 shadow drift-meter split (directive-v1 feature 2): slide[g] +
loop[g] tests.

  H-4  gauge-scramble invariance to machine precision for BOTH meters, proven
       NON-VACUOUS: for each invariance a gauge-COVARIANT mutant (the exact
       failure mode the test exists to catch) is shown to bite.
  H-3  delete-the-meters => bit-identical audio: byte-equality on a fixture
       schedule rendered with the shadow trace computed vs stubbed, plus the
       structural tooth (no module on the F/writer/render audio path imports
       ets.meters — deleting the meters CANNOT change audio), each with a
       bite.

Both meters are read-only instruments (I-5, I-14): the structural side is the
extended _check_i14 manifest sweep; here the value-only contract is asserted
behaviorally (inputs byte-identical after metering).
"""
from __future__ import annotations
import importlib.util
import inspect
import os
import numpy as np

import importlib

# module objects (the package __init__ re-exports same-named FUNCTIONS, so an
# `import ... as` attribute lookup would shadow the modules; import_module is
# unambiguous — same idiom as the I-14 manifest sweep).
GS = importlib.import_module("ets.meters.gauge_slide")
GL = importlib.import_module("ets.meters.gauge_loop")
from ets.meters.holonomy import signed_increment

S = 8  # metrical-circle cardinality used by the fixtures (worlds pass their own)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

def _varying_bar_O(n_bars=5, M=5, seed=42):
    """Settled-occupancy fixture with genuinely varying per-bar role masses
    (detailed balance broken), so the antisymmetrized loop defect is nonzero
    and the invariance tests below are non-vacuous."""
    rng = np.random.default_rng(seed)
    return rng.random((M, S * n_bars)) ** 3 + 1e-3


def _roll_bar_phase(O, c):
    """GLOBAL metrical-phase gauge action: roll every bar's slot axis by the
    same c (a re-choice of the downbeat origin)."""
    M, n = O.shape
    out = np.empty_like(O)
    for i in range(n // S):
        out[:, i * S:(i + 1) * S] = np.roll(O[:, i * S:(i + 1) * S], c, axis=1)
    return out


# --------------------------------------------------------------------------
# slide[g] — behaviour
# --------------------------------------------------------------------------

def test_slide_key_reports_z12_displacement_from_home():
    # composed increments, reduced to the Z_12 minimal signed representative.
    r = GS.slide_key([0, 11, 10])
    assert np.allclose(r.per_bar, [0, -1, -2])          # downward steps
    r = GS.slide_key([0, 7])
    assert np.allclose(r.per_bar, [0, -5])              # +7 == -5 on Z_12
    # winding accumulates then is quotiented: four +4 steps = +16 -> +4 in Z_12
    r = GS.slide_key([0, 4, 8, 0, 4])
    assert np.allclose(r.per_bar, [0, 4, -4, 0, 4])


def test_slide_phase_charge_zero_iff_no_unabsorbable_slide():
    # constant frame: no slide, charge exactly 0 at every bar.
    r = GS.slide_phase(np.full(6, 2.0), S)
    assert np.all(r.per_bar == 0.0)
    # a mid-trajectory half-circle jump: charge = 1 - |t_home - t_moved|/T.
    r = GS.slide_phase([0, 0, 0, 4, 4, 4], S)
    assert np.allclose(r.per_bar, [0, 0, 0, 0.5, 0.8, 1.0])
    # bounded in [0, 1].
    rng = np.random.default_rng(7)
    r = GS.slide_phase(rng.random(64) * S, S, mass=rng.random(64) + 0.1)
    assert np.all(r.per_bar >= 0.0) and np.all(r.per_bar <= 1.0)


def test_slide_phase_mass_weighting_participates():
    # same trajectory, mass concentrated on the moved bars -> higher charge is
    # impossible (charge is symmetric in which side holds the mass), but the
    # value must CHANGE vs uniform: the masses are genuinely read.
    traj = [0, 0, 4, 4]
    uniform = GS.slide_phase(traj, S).per_bar[-1]
    skewed = GS.slide_phase(traj, S, mass=[3.0, 3.0, 1.0, 1.0]).per_bar[-1]
    assert abs(uniform - skewed) > 1e-6


# --------------------------------------------------------------------------
# slide[g] — H-4 gauge-scramble invariance (machine precision) + bites
# --------------------------------------------------------------------------

def test_h4_slide_key_global_transposition_scramble_exact():
    rng = np.random.default_rng(1)
    for _ in range(20):
        traj = rng.integers(0, 12, size=16)
        c = int(rng.integers(1, 12))
        a = GS.slide_key(traj).per_bar
        b = GS.slide_key((traj + c) % 12).per_bar
        assert np.max(np.abs(a - b)) == 0.0             # EXACT


def test_h4_slide_phase_global_phase_scramble_machine_precision():
    rng = np.random.default_rng(2)
    worst = 0.0
    for _ in range(20):
        traj = rng.random(24) * S
        mass = rng.random(24) + 0.05
        delta = float(rng.random() * S)
        a = GS.slide_phase(traj, S, mass).per_bar
        b = GS.slide_phase((traj + delta) % S, S, mass).per_bar
        worst = max(worst, float(np.max(np.abs(a - b))))
    assert worst < 1e-12, f"phase-slide gauge deviation {worst}"


def test_h4_slide_phase_global_loudness_scramble_machine_precision():
    rng = np.random.default_rng(3)
    traj = rng.random(24) * S
    mass = rng.random(24) + 0.05
    a = GS.slide_phase(traj, S, mass).per_bar
    b = GS.slide_phase(traj, S, mass * 137.5).per_bar
    assert np.max(np.abs(a - b)) < 1e-12


def test_h4_slide_bite_gauge_covariant_mutants():
    """Non-vacuity: gauge-COVARIANT mutants must be distinguished by the same
    scrambles the real meters survive."""
    rng = np.random.default_rng(4)
    traj_i = rng.integers(0, 12, size=16)
    c = 5

    # mutant A: reads the ABSOLUTE frame (home = absolute 0) instead of
    # composing increments — covariant under a global transposition.
    def mutant_key(v):
        return signed_increment(np.asarray(v, float), 12.0)
    assert np.max(np.abs(mutant_key(traj_i) - mutant_key((traj_i + c) % 12))) > 0.0

    # mutant B: the phase charge with the gauge quotient REMOVED (Re instead of
    # |.| — "forgot the quotient", the exact H-4 failure mode).
    def mutant_phase(v, mod):
        x = np.asarray(v, float) / mod
        z = np.cumsum(np.exp(1j * 2 * np.pi * x))
        return 1.0 - np.real(z) / np.arange(1, len(x) + 1)
    traj_f = rng.random(24) * S
    delta = 1.234
    dev = np.max(np.abs(mutant_phase(traj_f, S)
                        - mutant_phase((traj_f + delta) % S, S)))
    assert dev > 1e-3, "covariant phase mutant did not bite"


# --------------------------------------------------------------------------
# loop[g] — behaviour
# --------------------------------------------------------------------------

def test_loop_g_zero_on_degenerate_and_symmetric_traffic():
    rng = np.random.default_rng(5)
    # fewer than 3 committed bars: no orientation-odd cycle exists.
    assert np.all(GL.loop_g(rng.random((5, S * 2)) + 0.01, S) == 0.0)
    # identical bars (detailed balance): both orientations close equally.
    base = rng.random((5, S)) + 0.1
    lg = GL.loop_g(np.tile(base, (1, 4)), S)
    assert np.max(np.abs(lg)) < 1e-12


def test_loop_g_nonzero_on_orientation_asymmetric_committed_traffic():
    lg = GL.loop_g(_varying_bar_O(), S)
    assert lg[0] == 0.0 and lg[1] == 0.0
    assert np.max(np.abs(lg[2:])) > 1e-5, \
        "loop_g vanished on genuinely curved committed traffic (vacuous meter)"


def test_loop_g_trailing_partial_bar_is_not_a_node():
    O = _varying_bar_O(n_bars=4)
    lg_full = GL.loop_g(O, S)
    lg_trunc = GL.loop_g(np.hstack([O, O[:, : S // 2]]), S)  # + partial bar
    assert np.array_equal(lg_full, lg_trunc)


# --------------------------------------------------------------------------
# loop[g] — H-4 gauge-scramble invariance (machine precision) + bite
# --------------------------------------------------------------------------

def test_h4_loop_global_phase_roll_machine_precision():
    O = _varying_bar_O()
    lg = GL.loop_g(O, S)
    assert np.max(np.abs(lg)) > 1e-5                     # non-vacuous
    for c in (1, 3, 5):
        dev = np.max(np.abs(lg - GL.loop_g(_roll_bar_phase(O, c), S)))
        assert dev < 1e-12, f"loop_g phase-roll deviation {dev}"


def test_h4_loop_global_loudness_scramble_machine_precision():
    O = _varying_bar_O()
    lg = GL.loop_g(O, S)
    dev = np.max(np.abs(lg - GL.loop_g(O * 73.1, S)))
    assert dev < 1e-12, f"loop_g loudness deviation {dev}"


def test_h4_loop_global_anchor_relabeling_machine_precision():
    O = _varying_bar_O()
    lg = GL.loop_g(O, S)
    perm = np.random.default_rng(6).permutation(O.shape[0])
    dev = np.max(np.abs(lg - GL.loop_g(O[perm], S)))
    assert dev < 1e-12, f"loop_g anchor-relabel deviation {dev}"


def test_h4_loop_bite_gauge_covariant_mutant():
    """Non-vacuity: a loop meter with a NON-circular (linear) bar metric is
    covariant under the phase roll and must be distinguished."""
    from ets.meters.holonomy import loop_defect

    def mutant_loop(O):
        pis, ms = GL.bar_blocks(O, S)
        p = np.arange(S)
        C_lin = np.abs(p[:, None] - p[None, :]) / float(S)   # NOT circular
        n = len(pis)
        out = np.zeros(n)
        for t in range(2, n):
            fwd = list(range(t + 1)) + [0]
            rev = [0] + list(range(t, 0, -1)) + [0]
            coup = {(a, b): GL.star_edge(pis, ms, a, b)
                    for cyc in (fwd, rev) for a, b in zip(cyc[:-1], cyc[1:])}
            out[t] = (loop_defect([C_lin] * n, ms, coup, fwd)
                      - loop_defect([C_lin] * n, ms, coup, rev))
        return out

    O = _varying_bar_O()
    dev = np.max(np.abs(mutant_loop(O) - mutant_loop(_roll_bar_phase(O, 3))))
    assert dev > 1e-9, "covariant loop mutant did not bite"


# --------------------------------------------------------------------------
# H-3 — delete-the-meters => bit-identical audio (shadow property)
# --------------------------------------------------------------------------

def _load_generate_batch_module():
    """Load scripts/generate_batch.py (the sidecar's production site) so the
    trace is tested WHERE it is produced, not on a copy."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "scripts", "generate_batch.py")
    spec = importlib.util.spec_from_file_location("gb_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture_schedule_and_bank(seed=1111):
    """A fixture schedule with TWO non-identity sections (so the per-bar gauge
    frame is non-trivial) + its source bank; 4 bars of 4 slots (s_phase=4)."""
    from ets.render.schedule import Schedule, Section, Gauge, PLACEMENT_DTYPE
    from ets.render.sources import SourceUnit, SourceUnitBank

    rng = np.random.default_rng(seed)
    s_phase, n_bars, L = 4, 4, 64
    n_slots = s_phase * n_bars
    bounds = np.arange(n_slots + 1, dtype=np.int64) * L
    bank = SourceUnitBank(sr=44100)
    rows = []
    for uid in range(n_slots):
        aud = rng.standard_normal(L)
        bank.add(SourceUnit(track_id=0, unit_id=uid, band=0,
                            src_start=0, src_end=L, audio=aud, sr=44100))
        sec = 0 if uid < n_slots // 2 else 1
        rows.append((uid, 0, uid, sec, 0.2 + 0.05 * uid))
    placements = np.array(rows, dtype=PLACEMENT_DTYPE)
    sections = (Section(0, 0, n_slots // 2, Gauge(phase_shift=0.25,
                                                  loudness_scale=0.7)),
                Section(1, n_slots // 2, n_slots, Gauge(phase_shift=0.1,
                                                        loudness_scale=0.9)))
    sched = Schedule(sr=44100, slot_boundaries=bounds,
                     placements=placements, sections=sections)
    O = rng.random((5, n_slots)) + 1e-3      # settlement-side fixture coupling
    return sched, bank, O, s_phase


def test_h3_meters_computed_vs_stubbed_bit_identical_audio():
    from ets.render.render import render

    gb = _load_generate_batch_module()
    sched, bank, O, s_phase = _fixture_schedule_and_bank()

    # STUBBED: no meter runs anywhere near the render.
    audio_stub, _ = render(sched, bank)

    # COMPUTED: the full shadow trace (the sidecar's own code path) runs on the
    # schedule + settled coupling FIRST; render after.
    before_p = sched.placements.tobytes()
    before_O = O.tobytes()
    trace = gb.gauge_trace(sched, O, s_phase)
    audio_met, _ = render(sched, bank)

    # byte-equality: the meters are pure shadow — deleting them changes nothing.
    assert audio_met.tobytes() == audio_stub.tobytes(), \
        "H-3 violated: computing the shadow meters changed the rendered audio"

    # read-only contract: metering left its inputs byte-identical.
    assert sched.placements.tobytes() == before_p
    assert O.tobytes() == before_O

    # trace format sanity (the registered sidecar shape).
    n_bars = sched.n_out_slots // s_phase
    assert trace["shadow"] is True
    assert trace["registry_id"] == "meter-split-gauge-slide-loop-2026-07-15"
    for key in ("slide_key_disp", "slide_phase_charge", "loop_g",
                "bar_settled_mass"):
        assert len(trace["per_bar"][key]) == n_bars
    # schedule-side mass: sum(mass^2) per bar, exact (registry amendment).
    p = sched.placements
    m0 = float(np.sum(p["mass"][(p["out_slot"] >= 0)
                                & (p["out_slot"] < s_phase)] ** 2))
    assert abs(trace["per_bar"]["bar_settled_mass"][0] - m0) < 1e-15

    # BITE: a "meter" that mutates its input WOULD be caught by the byte check.
    sched_mut, bank_mut, _, _ = _fixture_schedule_and_bank()
    sched_mut.placements["mass"][3] *= 1.5           # the mutation a shadow
    audio_mut, _ = render(sched_mut, bank_mut)       # meter must never make
    assert audio_mut.tobytes() != audio_stub.tobytes(), \
        "H-3 byte-equality check is vacuous (a mutated schedule was not seen)"


def test_h3_structural_no_audio_path_module_imports_meters():
    """Deleting ets.meters cannot change audio because nothing on the audio
    path references it: AST import scan of the functional, writer, and render
    packages (the settle->realize->render chain)."""
    from tests.invariants.manifest import _imported_modules
    import ets.functional.f, ets.functional.solver, ets.functional.ot, \
        ets.functional.anchors
    import ets.writer, ets.writer.tape, ets.writer.settle, ets.writer.realize
    import ets.render.render, ets.render.schedule, ets.render.sources, \
        ets.render.provenance

    audio_path = [
        ets.functional.f, ets.functional.solver, ets.functional.ot,
        ets.functional.anchors,
        ets.writer, ets.writer.tape, ets.writer.settle, ets.writer.realize,
        ets.render.render, ets.render.schedule, ets.render.sources,
        ets.render.provenance,
    ]

    def _meter_imports(src):
        return sorted(m for m in _imported_modules(src)
                      if "meters" in m.split("."))

    for mod in audio_path:
        hits = _meter_imports(inspect.getsource(mod))
        assert not hits, (
            f"H-3 structural: audio-path module {mod.__name__} imports the "
            f"meters package: {hits} (a deleted meter would change audio)")

    # BITE: absolute and relative meter imports are both flagged.
    assert _meter_imports("from ets.meters import loop_g\n")
    assert _meter_imports("from ..meters import gauge_slide\n")
