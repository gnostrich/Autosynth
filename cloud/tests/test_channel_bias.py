"""PREREG-channel-bias-squares — the SOFT per-channel bias contract (CI teeth).

The channel-bias mechanism is a SOFT lean folded into the ONE TiltTerms the writer
consumes (``channel_logbias`` on the fiber choice measure). Its two load-bearing
guarantees, pinned here out-of-process (the arch-v6 engine is kept out of the cloud
interpreter, like test_freeze_only_byte_identity):

  BYTE-IDENTITY  an all-zero bias ⇒ ``channel_logbias(...) is None`` ⇒ the tilt is
                 byte-identical to the un-biased tilt ⇒ produced rows AND settled O
                 are bit-identical, bar for bar (⇒ rendered audio is byte-identical,
                 render being I-11 pure).
  PULL           a nonzero bias on a channel MEASURABLY pulls the realized output's
                 provenance toward that channel's track (the Phase-1 H1 result) — so
                 the mechanism is live, not a silent no-op.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


_DUMP = r"""
import sys, json
sys.path.insert(0, r"%s")
sys.path.insert(0, r"%s/architecture-v6")
import numpy as np
from ets.engine.worldfile import load_world
from ets.engine.engine import Engine, resolve_sigma
from ets.panel.lanes import default_lane_vector
from cloud.companion.channel_bias import (channel_logbias, grain_logbias,
                                          field_logbias, track_role_logbias,
                                          channel_tids, default_strength)
from ets.writer.tilt import untilted
from ets.writer.realize import FiberThreader

def _engine(seed=0):
    wf = load_world("demo.etsworld")
    return wf.world, Engine(wf, seed=seed, sigma=resolve_sigma(wf, None))

# all-zero bias must produce NO lean object
w0, e0 = _engine()
tids = channel_tids(w0)
zero_is_none = channel_logbias(np.zeros(len(tids)), tids) is None

# REV2 (bidirectional): a NEGATIVE bias must build a lean with NEGATIVE weights
# (soft damp / down-weight), not None; a positive bias stays positive.
neg = channel_logbias([-1.0] + [0.0] * (len(tids) - 1), tids)
pos = channel_logbias([1.0] + [0.0] * (len(tids) - 1), tids)
neg_is_negative = (neg is not None and tids[0] in neg and neg[tids[0]] < 0.0
                   and all(v < 0.0 for v in neg.values()))
pos_is_positive = (pos is not None and tids[0] in pos and pos[tids[0]] > 0.0)

# byte-identity: unbiased writer vs writer fed the all-zero lean, bar for bar
wa, ea = _engine(); wb, eb = _engine()
ua = default_lane_vector(wa.M); ub = default_lane_vector(wb.M)
identical = True
for _ in range(6):
    ra = ea.writer.write_bar(tilt=ea._tilt_for(ua))
    clog = channel_logbias(np.zeros(len(tids)), tids)     # -> None
    rb = eb.writer.write_bar(tilt=eb._tilt_for(ub, channel_logbias=clog))
    if ra.rows != rb.rows or not np.array_equal(ra.O, rb.O):
        identical = False; break

# pull: bias channel 0 hard; measure track-0 provenance fraction vs baseline
def _frac(clog, n=48):
    w, e = _engine()
    u = default_lane_vector(w.M)
    tot = hit = 0
    for _ in range(n):
        r = e.writer.write_bar(tilt=e._tilt_for(u, channel_logbias=clog))
        for (_s, tid, _u, _sec, _m) in r.rows:
            tot += 1; hit += (int(tid) == tids[0])
    return hit / tot if tot else 0.0

base = _frac(None)
bias = _frac(channel_logbias([1.0] + [0.0]*(len(tids)-1), tids))

# ---- REV3 UNIT grain -----------------------------------------------------
strength = default_strength()
UID = 20            # a real pool unit_id on demo.etsworld
# a UNIT bias builds a non-None per-unit weight; empty / all-zero build None
unit_w = grain_logbias({UID: 0.5})
unit_nonnull = (unit_w is not None and unit_w.get(UID) == strength * 0.5)
unit_empty_none = (grain_logbias({}) is None and grain_logbias({UID: 0.0}) is None)

# UNIT + TRACK together SUM on a shared candidate: field_logbias carries both grains
# on the ONE TiltTerms; the per-candidate addend for a candidate in BOTH maps is the
# SUM (exactly what realize._choose resolves: tw.get(tid)+uw.get(uid)).
TID = int(tids[0])
tw = channel_logbias([1.0] + [0.0]*(len(tids)-1), tids)   # {TID: strength}
uw = grain_logbias({UID: 1.0})                            # {UID: strength}
field = field_logbias(track=tw, unit=uw)
tt = untilted(w0.M, channel_logbias=field)                # carried on the ONE TiltTerms
carried = tt.channel_logbias
tagged_ok = (isinstance(carried, dict) and set(carried) == {"track", "unit"}
             and carried["track"].get(TID) == strength
             and carried["unit"].get(UID) == strength)
