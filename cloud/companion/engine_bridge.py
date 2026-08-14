"""LOCAL render bridge — the on-device decoder (CS-4: LOCAL only, never cloud).

All engine/render imports live HERE, isolated from the companion's cloud path
(app.run_train -> cloud.client), so that path stays provably decoder-free. This
module reuses the engine's ``produce_one`` building blocks VERBATIM — the same
``write_bar`` / ``bar_schedule`` / ``render`` / ``_playback_soft_limit`` /
``bar_role_activity`` the native live instrument uses — driven by the SINGLE
region-tilt control. It makes NO engine edits and authors no learned object.

The engine that carries the live playback loudness cap + read-only telemetry is
the ui-v5 engine tree (``architecture-v6/ets``); we put it first on sys.path so
``import ets`` resolves to it. (Root engine-v1 is byte-identical minus the
live-only cap; the native instrument runs on this same tree.)

Realtime note: bar EMISSION is paced to realtime (``_loop``; small fixed lead),
because an unpaced fast host renders far ahead and makes steering audible
minutes late for a realtime listener. Render itself still runs at the host's
speed; a slow box still under-runs and the browser simply buffers. Nothing here
changes the arrangement (H-8): u=0 bars are byte-identical to ``render_offline``.
"""
from __future__ import annotations

import json
import logging
import os
import struct
import sys
import threading
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("ets.companion.bridge")

_ARCH_V6 = str(Path(__file__).resolve().parents[2] / "architecture-v6")

# Anchor-profile arming (Theorem A arming corollary — papers/paper1-typed-control-
# calculus.md §3, papers/paper2-ets-instrument.md §2-3). The frozen anchor
# band-profile matrix ``world.fstate.B`` (M anchors x n_bands) is the coupling's
# band-grouping observable: a unit's anchor profile is its band's column B[:, band],
# and the per-track profile / per-role unit pool are reductions of it. If B carries
# NO information — every anchor row is flat across bands (the band-blind fixed point:
# F is band-blind, so uniform B is its fixed point, and every world trained to date
# sits exactly there) — that observable's constrained fluctuation is identically
# zero. By the fluctuation-dissipation identity two field controls that route
# THROUGH B then degenerate and DISARM (Phase-1A typing table):
#   * the ROLE->UNIT drill — the per-role pools are B-column-ranked, and under
#     uniform B they collapse (tie + top_n insertion order) to a single monopolizing
#     track: a FALSE attribution, so no honest unit pool exists;
#   * the TRACK-square LEAN — a track-bias direction built from the (all-ones) flat
#     profiles collapses onto the global density marginal (phi_density = sum
#     phi_region): a degenerate T1 whose "lean this track" label would lie.
# What STAYS ARMED under uniform B (these do NOT route through B's columns): the
# TRACK->ROLE drill (roles shown by index, no false ranking) and ROLE-square bias
# (a well-typed T1 tilt through the role indicator e_r). This is Theorem A's
# degenerate case, MEASURED off B here, never a policy flag: a world whose B has
# real band spread ARMS all of it automatically, so the pre-registered engine change
# that makes B informative re-arms with no edit here.
_PROFILE_ARMING_EPS = 1e-6   # numerical-noise floor on B's RELATIVE row spread

# PER-UNIT nowplaying DISPLAY SMOOTHING (disclosed; PREREG-field-bias-REV3 Phase B).
# Per-track nowplaying is fresh-per-bar, but only a sparse subset of units is placed in
# any one bar (~60 of N), so a raw per-unit glow would STROBE. A light EMA across bars
# lets a just-played unit FADE over a few bars instead of hard-flickering off. This
# smooths REAL placement telemetry — a unit only ever lights from a bar that actually
# placed it and decays monotonically to 0 once it stops; nothing is fabricated. ALPHA is
# the per-bar attack/decay weight; entries below EPS are pruned so the map stays bounded.
_NP_UNIT_ALPHA = 0.45
_NP_UNIT_EPS = 1e-3


def anchor_profile_armed(B) -> bool:
    """MEASURED arming test for the anchor band-profile observable: ``True`` iff the
    matrix ``B`` (M x n_bands) DISTINGUISHES bands — i.e. some anchor row varies
    across bands above the numerical-noise floor. A uniform/degenerate B (the
    band-blind fixed point, every row flat) returns ``False`` (disarm the unit drill
    + track lean). The spread is measured RELATIVE to B's own magnitude, so it is
    scale-invariant and cannot be gamed by rescaling; it reads only the frozen B and
    nothing downstream."""
    Bm = np.asarray(B, dtype=np.float64)
    if Bm.size == 0:
        return False
    scale = float(np.max(np.abs(Bm)))
    if scale <= 0.0:                                   # all-zero B: no information
        return False
    row_ptp = float((Bm.max(axis=1) - Bm.min(axis=1)).max())
    return (row_ptp / scale) > _PROFILE_ARMING_EPS


def nowplaying_unit_activity(rows) -> dict:
    """READ-ONLY per-UNIT counterpart of ``engine.nowplaying_activity``.

    ``rows`` is the writer's produced schedule for the frontier bar (tuples
    ``(out_slot, src_track, src_unit, section, mass)``). Per-track nowplaying sums mass
    by ``src_track``; this sums by ``src_unit`` and normalizes by the bar's PEAK unit
    mass to a 0..1 activity, so each UNIT square glows by its OWN placement (units within
    a track DIVERGE, unlike the shared per-track glow). Reads produced rows only — no
    settlement / writer / render / F — so audio is byte-identical whether or not it runs.

    Returns ``{unit_id -> 0..1 activity}`` for the units placed this bar (a unit NOT
    placed is simply absent ⇒ the field reads it as 0 = dark)."""
    energy: dict = {}
    for (_slot, _tid, uid, _sec, mass) in rows:
        energy[int(uid)] = energy.get(int(uid), 0.0) + float(mass)
    if not energy:
        return {}
    peak = max(energy.values())
    if peak <= 0.0:
        return {uid: 0.0 for uid in energy}
    return {uid: energy[uid] / peak for uid in energy}


def track_role_activity(rows, O, B, s_phase) -> dict:
    """READ-ONLY per-(TRACK, ROLE) mass reduction of a produced bar — the role-cell glow.

    ``role`` is the SLOT role k the (track, role) bias mechanism keys on. ``place_slot``
    realizes output slot ``s`` from its settled column ``O[:, s_local]``: for each band b
    with energy ``e[b] = (col @ B)[b] > 0`` it emits ONE row of mass ``sqrt(e[b])`` under
    role ``k = argmax(col * B[:, b])`` (the same k ``_choose(k, b)`` keys the addend on).
    Rows within a slot are in band order, so this matches each row to its band by mass
    (two-pointer; a band that placed no unit is simply skipped) and credits the mass to
    ``(row.track_id, k)``. Faithfully reconstructs the mechanism's k from the committed O
    — no settlement / writer / render / F — so audio is byte-identical whether it runs.

    ``rows`` carry the GLOBAL slot ``s = bar*s_phase + s_local``; ``O`` is indexed by the
    LOCAL slot, so ``s_local = s % s_phase``. Returns ``{(track_id, role_k) -> summed mass}``."""
    O = np.asarray(O, dtype=np.float64)
    B = np.asarray(B, dtype=np.float64)
    n_bands = B.shape[1]
    sp = int(s_phase)
    by_slot: dict = {}
    for row in rows:
        by_slot.setdefault(int(row[0]), []).append(row)
    energy: dict = {}
    for sg, rs in by_slot.items():
        s_local = (sg % sp) if sp > 0 else int(sg)
        if s_local < 0 or s_local >= O.shape[1]:
            continue
        col = O[:, s_local]
        e = col @ B                                   # (n_bands,) settled band energy
        bands = [b for b in range(n_bands) if e[b] > 0.0]
        if not bands:
            continue
        bmass = [float(np.sqrt(e[b])) for b in bands]
        bk = [int(np.argmax(col * B[:, b])) for b in bands]
        bi = 0
        for row in rs:                                # rows in band order (subseq of bands)
            m = float(row[4])
            tid = int(row[1])
            while bi < len(bands) and abs(bmass[bi] - m) > 1e-6:
                bi += 1
            if bi < len(bands):
                k = bk[bi]
                bi += 1
            else:
                k = int(np.argmax(col))               # fallback: slot's dominant role
            key = (tid, k)
            energy[key] = energy.get(key, 0.0) + m
    return energy


def track_unit_pool(world, top_n: int = 48) -> dict:
    """READ-ONLY static PER-TRACK unit POOL for the field's TRACK -> UNITS drill.

    A per-track counterpart to ``ets.engine.engine.role_unit_pool``. ``role_unit_pool``
    keeps a GLOBAL top-N of units per ROLE, ranked by ``B[i, band]``; on a DEGENERATE
    anchor matrix B (k=1: every anchor ranks the bands near-identically) ONE track's
    bands sweep the top-N of EVERY role, so filtering the role pools by ``track_id``
    leaves the OTHER tracks EMPTY even though they own real units (the live-set bug:
    all role pools were 24 units, all ``track_id 0``). This pool is keyed by the unit's
    OWN track instead: for each track it takes THAT track's units (from
    ``track.provenance_index``), so membership is GROUND-TRUTH provenance (the track
    owns these units) — independent of B's degeneracy, so every track is non-empty.

    Per-track RANKING (disclosed): band ANCHOR-SALIENCE = ``max_i B[i, band]`` (how
    strongly any anchor claims the unit's band), descending, ties by ``unit_id`` ascending
    (deterministic). CAP (disclosed): ``top_n = 48`` units/track — a slightly larger
    navigable cap than the role pool's 24, since a track's own pool is the whole drill.

    SAME frozen inputs and entry shape as ``role_unit_pool`` (``unit_id, track_id, band,
    profile=B[:, band]``); pure reduction over the frozen world (``fstate.B`` + track
    provenance), computed ONCE, calls NOTHING downstream (pre-Gibbs, byte-identical to
    audio). Returns ``{track_id: [(unit_id, track_id, band, np.ndarray (M,)), ...]}``."""
    B = np.asarray(world.fstate.B, dtype=np.float64)          # (M, n_bands)
    M, n_bands = B.shape
    band_peak = B.max(axis=0) if M > 0 else np.zeros(n_bands)  # (n_bands,) salience
    pools: dict = {}
    for track in world.tracks:
        tid = int(track.track_id)
        prov = track.provenance_index
        uids = np.asarray(prov["unit_id"], dtype=np.int64).tolist()
        bands = np.asarray(prov["band"], dtype=np.int64).tolist()
        units = [(int(uid), int(band)) for uid, band in zip(uids, bands)
                 if 0 <= band < n_bands]
        units.sort(key=lambda ub: (-float(band_peak[ub[1]]), ub[0]))
        pools[tid] = [(uid, tid, band, B[:, band].copy())
                      for (uid, band) in units[:int(top_n)]]
    return pools


# ---------------------------------------------------------------------------
# WAVEMAP (PREREG-waveform-scrub, technical annex) — the READ-ONLY material map
# the TRACKS view draws on: per track, (a) a downsampled |peak| envelope of the
# user's OWN audio file (given material, not engine telemetry), (b) the world's
# STORED unit segmentation in track seconds, (c) each stored unit's STORED role
# assignment q. Pure reduction over the frozen world + the source files it names;
# touches NO engine state, no bank, no settlement, no writer, no F. Read-only.
#
# ==== THE q WALL (prereg "Honest walls", q(role|unit) sourcing) ==============
# The directive requires q from the trained world's STORED assignment, at the
# FINEST STORED level, with NO invented refinement. What the frozen world
# actually stores about units and roles, surveyed exhaustively:
#
#   1. ``world.index.unit_role[(track_id, unit_id)] -> int``  (RealizationIndex,
#      built at world-freeze by ``ets.writer.realize.build_index``): the unit's
#      dominant anchor role. STORED, PER-UNIT, exact — and HARD (an argmax).
#   2. ``world.fstate.pis[t]`` (K_t x M): the trained prototype->anchor coupling.
#      STORED and SOFT — but PER-PROTOTYPE, not per-unit.
#   3. ``world.tracks[t].units / provenance_index``: unit -> (slot, band, phase,
#      source span). NO role, NO prototype label.
#   4. ``world.protos[t]``: prototype masses/costs/histograms/centroids. The
#      per-unit cluster labels from ``roles.extract_prototypes`` are NOT kept.
#
# So the unit->prototype link needed to reach (2) IS NOT STORED anywhere. It can
# only be RE-DERIVED (nearest prototype timbre centroid, the way build_index
# recomputes it internally) — and worse, ``build_index`` does not even use
# ``fstate.pis`` for the role: it re-settles a per-track membership
# (``_track_membership``: 4 ``update_pi`` sweeps from an outer-product init) and
# argmaxes THAT. Serving row-normalized ``pis[t][p(unit)]`` would therefore mean
# (i) inventing an unstored map and (ii) serving a soft vector from a DIFFERENT
# coupling than the one the world's own stored per-unit role came from — a vector
# that can disagree with ``unit_role`` about which role the unit even is. That is
# an invented refinement plus a second role channel. Refused.
#
# DECISION (disclosed on the wire as ``q_source``): q(unit) is the exact
# INDICATOR of the world's own stored per-unit assignment,
#
#     q[k] = 1.0 if k == world.index.unit_role[(track_id, unit_id)] else 0.0
#
# an exact lookup of stored object (1) — normalized by construction (sums to 1),
# real values only, no smoothing, no refinement, no second channel. The DIVERGENCE
# from the directive's wording ("soft role mass") is reported, not papered over:
# no per-unit SOFT role mass exists in the stored world. The softness the directive
# asks for is recovered WHERE IT IS REAL — at the pointer's window, as the
# mass-weighted mixture over the stored units under it,
#     w_r = sum_u m_u * q_u[r] / sum_u m_u,
# every term of which is a stored value. That mixture is the consumer's (the
# TRACKS view's) reduction of these slices; this endpoint serves the stored
# per-unit terms and invents nothing.
#
# If a world carries a MINIMAL index (``unit_role`` empty — the dataclass default),
# NOTHING stored yields a per-slice q, and the wavemap REFUSES honestly (ok:false
# with the reason) rather than fabricate weights.
# ---------------------------------------------------------------------------
_WAVEMAP_VERSION = 1          # sidecar schema version (part of the cache stamp)
_WAVEMAP_N_PEAKS = 800        # envelope buckets per lane (the FE's lane resolution)

# The single wire-level disclosure of WHICH stored object q comes from. Served with
# every wavemap so the honesty of the mapping is auditable from the payload alone.
_WAVEMAP_Q_SOURCE = ("world.index.unit_role[(track_id, unit_id)] — the frozen "
                     "world's STORED per-unit dominant-anchor assignment, served "
                     "as its exact indicator vector (hard by construction; no "
                     "per-unit SOFT role mass is stored — see the q WALL note in "
                     "cloud/companion/engine_bridge.py)")


def unit_role_indicator(world, track_id: int, unit_id: int, M: int):
    """The stored role assignment of ONE unit as an exact indicator (length M).

    Reads ``world.index.unit_role`` ONLY (see the q WALL note above). Returns None
    when the world stores no assignment for that unit — the caller must then refuse,
    never fill in a value."""
    k = world.index.unit_role.get((int(track_id), int(unit_id)))
    if k is None or not (0 <= int(k) < int(M)):
        return None
    q = [0.0] * int(M)
    q[int(k)] = 1.0
    return q


def track_unit_slices(world, track, M: int):
    """The STORED unit segmentation of ONE track, in time order, with stored q.

    ``[[t0_s, t1_s, unit_id, mass, [q_0..q_{M-1}]], ...]`` — one entry per stored
    unit: its REAL stored source span (``provenance_index`` samples / the track's
    own sr), its unit id, its STORED mass, and the stored role indicator. Note the
    ingestion grain: a unit is a (slot, band) cell, so the n_bands units of one
    tatum share that tatum's span — the spans REPEAT by design (that is the world's
    own segmentation, not a bug). Order is (src_start, src_end, unit_id): the
    deterministic time order.

    Returns None (never a partial list, never a filled-in value) if ANY unit of the
    track lacks a stored role, so the caller refuses the whole map honestly."""
    prov = track.provenance_index
    uid = np.asarray(prov["unit_id"], dtype=np.int64)
    ss = np.asarray(prov["src_start"], dtype=np.int64)
    se = np.asarray(prov["src_end"], dtype=np.int64)
    masses = np.asarray(track.masses, dtype=np.float64)
    sr = float(track.sr)
    tid = int(track.track_id)
    order = np.lexsort((uid, se, ss))
    out = []
    for j in order:
        q = unit_role_indicator(world, tid, int(uid[j]), M)
        if q is None:
            return None
        out.append([float(ss[j]) / sr, float(se[j]) / sr, int(uid[j]),
                    float(masses[j]), q])
    return out


def peak_envelope(y, n_samples: int, n_peaks: int = _WAVEMAP_N_PEAKS):
    """Downsample a decoded mono signal to ``n_peaks`` |peak| buckets over the
    track's STORED sample length.

    The time axis is the world's stored ``n_samples`` (the same axis the unit spans
    live on), so lane pixels and slice boundaries cannot drift apart. A bucket with
    no decoded sample available reads 0.0 (honest absence — never interpolated).
    Values are float PCM magnitudes, capped at 1.0 (full scale) and NOT normalized:
    lane heights stay comparable across tracks because that is real information
    about the given material."""
    a = np.abs(np.asarray(y, dtype=np.float64).reshape(-1))
    n = int(n_samples)
    edges = np.linspace(0, n, int(n_peaks) + 1).astype(np.int64)
    peaks = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        seg = a[int(lo):int(hi)]
        peaks.append(min(1.0, float(seg.max())) if seg.size else 0.0)
    return peaks


