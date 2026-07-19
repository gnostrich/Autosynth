"""PREREG-field-bias-REV3 Phase B — the PER-TRACK unit pool (CI teeth).

The field drills TRACK -> UNITS, so each track needs its OWN units. The engine's
``role_unit_pool`` keeps a GLOBAL top-N per ROLE ranked by ``B[i, band]``; on a
degenerate anchor matrix B (k=1: every anchor ranks the bands near-identically) ONE
track's bands sweep the top-N of EVERY role, so filtering the role pools by
``track_id`` leaves the OTHER tracks EMPTY even though they own real units (the live
bug: all role pools were 24 units, all ``track_id 0``). ``engine_bridge.track_unit_pool``
fixes this at the INPUT level (read-only, pre-Gibbs, byte-identical to audio) by keying
the pool on the unit's OWN track — ground-truth provenance, independent of B's
degeneracy.

Teeth:
  MEMBERSHIP  every unit in track T's pool has ``track_id == T``.
  NON-EMPTY   every track with real units gets a non-empty pool (the fix's whole point).
  CONTRAST    the OLD move (a global top-N role pool filtered by ``track_id``) leaves
              non-dominant tracks EMPTY on a degenerate-but-armed B — the exact bug.
"""
from __future__ import annotations

import types

import numpy as np

from cloud.companion.engine_bridge import track_unit_pool, anchor_profile_armed


def _world(B, tracks):
    """A minimal frozen-world stand-in: track_unit_pool reads only ``world.fstate.B``
    and ``world.tracks[i].{track_id, provenance_index}`` — the SAME frozen inputs
    role_unit_pool uses. ``tracks`` = [(track_id, [unit_id...], [band...]), ...]."""
    fstate = types.SimpleNamespace(B=np.asarray(B, dtype=float))
    trks = [types.SimpleNamespace(
                track_id=tid,
                provenance_index={"unit_id": np.asarray(uids, dtype=np.int64),
                                  "band": np.asarray(bands, dtype=np.int64)})
            for (tid, uids, bands) in tracks]
    return types.SimpleNamespace(fstate=fstate, tracks=trks)


# DEGENERATE-BUT-ARMED B: track 0's bands (0,1) carry the globally-largest anchor mass
# in EVERY anchor row, so a global top-N-per-role pool fills with track 0 for every
# role. B still distinguishes bands (armed), so the pools are served — the live-set
# condition exactly.
_B = [[0.90, 0.85, 0.20, 0.10, 0.30, 0.15],
      [0.80, 0.75, 0.15, 0.25, 0.12, 0.28]]          # M=2 anchors, n_bands=6
_TRACKS = [(0, [10, 11], [0, 1]),                    # track 0 -> bands 0,1 (dominant)
           (1, [20, 21], [2, 3]),                    # track 1 -> bands 2,3
           (2, [30, 31], [4, 5])]                    # track 2 -> bands 4,5


def _old_role_pool_filtered(B, tracks, top_n, track_id):
    """The OLD move the FE used: role i's pool = ALL units ranked by B[i, band], top_n
    (exactly ets.role_unit_pool's ranking), then filter by track_id. Replicated inline
    so the test is hermetic (no arch-v6 import) and bites on the real bug."""
    B = np.asarray(B, dtype=float)
    M = B.shape[0]
    units = []
    for (tid, uids, bands) in tracks:
        for uid, band in zip(uids, bands):
            units.append((int(uid), int(tid), int(band)))
    got = []
    for i in range(M):
        ranked = sorted(units, key=lambda u: -float(B[i, u[2]]))[:top_n]
        got += [u for u in ranked if u[1] == track_id]
    return got


def test_track_unit_pool_membership_and_nonempty():
    w = _world(_B, _TRACKS)
    assert anchor_profile_armed(w.fstate.B), "the fixture world must be ARMED (B varies)"
    tp = track_unit_pool(w)
    assert set(tp) == {0, 1, 2}, f"a pool per track expected, got {set(tp)}"
    for tid, entries in tp.items():
        assert entries, f"track {tid} pool is EMPTY — the fix must give every track units"
        # MEMBERSHIP: every unit belongs to its own track (ground-truth provenance)
        assert all(int(tt) == int(tid) for (_u, tt, _b, _p) in entries), \
            f"track {tid} pool contains foreign-track units"
        # entry shape mirrors role_unit_pool: (unit_id, track_id, band, profile=B[:,band])
        uid, tt, band, prof = entries[0]
        assert isinstance(uid, int) and int(tt) == int(tid)
        assert np.asarray(prof).shape == (2,), "profile must be B[:, band] (length M)"
    # the exact units, per track (no cross-contamination)
    assert sorted(u for (u, _t, _b, _p) in tp[1]) == [20, 21]
    assert sorted(u for (u, _t, _b, _p) in tp[2]) == [30, 31]


def test_old_role_pool_filter_concentrates_but_track_pool_does_not():
    """The bug + the fix, side by side on the SAME degenerate-but-armed world."""
    w = _world(_B, _TRACKS)
    # OLD: a small global top-N role pool filtered by track leaves tracks 1,2 EMPTY,
    # because track 0's bands sweep the top of every role.
    assert _old_role_pool_filtered(_B, _TRACKS, top_n=2, track_id=0), \
        "sanity: the dominant track 0 IS present in the old role-pool filter"
    assert _old_role_pool_filtered(_B, _TRACKS, top_n=2, track_id=1) == [], \
        "the OLD role-pool-filtered move must starve non-dominant track 1 (the bug)"
    assert _old_role_pool_filtered(_B, _TRACKS, top_n=2, track_id=2) == [], \
        "the OLD role-pool-filtered move must starve non-dominant track 2 (the bug)"
    # NEW: the per-track pool gives tracks 1 and 2 their own units.
    tp = track_unit_pool(w)
    assert tp[1] and tp[2], "track_unit_pool must give every track its own units (the fix)"


def test_track_unit_pool_caps_top_n():
    """The disclosed navigable cap (top_n): a track with more units than the cap keeps
    exactly top_n, so a huge track stays navigable."""
    many = list(range(200))
    w = _world([[1.0] * 8, [0.5] * 8], [(0, many, [i % 8 for i in many])])
    # armed? rows are flat here -> not armed; force a spread B so it's a real test
    w = _world([[1.0, 0.1] + [0.2] * 6, [0.3, 0.9] + [0.1] * 6],
               [(0, many, [i % 8 for i in many])])
    tp = track_unit_pool(w, top_n=48)
    assert len(tp[0]) == 48, f"top_n cap must hold, got {len(tp[0])}"
