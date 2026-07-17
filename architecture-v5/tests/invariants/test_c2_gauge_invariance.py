"""C-2 (connector faithfulness, CI): machine-precision gauge invariance of
EVERY Layer-0 tilt observable phi_i.

The section gauges (spec s3 gauge group as it acts on the output tape's
sections: global transposition roll on the pitch-class circle, global
beat-phase roll, global loudness scale — loudness is lawful here because phi
reads SETTLED mass, which is settlement output, never the gauge loudness) are
applied to a fixture arrangement; every phi_i must be invariant to <= 1e-12
relative.

NON-VACUOUS by construction:
  (a) every phi_i is NONZERO on the fixture (invariance of a zero function
      proves nothing);
  (b) phi_gauge genuinely reads the gauge variables (three sections, distinct
      frames, moves crossing the pitch-class wrap), so its invariance tests
      the circular/log group metrics, not the absence of gauge reads;
  (c) the SAME harness run on a deliberately gauge-COVARIANT mutant observable
      (reads absolute frames) detects large violation — the check bites, per
      roll direction independently.

Plus the meter law at this interface (I-5 / I-14): the phi module imports
nothing from ets.meters and no holonomy/Hankel identifier appears in its code
— phi_novelty is the connector's tilt statistic, not the novelty-saturation
meter; phi_gauge is not the drift-CV jack.
"""
import ast
import inspect

import numpy as np
import pytest

import ets.connector.phi as phi_mod
from ets.connector.phi import PHI_NAMES, RoleMaps, phi_bars, _circ_dist
from ets.render.schedule import Schedule, Section, Gauge, PLACEMENT_DTYPE

S_PHASE = 4
TOL = 1e-12          # the C-2 precision contract (relative)


# --------------------------------------------------------------------------
# fixture arrangement: 6 bars, 2 bands, 3 sections with distinct gauge frames
# --------------------------------------------------------------------------

def _maps():
    return RoleMaps(
        unit_role={(0, u): [0, 0, 1, 2, 1, 0, 2, 1][u] for u in range(8)}
                  | {(1, u): [1, 2, 2, 0][u] for u in range(4)},
        unit_band={(0, u): 0 for u in range(8)} | {(1, u): 1 for u in range(4)},
        successor={(0, u): (0, u + 1) for u in range(7)}
                  | {(1, u): (1, u + 1) for u in range(3)},
        M=3)


def _fixture_schedule(sections):
    rows = [
        # bar 0: run heads + one continuation
        (0, 0, 0, 0.5), (0, 1, 0, 1.0),
        (1, 0, 1, 2.0),                    # continuity (0,0)->(0,1)
        (2, 0, 5, 0.7),                    # break
        # bar 1: continuation + band-1 continuation
        (4, 0, 6, 1.1), (5, 1, 1, 0.9),    # (1,0)->(1,1) continuity
        (6, 0, 7, 0.6),                    # (0,6)->(0,7) continuity
        # bar 2: reuse (novelty) + fresh
        (8, 0, 0, 1.0),                    # reuse, Delta=2 -> 1/2
        (9, 0, 1, 0.8),                    # continuity + reuse Delta=2
        (10, 1, 2, 1.2),                   # (1,1)->(1,2) continuity
        # bar 3
        (12, 0, 2, 0.4),                   # continuity (0,1)->(0,2)
        (14, 1, 3, 0.3),                   # continuity (1,2)->(1,3)
        # bar 4: reuse across a longer gap
        (16, 0, 5, 0.9),                   # reuse, Delta=4 -> 1/4
        (17, 0, 6, 0.5),                   # continuity + reuse Delta=3
        # bar 5
        (20, 0, 7, 1.3),                   # continuity + reuse Delta=4
        (22, 1, 0, 0.2),                   # reuse Delta=5
    ]
    p = np.zeros(len(rows), dtype=PLACEMENT_DTYPE)
    starts = np.array([s.out_slot_start for s in sections])
    for i, (slot, tid, uid, mass) in enumerate(rows):
        p[i]["out_slot"] = slot
        p[i]["src_track"] = tid
        p[i]["src_unit"] = uid
        p[i]["mass"] = mass
        p[i]["section"] = int(np.searchsorted(starts, slot, side="right") - 1)
    bounds = np.arange(24 + 1, dtype=np.int64) * 100
    return Schedule(sr=44100, slot_boundaries=bounds, placements=p,
                    sections=sections)