# ---------------------------------------------------------------------------
# EIGENPANEL (OPEN_ENDS #23; E1/E2) — the object's own control basis.
#
# READ-ONLY, once at world load: authors nothing, mutates no settlement. The
# METHOD reproduces papers/findings/EIGEN-modes-2026-07-18.md exactly (its
# PREREG scratchpad/eigen/PREREG.md, its script scratchpad/eigen/run_eigen.py)
# at a load-time-viable ensemble size — same estimator, same decision rule,
# smaller N (disclosed precision tradeoff below).
#
# CORRECTION ON RECORD (superseding the original directive's wording): the
# "constrained covariance" is NOT the plain sample covariance of the
# observables. That was measured to be WRONG on this very object — the
# marginal covariance is fooled by the P5 finding (continuity is armed-but-
# inert: its marginal variance is the LARGEST of any observable, ~8, yet its
# steering response is ~zero). Variance and response decouple exactly where
# FDT breaks. A covariance-basis panel would render the dead continuity knob
# as the biggest knob in the room — re-committing the disarmed lie inside the
# eigenbasis. Theorem A's actual identity is d<Phi>/du = (1/eps)*Cov|_projected
# — the RESPONSE kernel realizes that projection automatically (a saturated/
# inert lane's response row is measured ~0, whether or not its raw variance
# is large). So the basis here is the SYMMETRIZED RESPONSE KERNEL:
#
#   R_ij = d<Phi_i>/du_j            (central finite difference, common seeds)
#   K_ij = R_ij / sigma_i           (the world's OWN sigma_phi; scale-consistent)
#   Ksym = (K + K^T)/2              (Theorem B: the true tilt-tilt kernel is
#                                     Maxwell-symmetric; the antisymmetric part
#                                     is the D1-D4 sampler-ordering artifact,
#                                     proven RESIDUAL-NULL, so symmetrizing is
#                                     the honest projection, not a fudge)
#
# eigh(Ksym) -> eigenvalues = the honest GAINS (signed: a negative gain is an
# INVERTED response, retained and flagged, never dropped or folded to |.|
# silently). k = eigenvalues whose magnitude clears a MEASURED noise floor.
#
# OBSERVABLE SET (a second wall, found and resolved here): the directive also
# asked for "fill" (region occupancy sum) as its own observable alongside the
# per-anchor region masses. But fill = sum(region masses) EXACTLY, every bar,
# by construction — an exact linear dependency. Folding it into the kernel as
# an extra row/column makes the matrix rank-deficient in a way that, once you
# drop "fill" back out again to build the FORCE (there is no engine lane for
# "aggregate fill" — only the per-anchor region lane exists), breaks exact
# eigenvector orthogonality on the pushed subspace (EP-2 needs push_i . push_j
# == 0 for i != j; algebraically dot(v_i, v_j) restricted to a de-facto
# subspace of an orthonormal basis is NOT itself orthogonal in general, and
# here it provably is only when the dropped coordinate's own component is
# zero, which is not guaranteed for every mode). The clean fix: don't put the
# redundant coordinate in the matrix in the analysis. The kernel is built over
# the actual force-bearing observables only (region_0..M-1, density, cont,
# novelty — exactly ets.panel.lanes' four DIRECTION lanes, minus gauge, which
# is structurally degenerate at v0 and carried at sigma=0 -> its row is the
# explicit zero axis). "fill" is then reported as a DERIVED display quantity
# per surviving mode, fill_i = sum_a v_i[region_a] — which for any mode with
# nonzero eigenvalue is the object's TRUE aggregate-fill loading, not an
# approximation (it's an exact identity: for K symmetric with Ksym*w=0 on the
# "fill minus sum(region)" null direction, every eigenvector of a nonzero
# eigenvalue is orthogonal to that null direction, i.e. v[fill] == sum(v[region])
# — the same number you'd get by including fill as a column and then
# discarding it, without the orthogonality cost). No information is lost;
# the matrix stays exactly the space the force actually pushes.
#
# ENSEMBLE (OPEN_ENDS #23 boot-ensemble fix, 2026-07-18): the authoritative
# E1/E2 run (papers/findings/EIGEN-modes-2026-07-18.md) used N_SEED=24,
# N_BAR=32 (wall ~85-173s/world on that measurement's hardware; measured
# ~40s/world in THIS sandbox via write_bar-only probes, no audio render).
# A previous production default (N_SEED=4, N_BAR=6, chosen to keep this
# synchronous at boot) was found to UNDER-RESOLVE: the null floor is derived
# from THIS SAME finite-difference ensemble by a label-shuffle, so a small
# N_SEED makes the floor estimate itself noisy and it inflates ~22x, collapsing
# a real k=2 world (this demo, informative B) to a false k=1 (one strip, no XY
# pad) — an honest-but-under-powered floor, not a fabrication, but a real
# listener-facing wall (BINDING NOTE, item 5). FIX: the eigenmode computation
# now runs the FULL AUTHORITATIVE ensemble (N_SEED=24, N_BAR=32 below — the
# SAME numbers as the pre-registered findings run, not arbitrarily chosen) in
# a BACKGROUND THREAD started at StreamPlayer construction (see
# StreamPlayer._eigen_worker), off the listener's critical path: first bar /
# first audio is never blocked. world_info() reports "eigen_pending": true
# until the thread lands (compute_eigenmodes itself is UNCHANGED — same
# estimator, same deterministic rng_seed, same JSON encoding; only the
# SCHEDULING moved off the boot path). No fabricated modes are ever emitted —
# a still-pending world reports k=0/modes=[] HONESTLY (distinct from a world
# that measured k=0 for real: the "pending" flag disambiguates the two so the
# FE can show "measuring the object's modes…" rather than a false "k=1
# strip"). The null floor is derived from the SAME finite-difference ensemble
# via a label-shuffle (destroy the +/-h assignment, keep the per-column
# noise) rather than a separate u=0 pool, to avoid a second ensemble's worth
# of bars. Same estimator, same 2-part decision rule (|gain|>floor AND
# |gain|-2*SE>floor via seed bootstrap) throughout.
_EIGEN_N_SEED = 24       # FD ensemble seeds per lane column (authoritative)
_EIGEN_N_BAR = 32        # bars per seed run (authoritative)
_EIGEN_H = 0.75          # FD step, knob units (the deployed interface step)
_EIGEN_N_BOOT = 60       # bootstrap resamples for the eigenvalue SE
# The live pad uses the FULL authoritative 24x32 ensemble (it resolves the real
# multi-mode structure; a smaller ensemble raises the noise floor and collapses k).
# On a single-core container this measurement cannot run concurrently with realtime
# audio without one starving the other, so it is NEVER computed on the playback path:
# the result is measured once off-playback (idle load, or wait_eigen for tools) and
# persisted to a sidecar cache (see StreamPlayer._load_eigen_cache), then read
# instantly on every subsequent load. Audio-first + cached modes, no fight.
_EIGEN_N_NULL = 200      # label-shuffle null draws for the floor
_EIGEN_FLOOR_PCT = 97.5  # null floor percentile of max|eigenvalue|
# MODES-BY-TEMPERATURE (PREREG-temperature-sweep): the T_s grid the auto-sweep measures a
# world's mode-set at, so the pad can reselect its basis as the operator heats. A COARSE even
# spread — the mode count only steps 1->2->3 and the directions are stable across T (measured),
# so a few well-placed points capture the whole story (cold/default/warm/hot) at a fraction of
# a fine sweep's cost. The default T_s=1.0 MUST be in the grid (the pad restores the
# authoritative basis there). The temperatures are INDEPENDENT, so they are measured in
# PARALLEL across processes (see _sweep_one_temp / _sweep_worker), off the audio path, cached.
_SWEEP_T_GRID = [0.5, 1.0, 2.0, 4.0]
_SWEEP_DEFER_POLL = 1.5  # while audio is live, the sweep worker parks before launching heavy
                         # compute (this poll interval) instead of computing — so a one-time
                         # measurement can never starve realtime playback on a constrained
                         # host. It resumes the instant playback pauses.


def _sweep_one_temp(args):
    """Module-level worker for the process pool: measure ONE temperature's mode-set. Runs in a
    SEPARATE process with the pickled (world, sigma) — identical objects, so the modes it
    returns are exactly what a serial measurement would produce, just computed in parallel.
    Pure read-only measurement (temperature_sweep uses fresh probes; sampler/F/world untouched)."""
    world, sigma, M, T, n_seed, n_bar = args
    # self-sufficient in a fresh (spawned) process: put the ui-v5 engine tree on the path
    # before importing, so `import ets` resolves exactly as it does in the server.
    if _ARCH_V6 not in sys.path:
        sys.path.insert(0, _ARCH_V6)
    from cloud.companion.eigen_experimental import temperature_sweep
    r = temperature_sweep(world, sigma, M, [T], n_seed=n_seed, n_bar=n_bar)
    if isinstance(r, dict) and isinstance(r.get("sweep"), list) and r["sweep"]:
        return r["sweep"][0], {k: r[k] for k in ("M", "n_seed", "n_bar", "observable_names")}
    return None, None
_EIGEN_WORD_FLOOR = 0.6  # |loading| a scalar observable needs to earn a word
_EIGEN_WORD_MAP = {"density": "busier", "cont": "steady", "novelty": "fresh"}


def _eigen_obs_names(M: int):
    return [f"region{i}" for i in range(M)] + ["density", "cont", "novelty"]


def _eigen_phi_vec(phi, M: int) -> np.ndarray:
    reg = np.asarray(phi["region"], float).reshape(-1)[:M]
    return np.concatenate([reg, [float(phi["density"]), float(phi["cont"]),
                                 float(phi["novelty"])]])


def _eigen_lane_vector(M: int, region_idx=None, region_val: float = 0.0,
                       density: float = 0.0, cont: float = 0.0, novelty: float = 0.0):
    from ets.panel.lanes import default_lane_vector
    u = default_lane_vector(M)
    u.resize_region(M)
    if region_idx is not None:
        u.u_region[int(region_idx)] = float(region_val)
    u.u_density = float(density)
    u.u_continuity = float(cont)
    u.u_novelty = float(novelty)
    return u


def _eigen_run_mean(world, sigma, u, seed: int, n_bar: int, M: int) -> np.ndarray:
    from ets.writer.tilt import layer0
    from ets.writer.stream import StreamWriter
    tilt = layer0(u, sigma)
    w = StreamWriter(world, seed=int(seed))
    acc = np.zeros(M + 3, dtype=np.float64)
    for _ in range(n_bar):
        acc += _eigen_phi_vec(w.write_bar(tilt=tilt).phi, M)
    return acc / n_bar


def _eigen_node_means(world, sigma, builder, M: int, seed0: int, n_seed: int,
                      n_bar: int, defer=None) -> np.ndarray:
    # ``defer`` (optional callable) is invoked BEFORE each seed's settlement run —
    # the audio-defer seam (same contract as the sweep worker's per-temperature
    # park): heavy measurement yields to live playback at run granularity. None
    # (tests / CLI) computes exactly as before.
    runs = []
    for i in range(n_seed):
        if defer is not None:
            defer()
        runs.append(_eigen_run_mean(world, sigma, builder(), seed0 + i, n_bar, M))
    return np.stack(runs)


def compute_eigenmodes(world, sigma, M: int, n_seed: int = _EIGEN_N_SEED,
                       n_bar: int = _EIGEN_N_BAR, h: float = _EIGEN_H,
                       n_boot: int = _EIGEN_N_BOOT, n_null: int = _EIGEN_N_NULL,
                       floor_pct: float = _EIGEN_FLOOR_PCT,
                       rng_seed: int = 20260718, defer=None) -> dict:
    """The object's native control eigenbasis (E1/E2; see the module-level
    doctring above for the full derivation and the two walls it resolves).
    Read-only: builds fresh ``StreamWriter`` instances at probe leans (never
    touches ``world`` or any live engine state) and returns a JSON-ready dict:

        {"modes": [{"index", "gain", "sign", "composition", "earned_word"}, ...],
         "eigen_floor": float, "k": int, "basis": "response_kernel_sym",
         "observable_names": [...]}

    ``modes`` holds ONLY the surviving (k) modes, sorted by |gain| descending
    (so mode[0]/mode[1] are the top-two for the FE's XY pad). A world with no
    calibration (``sigma is None``) or M<=0 returns an honest empty result —
    no computation attempted, no fabricated axis."""
    M = int(M)
    if sigma is None or M <= 0:
        return {"modes": [], "eigen_floor": None, "k": 0,
                "basis": "response_kernel_sym", "observable_names": []}
    D = M + 3
    names = _eigen_obs_names(M)
    sig = np.concatenate([np.asarray(sigma.region, float).reshape(-1)[:M],
                          [float(sigma.density), float(sigma.cont), float(sigma.novelty)]])
    # sigma=0 (degenerate/disarmed observable, e.g. gauge is excluded entirely,
    # but density/cont/novelty/region CAN legitimately be sigma=0 on some other
    # world): guard the row, don't divide by zero — the explicit-zero-axis
    # treatment the PREREG established for gauge, generalized to any lane.
    sig_safe = np.where(sig > 0.0, sig, 1.0)

    builders = []
    for i in range(M):
        builders.append((
            (lambda ii=i: _eigen_lane_vector(M, region_idx=ii, region_val=+h)),
            (lambda ii=i: _eigen_lane_vector(M, region_idx=ii, region_val=-h))))
    builders.append(((lambda: _eigen_lane_vector(M, density=+h)),
                     (lambda: _eigen_lane_vector(M, density=-h))))
    builders.append(((lambda: _eigen_lane_vector(M, cont=+h)),
                     (lambda: _eigen_lane_vector(M, cont=-h))))
    builders.append(((lambda: _eigen_lane_vector(M, novelty=+h)),
                     (lambda: _eigen_lane_vector(M, novelty=-h))))

    R = np.zeros((D, D))
    node_data = []          # (mp, mm) per column, each (n_seed, D) -- for null + bootstrap
    for j, (up, um) in enumerate(builders):
        mp = _eigen_node_means(world, sigma, up, M, 70000 + j * 1000, n_seed, n_bar,
                               defer=defer)
        mm = _eigen_node_means(world, sigma, um, M, 70000 + j * 1000 + 500, n_seed,
                               n_bar, defer=defer)
        node_data.append((mp, mm))
        R[:, j] = (mp.mean(0) - mm.mean(0)) / (2.0 * h)

    def _ksym(Rmat):
        K = Rmat / sig_safe[:, None]
        K[sig <= 0.0, :] = 0.0
        return 0.5 * (K + K.T)

    Ksym = _ksym(R)
    w_eig, V = np.linalg.eigh(Ksym)
    order = np.argsort(-np.abs(w_eig))
    w_eig, V = w_eig[order], V[:, order]

    rng = np.random.default_rng(rng_seed)
    # NULL FLOOR: shuffle which runs are labeled "+h" vs "-h" per column (destroys
    # the systematic FD signal, preserves the per-column sampling noise) — the
    # response-kernel analogue of "shuffle the series and recompute the spectrum".
    null_max = []
    for _ in range(n_null):
        Rn = np.zeros((D, D))
        for j, (mp, mm) in enumerate(node_data):
            both = np.concatenate([mp, mm], axis=0)
            idx = rng.permutation(both.shape[0])
            half = both.shape[0] // 2
            a, b = both[idx[:half]], both[idx[half:2 * half]]
            Rn[:, j] = (a.mean(0) - b.mean(0)) / (2.0 * h)
        wn, _ = np.linalg.eigh(_ksym(Rn))
        null_max.append(float(np.max(np.abs(wn))))
    floor = float(np.percentile(null_max, floor_pct)) if null_max else 0.0

    # BOOTSTRAP SE: resample the FD seed block per column, recompute, track the
    # spread of the SAME sorted-by-|.| slot across resamples.
    boot = []
    for _ in range(n_boot):
        Rb = np.zeros((D, D))
        for j, (mp, mm) in enumerate(node_data):
            idx = rng.integers(0, n_seed, n_seed)
            Rb[:, j] = (mp[idx].mean(0) - mm[idx].mean(0)) / (2.0 * h)
        wb, _ = np.linalg.eigh(_ksym(Rb))
        boot.append(wb[np.argsort(-np.abs(wb))])
    se = np.std(np.stack(boot), axis=0) if boot else np.zeros(D)

    surviving = []
    for r in range(D):
        lam, s = float(w_eig[r]), float(se[r])
        surviving.append(abs(lam) > floor and abs(lam) - 2.0 * s > floor)
    k = int(sum(surviving))

    modes = []
    out_idx = 0
    for r in range(D):
        if not surviving[r]:
            continue
        vec = V[:, r]
        comp = {names[a]: float(vec[a]) for a in range(D)}
        comp["fill"] = float(sum(vec[a] for a in range(M)))   # derived (see docstring)
        best_key, best_val = None, 0.0
        for key in ("density", "cont", "novelty"):
            v = abs(comp[key])
            if v > best_val:
                best_key, best_val = key, v
        word = _EIGEN_WORD_MAP[best_key] if (best_key and best_val >= _EIGEN_WORD_FLOOR) else None
        gain = float(w_eig[r])
        modes.append({"index": out_idx, "gain": gain, "sign": (1 if gain >= 0.0 else -1),
                      "composition": comp, "earned_word": word})
        out_idx += 1

    return {"modes": modes, "eigen_floor": floor, "k": k,
           "basis": "response_kernel_sym", "observable_names": names}