# additive addend for the shared candidate (TID, UID)
addend = carried["track"].get(TID, 0.0) + carried["unit"].get(UID, 0.0)
sum_is_additive = abs(addend - 2.0 * strength) < 1e-9

# all-empty at EVERY grain ⇒ None ⇒ byte-identical (the hard invariant, REV3 form)
field_empty_none = (field_logbias(track=None, unit=None) is None
                    and field_logbias(track={}, unit={}) is None)
we, ee1 = _engine(); _we2, ee2 = _engine()
ue1 = default_lane_vector(we.M); ue2 = default_lane_vector(_we2.M)
field_identical = True
for _ in range(6):
    ra = ee1.writer.write_bar(tilt=ee1._tilt_for(ue1))
    fld = field_logbias(track=None, unit=grain_logbias({}))   # -> None
    rb = ee2.writer.write_bar(tilt=ee2._tilt_for(ue2, channel_logbias=fld))
    if ra.rows != rb.rows or not np.array_equal(ra.O, rb.O):
        field_identical = False; break

# ---- track_role SUB-TRACK grain (PREREG-track-role-bias) -----------------
# builder + tuple-key carrier
tr_w = track_role_logbias({(TID, 0): 0.5})
tr_nonnull = (tr_w is not None and tr_w.get((TID, 0)) == strength * 0.5)
tr_field = field_logbias(track_role=track_role_logbias({(TID, 0): 1.0}))
tr_tt = untilted(w0.M, channel_logbias=tr_field)
tr_carried = tr_tt.channel_logbias
tr_tagged = (isinstance(tr_carried, dict) and set(tr_carried) == {"track_role"}
             and tr_carried["track_role"].get((TID, 0)) == strength)
tr_empty_none = (track_role_logbias({}) is None
                 and field_logbias(track_role=track_role_logbias({(TID, 0): 0.0})) is None)

# THE dodges-the-wall contrast: a PURE role-k bias (ALL tracks in role k) is a
# per-choice-set constant ⇒ INERT (bit-identical); a single (T,k) cell VARIES via
# the track key ⇒ MOVES. Census a real slot role k (instrument _choose to see it).
_stat = {}
_orig = FiberThreader._choose
def _probe(self, k, b, psi, bar):
    r = _orig(self, k, b, psi, bar)
    if r is not None:
        _stat[(int(r[0][0]), int(k))] = _stat.get((int(r[0][0]), int(k)), 0) + 1
    return r
FiberThreader._choose = _probe
_wc, _ec = _engine(); _uc = default_lane_vector(_wc.M)
for _ in range(24):
    _ec.writer.write_bar(tilt=_ec._tilt_for(_uc))
FiberThreader._choose = _orig
def _identical(clog, n=24):
    wa, ea = _engine(); wb, eb = _engine()
    ua = default_lane_vector(wa.M); ub = default_lane_vector(wb.M)
    for _ in range(n):
        ra = ea.writer.write_bar(tilt=ea._tilt_for(ua))
        rb = eb.writer.write_bar(tilt=eb._tilt_for(ub, channel_logbias=clog))
        if ra.rows != rb.rows or not np.array_equal(ra.O, rb.O):
            return False
    return True
# CONTESTED cells (headroom both ways) are the ones a one-strength lean can move; the
# MOST-present cell is the most dominant and hardest to dethrone. Rank by headroom.
_role_tot = {}
for (t, k), c in _stat.items():
    _role_tot[k] = _role_tot.get(k, 0) + c
_cells = sorted(_stat, key=lambda c: min(_stat[c], _role_tot[c[1]] - _stat[c]), reverse=True)
(TT, KK) = _cells[0]
# pure role-KK bias (ALL tracks in role KK) must be a per-choice-set constant ⇒ inert
pure_role = field_logbias(track_role=track_role_logbias({(int(t), KK): 1.0 for t in tids}))
tr_pure_role_inert = _identical(pure_role)
# a single (T,k) cell bias MOVES the stream — scan the top contested cells (the grain
# is live if ANY contested cell steers under a damp or amplify lean).
tr_cell_moves = False
for (ct, ck) in _cells[:5]:
    if (not _identical(field_logbias(track_role=track_role_logbias({(ct, ck): -1.0})))
            or not _identical(field_logbias(track_role=track_role_logbias({(ct, ck): 1.0})))):
        tr_cell_moves = True; TT, KK = ct, ck; break

print(json.dumps({"zero_is_none": zero_is_none, "identical": identical,
                  "base": base, "bias": bias, "n_channels": len(tids),
                  "neg_is_negative": neg_is_negative,
                  "pos_is_positive": pos_is_positive,
                  "unit_nonnull": unit_nonnull, "unit_empty_none": unit_empty_none,
                  "tagged_ok": tagged_ok, "sum_is_additive": sum_is_additive,
                  "field_empty_none": field_empty_none,
                  "field_identical": field_identical,
                  "tr_nonnull": tr_nonnull, "tr_tagged": tr_tagged,
                  "tr_empty_none": tr_empty_none,
                  "tr_pure_role_inert": tr_pure_role_inert,
                  "tr_cell_moves": tr_cell_moves}))