def _base_sections():
    # three distinct frames; both transposition moves are > 6 semitones apart
    # on the circle (2 -> 9.5 -> 1.9), so the circular metric differs from the
    # plain one and the wrap is genuinely load-bearing below.
    return (Section(0, 0, 6, Gauge(2.0, 0.10, 1.00)),
            Section(1, 6, 14, Gauge(9.5, 0.85, 0.50)),
            Section(2, 14, 24, Gauge(1.9, 0.05, 2.00)))


def _rolled_sections(sections, dt=0.0, dp=0.0, dl=1.0, wrap=True):
    """The global section-gauge action: transposition roll +dt (pitch-class
    circle; ``wrap`` stores the mod-12 representative, as an engine working on
    the circle would — the same group element either way), phase roll +dp
    (mod 1), loudness scale x dl — applied to EVERY section (a global move)."""
    def _t(t):
        return (t + dt) % 12.0 if wrap else (t + dt)
    return tuple(
        Section(s.section_id, s.out_slot_start, s.out_slot_end,
                Gauge(transpose_semitones=_t(s.gauge.transpose_semitones),
                      phase_shift=(s.gauge.phase_shift + dp) % 1.0,
                      loudness_scale=s.gauge.loudness_scale * dl))
        for s in sections)


ROLLS = [                     # each direction alone, both transpose
    dict(dt=5.0), dict(dt=-7.0), dict(dt=11.5),      # representatives (mod 12)
    dict(dt=5.0, wrap=False), dict(dt=30.7, wrap=False),   # and un-wrapped
    dict(dp=0.25), dict(dp=0.999),
    dict(dl=0.125), dict(dl=8.0),
    dict(dt=3.5, dp=0.4, dl=2.5),
]


def _compute(sections):
    return phi_bars(_fixture_schedule(sections), _maps(), S_PHASE)


def _max_rel_err(pa, pb):
    """max over observables/components of |a-b| / max(1, |a|, |b|)."""
    worst = 0.0
    for name in PHI_NAMES:
        a = np.asarray(pa[name], float)
        b = np.asarray(pb[name], float)
        scale = np.maximum(1.0, np.maximum(np.abs(a), np.abs(b)))
        worst = max(worst, float(np.max(np.abs(a - b) / scale)))
    return worst


def test_fixture_is_non_vacuous_every_phi_nonzero():
    phis = _compute(_base_sections())
    assert np.count_nonzero(phis["region"]) >= 6      # role mass spread
    assert np.all(phis["density"][phis["density"] > 0].size >= 5)
    assert phis["continuity"].sum() >= 6
    assert np.count_nonzero(phis["gauge"]) == 2       # two frame moves
    assert phis["novelty"].sum() > 0.5
    for name in PHI_NAMES:
        assert np.any(np.asarray(phis[name]) != 0.0), f"phi_{name} vacuously 0"


@pytest.mark.parametrize("roll", ROLLS, ids=[str(r) for r in ROLLS])
def test_c2_every_phi_gauge_invariant_to_machine_precision(roll):
    base = _compute(_base_sections())
    rolled = _compute(_rolled_sections(_base_sections(), **roll))
    err = _max_rel_err(base, rolled)
    assert err <= TOL, f"C-2 violation: phi moved {err:.3e} under gauge roll {roll}"


