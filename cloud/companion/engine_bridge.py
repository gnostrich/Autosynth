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
# world's mode-set at, so the pad can reselect its basis as the operator heats. The default
# T_s=1.0 IS in the grid (it must be — the pad restores the authoritative basis there). This
# is 7x the single-temperature ensemble, so it runs LAST (after the boot eigen lands) in the
# same off-playback background thread, cached to a sidecar; never on the audio path.
_SWEEP_T_GRID = [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0]
_SWEEP_DEFER_POLL = 1.5  # while audio is live, the sweep worker parks between temperatures
                         # (this poll interval) instead of computing — so a one-time,
                         # multi-minute measurement can never starve realtime playback on a
                         # constrained host. It resumes the instant playback pauses.
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
                      n_bar: int) -> np.ndarray:
    return np.stack([_eigen_run_mean(world, sigma, builder(), seed0 + i, n_bar, M)
                     for i in range(n_seed)])


def compute_eigenmodes(world, sigma, M: int, n_seed: int = _EIGEN_N_SEED,
                       n_bar: int = _EIGEN_N_BAR, h: float = _EIGEN_H,
                       n_boot: int = _EIGEN_N_BOOT, n_null: int = _EIGEN_N_NULL,
                       floor_pct: float = _EIGEN_FLOOR_PCT,
                       rng_seed: int = 20260718) -> dict:
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
        mp = _eigen_node_means(world, sigma, up, M, 70000 + j * 1000, n_seed, n_bar)
        mm = _eigen_node_means(world, sigma, um, M, 70000 + j * 1000 + 500, n_seed, n_bar)
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
        self._lock = threading.Lock()
        self._playing = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._bar_index = 0
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
        # STATIC per-world field telemetry (computed ONCE, here at load): the SAME
        # read-only reductions the desktop engine emits over /ets/profiles +
        # /ets/unitpool (ets.engine.engine.track_anchor_profiles / role_unit_pool).
        # They read only the frozen world (fstate.B + track provenance) — no bank,
        # no settlement, no writer, no F. Mirrors Engine.run_live's startup exactly.
        from ets.engine.engine import track_anchor_profiles, role_unit_pool
        self._track_profiles = track_anchor_profiles(self.world)   # {tid: (M,)}
        self._role_pools = role_unit_pool(self.world)              # {role: [...]}
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
        # ONCE per world by an off-playback background worker (7x the boot ensemble, so it runs
        # AFTER the eigen lands) and cached to a sidecar, exactly like the eigen modes — so any
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
        self._sweep_args = ((sigma, list(_SWEEP_T_GRID), eigen_n_seed, eigen_n_bar)
                            if (_missing and sigma is not None and self.M > 0) else None)
        self._static_field_cache: Optional[dict] = None
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
        """Start the deferred modes-by-temperature measurement exactly once. It is 7x the
        boot ensemble, so it is triggered only AFTER the eigen worker lands (chained from
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

        AUDIO SAFETY (auditor Note A): this one-time, multi-minute measurement DEFERS while
        playback is live — it parks between temperatures until `self._playing` clears — so it
        can never push the realtime produce loop past deadline and cause mid-stream
        under-runs on a constrained host. It resumes the instant playback pauses; a set
        played nonstop simply shows the honest `sweep_pending` state until the first pause.
        A failure is logged (pending clears) rather than left silently stuck."""
        import time as _t
        try:
            from cloud.companion.eigen_experimental import temperature_sweep
            # RESUME: seed from any partial table already measured (survives eviction/redeploy).
            prior = self._sweep if isinstance(self._sweep, dict) else None
            rows = list(prior["sweep"]) if (prior and prior.get("sweep")) else []
            done_T = {round(float(r["T_s"]), 4) for r in rows}
            meta = ({k: prior[k] for k in ("M", "n_seed", "n_bar", "observable_names")}
                    if (prior and "observable_names" in prior) else None)
            for T in grid:
                if round(float(T), 4) in done_T:
                    continue                             # already measured — resume past it
                # Park (don't compute) while audio is live — heavy work only in idle windows.
                while getattr(self, "_playing", None) is not None and self._playing.is_set():
                    _t.sleep(_SWEEP_DEFER_POLL)
                part = temperature_sweep(self.world, sigma, self.M, [T],
                                         n_seed=n_seed, n_bar=n_bar)
                if not (isinstance(part, dict) and isinstance(part.get("sweep"), list) and part["sweep"]):
                    return                               # honest: measurement produced nothing usable
                if meta is None:
                    meta = {k: part[k] for k in ("M", "n_seed", "n_bar", "observable_names")}
                rows.append(part["sweep"][0])
                rows.sort(key=lambda r: float(r["T_s"]))
                landed = dict(meta); landed["sweep"] = list(rows)
                self._sweep = landed                     # land incrementally (atomic reassign)
                # PERSIST each temperature as it lands — an eviction here loses nothing; the
                # next load resumes the remaining temperatures from this sidecar.
                self._write_sweep_cache(landed, n_seed, n_bar)
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
            result = compute_eigenmodes(self.world, sigma, self.M,
                                        n_seed=eigen_n_seed, n_bar=eigen_n_bar)
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
        return {"ready": True, "M": self.M, "sr": self.sr,
                "world": Path(self.world_path).name,
                "is_trained": self.is_trained,
                "armed": armed, "disarmed": disarmed,
                "degenerate": degenerate, "steerable": steerable,
                "region_armed": ("region" in armed),
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
            — each role's drill-in unit pool (role_unit_pool). The UNIT grain.
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
            kind = "track" if self.is_trained else "demo track"
            names = {int(t): "%s %d" % (kind, int(t)) for t in profiles}
            self._static_field_cache = {"profiles": profiles, "unit_pools": pools,
                                        "track_names": names,
                                        "profile_armed": bool(self._profile_armed)}
        return self._static_field_cache

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
        live loop does. Returns (pcm_int16_bytes, roles_list)."""
        from ets.engine.engine import (bar_schedule, _playback_soft_limit,
                                        bar_role_activity, nowplaying_activity)
        from ets.render import render as render_schedule
        self._ensure_bank()
        u = self._current_lane()
        tilt = self.engine._tilt_for(u)                      # ONE lane->tilt point
        r = self.engine.writer.write_bar(tilt=tilt)
        sched = bar_schedule(self.world, r.rows, self.s_phase)
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
        self._bar_index = int(r.bar)
        lanes = self._lane_readouts(r)
        loop_val, slide_val = self._gauge_meters(r)
        self.telemetry = {"roles": roles, "bar": int(r.bar),
                          "t": float(r.bar * self.engine.writer.bar_seconds),
                          "nowplaying": nowplaying,
                          "lanes": lanes, "loop": loop_val, "slide": slide_val}
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
        while self._playing.is_set():
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