class StreamPlayer:
    """Owns a loaded world + engine and a produce loop. The settlement input is
    staged by :meth:`set_region` (the region-tilt vector lane) and the typed
    scalar-lane setters (:meth:`set_continuity` / :meth:`set_novelty` /
    :meth:`set_density` / :meth:`set_gauge` / :meth:`set_temperature`); ALL are
    assembled into the ONE ``LaneVector`` the engine's single ``_tilt_for(u)``
    consumes (I-1 / C-3). These are the paper2 §2 conjugate-control lanes — the
    web analog of the desktop panel's per-field lane staging (widget._on_scalar).
    Everything else reads produced state."""

    def __init__(self, world_path: str, seed: int = 0, sigma_path: Optional[str] = None,
                 is_trained: bool = False, eigen_n_seed: int = _EIGEN_N_SEED,
                 eigen_n_bar: int = _EIGEN_N_BAR):
        # Force the ui-v5 engine tree to the FRONT of sys.path (membership isn't
        # enough — root engine-v1 must not shadow it), THEN assert we actually
        # resolved the capped engine. If root ets was imported first, fail LOUD
        # rather than silently render without the eardrum cap / telemetry.
        while _ARCH_V6 in sys.path:
            sys.path.remove(_ARCH_V6)
        sys.path.insert(0, _ARCH_V6)
        import ets.engine.engine as _eng
        if not (hasattr(_eng, "_playback_soft_limit") and hasattr(_eng, "bar_role_activity")):
            raise RuntimeError(
                "companion resolved the ROOT engine-v1 (missing the live playback "
                "cap + telemetry). architecture-v6 must own `import ets`; run via "
                "`python -m cloud.companion` and ensure no root-ets import precedes "
                f"the bridge. resolved: {getattr(_eng, '__file__', '?')}")
        from ets.engine.engine import Engine, resolve_sigma
        from ets.engine.worldfile import load_world

        self.world_path = world_path
        # is_trained reports (truthfully) whether this world is the user's freshly
        # cloud-trained corpus (True) or the founding/demo world (False). The
        # Companion passes True only when it built the player from the trained
        # .etsworld produced by the train->play seam (cloud.companion.train_local).
        self.is_trained = bool(is_trained)
        self.wf = load_world(world_path)                 # ~0.5s (fast); no bank yet
        self.world = self.wf.world
        self.M = int(self.world.M)
        self.sr = int(self.world.sr)
        self.seed = int(seed)
        sigma = resolve_sigma(self.wf, sigma_path)
        self.engine = Engine(self.wf, profile="desktop", seed=self.seed, sigma=sigma)
        self.s_phase = self.engine.writer.s_phase

        self._bank = None                                # lazy: built on first bar (slow)
        self._region = np.zeros(self.M, dtype=np.float32)  # region-tilt vector lane
        # TYPED SCALAR FORCE LANES (paper2 §2; paper1 T1 tilt + T2 thermodynamic).
        # Each is ONE datum of the lane vector u that the engine's SINGLE
        # _tilt_for(u) consumes — never a parallel control channel. Defaults are the
        # lane-spec defaults (direction leans u=0 → identity tilt; T_s=1 sharpness),
        # so an un-driven lane is byte-identical to region-only play (H-8).
        self._u_continuity = 0.0     # VARY   → φ_cont     (T1)
        self._u_novelty = 0.0        # SPREAD → φ_novelty  (T1)
        self._u_density = 0.0        # DENSITY→ φ_density  (T1)
        self._u_gauge = 0.0          # KEY LOCK→ gauge frame (T3; degenerate on v0)
        self._T_s = 1.0              # CHAOS  → temperature (T2, directionless)
        # COVARIANCE-SHAPE (PREREG-sampler-covariance-xy): the OPTIONAL per-
        # eigendirection second-moment anisotropy `a` (length M, stiffest-first).
        # Default None ⇒ ones ⇒ byte-identical draw. It is NOT a φ lane (no σ, no
        # effect on the settled mode); it rides the ONE TiltTerms the writer
        # consumes via _tilt_for(u, a=...), the same single tilt-construction
        # point as every other setter — never a second control channel.
        self._wobble: Optional[np.ndarray] = None
        # CHANNEL-BIAS (PREREG-channel-bias-squares, Phase 1 — SOFT revision): per-
        # channel (=per source track) amplify ∈ [0,1] = bias STRENGTH. Amplify T ⇒
        # a SOFT additive log-weight on track-T's candidate units inside the Layer-0
        # FIBER choice measure (the distribution over pooled channels at each beat);
        # the settlement PERCEIVES the lean and accommodates it, nothing pinned. It
        # rides the SAME ONE TiltTerms the writer consumes (I-1) — no clamp, no new
        # lane. Default None ⇒ no addend ⇒ byte-identical fiber draw.
        from .channel_bias import channel_tids
        self._channel_bias: Optional[np.ndarray] = None
        self._channel_tids = channel_tids(self.world)
        # FIELD-BIAS UNIT GRAIN (PREREG-field-bias-REV3): the per-UNIT amplify map
        # {unit_id -> amplify∈[-1,1]} — the operator's ultimate "channel" (a beat-
        # normalized sound unit). It rides the SAME ONE TiltTerms as the track grain
        # (single carrier, I-1), assembled ADDITIVELY in produce_one_bar via
        # field_logbias. Default None ⇒ no addend ⇒ byte-identical fiber draw.
        self._unit_bias: Optional[dict] = None
        # FIELD-BIAS SUB-TRACK GRAIN (PREREG-track-role-bias, prototype): the per-cell
        # amplify map {(track_id, role_k) -> amplify∈[-1,1]} — lean track T ONLY where
        # it plays the settled role k. Keyed on an EMERGENT structure (roles). Rides
        # the SAME ONE TiltTerms; None ⇒ no addend ⇒ byte-identical.
        self._track_role_bias: Optional[dict] = None
        # LIVE MODE (papers/PREREG-live-mode.md, Train B2 — playable milestone
        # only: straight play under a FULL FENCE; no bridge/arrival/fidelity
        # yet). The ONLY new object this touches is the Part-A ClampTerms
        # carrier, handed to write_bar ALONGSIDE tilt (see live.py) — never a
        # second settlement/casting channel (A-5). "mode":
        #   "off"      — this session has never called a /api/live/* route;
        #                GRID/TRACKS' existing free-blend behavior is
        #                untouched, byte-for-byte (LM-0).
        #   "idle"     — AMENDMENT 2 B-0: entered LIVE, no fence set yet. A
        #                TRANSPORT-GATED HOLD enforced by _loop (see below) —
        #                NOT a neutral/empty ClampTerms (that means NO
        #                restriction = the free blend, exactly what B-0
        #                forbids sounding in LIVE).
        #   "straight" — B-1 amended: a full fence is set; straight play runs.
        #   "bridge"   — a second click while playing: THE BRIDGE (2026-08-14
        #                reframe; see live.py's module docstring section).
        #                ``self._bridge`` (below) carries the journey's own
        #                state; ``self._live["track"]`` stays the SOURCE track
        #                (the release fence's own pin) until arrival flips it.
        self._live: dict = {"mode": "off", "clamp": None, "track": None,
                            "uid_index": {}, "current_unit": None,
                            "current_slice_index": None, "starved": False,
                            "pin_units": (), "bars_elapsed": 0,
                          "slices": (), "core_units": frozenset(),
                          "n_widened": 0, "off_window": 0, "n_cast": 0}
        # THE BRIDGE (default v0: release + pull, no intervention). None
        # whenever mode != "bridge". See live.py's "DEFAULT BRIDGE v0" section
        # for every field's meaning; built fresh by ``_live_bridge_click``.
        self._bridge: Optional[dict] = None
        # DIAGNOSTIC-ONLY wobble history (B-7): achieved column-share vectors
        # from recent STRAIGHT-phase bars, used SOLELY to report the retired
        # profile-distance floor as a readout (never to gate arrival). Bounded
        # exactly like the I-8 gauge-meter windows (reusing _METER_WINDOW
        # below, defined later in __init__ — see its own assignment).
        self._live_lock = threading.Lock()
        self._lock = threading.Lock()
        self._playing = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._bar_index = 0
        # PER-UNIT nowplaying EMA state (display smoothing of REAL per-unit placement
        # telemetry; see _NP_UNIT_ALPHA). {unit_id -> smoothed 0..1 activity}, updated
        # each produced bar, pruned below _NP_UNIT_EPS. Display-only; never touches audio.
        self._nowplaying_unit_ema: dict = {}
        # PER-(TRACK, ROLE) nowplaying EMA state (the drill role-cell glow; same display
        # smoothing as the per-unit map). {(track_id, role_k) -> smoothed 0..1 activity}.
        self._nowplaying_track_role_ema: dict = {}
        # WARMED (OPEN_ENDS #21d): has the produce loop rendered its FIRST bar yet?
        # False until the loop emits (the bank build + first render is the multi-
        # minute cold window a listener would otherwise sit through in silence).
        # Read-only state for /api/world; set once by _loop, never by any input.
        self._warmed = False
        # LOOP HONESTY (OPEN_ENDS #21c): the last produce-loop failure, as a
        # timestamped "<ISO-time> <ExcType>: <msg>" string, or None. Exposed via
        # world_info()/telemetry so a dead engine reports "engine failed: <type>"
        # instead of an infinite silent stream.
        self.last_error: Optional[str] = None
        # latest read-only telemetry (roles 0..1, per-track nowplaying, elapsed
        # seconds) — for /api/telemetry. `nowplaying` starts empty (no bar yet).
        # `lanes` are per-bar Layer-0 φ statistics reduced to intrinsic [0,1]
        # readouts; `loop`/`slide` are the gauge-drift jack pair (read-only meters,
        # spec §9). All start absent (None → "—" on the web) until the first bar.
        self.telemetry = {"roles": [0.0] * self.M, "t": 0.0, "bar": 0,
                          "nowplaying": {},
                          "lanes": {"region": None, "continuity": None,
                                    "novelty": None, "density": None},
                          "loop": None, "slide": None}
        # I-8 bounded windows (deque, maxlen) for the two whole-trajectory gauge
        # meters: committed occupancy O per bar (loop[g]) and the gauge-frame
        # trajectory (slide[g]). Bounded by material window, never by elapsed time.
        from collections import deque
        self._METER_WINDOW = 16
        self._O_window: "deque" = deque(maxlen=self._METER_WINDOW)
        self._frame_hist: "deque" = deque(maxlen=self._METER_WINDOW)
        # DIAGNOSTIC-ONLY (B-7): achieved column-share vectors from recent
        # STRAIGHT-phase bars, the SAME bounded-window convention as the two
        # meters just above — reported as the retired profile-distance floor
        # readout only (live_state()), never consulted by the arrival gate.
        self._live_wobble_hist: "deque" = deque(maxlen=self._METER_WINDOW)
        # BS-4: per-bar PER-TRACK placement shares over the registered window W.
        # The only input to "which tracks are currently sounding" at a re-click.
        # THE CURRENT LEG's drawn-from set (Amendment 6 ruling 1) — cleared at
        # every click, so it can never accumulate across legs.
        self._leg_drawn: set = set()
        # bar index -> was that bar composed under a LIVE fence (see _compose_bar)
        self._fenced_bar: dict = {}
        # S-3 default scope for a journey (env-flagged; DIRECT unless asked).
        self._bridge_scope = (os.environ.get("ETS_BRIDGE_SCOPE", "").strip().lower()
                              or "direct")
        # STATIC per-world field telemetry (computed ONCE, here at load): the SAME
        # read-only reductions the desktop engine emits over /ets/profiles +
        # /ets/unitpool (ets.engine.engine.track_anchor_profiles / role_unit_pool).
        # They read only the frozen world (fstate.B + track provenance) — no bank,
        # no settlement, no writer, no F. Mirrors Engine.run_live's startup exactly.
        from ets.engine.engine import track_anchor_profiles, role_unit_pool
        self._track_profiles = track_anchor_profiles(self.world)   # {tid: (M,)}
        self._role_pools = role_unit_pool(self.world)              # {role: [...]}
        # PER-TRACK unit pool (cloud-layer, input-level display fix): the field drills
        # TRACK -> UNITS, so it needs each track's OWN units. The role pools above
        # concentrate onto one track on a degenerate B (see track_unit_pool); this
        # per-track pool is keyed by the unit's own track (ground-truth provenance) so
        # every track drills to its own units. Read-only, pre-Gibbs, byte-identical.
        self._track_pools = track_unit_pool(self.world)            # {tid: [...]}
        # ANCHOR-PROFILE ARMING (Theorem A arming corollary; module docstring above).
        # MEASURED once off the frozen world's anchor band-profile B: True iff B
        # distinguishes bands (some anchor row varies), False on the band-blind fixed
        # point (uniform B). It gates the two field controls that route through B's
        # columns — the ROLE->UNIT drill (pools) and the TRACK-square LEAN — while the
        # TRACK->ROLE drill and ROLE bias (which do not route through B) stay armed.
        self._profile_armed = anchor_profile_armed(self.world.fstate.B)
        # EIGENPANEL (OPEN_ENDS #23; E1/E2) — the object's native control basis,
        # computed ONCE here from the SYMMETRIZED RESPONSE KERNEL of the sanctioned
        # scalar/region lanes (see compute_eigenmodes' docstring: the P5-covariance
        # trap and the redundant-"fill" wall, both resolved there). Read-only:
        # authors nothing, mutates no settlement, touches no live engine state
        # (fresh StreamWriter probes only). A world with no σ_φ calibration yields
        # an honest empty result (k=0), never a fabricated axis.
        #
        # BOOT-ENSEMBLE (OPEN_ENDS #23 item 5; see the ENSEMBLE comment at the top
        # of this module): the FULL authoritative ensemble is real compute (~40s
        # measured in this sandbox on the demo world) and must never block the
        # listener's first bar. It runs in a daemon BACKGROUND THREAD started here;
        # `self._eigen` starts as an HONEST "pending" placeholder (k=0, modes=[],
        # names computed immediately since they need no computation) and is
        # replaced by ONE atomic attribute assignment when the real result lands
        # (`_eigen_worker`) — readers (`world_info`) always see either the honest
        # pending state or the complete real one, never a half-written dict. The
        # world/sigma this thread reads are frozen (read-only) data structures never
        # mutated by any steer setter, so this is safe to run concurrently with the
        # produce loop and any /api/steer call.
        self._eigen = {"modes": [], "eigen_floor": None, "k": 0,
                       "basis": "response_kernel_sym",
                       "observable_names": _eigen_obs_names(self.M) if (sigma is not None and self.M > 0) else [],
                       "pending": (sigma is not None and self.M > 0)}
        # AUDIO-FIRST (2026-07-18): the FULL authoritative ensemble is what resolves
        # the real multi-mode pad, but it is heavy (~40s) and, started at boot on a
        # single-core container, it starves the realtime produce loop so the first
        # bar never warms (silent playback). So DO NOT start it here. Stash the params
        # and let the produce loop (_loop) kick it off AFTER the first bar is produced
        # (self._warmed), so audio always warms first and modes resolve a few seconds
        # later. Offline tools call _eigen_worker / wait_eigen directly and are
        # unaffected. A pure reader (no playback) still gets the modes: world_info()
        # lazily triggers the deferred start too (see _ensure_eigen_started).
        self._eigen_thread: Optional[threading.Thread] = None
        self._eigen_args = ((sigma, eigen_n_seed, eigen_n_bar)
                            if (sigma is not None and self.M > 0) else None)
        self._eigen_lock = threading.Lock()
        # SIDECAR CACHE: the modes are a property of the frozen world. On a single
        # core they cannot be measured while audio plays without one starving the
        # other, so compute ONCE and persist the REAL result next to the world file
        # (world_path + ".eigen.json"). A cache hit loads the honest measured modes
        # instantly and skips all serve-time compute. Invalidated if the world file
        # or the ensemble params change (never a fabricated/ stale mode set).
        if self._eigen_args is not None:
            cached = self._load_eigen_cache(eigen_n_seed, eigen_n_bar)
            if cached is not None:
                self._eigen = cached                 # honest measured result, pending=False
                self._eigen_args = None              # nothing to compute
        # MODES-BY-TEMPERATURE (PREREG-temperature-sweep + addendum): the pad reselects its
        # steering basis to the modes measured at the operator's TEMP. That table is measured
        # ONCE per world by an off-playback background worker (a coarse 4-point grid measured
        # in PARALLEL across processes, run AFTER the eigen lands) and cached to a sidecar — so any
        # world, existing OR freshly trained, gets the temperature axis automatically with no
        # manual step. A cache hit (committed demo, an admin upload, or a prior auto-run) loads
        # instantly and skips compute.
        self._sweep = self._load_sweep_cache()
        self._sweep_thread: Optional[threading.Thread] = None
        self._sweep_lock = threading.Lock()
        # RESUMABLE: arm the worker whenever the cached table is absent OR a PARTIAL
        # auto-cache (fewer than the full grid of temperatures). The worker persists each
        # temperature as it lands and skips ones already done, so an LRU eviction mid-sweep
        # never loses progress — the next load resumes the remaining temperatures instead of
        # restarting from scratch (the bug that left a slow trained-world sweep stuck at 1/7).
        # An externally-supplied table (committed demo / admin upload, unstamped) is taken
        # as-is and never auto-extended.
        _loaded = self._sweep
        if isinstance(_loaded, dict) and _loaded.get("sweep") and _loaded.get("stamp") is None:
            _missing = []                                # external table: authoritative as given
        else:
            _have = ({round(float(r["T_s"]), 4) for r in _loaded["sweep"]}
                     if isinstance(_loaded, dict) and _loaded.get("sweep") else set())
            _missing = [T for T in _SWEEP_T_GRID if round(float(T), 4) not in _have]
        # AUTO-SWEEP DISABLED (2026-07-18): the measured trained corpora are single-mode at
        # every temperature (k=1: top mode dominates 10-30x, 2nd mode <2% of the noise floor
        # when hot — heating makes it MORE single-mode, not less). So the auto-sweep spends
        # ~20-40 min of background compute per world only to confirm a flat k=1 table, which
        # isn't worth the load on the audio-serving box. The whole apparatus is kept intact
        # and DORMANT: any externally-supplied table (the committed demo, an admin upload) is
        # still loaded and used, and the FE reselection still works when a table is present —
        # only the automatic RE-MEASUREMENT is off. Flip _SWEEP_AUTO back to True to re-enable
        # (e.g. once a corpus is trained that actually resolves >=2 steerable modes).
        _SWEEP_AUTO = False
        self._sweep_args = ((sigma, list(_SWEEP_T_GRID), eigen_n_seed, eigen_n_bar)
                            if (_SWEEP_AUTO and _missing and sigma is not None and self.M > 0) else None)
        self._static_field_cache: Optional[dict] = None
        # WAVEMAP (PREREG-waveform-scrub): the TRACKS view's read-only material map.
        # Lazy — the source decode is real work and must never run at load (it would
        # sit in front of the listener's first bar). Computed on first request,
        # memoized here and persisted to a sidecar next to the world file.
        self._wavemap_cache: Optional[dict] = None
        self._wavemap_lock = threading.Lock()
        # Per-listener PCM fan-out. ONE produce loop broadcasts each bar to every
        # subscriber's own queue, so a SHARED engine (the demo singleton, or a shared
        # set several visitors opened) can serve concurrent listeners without any
        # listener stealing another's audio. Steer + telemetry AND TRANSPORT
        # (play/stop) are shared state on a shared engine — a disclosed
        # consequence of one engine per world: concurrent listeners co-play one
        # live mix. An LRU-evicted engine stops mid-stream for any current
        # listener (the memory bound is real; the world file reloads on demand).
        self._subscribers: set = set()
        self._sub_lock = threading.Lock()

    # --- EIGENPANEL background computation (OPEN_ENDS #23 item 5) ----------
    def _ensure_eigen_started(self) -> None:
        """Start the deferred eigenmode measurement exactly once. Called by the
        produce loop right after the first audio bar warms (audio-first, so the
        heavy ensemble never starves the cold-start), and by world_info() so a
        pure reader that never presses play still gets the modes. Idempotent."""
        # Defensive: a bare/partially-built player (e.g. test harness via
        # object.__new__) may lack these — nothing to start then.
        args = getattr(self, "_eigen_args", None)
        lock = getattr(self, "_eigen_lock", None)
        if args is None or lock is None:
            return
        with lock:
            if self._eigen_thread is not None:
                return
            t = threading.Thread(target=self._eigen_worker, args=args, daemon=True)
            self._eigen_thread = t
            t.start()

    # --- sidecar cache for the measured modes (survives eviction + redeploy) ----
    def _eigen_cache_path(self) -> str:
        return str(self.world_path) + ".eigen.json"

    def _eigen_cache_stamp(self, n_seed: int, n_bar: int) -> dict:
        """Identity of the world+params this cache is valid for. If the world file
        or the ensemble params change, the stamp mismatches and we recompute — so a
        stale/foreign mode set can never be served."""
        try:
            st = os.stat(self.world_path)
            wsig = [int(st.st_size), int(st.st_mtime)]
        except OSError:
            wsig = None
        return {"n_seed": int(n_seed), "n_bar": int(n_bar), "M": int(self.M), "world": wsig}

    def _load_eigen_cache(self, n_seed: int, n_bar: int):
        """Return the cached REAL result dict (pending=False) iff a valid sidecar
        exists for this exact world+params, else None. Never fabricates."""
        path = self._eigen_cache_path()
        try:
            with open(path, "r") as f:
                blob = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(blob, dict) or blob.get("stamp") != self._eigen_cache_stamp(n_seed, n_bar):
            return None
        res = blob.get("result")
        if not isinstance(res, dict) or "modes" not in res or "k" not in res:
            return None
        res = dict(res)
        res["pending"] = False
        return res

    def _write_eigen_cache(self, result: dict, n_seed: int, n_bar: int) -> None:
        path = self._eigen_cache_path()
        blob = {"stamp": self._eigen_cache_stamp(n_seed, n_bar), "result": result}
        tmp = path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(blob, f)
            os.replace(tmp, path)                        # atomic
        except OSError:
            logger.warning("could not persist eigen cache at %s", path)

    def _sweep_cache_path(self) -> str:
        return str(self.world_path) + ".sweep.json"

    def _sweep_cache_stamp(self, n_seed: int, n_bar: int) -> dict:
        """Identity of the world+params an AUTO-generated sweep cache is valid for —
        same contract as the eigen stamp, so a world-file change forces a recompute and
        a stale/foreign table can never be served."""
        try:
            st = os.stat(self.world_path)
            wsig = [int(st.st_size), int(st.st_mtime)]
        except OSError:
            wsig = None
        return {"n_seed": int(n_seed), "n_bar": int(n_bar), "M": int(self.M),
                "grid": list(_SWEEP_T_GRID), "world": wsig}

    def _load_sweep_cache(self):
        """The modes-by-temperature table for this world, or None. A dict with a
        `sweep` list of {T_s, k, modes, eigen_floor} rows. Read-only; never fabricated
        (written only from a real temperature_sweep run — committed demo, admin upload,
        or the auto-worker). If the blob carries a `stamp` (auto-generated caches do),
        it is validated against the current world+params so a stale auto-cache is
        rejected; externally-supplied tables (committed demo / admin upload) carry no
        stamp and are trusted as-is."""
        try:
            with open(self._sweep_cache_path(), "r") as f:
                blob = json.load(f)
        except (OSError, ValueError):
            return None
        if not (isinstance(blob, dict) and isinstance(blob.get("sweep"), list)):
            return None
        stamp = blob.get("stamp")
        if stamp is not None:
            n_seed = int(blob.get("n_seed", _EIGEN_N_SEED)); n_bar = int(blob.get("n_bar", _EIGEN_N_BAR))
            if stamp != self._sweep_cache_stamp(n_seed, n_bar):
                return None                              # stale auto-cache → recompute
        return blob

    def _write_sweep_cache(self, result: dict, n_seed: int, n_bar: int) -> None:
        """Persist a REAL measured sweep result next to the world (atomic), stamped so a
        later world/param change invalidates it. Same durability contract as the eigen
        cache — the modes-by-temperature table survives eviction + redeploy."""
        path = self._sweep_cache_path()
        blob = dict(result); blob["stamp"] = self._sweep_cache_stamp(n_seed, n_bar)
        tmp = path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(blob, f)
            os.replace(tmp, path)                        # atomic
        except OSError:
            logger.warning("could not persist sweep cache at %s", path)

    def _ensure_sweep_started(self) -> None:
        """Start the deferred modes-by-temperature measurement exactly once. It is heavier than
        the boot ensemble, so it is triggered only AFTER the eigen worker lands (chained from
        `_eigen_worker`) or by a pure reader via world_info() — never on the audio path,
        never before audio has warmed. Idempotent; defensive against a bare test player."""
        args = getattr(self, "_sweep_args", None)
        lock = getattr(self, "_sweep_lock", None)
        if args is None or lock is None:
            return
        with lock:
            if self._sweep_thread is not None:
                return
            t = threading.Thread(target=self._sweep_worker, args=args, daemon=True)
            self._sweep_thread = t
            t.start()

    def _sweep_worker(self, sigma, grid, n_seed: int, n_bar: int) -> None:
        """Measure the temperature sweep off-thread ONE temperature at a time, landing the
        table incrementally (atomic reassignment of `self._sweep`) and persisting the
        sidecar when complete. Uses the experimental temperature_sweep (per-T_s re-derived
        floor, real measured eigenvectors) — reads only the frozen world/sigma via fresh
        probes; never touches settlement/F.

        AUDIO SAFETY: this one-time measurement DEFERS while playback is live — it parks before
        launching (serial path: between temperatures) until `self._playing` clears — so it does
        not push the realtime produce loop past deadline on a constrained host. Two disclosed
        residuals: (1) the PARALLEL path checks the defer guard once before launching the pool
        but does NOT re-check mid-batch, so if playback STARTS mid-sweep the pool finishes the
        remaining (<=4) temps on cpu_count-1 cores during playback — bounded, one core reserved
        for audio, spawn-isolated; (2) each of the up-to-(cpu_count-1) workers unpickles its own
        copy of the world (memory bounded by core count; falls to serial on <=2 cores). It
        resumes the instant playback pauses; a set played nonstop shows the honest
        `sweep_pending` state until the first pause. A failure is logged, not left stuck."""
        import time as _t
        try:
            # RESUME: seed from any partial table already measured (survives eviction/redeploy).
            prior = self._sweep if isinstance(self._sweep, dict) else None
            rows = list(prior["sweep"]) if (prior and prior.get("sweep")) else []
            done_T = {round(float(r["T_s"]), 4) for r in rows}
            meta = [{k: prior[k] for k in ("M", "n_seed", "n_bar", "observable_names")}
                    if (prior and "observable_names" in prior) else None]   # cell (closure-mutable)
            remaining = [T for T in grid if round(float(T), 4) not in done_T]
            if not remaining:
                return

            def _persist(row):
                # land one measured temperature: atomic in-memory reassign + incremental
                # sidecar write, so an eviction mid-sweep loses nothing (next load resumes).
                rows.append(row); rows.sort(key=lambda r: float(r["T_s"]))
                if meta[0] is None:
                    return                               # no meta yet (shouldn't happen once a row lands)
                landed = dict(meta[0]); landed["sweep"] = list(rows)
                self._sweep = landed
                self._write_sweep_cache(landed, n_seed, n_bar)

            # Park (don't launch heavy compute) while audio is live — measurement runs in idle
            # windows only, so it can never starve realtime playback.
            while getattr(self, "_playing", None) is not None and self._playing.is_set():
                _t.sleep(_SWEEP_DEFER_POLL)

            n_workers = max(1, min((os.cpu_count() or 1) - 1, len(remaining)))
            if n_workers <= 1:
                # single core: serial, still incremental + resumable + audio-deferred per temp.
                from cloud.companion.eigen_experimental import temperature_sweep
                for T in remaining:
                    while getattr(self, "_playing", None) is not None and self._playing.is_set():
                        _t.sleep(_SWEEP_DEFER_POLL)
                    part = temperature_sweep(self.world, sigma, self.M, [T],
                                             n_seed=n_seed, n_bar=n_bar)
                    if not (isinstance(part, dict) and part.get("sweep")):
                        return
                    if meta[0] is None:
                        meta[0] = {k: part[k] for k in ("M", "n_seed", "n_bar", "observable_names")}
                    _persist(part["sweep"][0])
            else:
                # PARALLEL: the temperatures are independent, so measure them across worker
                # PROCESSES (the settlement is GIL-bound — threads don't help). 'spawn' keeps a
                # threaded server safe; max_workers leaves a core free for the audio loop. Each
                # future's row is persisted as it completes (still incremental + resumable).
                import concurrent.futures as _f
                import multiprocessing as _mp
                ctx = _mp.get_context("spawn")
                jobs = [(self.world, sigma, self.M, T, n_seed, n_bar) for T in remaining]
                with _f.ProcessPoolExecutor(max_workers=n_workers, mp_context=ctx) as ex:
                    futs = [ex.submit(_sweep_one_temp, j) for j in jobs]
                    for fut in _f.as_completed(futs):
                        row, rmeta = fut.result()
                        if row is None:
                            continue
                        if meta[0] is None:
                            meta[0] = rmeta
                        _persist(row)
        except Exception:                                # pragma: no cover (defensive)
            logger.exception("modes-by-temperature background sweep failed")
        finally:
            self._sweep_args = None                      # sweep_pending clears either way

    def _eigen_worker(self, sigma, eigen_n_seed: int, eigen_n_bar: int) -> None:
        """Runs the FULL authoritative eigenmode ensemble off-thread, then lands
        the real result in ONE atomic assignment (`self._eigen = ...`) and persists
        it to the sidecar cache so future loads/redeploys read it instantly. Never
        touches `self.engine`/settlement — reads only the frozen `self.world` and
        `sigma` via fresh `StreamWriter` probes (the same read-only contract
        `compute_eigenmodes` documents). A computation failure is recorded
        honestly (pending clears, k stays 0) rather than left silently stuck."""
        try:
            # AUDIO-DEFER (2026-07-24, measured live: the un-deferred ensemble
            # starved the realtime produce loop to 0.06x delivery on a full-length
            # 10-track corpus): the eigen worker now parks at seed-run granularity
            # while playback is live — the SAME defer contract the sweep worker
            # already carries ("runs in idle windows only"). A set played nonstop
            # honestly shows eigen pending until the first pause.
            import time as _t

            def _park():
                while (getattr(self, "_playing", None) is not None
                       and self._playing.is_set()):
                    _t.sleep(_SWEEP_DEFER_POLL)

            _park()
            result = compute_eigenmodes(self.world, sigma, self.M,
                                        n_seed=eigen_n_seed, n_bar=eigen_n_bar,
                                        defer=_park)
            result["pending"] = False
            self._eigen = result
            self._write_eigen_cache(result, eigen_n_seed, eigen_n_bar)
            # CHAIN: now that the single-temperature ensemble has landed, kick the
            # (heavier) modes-by-temperature sweep LAST — audio has long since warmed and
            # the eigen is done, so this is the lowest-priority background measurement.
            self._ensure_sweep_started()
        except Exception as exc:                       # pragma: no cover (defensive)
            logger.exception("eigenmode background computation failed")
            self._eigen = {"modes": [], "eigen_floor": None, "k": 0,
                           "basis": "response_kernel_sym",
                           "observable_names": _eigen_obs_names(self.M),
                           "pending": False, "error": "%s: %s" % (type(exc).__name__, exc)}

    def wait_eigen(self, timeout: Optional[float] = None) -> bool:
        """Block until the background eigenmode computation lands (or `timeout`
        elapses). Returns True once `self._eigen["pending"]` is False. Not on any
        request path — a convenience for callers (tests, CLI tools) that need the
        real modes deterministically rather than racing the background thread."""
        self._ensure_eigen_started()      # deferred start: trigger it, then wait
        if self._eigen_thread is not None:
            self._eigen_thread.join(timeout=timeout)
        return not self._eigen.get("pending", False)

    # --- world info ---------------------------------------------------------
    def world_info(self) -> dict:
        # A reader that opens a set but never presses play still deserves its
        # modes — but ONLY start the heavy ensemble here when NOT playing. If the
        # produce loop is running, it starts the eigen AFTER the first bar warms
        # (audio-first); triggering it from a status poll would start the heavy
        # compute before the first bar and starve the warm (the silent-audio bug).
        if not self._playing.is_set():
            self._ensure_eigen_started()
            # A pure reader (opens a set, never presses play) also auto-measures the
            # modes-by-temperature sweep — same not-playing guard so a status poll never
            # starts the heavy compute ahead of a first bar. During playback the produce
            # loop kicks it (after eigen), so it is covered either way.
            self._ensure_sweep_started()
        # `is_trained` reports truthfully which world is loaded: True for the
        # user's freshly cloud-trained corpus (built by the train->play seam,
        # cloud.companion.train_local: local ingest -> cloud anchor-fit -> local
        # build_index -> playable .etsworld), False for the founding/demo world.
        # The UI reads this to label what is actually playing. (The seam is WIRED;
        # see PREREG-cloud-mvp2 "Phase-2 seam WIRED" amendment.)
        # Which steering lanes are ARMED (their σ_φ scale was identified) vs
        # DISARMED (measured σ=0 at u=0 → no tilt applied). Reported so the UI can
        # be honest: a DISARMED region means region-tilt taps settle no differently,
        # so the steer surface must say so rather than pretend it steers.
        sig = getattr(self.engine, "sigma", None)
        lanes = ["region", "cont", "novelty", "density", "gauge"]
        if sig is None:
            armed, disarmed, degenerate = [], list(lanes), []
        else:
            armed = [ln for ln in lanes if sig.is_identifiable(ln)]
            disarmed = [ln for ln in lanes if not sig.is_identifiable(ln)]
            # DEGENERATE (Theorem A corollary; distinct from disarmed): a lane whose
            # scale IS identifiable but whose measured σ_φ = 0 — the observable was
            # constant along the untilted trajectory, so the tilt is the EXACT
            # identity (λ=0 for every u) and the lane is just as inert as a disarmed
            # one. On a v0 world φ_gauge is degenerate (frozen frame; tilt.py wall).
            # Reported so the scalar-lane surface greys BOTH classes honestly — a
            # lane that cannot lean is never drawn as a live control (real-or-absent).
            degenerate = [ln for ln in lanes
                          if sig.is_identifiable(ln) and self._sigma_scalar(sig, ln) == 0.0]
        # STEERABLE = a lane that can actually apply a tilt: identifiable AND σ>0.
        # This is the honest arming the scalar force lanes render live vs greyed.
        steerable = [ln for ln in armed if ln not in degenerate]
        # REGION_CAP (read-only telemetry): the engine's OWN safe-envelope cap on the
        # transmitted region lean (ets.panel.envelope.SAFE_REGION_MAGNITUDE — the value
        # set_region clamps to and the pad ring is painted at). The FE mirrors this as its
        # column-bias REGION_SCALE so amp=±1 maps a single role column linearly onto the
        # full in-range region envelope with no clamp dead-zone; it is not an invented gain
        # and it tracks the engine constant. Consumed ONLY by the FE's outbound region
        # scaling — never an objective, gradient, or settlement input.
        try:
            from ets.panel.envelope import SAFE_REGION_MAGNITUDE as _region_cap
        except Exception:
            _region_cap = 1.0
        return {"ready": True, "M": self.M, "sr": self.sr,
                "world": Path(self.world_path).name,
                "is_trained": self.is_trained,
                "armed": armed, "disarmed": disarmed,
                "degenerate": degenerate, "steerable": steerable,
                "region_armed": ("region" in armed),
                "region_cap": float(_region_cap),
                # ANCHOR-PROFILE ARMING (Theorem A corollary): whether the anchor
                # band-profile observable carries information on THIS world (measured
                # off B). False on the band-blind fixed point (uniform B) → the FE
                # disarms the role->unit drill and the track-square lean, keeping the
                # track->role drill and role bias live.
                "profile_armed": bool(self._profile_armed),
                # honest engine-state readouts (OPEN_ENDS #21c/d): warmed = has the
                # produce loop rendered its first bar; last_error = the loop's
                # recorded failure (None while healthy). Real flags, never inferred.
                "warmed": bool(self._warmed),
                "last_error": self.last_error,
                "bar_seconds": float(self.engine.writer.bar_seconds),
                # EIGENPANEL (OPEN_ENDS #23; E1/E2): the object's native control
                # basis, computed in a background thread at load (compute_eigenmodes,
                # the FULL authoritative ensemble — item 5). "modes" is the radial
                # surface's ENTIRE axis set — self-sizing: k=0 on a flat/uncalibrated
                # world (honest, no disarm theater), k grows with the object's real
                # spectrum. Never hand-set, never recomputed per-steer.
                # "eigen_pending" disambiguates "still measuring" (k=0, pending=true —
                # the FE shows "measuring the object's modes…") from a REAL k=0
                # (measured, pending=false — the honest single-strip-or-empty case).
                "modes": self._eigen["modes"], "eigen_floor": self._eigen["eigen_floor"],
                "k": self._eigen["k"], "basis": self._eigen["basis"],
                "observable_names": self._eigen["observable_names"],
                "eigen_pending": bool(self._eigen.get("pending", False)),
                # MODES-BY-TEMPERATURE (PREREG-temperature-sweep + addendum): a table of the
                # object's eigenmodes measured across sampler temperatures T_s
                # [{T_s, k, modes, eigen_floor}, ...]. The measurement is off-playback and
                # read-only w.r.t. audio/settlement; the FE USES it to reselect the pad's
                # steering basis per-T_s (a faithful steering change — see the FE + the prereg
                # addendum, NOT display-only). None until a sweep is cached.
                "modes_by_temperature": (self._sweep.get("sweep") if getattr(self, "_sweep", None) else None),
                # sweep_pending: the modes-by-temperature table is still being measured in
                # the background (honest "measuring temperature modes…" state, distinct from
                # a world that simply has no table). True while the auto-sweep worker is armed
                # — including while a PARTIAL table has landed (incremental measurement) — and
                # cleared (in the worker's finally) once the full grid is done or it fails.
                "sweep_pending": bool(getattr(self, "_sweep_args", None) is not None),
                # SIGMA_PHI (OPEN_ENDS #22/23 tether amendment): the world's own
                # MEASURED calibration scale per direction lane — the "lane's own
                # calibration gain" the living-mark/tether law (T-2) reads for the
                # scalar sliders' yield-rate (radial modes use their own eigenvalue
                # `gain`, already reported above). Read-only telemetry, never a second
                # control channel: nothing downstream consumes this but the FE's
                # display-side tether-yield computation.
                "sigma": ({"region": [float(x) for x in np.asarray(sig.region, float).reshape(-1)[:self.M]],
                          "density": float(sig.density), "cont": float(sig.cont),
                          "novelty": float(sig.novelty)} if sig is not None else None)}

    # --- STATIC per-world field telemetry (read-only, once-per-world) -------
    def static_field(self) -> dict:
        """The world's STATIC field telemetry as JSON-ready dicts — the web analog
        of the desktop's /ets/profiles + /ets/unitpool feeds, from the SAME
        reductions (computed at load in __init__):

          * ``profiles``   {track_id: [float]*M}  — each source track's peak-
            normalized anchor-mass profile (track_anchor_profiles). The TRACK
            grain of the field ladder: fill/expandability come from these.
          * ``unit_pools`` {role: [{unit_id, track_id, band, profile:[float]*M}]}
            — each ROLE's drill-in unit pool (role_unit_pool). Kept for role grouping.
          * ``track_unit_pools`` {track_id: [{unit_id, track_id, band, profile:[float]*M}]}
            — each TRACK's OWN drill-in units (track_unit_pool). The field's TRACK ->
            UNITS grain; per-track membership, so a degenerate B can't concentrate the
            drill onto one track. Same arming gate as unit_pools.
          * ``track_names`` {track_id: str} — an HONEST display label per track.
            The frozen world carries NO source filenames (embedded/synthetic
            tracks have none), so the bridge labels tracks by WHAT THEY ARE: a
            demo/founding world's tracks are ``"demo track N"``; a trained world's
            tracks are ``"track N"`` here. Real ingested filenames are known only
            to the SESSION (not the world), so the companion overrides these with
            the true names for a session's OWN trained world (see app.py). No
            invented names, ever.

        Pure serialization of already-frozen reductions; it touches NOTHING
        downstream (no bank, settlement, writer, render, F) and is cached, so a
        world's static section is built once. Static."""
        if self._static_field_cache is None:
            profiles = {int(t): [float(x) for x in np.asarray(v).reshape(-1)]
                        for t, v in self._track_profiles.items()}
            # UNIT-DRILL DISARM (Theorem A arming corollary). The per-role unit POOLS
            # are the role->unit reduction of the band-profile grouping observable. On
            # the band-blind fixed point (uniform B) that observable carries no
            # information: the pools collapse (tie + top_n insertion order) to a single
            # monopolizing track, a FALSE attribution. We refuse to serve them as
            # informative — the pools are EMPTY when disarmed, and profile_armed says
            # so honestly, so the FE's floor gate makes role squares non-expandable
            # (no unit drill). The per-TRACK profiles STAY (tracks are real provenance;
            # a flat profile is the honest truth of uniform B), keeping the track->role
            # drill open (roles shown by index, no false ranking) and role bias live;
            # only the TRACK-square lean is gated off on the FE (profile_armed). A
            # world whose B is informative arms automatically → pools served.
            pools: dict = {}
            if self._profile_armed:
                for role, entries in self._role_pools.items():
                    pools[int(role)] = [
                        {"unit_id": int(uid), "track_id": int(tid), "band": int(band),
                         "profile": [float(x) for x in np.asarray(prof).reshape(-1)]}
                        for (uid, tid, band, prof) in entries]
            # PER-TRACK unit pools (the field's TRACK -> UNITS drill). Same arming gate
            # as the role pools (Theorem A): served ONLY on an informative B, so a
            # band-blind world still disarms the unit drill honestly. On an ARMED world
            # this pool is keyed by the unit's OWN track (ground-truth provenance), so a
            # degenerate-but-armed B no longer concentrates every track's drill onto one
            # track — each floor-clearing track drills to ITS OWN units. Read-only,
            # pre-Gibbs; the role `unit_pools` above are KEPT (role grouping may read
            # them), this only ADDS the per-track view.
            track_pools: dict = {}
            if self._profile_armed:
                for tid, entries in self._track_pools.items():
                    track_pools[int(tid)] = [
                        {"unit_id": int(uid), "track_id": int(tt), "band": int(band),
                         "profile": [float(x) for x in np.asarray(prof).reshape(-1)]}
                        for (uid, tt, band, prof) in entries]
            names = {int(t): self._base_track_name(int(t)) for t in profiles}
            self._static_field_cache = {"profiles": profiles, "unit_pools": pools,
                                        "track_unit_pools": track_pools,
                                        "track_names": names,
                                        "profile_armed": bool(self._profile_armed)}
        return self._static_field_cache

    def _base_track_name(self, tid: int) -> str:
        """The world-level HONEST label for one track (the ONE formula; used by
        static_field, channel_info and the wavemap so a track can never be named two
        ways). The frozen world carries no source filenames — a trained world's
        tracks are ``track N``, the demo/founding world's are ``demo track N``. The
        session-level override (real ingested filenames / an opened set's published
        names) is applied ONCE in app.py, for every surface alike."""
        return "%s %d" % ("track" if self.is_trained else "demo track", int(tid))

    # --- WAVEMAP (PREREG-waveform-scrub) — READ-ONLY material map -----------
    def _wavemap_cache_path(self) -> str:
        return str(self.world_path) + ".wavemap.json"

    def _wavemap_cache_stamp(self, paths: dict) -> dict:
        """Identity of the world + source files this cached wavemap is valid for.
        Same contract as the eigen/sweep stamps (world file size+mtime), PLUS the
        identity of each decoded source file — so a replaced/edited audio file can
        never be served as a stale envelope of the file it replaced."""
        try:
            st = os.stat(self.world_path)
            wsig = [int(st.st_size), int(st.st_mtime)]
        except OSError:
            wsig = None
        srcs = []
        for tid in sorted(paths):
            try:
                s = os.stat(paths[tid])
                srcs.append([int(tid), str(paths[tid]), int(s.st_size), int(s.st_mtime)])
            except OSError:
                srcs.append([int(tid), str(paths[tid]), None, None])
        return {"v": _WAVEMAP_VERSION, "n_peaks": _WAVEMAP_N_PEAKS,
                "M": int(self.M), "world": wsig, "sources": srcs}

    def _wavemap_source_paths(self):
        """``({track_id: path}, None)`` from the world's OWN stored sources block, or
        ``(None, reason)``. The world names its sources; nothing else does."""
        s = getattr(self.wf, "sources", None) or {}
        if s.get("kind") != "corpus":
            return None, ("this world carries embedded source units, not the "
                          "session's audio files — no waveform to serve")
        raw = s.get("paths") or {}
        paths, missing = {}, []
        for track in self.world.tracks:
            tid = int(track.track_id)
            p = raw.get(tid, raw.get(str(tid)))
            if p and os.path.isfile(str(p)):
                paths[tid] = str(p)
            else:
                missing.append(tid)
        if missing:
            return None, ("source audio for track(s) %s is not on this volume — "
                          "no waveform to serve" % ", ".join(str(t) for t in missing))
        return paths, None

    def wavemap(self) -> dict:
        """The TRACKS view's READ-ONLY material map (PREREG-waveform-scrub annex).

        Returns the WIRE object itself:
          ``{ok: true, M, sr, q_source, tracks: {"<tid>": {name, duration_s,
             peaks: [~800 floats], slices: [[t0_s, t1_s, uid, m, [q...]], ...]}}}``
        or an HONEST refusal ``{ok: false, error: <reason>}`` — never a partial or
        filled-in map. Refusals are NOT cached (a missing file may come back).

        Everything served is stored or decoded from stored sources: the peaks are the
        user's own audio file (named by the world's own ``sources`` block, decoded with
        the SAME ``librosa.load`` call ingestion used), the spans are
        ``provenance_index``, the masses are ``track.masses``, and q is the world's
        stored per-unit role assignment (see the q WALL note at module scope).

        Pure read: no engine state, no bank, no settlement, no writer, no F, no
        telemetry — so a wavemap that is never computed changes no audio byte, and a
        computed one changes none either. Computed ONCE per world and persisted next
        to the world file (``<world>.wavemap.json``), stamped with the world + source
        file identities so a stale map can never be served."""
        cached = getattr(self, "_wavemap_cache", None)
        if cached is not None:
            return cached
        if not getattr(self.world.index, "unit_role", None):
            # The world stores NO per-unit role assignment (a minimal index). Nothing
            # stored yields a per-slice q, so we refuse rather than invent weights.
            return {"ok": False, "error": "this world stores no per-unit role "
                    "assignment (minimal realization index) — no honest q to serve"}
        paths, reason = self._wavemap_source_paths()
        if paths is None:
            return {"ok": False, "error": reason}
        with self._wavemap_lock:
            cached = getattr(self, "_wavemap_cache", None)
            if cached is not None:
                return cached
            stamp = self._wavemap_cache_stamp(paths)
            blob = self._load_wavemap_cache(stamp)
            if blob is None:
                blob = self._compute_wavemap(paths)
                if not blob.get("ok"):
                    return blob                       # honest refusal; never cached
                self._write_wavemap_cache(blob, stamp)
            self._wavemap_cache = blob
            return blob

    def _compute_wavemap(self, paths: dict) -> dict:
        """Decode + reduce (the slow half; runs once per world). See ``wavemap``."""
        import librosa                                # the decode ingestion uses
        tracks = {}
        for track in self.world.tracks:
            tid = int(track.track_id)
            sr = int(track.sr)
            n = int(track.n_samples)
            slices = track_unit_slices(self.world, track, self.M)
            if slices is None:
                return {"ok": False, "error": "track %d has stored units with no "
                        "stored role assignment — no honest q to serve" % tid}
            try:
                y, _ = librosa.load(paths[tid], sr=sr, mono=True)
            except Exception as exc:                  # unreadable/corrupt source file
                return {"ok": False, "error": "could not decode the source audio for "
                        "track %d (%s: %s)" % (tid, type(exc).__name__, exc)}
            # ALIGNMENT: the envelope's axis is the world's stored n_samples. A file
            # that no longer decodes to (about) that length is not the file this track
            # was ingested from, and drawing it would put every slice boundary in the
            # wrong place — refuse instead. Tolerance covers decoder-version jitter only.
            if abs(len(y) - n) > max(1, int(0.02 * sr)):
                return {"ok": False, "error": "source audio for track %d decodes to "
                        "%d samples but the world stores %d — the file does not match "
                        "the ingested track" % (tid, len(y), n)}
            tracks[str(tid)] = {"name": self._base_track_name(tid),
                                "duration_s": float(n) / float(sr),
                                "peaks": peak_envelope(y, n),
                                "slices": slices}
        return {"ok": True, "M": int(self.M), "sr": int(self.sr),
                "q_source": _WAVEMAP_Q_SOURCE, "tracks": tracks}

    def _load_wavemap_cache(self, stamp: dict):
        """The cached wavemap for EXACTLY this world+sources, or None. Never
        fabricates and never serves across a stamp change."""
        try:
            with open(self._wavemap_cache_path(), "r") as f:
                blob = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(blob, dict) or blob.get("stamp") != stamp:
            return None
        wm = blob.get("wavemap")
        if not (isinstance(wm, dict) and wm.get("ok") and isinstance(wm.get("tracks"), dict)):
            return None
        return wm

    def _write_wavemap_cache(self, wavemap: dict, stamp: dict) -> None:
        path = self._wavemap_cache_path()
        tmp = path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump({"stamp": stamp, "wavemap": wavemap}, f)
            os.replace(tmp, path)                    # atomic
        except OSError:
            logger.warning("could not persist wavemap cache at %s", path)

    # --- THE SINGLE ENGINE-CONTROL PATH ------------------------------------
    def set_region(self, region) -> None:
        """Set the region-tilt lane — the ONLY input that reaches settlement.
        `region` is a length-M vector; it is clamped to the panel's safe envelope
        so a decisive multi-lane steer can't drive the writer to divergence."""
        vec = np.asarray(region, dtype=np.float32).reshape(-1)
        if vec.size < self.M:
            vec = np.concatenate([vec, np.zeros(self.M - vec.size, np.float32)])
        vec = vec[:self.M]
        from ets.panel.envelope import clamp_region     # reuse the engine's own wall
        vec = np.asarray(clamp_region(vec), dtype=np.float32)
        with self._lock:
            self._region = vec

    # --- typed scalar force lanes (paper2 §2; each its ONE lane-vector datum) ----
    # These mirror the desktop panel's per-field lane routing (widget._on_scalar):
    # each writes exactly ONE field of the staged lane vector; the vector is then
    # assembled by `_current_lane` and consumed by the SINGLE `_tilt_for(u)`. There
    # is no second control channel and no per-lane engine setter — the engine's one
    # control entry (C-3) takes the whole LaneVector.
    def _set_lean(self, lane_id: str, attr: str, u) -> None:
        from ets.panel.lanes import spec
        s = spec(lane_id)
        try:
            v = float(u)
        except (TypeError, ValueError):
            v = 0.0
        if not np.isfinite(v):
            v = 0.0
        v = max(s.lo, min(s.hi, v))          # the lane's own declared control range
        with self._lock:
            setattr(self, attr, v)

    def set_continuity(self, u) -> None:     # VARY (T1, φ_cont)
        self._set_lean("continuity", "_u_continuity", u)

    def set_novelty(self, u) -> None:        # SPREAD (T1, φ_novelty)
        self._set_lean("novelty", "_u_novelty", u)

    def set_density(self, u) -> None:        # DENSITY (T1, φ_density)
        self._set_lean("density", "_u_density", u)

    def set_gauge(self, u) -> None:          # KEY LOCK (T3 frame; degenerate on v0)
        self._set_lean("gauge", "_u_gauge", u)

    def set_temperature(self, T_s) -> None:  # CHAOS (T2, directionless sharpness)
        from ets.panel.lanes import spec
        s = spec("temperature")
        try:
            v = float(T_s)
        except (TypeError, ValueError):
            v = float(s.default)
        if not np.isfinite(v):
            v = float(s.default)
        v = max(s.lo, min(s.hi, v))
        with self._lock:
            self._T_s = v

    def set_wobble(self, vec) -> None:        # SHAPE (covariance-shape XY; PREREG)
        """Set the OPTIONAL second-moment anisotropy `a` — how the draw's SPREAD
        is shaped per Hessian eigendirection (stiffest-first), NOT where the mean
        goes. Mirrors the other setters: it stores one datum that `produce_one_bar`
        folds into the SINGLE TiltTerms the writer consumes (no new channel). A
        None/empty vector clears it (=> ones => byte-identical draw). The vector is
        length-M and clamped to the writer's safe band [A_SHAPE_LO, A_SHAPE_HI]; the
        engine re-clamps at the TiltTerms boundary, so this is defence-in-depth,
        never the only guard."""
        from ets.writer.tilt import A_SHAPE_LO, A_SHAPE_HI
        if vec is None:
            with self._lock:
                self._wobble = None
            return
        a = np.asarray(vec, dtype=np.float64).reshape(-1)
        if a.size == 0:
            with self._lock:
                self._wobble = None
            return
        if a.size < self.M:
            a = np.concatenate([a, np.ones(self.M - a.size, np.float64)])
        a = a[:self.M]
        a = np.where(np.isfinite(a), a, 1.0)
        a = np.clip(a, float(A_SHAPE_LO), float(A_SHAPE_HI))
        with self._lock:
            self._wobble = a

    def set_channel_bias(self, vec) -> None:
        """Set the per-channel amplify vector (PREREG-channel-bias-squares-REV2-
        bidirectional; extends REV1-soft). Each component ∈ [-1, 1] applies a SOFT
        lean on one channel (a source track, ordered by ``self._channel_tids``) at
        the FIBER-CHOICE measure: it becomes a ``channel_logbias`` addend on the
        pooled-channel candidate logits in ``fiber_choice_logits`` (the writer's
        which-unit-fills-this-slot draw), carried on the ONE ``TiltTerms`` and
        consumed in ``produce_one_bar`` via ``_tilt_for(u, channel_logbias=...)``.
        POSITIVE up-weights (amplify) that channel; NEGATIVE soft-damps / down-
        weights it — same softmax addend, sign flipped; by gauge invariance only
        the RELATIVE β between channels matters. It is a bias the settlement works
        AROUND, not a clamp — nothing is pinned, and damp does not hard-mute (stays
        generative). ``channel_logbias`` is excluded from ``is_untilted``, so F /
        the O-block role solve / settlement / render are mathematically unchanged;
        only the fiber choice leans. A None / empty / all-zero vector clears the
        bias ⇒ no addend ⇒ byte-identical audio."""
        if vec is None:
            with self._lock:
                self._channel_bias = None
            return
        v = np.asarray(vec, dtype=np.float64).reshape(-1)
        if v.size == 0:
            with self._lock:
                self._channel_bias = None
            return
        v = np.where(np.isfinite(v), v, 0.0)
        v = np.clip(v, -1.0, 1.0)
        if not np.any(v != 0.0):        # all-zero (any sign) ⇒ no addend ⇒ byte-identical
            with self._lock:
                self._channel_bias = None
            return
        with self._lock:
            self._channel_bias = v

    def set_unit_bias(self, unit_amp) -> None:
        """Set the per-UNIT amplify map (PREREG-field-bias-REV3, extends the REV2
        track grain). ``unit_amp`` is a mapping {unit_id -> amplify∈[-1,1]}: each
        entry applies a SOFT bidirectional lean on THAT unit's candidate at the
        FIBER-CHOICE measure — the UNIT grain, the operator's ultimate "channel"
        (a beat-normalized sound unit). It becomes the ``"unit"`` sub-map of the ONE
        ``channel_logbias`` datum the writer consumes (single carrier, I-1), summed
        ADDITIVELY with the track roll-up per candidate (β_track[tid]+β_unit[uid]).
        POSITIVE up-weights that unit; NEGATIVE soft-damps it — same softmax addend,
        sign flipped. It is a bias the settlement works AROUND, not a clamp; a unit
        only leans where its (role,band) makes it a candidate (soft, coverage-
        contingent). Excluded from ``is_untilted``, so F / the O-block solve /
        settlement / render stay byte-identical. A None / empty / all-zero map clears
        the unit grain ⇒ no unit addend ⇒ (with no track bias) byte-identical audio."""
        if not unit_amp:
            with self._lock:
                self._unit_bias = None
            return
        clean: dict = {}
        for uid, a in dict(unit_amp).items():
            try:
                av = float(a)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(av):
                av = 0.0
            av = max(-1.0, min(1.0, av))
            if av != 0.0:
                clean[int(uid)] = av
        with self._lock:
            self._unit_bias = clean or None

    def set_track_role_bias(self, cell_amp) -> None:
        """Set the per-(track, role) SUB-TRACK amplify map (PREREG-track-role-bias,
        prototype). ``cell_amp`` is a mapping {(track_id, role_k) -> amplify∈[-1,1]}:
        each entry leans track T's candidates SOFTLY, but ONLY inside slots whose
        settled role is k — the first bias keyed on an EMERGENT structure (roles).
        It becomes the ``"track_role"`` sub-map of the ONE ``channel_logbias`` datum
        the writer consumes (single carrier, I-1), summed ADDITIVELY with the track
        roll-up and unit grains per candidate. POSITIVE up-weights, NEGATIVE soft-
        damps. It varies within a role-k choice set (via the track key) and so DODGES
        the pure-role wall. Excluded from ``is_untilted``, so F / the O-block solve /
        settlement / render stay byte-identical. A None / empty / all-zero map clears
        the grain ⇒ (with no other bias) byte-identical audio."""
        if not cell_amp:
            with self._lock:
                self._track_role_bias = None
            return
        clean: dict = {}
        for key, a in dict(cell_amp).items():
            try:
                tid, role = key
                av = float(a)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(av):
                av = 0.0
            av = max(-1.0, min(1.0, av))
            if av != 0.0:
                clean[(int(tid), int(role))] = av
        with self._lock:
            self._track_role_bias = clean or None

    def channel_info(self) -> dict:
        """Read-only channel roster for the squares FE: channel index → track_id +
        display name. Which channels can actually PULL (vs disarm) is a MEASURED
        property (PREREG Phase-1 gate), not asserted here. Reads only the frozen
        roster; touches no engine state."""
        chans = [{"channel": ch, "track_id": int(tid),
                  "name": self._base_track_name(int(tid))}
                 for ch, tid in enumerate(self._channel_tids)]
        return {"n_channels": len(chans), "s_phase": int(self.s_phase),
                "channels": chans}

    @staticmethod
    def _sigma_scalar(sig, lane: str) -> float:
        """The scalar σ_φ magnitude of one lane (region → its max per-anchor σ), for
        the degenerate (identifiable-but-σ=0) test. Reads the registered calibration
        only; never a hand-set value."""
        if lane == "region":
            r = np.asarray(sig.region, float).reshape(-1)
            return float(r.max()) if r.size else 0.0
        return float(getattr(sig, lane))

    def _current_lane(self):
        from ets.panel.lanes import default_lane_vector
        u = default_lane_vector(self.M)
        with self._lock:
            u.u_region = np.asarray(self._region, dtype=np.float32).copy()
            u.u_continuity = float(self._u_continuity)
            u.u_novelty = float(self._u_novelty)
            u.u_density = float(self._u_density)
            u.u_gauge = float(self._u_gauge)
            u.T_s = float(self._T_s)
        return u

    # --- bar production (mirrors Engine.produce_one) -----------------------
    def _ensure_bank(self):
        if self._bank is None:
            from ets.engine.engine import build_bank
            self._bank = build_bank(self.wf)      # slow warmup (materialize units)

    def produce_one_bar(self):
        """Produce ONE bar of capped PCM + role telemetry, exactly as the engine's
        live loop does. Returns (pcm_int16_bytes, roles_list).

        Split into COMPOSE (settle/choose/schedule — mutates writer state, strictly
        serial) and FINISH (pure render + telemetry from the composed bar) so the
        produce loop can PIPELINE them (compose bar N+1 while bar N renders,
        ETS_PIPELINE) without changing WHAT is composed or rendered: this method
        remains the exact serial composition of the two halves."""
        r, sched = self._compose_bar()
        return self._finish_bar(r, sched)

    def _compose_bar(self):
        """COMPOSE one bar: tilt → write_bar (settlement + fiber choice; MUTATES
        the writer/tape — the strictly-serial half) → schedule. Returns (r, sched)."""
        from ets.engine.engine import bar_schedule
        from . import live as live_mod
        self._ensure_bank()
        # LIVE MODE: the Part-A ClampTerms carrier, delivered to the writer
        # ALONGSIDE tilt (A-1) — the ONE restriction channel, never a second
        # settlement/casting path (A-5). None (GRID/TRACKS, or LIVE never
        # touched) -> clamp_call_kwargs returns {} WITHOUT introspecting
        # anything, so this call stays the exact write_bar(tilt=tilt) it is
        # today (byte-identical; LM-0/LM-1).
        #
        # STRAIGHT PLAY WALKS FORWARD (B-1: "bars pinned to that track's
        # CONSECUTIVE slices"). The fence is rebuilt EVERY bar from a moving
        # cursor over the pinned run, so the choice set for this bar is this
        # bar's slices — not the track's whole remaining set, which let the
        # tape roam inside the track (the measured 2026-08-13 defect). Past
        # the end of the run the window empties and LIVE returns to idle
        # silence rather than wrapping, repeating, or inventing material.
        clamp_terms = None
        with self._live_lock:
            live = dict(self._live)
        if live.get("mode") == "straight" and live.get("slices"):
            win = live_mod.bar_window(live["slices"],
                                      live.get("bars_elapsed", 0),
                                      self.s_phase,
                                      demanded_roles=range(int(self.world.M)),
                                      start_group=live.get("start_group", 0),
                                      plan=live.get("plan"))
            if win["exhausted"]:
                # Ran off the end. THIS bar is still composed and streamed, so
                # it needs a fence of its own — leaving clamp_terms None cast it
                # against the whole corpus and sounded every track for one bar
                # (measured 2026-08-14). Silence is inside the fence.
                clamp_terms = live_mod.silent_fence(live["track"])
                self.live_enter()              # ran off the end: idle silence
            else:
                admitted = tuple(win["core"]) + tuple(win["widened"])
                clamp_terms = live_mod.build_full_fence(live["track"], admitted,
                                                       slot_pin=win.get("slot_pin"))
                with self._live_lock:
                    if self._live.get("mode") == "straight":
                        self._live["clamp"] = clamp_terms
                        self._live["bars_elapsed"] = \
                            int(self._live.get("bars_elapsed", 0)) + 1
                        # R2(b): what the bar could only get by widening —
                        # inside the fenced track, outside the forward core.
                        self._live["core_units"] = frozenset(win["core"])
                        self._live["n_widened"] = len(win["widened"])
                        # THE ADMITTED WINDOW (Amendment 6, ruling 3): the time
                        # span this bar's fence actually admits, from the fence's
                        # own core units. It advances by construction because the
                        # window walks forward. This is NOT a sample position and
                        # the view must not label it as one.
                        self._live["window"] = live_mod.window_span(
                            live["slices"], win["core"])
        elif live.get("mode") == "bridge" and self._bridge is not None:
            with self._live_lock:
                br = dict(self._bridge)
            # B-2 PULL: advance the slewed lean toward the pinned target and
            # set it on the SAME region-tilt channel every other view drives
            # (StreamPlayer.set_region -> the ONE _tilt_for(u)) — BEFORE
            # `_current_lane()` reads it below, so THIS bar's tilt already
            # carries the freshly-stepped value. Nothing else is emitted.
            new_lean = live_mod.pull_step(br.get("lean_cur"), br["pull_target"])
            self.set_region(new_lean)
            # B-1 RELEASE: while still releasing, continue the source's
            # forward-walking window at the CURRENT (decaying) openness —
            # the exact straight-play mechanism, just with a shrinking
            # threshold instead of a fixed 1.0. Once fully released
            # (openness_cur <= 0) release_clamp returns None: no restriction
            # left at all (B-3 — no corridor, no second mask, ever).
            win = None
            if br["openness_cur"] > 0.0 and live.get("slices"):
                win = live_mod.bar_window(live["slices"],
                                          live.get("bars_elapsed", 0),
                                          self.s_phase,
                                          demanded_roles=range(int(self.world.M)),
                                          start_group=live.get("start_group", 0),
                                          plan=live.get("plan"))
            pin_units, slot_pin = None, None
            if win is not None and not win["exhausted"]:
                pin_units = tuple(win["core"]) + tuple(win["widened"])
                slot_pin = win.get("slot_pin")
            clamp_terms = live_mod.release_clamp(
                br["openness_cur"], br["source_track"],
                pin_units=pin_units, slot_pin=slot_pin,
                dest_track=br.get("dest_track"),
                scope=br.get("scope", live_mod.BRIDGE_SCOPE_DIRECT),
                carry_tracks=br.get("carry_tracks"))
            nxt_openness = live_mod.release_step(br["openness_cur"])
            with self._live_lock:
                if self._bridge is not None:
                    self._bridge["lean_cur"] = new_lean
                    self._bridge["openness_cur"] = nxt_openness
                    self._bridge["bars_elapsed"] = \
                        int(self._bridge.get("bars_elapsed", 0)) + 1
                if win is not None and not win["exhausted"]:
                    self._live["bars_elapsed"] = \
                        int(self._live.get("bars_elapsed", 0)) + 1
        # IN LIVE, NEVER CAST UNFENCED. Every branch above that fails to build a
        # fence (no slices, a bridge dict that vanished under a concurrent stop)
        # would otherwise fall through with clamp_terms None — which is not
        # "no restriction chosen" but "the whole corpus", the exact defect the
        # exhaustion bar had. LIVE's honest output when it cannot fence is
        # silence, so that is what it casts.
        if clamp_terms is None and live.get("mode") in ("straight", "bridge"):
            clamp_terms = live_mod.silent_fence(int(live.get("track") or 0))
        u = self._current_lane()
        with self._lock:                                     # second-moment shape (PREREG):
            a = None if self._wobble is None else np.asarray(self._wobble).copy()
        # FIELD-BIAS (PREREG-field-bias-REV3, SOFT multi-grain): fold the per-TRACK
        # amplify vector (roll-up) AND the per-UNIT amplify map (the ultimate
        # "channel") into the ONE TiltTerms via `channel_logbias` — a soft lean in
        # the fiber choice measure, NOT a clamp, resolved ADDITIVELY per candidate
        # (β_track[tid]+β_unit[uid]). Empty at BOTH grains ⇒ no addend ⇒ byte-
        # identical to the un-biased tilt. Assembled at the SAME single tilt-
        # construction point as every other setter (a rides it too); no new channel.
        with self._lock:
            bias = None if self._channel_bias is None else self._channel_bias.copy()
            unit_amp = None if self._unit_bias is None else dict(self._unit_bias)
            cell_amp = None if self._track_role_bias is None else dict(self._track_role_bias)
        from .channel_bias import (channel_logbias, grain_logbias, field_logbias,
                                   track_role_logbias)
        track_w = channel_logbias(bias, self._channel_tids) if bias is not None else None
        unit_w = grain_logbias(unit_amp) if unit_amp else None
        cell_w = track_role_logbias(cell_amp) if cell_amp else None
        clogbias = field_logbias(track=track_w, unit=unit_w, track_role=cell_w)
        tilt = self.engine._tilt_for(u, a=a, channel_logbias=clogbias)
        clamp_kwargs = live_mod.clamp_call_kwargs(self.engine.writer.write_bar,
                                                   clamp_terms)
        r = self.engine.writer.write_bar(tilt=tilt, **clamp_kwargs)
        # WAS THIS BAR CAST UNDER A LIVE FENCE? `_finish_bar` runs one or more
        # bars behind `_compose_bar` under the pipeline, so it cannot read the
        # CURRENT mode to answer this: a GRID bar composed unfenced but finished
        # after the first LIVE click was being recorded as LIVE material, which
        # put every track into "currently sounding" and so into the next leg's
        # admitted set (measured: a DIRECT mask of {0,1,2,3} on a 4-track world).
        # The bar itself carries the answer; keep it with the bar.
        self._fenced_bar[int(r.bar)] = clamp_terms is not None
        if len(self._fenced_bar) > 256:
            for k in sorted(self._fenced_bar)[:128]:
                self._fenced_bar.pop(k, None)
        sched = bar_schedule(self.world, r.rows, self.s_phase)
        return r, sched

    def _finish_bar(self, r, sched):
        """FINISH one composed bar: pure render from (sched, bank) + the read-only
        telemetry reductions + PCM conversion. Reads the writer's committed result
        only — never mutates writer/tape state — so it may overlap the NEXT bar's
        compose. EMA/telemetry mutations stay bar-ordered because the pipeline
        executes finishes on ONE worker in submission order."""
        from ets.engine.engine import (_playback_soft_limit,
                                        bar_role_activity, nowplaying_activity)
        from ets.render import render as render_schedule
        audio, _prov = render_schedule(sched, self._bank)
        audio = _playback_soft_limit(audio)                  # LIVE-only eardrum cap
        # STREAM MONO CONTRACT (live-only, like the soft limit): `wav_header` declares
        # ONE channel, and the FE frames the byte stream as mono int16. If a render
        # ever returns a 2-D (multi-channel) buffer, `_to_int16` would emit INTERLEAVED
        # samples that the mono header mislabels — the exact "sample alignment / dtype
        # mismatch" failure mode that decodes as white-noise garbage. Collapse to mono
        # here so the emitted PCM can never disagree with the header. For the demo world
        # (mono render) this is a no-op — the streamed bytes stay byte-identical to
        # `produce_one`, verified in tests/test_stream_decode.py.
        audio = np.asarray(audio)
        if audio.ndim > 1:
            audio = audio.mean(axis=tuple(range(1, audio.ndim)))
        roles = bar_role_activity(r.rows, self._bank, self.world.fstate.B)
        roles = [float(x) for x in np.asarray(roles).reshape(-1)[:self.M]]
        # READ-ONLY per-track nowplaying: reduce the just-produced bar's rows by
        # source track (the SAME reduction the desktop emits on /ets/nowplaying —
        # engine.nowplaying_activity). Reads produced rows only; adds no downstream
        # call (audio byte-identical on/off). Keyed by track_id for the field's
        # TRACK/UNIT square fills.
        nowplaying = {int(tid): float(act)
                      for tid, act in nowplaying_activity(r.rows)}
        # READ-ONLY per-UNIT nowplaying: the SAME reduction as per-track nowplaying but
        # keyed by source UNIT (r.rows carry (slot, tid, uid, sec, mass)). Sum mass per
        # uid, normalize by the bar's PEAK unit mass to 0..1 — so each UNIT square glows
        # by its OWN placement activity (units within a track diverge live, unlike the
        # shared per-track glow). Reads produced rows only; no downstream call → audio
        # byte-identical. A light EMA across bars (disclosed, _NP_UNIT_ALPHA) fades a
        # just-played unit instead of strobing, since only a sparse subset lights per bar.
        raw_unit = nowplaying_unit_activity(r.rows)
        ema = self._nowplaying_unit_ema
        for uid in set(ema) | set(raw_unit):
            v = (_NP_UNIT_ALPHA * raw_unit.get(uid, 0.0)
                 + (1.0 - _NP_UNIT_ALPHA) * ema.get(uid, 0.0))
            if v >= _NP_UNIT_EPS:
                ema[uid] = v
            else:
                ema.pop(uid, None)
        nowplaying_unit = {int(uid): float(v) for uid, v in ema.items()}
        # READ-ONLY per-(TRACK, ROLE) nowplaying: the drill role-cell glow. Reduce the bar
        # by (track_id, slot-role k) — the SAME emergent slot role the (track,role) bias
        # mechanism keys on, reconstructed from the committed O (track_role_activity).
        # Normalize by the bar's peak cell mass to 0..1, EMA-smoothed like the per-unit
        # glow. Reads produced rows + O only; audio byte-identical. Keyed "tid,k" for JSON.
        tr_energy = track_role_activity(r.rows, r.O, self.world.fstate.B, self.s_phase)
        tr_peak = max(tr_energy.values()) if tr_energy else 0.0
        raw_tr = ({cell: v / tr_peak for cell, v in tr_energy.items()} if tr_peak > 0.0
                  else {cell: 0.0 for cell in tr_energy})
        tr_ema = self._nowplaying_track_role_ema
        for cell in set(tr_ema) | set(raw_tr):
            v = (_NP_UNIT_ALPHA * raw_tr.get(cell, 0.0)
                 + (1.0 - _NP_UNIT_ALPHA) * tr_ema.get(cell, 0.0))
            if v >= _NP_UNIT_EPS:
                tr_ema[cell] = v
            else:
                tr_ema.pop(cell, None)
        nowplaying_track_role = {("%d,%d" % (t, k)): float(v)
                                 for (t, k), v in tr_ema.items()}
        self._bar_index = int(r.bar)
        lanes = self._lane_readouts(r)
        loop_val, slide_val = self._gauge_meters(r)
        self.telemetry = {"roles": roles, "bar": int(r.bar),
                          "t": float(r.bar * self.engine.writer.bar_seconds),
                          "nowplaying": nowplaying,
                          "nowplaying_unit": nowplaying_unit,
                          "nowplaying_track_role": nowplaying_track_role,
                          "lanes": lanes, "loop": loop_val, "slide": slide_val}
        # LIVE MODE (Train B2): "state is measured, not asserted" — read the
        # ACTUALLY placed unit for the fenced track straight off this bar's
        # own rows (the same placement feed nowplaying/nowplaying_unit reduce
        # above), never a timer or the originally-requested position.
        with self._live_lock:
            live_track = self._live.get("track")
            uid_index = self._live.get("uid_index", {})
        if live_track is not None:
            from . import live as live_mod
            placement = live_mod.current_placement(r.rows, live_track, uid_index)
            # STARVATION (§2.1): disclosed, never silent, if the carrier
            # records it. Defensive read (getattr, default False) — BarResult
            # carries no such field as of this build; see the Train B2
            # handoff for exactly what to wire once Part A lands.
            starved_flag = bool(getattr(r, "starved", False))
            with self._live_lock:
                if self._live.get("track") == live_track:  # no fence swap mid-flight
                    if placement is not None:
                        self._live["current_unit"] = placement[0]
                        self._live["current_slice_index"] = placement[1]
                    self._live["starved"] = starved_flag
        # THE BRIDGE (v0): B-4 arrival is OBSERVED off THIS bar's raw rows —
        # never the EMA-smoothed display telemetry above. B-7's retired
        # profile-distance gap rides along as a DIAGNOSTIC only (never a
        # gate). Straight-phase bars feed the SAME column-share reduction
        # into a bounded wobble history, which is all that diagnostic floor
        # is ever measured from (never hardcoded, never gating anything).
        from . import live as live_mod
        with self._live_lock:
            raw_mode = self._live.get("mode")
        if raw_mode in ("straight", "bridge") and self._fenced_bar.get(int(r.bar)):
            # THE CURRENT LEG'S DRAWN-FROM SET (Amendment 6, ruling 1). Not a
            # window, not a trend, not a decay: the set of tracks THIS LEG has
            # actually cast from, cleared at every click. Nothing accumulates
            # across legs, so there is no history for a smoothing constant to
            # be needed on.
            with self._live_lock:
                for _t, _v in live_mod.track_shares(r.rows).items():
                    if float(_v) > 0.0:
                        self._leg_drawn.add(int(_t))
        if raw_mode == "straight":
            self._live_wobble_hist.append(
                live_mod.column_shares(nowplaying_track_role, self.M))
        elif raw_mode == "bridge" and self._bridge is not None:
            # SHARE IS REPORTED, NEVER CONSULTED (Amendment 6, ruling 2). This
            # block used to decide something: it accumulated a window of shares,
            # tracked a high-water mark and closed the journey when the mark
            # stopped moving. All of that is deleted — arrival does not occur
            # (registered proven-negative), so there was nothing for it to
            # detect. What remains is display state, read off this bar only.
            dest_track = self._bridge.get("dest_track")
            share = live_mod.dest_share(r.rows, dest_track)
            dest_uid_index = self._bridge.get("dest_uid_index") or {}
            dest_placement = live_mod.current_placement(r.rows, dest_track, dest_uid_index)
            with self._live_lock:
                if self._bridge is not None:
                    self._bridge["share"] = share
                    self._bridge["blend"] = live_mod.track_shares(r.rows)
                    if dest_placement is not None:
                        self._bridge["dest_current_unit"] = dest_placement[0]
                        self._bridge["dest_current_slice_index"] = dest_placement[1]
        pcm = _to_int16(audio)
        return pcm, roles

    # --- read-only display reductions of the produced bar (spec §9) ---------
    def _lane_readouts(self, r) -> dict:
        """The four Lane-Console lanes as INTRINSIC [0,1] reductions of this bar's
        Layer-0 φ statistics (ets.writer.phi; carried on r.phi) — the SAME read-only
        pattern as roles/nowplaying. No invented constant: every bound comes from the
        bar itself (anchor count M, placement count, slot count s_phase). Feeds the
        web display only; touches no settlement/writer/F (I-5/I-14)."""
        phi = r.phi
        # region: occupancy concentration of φ_region, 0=uniform .. 1=one anchor.
        region_vec = np.asarray(phi["region"], float).reshape(-1)
        tot = float(region_vec.sum())
        if tot > 0.0 and self.M > 1:
            peak = float(region_vec.max()) / tot
            region = (peak - 1.0 / self.M) / (1.0 - 1.0 / self.M)
        else:
            region = 0.0
        # continuity: share of this bar's placements that continue a real source run.
        n_place = len(r.rows)
        continuity = (float(phi["cont"]) / n_place) if n_place else 0.0
        # density: fraction of the bar's metrical slots carrying any placement.
        filled = len({int(row[0]) % self.s_phase for row in r.rows})
        density = filled / float(self.s_phase) if self.s_phase else 0.0
        # novelty: recency-weighted unit reuse vs the committed tape (already [0,1]).
        novelty = float(phi["novelty"])
        clamp = lambda v: float(max(0.0, min(1.0, v)))
        return {"region": clamp(region), "continuity": clamp(continuity),
                "novelty": clamp(novelty), "density": clamp(density)}

    def _gauge_meters(self, r):
        """The gauge-drift jack pair (spec §9), read-only, over BOUNDED windows:
          loop[g] — ets.meters.gauge_loop.loop_g over the committed occupancy O of
                    the last W bars (the incorruptible holonomy quantity). Real and
                    live; None until a 3-bar cycle exists.
          slide[g] — ets.meters.gauge_slide over the gauge-frame trajectory. On a v0
                    world the writer holds the frame at the identity every bar, so
                    slide is structurally zero and DISARMS (None); it auto-arms only
                    if the frame ever actually moves. Never fabricated.
        Imports the existing meter modules (no engine edit); consumes produced state
        only; feeds nothing back into any objective/gradient/settlement (I-5/I-14)."""
        from ets.meters.gauge_loop import loop_g
        from ets.meters.gauge_slide import gauge_slide
        self._O_window.append(np.asarray(r.O, float))
        fr = self.engine.writer.frame
        self._frame_hist.append((float(fr.transpose), float(fr.phase)))
        # loop[g]: committed-region holonomy over the window (needs >= 3 bar nodes).
        loop_val = None
        if len(self._O_window) >= 3:
            Ocat = np.concatenate(list(self._O_window), axis=1)
            loop_val = float(loop_g(Ocat, self.s_phase)[-1])
        # slide[g]: armed only if the gauge frame actually moved across the window.
        ts = {t for (t, _p) in self._frame_hist}
        ps = {p for (_t, p) in self._frame_hist}
        slide_val = None
        if len(ts) > 1 or len(ps) > 1:
            ft = [t for (t, _p) in self._frame_hist]
            fp = [p for (_t, p) in self._frame_hist]
            slide_val = float(gauge_slide(ft, fp, float(self.s_phase)).phase.per_bar[-1])
        return loop_val, slide_val

    # --- transport / streaming ---------------------------------------------
    def subscribe(self):
        """Register a NEW listener queue and ensure the produce loop is running.
        Each /api/stream connection gets its own queue (fan-out) so concurrent
        listeners on a shared engine never steal each other's PCM."""
        import queue
        q: "queue.Queue[bytes]" = queue.Queue(maxsize=64)
        with self._sub_lock:
            self._subscribers.add(q)
        self.start()
        return q

    def unsubscribe(self, q) -> None:
        with self._sub_lock:
            self._subscribers.discard(q)

    # Steady-state lead the producer keeps over realtime, so a network hiccup
    # never starves the client. With the emission re-anchor below, steering
    # latency is bounded by roughly this lead + the re-anchor threshold +
    # client-side buffering — a producer stall shifts the stream's timeline
    # instead of silently inflating the client's buffer forever.
    PACE_LEAD_SECONDS = 1.0
    # If the schedule falls this far behind wall clock (first-bar warmup such
    # as _ensure_bank, or a mid-stream render stall), re-anchor to NOW rather
    # than bursting at host speed to catch up — a catch-up burst would land in
    # the client's buffer and become permanent extra steering latency
    # (auditor note 1, 2026-07-18).
    PACE_REANCHOR_SECONDS = 2.0

    def _loop(self):
        # REALTIME PACING. Unpaced, a fast host renders far ahead of realtime
        # (measured 10.8x on the hosted deploy, 2026-07-18), so a realtime
        # listener buffers ever further behind "live" and steering becomes
        # audible minutes late. Pacing changes WHEN a bar is emitted, never
        # WHAT is rendered (H-8 untouched: u=0 bars stay byte-identical to
        # render_offline). A slow host is never slept — under-run behavior is
        # unchanged (the browser buffers).
        import time as _time
        t0 = None                                  # anchored on FIRST EMISSION
        sent = 0                                   # samples emitted so far
        kicked_eigen = False                       # LOCAL once-flag (never reads
                                                   # self._warmed — a bare test-harness
                                                   # player has no such attr)
        kicked_sweep = False                       # modes-by-temperature: kicked once the
                                                   # eigen is done (cached or landed), so a
                                                   # cache-hit-eigen world still auto-sweeps
        # IDLE-STOP (2026-07-24, measured live): a warm loop with NO listeners on a
        # corpus whose render is SLOWER than realtime can never catch its pace lead —
        # it burns a full core forever and (same process) degrades every OTHER
        # world's playback. Warm therefore has a BOUNDED unlistened window: after
        # ETS_WARM_IDLE_S seconds with zero subscribers the loop parks itself
        # (start() on the next subscribe resumes it; bars already produced stay
        # buffered). Pacing/render behavior for LISTENED playback is unchanged.
        idle_stop_s = float(os.environ.get("ETS_WARM_IDLE_S", "120"))
        last_subscribed = _time.monotonic()
        while self._playing.is_set():
            with self._sub_lock:
                n_subs = len(self._subscribers)
            now_idle = _time.monotonic()
            if n_subs > 0:
                last_subscribed = now_idle
            elif now_idle - last_subscribed > idle_stop_s:
                logger.info("produce loop idle-stopped after %.0fs with no "
                            "listeners (warm window closed)", idle_stop_s)
                self._playing.clear()
                break
            # LIVE IDLE HOLD (papers/PREREG-live-mode.md AMENDMENT 2, B-0 /
            # A2.3 / LM-9): a session that has entered LIVE with no fence set
            # casts NOTHING here — the SAME idle/park SHAPE as the
            # unlistened-idle-stop check just above, extended rather than
            # duplicated (this is a HOLD, not a stop: the loop stays alive so
            # a fence set a moment later begins within one bar, LM-10). This
            # is a TRANSPORT-GATED hold, never a neutral/empty ClampTerms —
            # a neutral carrier means NO restriction (the free blend), which
            # is exactly what B-0 forbids sounding in LIVE.
            # getattr-guarded: a bare transport-only test harness (the
            # test_stream_pacing.py pattern) carries no ``_live`` and is
            # completely unaffected (mode defaults absent -> never held).
            live_lock = getattr(self, "_live_lock", None)
            if live_lock is not None:
                with live_lock:
                    live_mode = self._live.get("mode")
                if live_mode == "idle":
                    _time.sleep(0.05)
                    continue
            try:
                pcm, _ = self.produce_one_bar()
            except Exception as exc:
                # LOOP HONESTY (OPEN_ENDS #21c): a failing engine must be LOUD.
                # The old bare `except: break` died silently and every listener's
                # stream then hung forever with no trace. Log the FULL traceback
                # and record a timestamped last_error for world_info()/telemetry,
                # then still break — no retry loop: a failing engine must not spin.
                logger.exception("produce_one_bar failed — the produce loop halts")
                self.last_error = "%s %s: %s" % (
                    _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                    type(exc).__name__, exc)
                tel = dict(self.telemetry)
                tel["last_error"] = self.last_error
                self.telemetry = tel
                break
            # WARMED (OPEN_ENDS #21d): the first successfully produced bar ends
            # the cold window — the honest flag /api/world reports.
            self._warmed = True
            if not kicked_eigen:
                kicked_eigen = True
                # AUDIO-FIRST: now that a bar has warmed, kick off the deferred
                # heavy eigenmode ensemble (it never blocked the first sound).
                self._ensure_eigen_started()
            if not kicked_sweep:
                # eigen done (cached, or the worker landed and chained already) → make sure
                # the modes-by-temperature sweep is started even when eigen was a cache hit
                # and no worker ran to chain it. getattr-guarded: a bare test-harness player
                # (object.__new__, no _eigen) simply never triggers this. Idempotent.
                _eig = getattr(self, "_eigen", None)
                if _eig is not None and not _eig.get("pending", True):
                    kicked_sweep = True
                    self._ensure_sweep_started()
            now = _time.monotonic()
            if t0 is None or now - (t0 + sent / self.sr) > self.PACE_REANCHOR_SECONDS:
                t0 = now - sent / self.sr          # anchor/re-anchor at emission
            with self._sub_lock:
                subs = list(self._subscribers)
            for q in subs:
                try:
                    q.put_nowait(pcm)
                except Exception:
                    # subscriber fell behind: drop its oldest bar, keep it current.
                    try:
                        q.get_nowait()
                        q.put_nowait(pcm)
                    except Exception:
                        pass
            sent += len(pcm) // 2                  # mono int16 -> samples
            # Interruptible pacing wait: stop() must not have to out-wait a
            # bar-slot sleep (auditor note 2) — poll the playing flag.
            end = t0 + sent / self.sr - self.PACE_LEAD_SECONDS
            while self._playing.is_set():
                remaining = end - _time.monotonic()
                if remaining <= 0:
                    break
                _time.sleep(min(remaining, 0.05))

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._playing.set()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._playing.clear()
        # drain every subscriber queue
        with self._sub_lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                while True:
                    q.get_nowait()
            except Exception:
                pass

    # --- LIVE mode (papers/PREREG-live-mode.md, Train B2) -------------------
    def _straight_track_slices(self, track: int):
        """Look up ``track`` and its stored slices, or raise honestly —
        shared by ``live_start`` (first click) and ``_bridge_arrive`` (a
        journey's destination close), so both build the FULL FENCE from the
        exact same slice source (§2 of the prereg), never re-derived twice."""
        from . import live as live_mod
        track = int(track)
        by_id = {int(tr.track_id): tr for tr in self.world.tracks}
        if track not in by_id:
            raise ValueError(f"unknown track {track}")
        slices = track_unit_slices(self.world, by_id[track], self.M)
        if slices is None:
            raise live_mod.LiveCarrierUnavailable(
                "track_unit_slices refused this track (a unit lacks a stored "
                "role) — the same honest refusal the wavemap gives; LIVE "
                "cannot fence a track it cannot slice")
        return track, slices

    def _straight_live_dict(self, track: int, slices, t: float) -> dict:
        """Build the B-1 STRAIGHT-mode ``self._live`` payload for (``track``,
        the slice covering second ``t``) — used identically whether this is
        the FIRST click (``live_start``) or a bridge's destination close
        (``_bridge_arrive``). May raise ``live.LiveCarrierUnavailable`` (the
        fence construction, probed against the real writer)."""
        from . import live as live_mod
        j0 = live_mod.resolve_start_index(slices, t)
        unit_ids = live_mod.pin_unit_ids(slices, j0)
        fence = live_mod.build_full_fence(track, unit_ids)     # may raise
        # PROBE the writer NOW (not on the first produced bar) so a missing
        # wiring refuses honestly before straight play is ever promised.
        live_mod.clamp_call_kwargs(self.engine.writer.write_bar, fence)
        return {"mode": "straight", "clamp": fence, "track": int(track),
               "uid_index": live_mod.uid_index_map(slices),
               "current_unit": None, "current_slice_index": None,
               "starved": False,
               # the whole pinned run + the bar cursor over it; the produce
               # loop narrows this to ONE bar's window each bar so straight
               # play walks the track forward
               "pin_units": tuple(unit_ids), "bars_elapsed": 0,
               # the track's OWN stored slices (span/uid/role), so each bar
               # can cut its tatum window and widen per role
               "slices": slices,
               # straight play starts where the user CLICKED
               "start_group": live_mod.group_of_index(slices, j0),
               # built ONCE here, not per bar (the measured stall)
               "plan": live_mod.build_plan(slices),
               "core_units": frozenset(),
               "n_widened": 0, "off_window": 0, "n_cast": 0,
               "start_unit": int(slices[j0][2])}

    def live_start(self, track: int, t: float) -> dict:
        """B-1 amended / LM-3 / LM-10: close the FULL FENCE to (``track``, the
        slice covering second ``t``) and let straight play begin there AT
        ONCE — no bridge, no lean (AMENDMENT 2 A2.4: idle has no source
        character to travel from, so the first click emits no tilt payload
        at all). Reuses the SAME slice source the wavemap already reads
        (``track_unit_slices``) — never re-derived (§2 of the prereg).

        Raises ``ValueError`` for an unknown track, or
        ``live.LiveCarrierUnavailable`` if Part A's carrier isn't ready (not
        importable yet, or importable but not wired into ``write_bar``) — LIVE
        refuses rather than ever falling back to unfenced play."""
        track, slices = self._straight_track_slices(track)
        live_dict = self._straight_live_dict(track, slices, t)
        start_unit = live_dict.pop("start_unit")
        with self._live_lock:
            self._live = live_dict
            self._bridge = None      # a fresh straight start is never mid-journey
        self.set_region(np.zeros(self.M, dtype=np.float32))   # B-2's job, if any, is done
        self.start()               # ensure the shared produce loop is running
        return {"track": track, "unit": start_unit}

    def live_enter(self) -> None:
        """ENTERING the LIVE view: drop any fence AND any bridge, hold the
        transport idle-silent (AMENDMENT 2 B-0), and neutral the region-tilt
        lane (BR-6: a lean latched by a prior bridge must not survive into a
        fresh LIVE session — byte-identical to a player that never touched
        LIVE). The hold is enforced by ``_loop`` itself, never by an
        empty/neutral ClampTerms.

        This is deliberately SEPARATE from ``live_stop``. The idle hold means
        "the user is in LIVE and has not clicked yet" — it must NOT outlive the
        LIVE view, or GRID/TRACKS inherit a silenced engine (the cross-tab
        handback defect: one StreamPlayer serves all three views, so a hold set
        on leaving LIVE silenced the other two)."""
        with self._live_lock:
            self._live = {"mode": "idle", "clamp": None, "track": None,
                          "uid_index": {}, "current_unit": None,
                          "current_slice_index": None, "starved": False,
                          "pin_units": (), "bars_elapsed": 0,
                          "slices": (), "core_units": frozenset(),
                          "n_widened": 0, "off_window": 0, "n_cast": 0,
                          "via_bridge": False}
            self._bridge = None
        self.set_region(np.zeros(self.M, dtype=np.float32))

    def live_stop(self) -> None:
        """LEAVING LIVE (V-1 / BR-6): drop the fence AND any bridge, neutral
        the region-tilt lane, and release the transport back to the other
        views. Mode returns to "off" — never "idle", which would keep the
        produce loop parked for GRID/TRACKS as well."""
        with self._live_lock:
            self._live = {"mode": "off", "clamp": None, "track": None,
                          "uid_index": {}, "current_unit": None,
                          "current_slice_index": None, "starved": False,
                          "pin_units": (), "bars_elapsed": 0,
                          "slices": (), "core_units": frozenset(),
                          "n_widened": 0, "off_window": 0, "n_cast": 0,
                          "via_bridge": False}
            self._bridge = None
        self.set_region(np.zeros(self.M, dtype=np.float32))

    # --- THE BRIDGE (v0 — release + pull, no intervention; see live.py) ----
    def live_click(self, track: int, t: float) -> dict:
        """THE click dispatcher. Three cases, decided by what is already
        playing — no state machine beyond this, and no machine judgement about
        whether a journey is "done" (Amendment 6 / the proven negative:
        arrival does not occur, so there is nothing to detect).

          idle/off              -> Amendment 2's immediate straight start
          playing, NEW spot     -> travel toward it (the blend)
          mid-bridge, the SAME
          destination you are
          already traveling to  -> COMMIT: the fence closes there and
                                   straight play resumes at the clicked spot.

        LANDING IS A HUMAN ACT — a wall is human content; the machine cannot
        decide it. The second click IS the landing, not a report that one
        happened."""
        with self._live_lock:
            mode = self._live.get("mode")
            dest = None if not self._bridge else self._bridge.get("dest_track")
        if mode not in ("straight", "bridge"):
            return self.live_start(track, t)
        if mode == "bridge" and dest is not None and int(dest) == int(track):
            return self._live_commit(int(track), float(t))
        return self._live_bridge_click(int(track), float(t))

    def _live_commit(self, track: int, t: float) -> dict:
        """COMMIT-TO-LAND (Amendment 6, ruling 2). Close the fence on the
        track the blend is already traveling to, at the spot just clicked, and
        resume straight play. Nothing is measured, compared or waited for: the
        close CREATES the destination state rather than recognising one, which
        is exactly what the registered proven-negative says is the only way it
        can come about."""
        self._bridge_close(int(track), float(t))
        with self._live_lock:
            n_admitted = 1 if self._live.get("mode") == "straight" else 0
        return {"ok": True, "mode": "straight", "track": int(track),
                "committed": True, "n_admitted": n_admitted}

    def _live_bridge_click(self, track: int, t: float) -> dict:
        """B-1/B-2: (re-)latch a journey toward (``track``, ``t``). A click
        while ALREADY mid-bridge RE-ANCHORS — the release/lean already in
        flight simply keep going (momentum honest; there is no reason to
        restart a fence that is already open/opening toward a DIFFERENT
        target), only the destination and its pull target change, and the
        arrival window (recent placement-share history) resets — a fresh
        destination has no bearing on a share earned toward the old one."""
        from . import live as live_mod
        dest_track, dest_slices = self._straight_track_slices(track)
        stored_char = live_mod.stored_character(dest_slices, float(t), self.M)
        tgt = live_mod.pull_target(stored_char)
        dest_uid_index = live_mod.uid_index_map(dest_slices)
        with self._live_lock:
            source_track = self._live.get("track")
            prior = self._bridge
            cur_lean = None if prior is None else prior.get("lean_cur")
            cur_openness = 1.0 if prior is None else float(prior.get("openness_cur", 1.0))
        if source_track is None:
            # Defensive: live_click only reaches here when mode is "straight"
            # or "bridge", both of which always carry a source track. Refuse
            # rather than guess one.
            raise live_mod.LiveCarrierUnavailable(
                "no source track on record for this session's playing state")
        # ADMISSION IS HISTORY-FREE (Amendment 6, ruling 1): the new leg carries
        # exactly the tracks THE CURRENT LEG ACTUALLY DREW FROM, then that record
        # is cleared. No window, no trend, no decay — measurement showed there is
        # nothing to trend on (AUC 0.486 / 0.552 against 0.5, zero zero-share
        # bars), and that admission is self-fulfilling, so a sounding-over-W test
        # could only ever ratify what the fence already allowed. Clearing per leg
        # is what makes accumulation impossible (CL-4).
        with self._live_lock:
            drawn = set(int(x) for x in self._leg_drawn)
            self._leg_drawn = set()
        carried = drawn | {int(source_track)}
        carried.discard(int(dest_track))          # the destination is admitted by scope
        carry = tuple(sorted(carried)) or (int(source_track),)
        from collections import deque
        with self._live_lock:
            self._bridge = {
                "source_track": int(source_track), "dest_track": int(dest_track),
                # S-3: scope is fence DATA, chosen at journey start, constant
                # for this journey, logged. DIRECT (default) admits only the
                # carried set plus the destination; OPEN releases to the corpus.
                "scope": str(self._bridge_scope),
                "carry_tracks": carry,
                "dest_t": float(t), "dest_uid_index": dest_uid_index,
                "pull_target": tgt,
                "lean_cur": (tuple(cur_lean) if cur_lean is not None
                            else tuple(0.0 for _ in range(self.M))),
                "openness_cur": cur_openness,
                # REPORTED ONLY (Amendment 6): this bar's destination share and
                # this bar's full per-track blend, for the view's descriptive
                # copy. No history is kept because nothing reads history any
                # more — the completion path holds no window at all.
                "share": 0.0,
                "blend": {},
                "T_s_pinned": float(self._T_s), "bars_elapsed": 0,
                "dest_current_unit": None, "dest_current_slice_index": None,
            }
            self._live["mode"] = "bridge"
            self._live["current_unit"] = None
            self._live["current_slice_index"] = None
            self._live["starved"] = False
            self._live["via_bridge"] = False
        self.start()
        return {"track": int(dest_track), "bridge": True}

    def _bridge_close(self, dest_track=None, dest_t=None) -> None:
        """Close the fence on ``dest_track`` at ``dest_t`` and resume straight
        play (Amendment 6). Called ONLY by a human commit — the second click on
        the destination already being traveled to. There is no observed-arrival
        caller any more: the completion path holds no window, no high-water
        mark, no share level and no timeout, because none of those can decide
        this (see the registered proven-negative). The lean drops to neutral —
        its job is done; a closed fence alone determines content from here,
        exactly as straight play always has."""
        with self._live_lock:
            br = dict(self._bridge) if self._bridge else None
        if br is None:
            return
        try:
            track, slices = self._straight_track_slices(
                br["dest_track"] if dest_track is None else dest_track)
            live_dict = self._straight_live_dict(
                track, slices, br["dest_t"] if dest_t is None else float(dest_t))
        except Exception:
            # The destination became unfenceable mid-journey (should not
            # happen — it was already probed at click time). Never fabricate
            # arrival: fall back to idle-silent rather than claim a fence
            # that does not exist.
            logger.exception("the destination fence could not be closed on commit")
            self.live_enter()
            return
        live_dict.pop("start_unit", None)
        live_dict["via_bridge"] = True
        self.set_region(np.zeros(self.M, dtype=np.float32))     # B-2's job is done
        with self._live_lock:
            self._live = live_dict
            self._bridge = None

    def live_state(self) -> dict:
        """Measured, not asserted (the route contract): the unit/slice this
        reports comes from ``_finish_bar``'s own reduction of the produced
        bar's rows (the same placement feed the heatmap reads), never a timer
        or the originally-requested position. A session that has never
        touched LIVE ("off") reports "idle" — honest: no fence, nothing
        playing under one.

        For an ACTIVE bridge, also reports the fields the view needs to
        render the winding honestly (2026-08-14 reframe): the destination
        track, the RECENT per-bar destination placement-share history (not a
        smoothed scalar — B-4 reads raw per-bar shares), and a ``phase`` of
        "straight" | "bridging" | "stalled" | "arrived". "stalled" is a
        DISPLAY-ONLY read of "share never rose in the recent window" — it
        never feeds back into the fence/lean (BR-1); only
        a HUMAN COMMIT (a second click on the destination) can ever close
        the destination fence. The retired profile-distance floor (B-7)
        rides along as diagnostics only, never gating anything."""
        from . import live as live_mod
        with self._live_lock:
            live = dict(self._live)
            br = dict(self._bridge) if self._bridge else None
        raw_mode = live.get("mode")
        mode = "straight" if raw_mode in ("straight", "bridge") else "idle"
        bars_elapsed = int(live.get("bars_elapsed", 0))
        n_widened = int(live.get("n_widened", 0))
        out = {"mode": mode, "track": live.get("track"),
              "unit": live.get("current_unit"),
              "slice_index": live.get("current_slice_index"),
              "starved": bool(live.get("starved", False)),
              "bars_elapsed": bars_elapsed, "widened": n_widened,
              # ruling 3: reported ONLY while a straight-play pin exists. During a
              # bridge the pin is released and there is no window to show, so this
              # is null rather than a stale or invented span.
              "window": (live.get("window") if raw_mode == "straight" else None)}
        if raw_mode == "bridge" and br is not None:
            # BLENDING, DESCRIPTIVELY (Amendment 6, ruling 2). No phase called
            # "stalled", no high-water mark, no settle window, no target: the
            # blend is where the physics goes, and it ends when the human clicks
            # the destination again. Everything here is this bar's measurement,
            # reported for copy — nothing is compared to anything.
            blend = {int(k): float(v) for k, v in (br.get("blend") or {}).items()}
            carry = list(br.get("carry_tracks") or ())
            admitted = sorted(set(carry) | ({int(br["dest_track"])}
                                            if br.get("dest_track") is not None else set()))
            floor_diag = live_mod.measure_floor(list(self._live_wobble_hist))
            out.update({
                "phase": "blending",
                "source_track": br.get("source_track"),
                "dest_track": br.get("dest_track"),
                "dest_unit": br.get("dest_current_unit"),
                "dest_slice_index": br.get("dest_current_slice_index"),
                "share": float(br.get("share") or 0.0),
                "blend": blend,
                "admitted": admitted,
                "n_admitted": len(admitted),
                "openness": br.get("openness_cur"),
                "floor_diag": (floor_diag or {}).get("floor"),
                "T_s_pinned": br.get("T_s_pinned"),
                # THE SHAPE THE VIEW READS.
                "journey": {
                    "active": True,
                    "target": br.get("dest_track"),
                    "share": float(br.get("share") or 0.0),
                    "blend": blend,
                    "admitted": admitted,
                    "scope": br.get("scope"),
                    "carry_tracks": carry,
                    # the ONE thing the human can do to end it (ruling 2)
                    "commit_hint": "click the destination again to land",
                },
            })
        elif raw_mode == "straight":
            out["phase"] = "arrived" if live.get("via_bridge") else "straight"
        return out

    def wav_header(self, data_len: int = 0xFFFFFFFF - 44) -> bytes:
        """A streaming WAV header (mono int16 @ sr) with an open-ended size."""
        return _wav_header(self.sr, 1, data_len)

    def stream_chunks(self):
        """Yield the WAV header then this listener's PCM chunks as bars are produced,
        until stop. Each caller gets its OWN fan-out queue (see :meth:`subscribe`)."""
        import queue
        yield self.wav_header()
        q = self.subscribe()
        try:
            while self._playing.is_set():
                try:
                    yield q.get(timeout=1.0)
                except queue.Empty:
                    continue
        finally:
            self.unsubscribe(q)


def _to_int16(audio: np.ndarray) -> bytes:
    a = np.nan_to_num(np.asarray(audio, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    a = np.clip(a, -1.0, 1.0)
    return (a * 32767.0).astype("<i2").tobytes()


def _wav_header(sr: int, channels: int, data_len: int) -> bytes:
    byte_rate = sr * channels * 2
    block_align = channels * 2
    return b"".join([
        b"RIFF", struct.pack("<I", 36 + data_len), b"WAVE",
        b"fmt ", struct.pack("<IHHIIHH", 16, 1, channels, sr, byte_rate, block_align, 16),
        b"data", struct.pack("<I", data_len),
    ])