def test_c2_transpose_wrap_is_load_bearing():
    # (a) the fixture's frame moves genuinely differ between circular and
    # plain metrics, so the invariance runs above exercised the wrap...
    ts = [s.gauge.transpose_semitones for s in _base_sections()]
    for t1, t2 in zip(ts[:-1], ts[1:]):
        assert abs(_circ_dist(t2 - t1, 12.0) - abs(t2 - t1)) > 1e-3, \
            "wrap not exercised: circular and plain distance agree on the fixture"

    # (b) ...and a PLAIN-metric phi_gauge (|t2-t1|/12 instead of circular)
    # FAILS invariance under a mod-12 representative roll: the circular group
    # metric is required, not decorative.
    def plain_gauge(sections, s_phase):
        secs = sorted(sections, key=lambda s: s.out_slot_start)
        out = np.zeros(24 // s_phase)
        for s1, s2 in zip(secs[:-1], secs[1:]):
            r = int(s2.out_slot_start) // s_phase
            out[r] += abs(s2.gauge.transpose_semitones
                          - s1.gauge.transpose_semitones) / 12.0
        return out

    a = plain_gauge(_base_sections(), S_PHASE)
    b = plain_gauge(_rolled_sections(_base_sections(), dt=5.0), S_PHASE)
    assert float(np.max(np.abs(a - b))) > 1e-3, \
        "plain-metric mutant survived a wrapping roll — the wrap check is vacuous"


# --------------------------------------------------------------------------
# the check BITES: a gauge-COVARIANT mutant observable is caught by the same
# harness, per roll direction independently.
# --------------------------------------------------------------------------

def _mutant_absolute_frame(schedule, s_phase):
    """Deliberately ILLEGAL observable: reads the ABSOLUTE gauge frame (the
    new section's absolute transposition/phase/loudness at each boundary)
    instead of the frame MOVE. Exists only to prove C-2 has teeth."""
    n_slots = int(schedule.n_out_slots)
    R = n_slots // s_phase
    out = np.zeros(R)
    secs = sorted(schedule.sections, key=lambda s: s.out_slot_start)
    for s1, s2 in zip(secs[:-1], secs[1:]):
        r = int(s2.out_slot_start) // s_phase
        if r < R:
            g = s2.gauge
            out[r] += (abs(g.transpose_semitones) + g.phase_shift
                       + g.loudness_scale)
    return {"gauge": out}


@pytest.mark.parametrize("roll", [dict(dt=5.0), dict(dp=0.25), dict(dl=8.0)],
                         ids=["transpose", "phase", "loudness"])
def test_c2_bites_on_gauge_covariant_mutant(roll):
    base = _mutant_absolute_frame(_fixture_schedule(_base_sections()), S_PHASE)
    rolled = _mutant_absolute_frame(
        _fixture_schedule(_rolled_sections(_base_sections(), **roll)), S_PHASE)
    a, b = base["gauge"], rolled["gauge"]
    scale = np.maximum(1.0, np.maximum(np.abs(a), np.abs(b)))
    err = float(np.max(np.abs(a - b) / scale))
    assert err > 1e-3, (
        f"C-2 harness is vacuous: an absolute-frame observable was not moved "
        f"by gauge roll {roll}")


# --------------------------------------------------------------------------
# meter law at the phi interface (I-5 / I-14)
# --------------------------------------------------------------------------

def _imports_of(src):
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            base = ("." * n.level) + (n.module or "")
            mods.add(base)
            mods.update(base + "." + a.name for a in n.names)
    return mods


def test_phi_module_imports_no_meters_and_no_holonomy_identifiers():
    src = inspect.getsource(phi_mod)
    leaked = sorted(m for m in _imports_of(src) if "meter" in m.lower())
    assert not leaked, f"phi module imports meters (I-5/I-14): {leaked}"

    idents = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Name):
            idents.add(n.id.lower())
        elif isinstance(n, ast.Attribute):
            idents.add(n.attr.lower())
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            idents.add(n.name.lower())
    for tok in ("holonomy", "hankel", "drift", "eoc", "saturation"):
        hits = sorted(i for i in idents if tok in i)
        assert not hits, f"phi module carries meter identifier {hits} (I-5/I-14)"
    # bite: the scan sees real identifiers (novelty, the sanctioned phi, is there)
    assert any("novelty" in i for i in idents), "identifier scan is vacuous"