""" % (str(_ROOT), str(_ROOT))


def _dump():
    r = subprocess.run([sys.executable, "-c", _DUMP], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"subprocess failed:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_zero_bias_is_byte_identical_and_nonzero_bias_pulls():
    d = _dump()
    assert d["n_channels"] >= 2, "need >=2 channels to test a per-channel pull"
    assert d["zero_is_none"], "all-zero bias must build no lean (None), not an empty tilt"
    assert d["identical"], (
        "all-zero channel bias must leave the writer byte-identical (rows + settled "
        "O bit-identical) — the mechanism is default-off")
    assert d["bias"] >= d["base"] + 0.10, (
        f"a full bias on channel 0 must materially pull provenance toward its track "
        f"(baseline {d['base']:.3f} -> biased {d['bias']:.3f})")


def test_negative_bias_builds_a_down_weight_lean_and_zero_stays_none():
    """REV2 bidirectional: a negative amplify builds a non-None lean whose weights
    are NEGATIVE (soft down-weight / damp), a positive amplify builds positive
    weights, and an all-zero vector STILL builds no lean (None) — so byte-identity
    at neutral is preserved for the widened [-1, 1] range."""
    d = _dump()
    assert d["zero_is_none"], "all-zero bias must still build no lean (None) under REV2"
    assert d["neg_is_negative"], (
        "a negative amplify must build a lean with NEGATIVE log-weights (soft damp), "
        "not None and not positive")
    assert d["pos_is_positive"], "a positive amplify must build a lean with positive log-weights"
    assert d["identical"], "all-zero channel bias must still be byte-identical under REV2"


def test_unit_grain_builds_a_nonnull_weight_and_empty_stays_none():
    """REV3 UNIT grain: a per-unit amplify builds a non-None {unit_id -> β} weight
    (β = LAMBDA['T1p']·amplify, the same derived scale as the track grain); an empty
    or all-zero unit map builds no lean (None), so byte-identity at neutral holds."""
    d = _dump()
    assert d["unit_nonnull"], (
        "a unit amplify must build a {unit_id -> β} weight with β = strength·amplify")
    assert d["unit_empty_none"], (
        "an empty / all-zero unit map must build no lean (None) — byte-identity at zero")


def test_track_and_unit_sum_on_a_shared_candidate_on_one_tiltterms():
    """REV3 single-carrier + additive sum: field_logbias carries BOTH grains on the
    ONE TiltTerms as a tagged {"track","unit"} datum, and a candidate biased at both
    grains gets the SUM addend (β_track[tid] + β_unit[uid]) — exactly what
    realize._choose resolves. All-empty at every grain ⇒ None ⇒ byte-identical."""
    d = _dump()
    assert d["tagged_ok"], (
        "field_logbias must carry both grains on the ONE TiltTerms.channel_logbias "
        "as {'track': {tid->β}, 'unit': {uid->β}} (single carrier, I-1)")
    assert d["sum_is_additive"], (
        "a candidate biased at BOTH grains must get the SUM addend β_track+β_unit")
    assert d["field_empty_none"], "an all-empty field (every grain) must build None"
    assert d["field_identical"], (
        "an all-empty REV3 field must leave the writer byte-identical (rows + settled "
        "O bit-identical) — the hard invariant, unchanged")


def test_track_role_grain_builds_tuple_keyed_carrier_and_empty_stays_none():
    """PREREG-track-role-bias: the (track, role) SUB-TRACK grain builds a
    {(track_id, role_k) -> β} weight (β = strength·amplify), carried on the ONE
    TiltTerms.channel_logbias as {"track_role": {(tid, k): β}} (tuple keys survive the
    boundary). An empty / all-zero cell map builds None (byte-identity at zero)."""
    d = _dump()
    assert d["tr_nonnull"], "a (track,role) amplify must build a {(tid,k) -> β} weight"
    assert d["tr_tagged"], (
        "field_logbias must carry the sub-track grain as {'track_role': {(tid,k): β}} "
        "on the ONE TiltTerms with the tuple key intact (single carrier, I-1)")
    assert d["tr_empty_none"], "an empty / all-zero cell map must build None"


def test_track_role_dodges_the_role_wall_pure_role_inert_but_cell_moves():
    """The load-bearing contrast (PREREG-track-role-bias): a PURE role-k bias (ALL
    tracks in role k, equal) is a per-choice-set CONSTANT ⇒ byte-identical (inert, the
    measured role wall), while a single (T, k) cell bias VARIES within the set via the
    track key ⇒ it MOVES the stream. Same grain — the difference is one track vs all."""
    d = _dump()
    assert d["tr_pure_role_inert"], (
        "a pure role-k bias (every track in role k) must be bit-identical to baseline "
        "— a per-choice-set constant cancels (the role wall)")
    assert d["tr_cell_moves"], (
        "a single (track, role) cell bias must MOVE the stream — it varies within the "
        "role-k choice set via the track key, so it dodges the wall")
