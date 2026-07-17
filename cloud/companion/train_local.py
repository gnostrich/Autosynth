"""The train -> play-YOUR-corpus seam (MVP-2 phase-2, the local build_index half).

This is the LOCAL half of a cloud train: the cloud returns only the anchor
GEOMETRY (``fstate``, the gauge-invariant intrinsic structure); turning it into a
PLAYABLE world needs the on-device realization index + source references, which
depend on the user's local tracks/audio and therefore can NEVER move to the cloud
(CS-1). This module does exactly that assembly and nothing else.

It mirrors the reference standalone builder
``ets.writer.build_world_from_tracks`` VERBATIM, with ONE substitution: instead of
the LOCAL ``anchors.build_world``, the ``fstate`` comes from the CLOUD anchor-fit
(the offloaded heavy step). Every other piece — ingest, stage-3 prototypes,
``build_index``, the ``World`` object, ``save_world`` — is the same engine code
the native instrument uses; nothing is re-implemented.

CS boundary (load-bearing):
  * The ONLY wire exit is ``cloud.client.cli.post_job`` on the whitelist-encoded
    stage-3 job (``cloud.common.encode_job`` reads ONLY cost/mass/slot_hist/
    band_profile). Tracks, raw audio, provenance, and the realization index are
    NEVER serialized here and never cross the wire (CS-1).
  * All renderer/engine imports live in THIS module (and engine_bridge), never on
    the companion's cloud path (app.py / cli.py stay decoder-free, CS-4). This
    module is imported LAZILY (only when raw audio is present), and its engine
    imports are deferred to call time so importing it is cheap.

σ_φ RESOLUTION (measured, not fabricated): a freshly-trained world has a NEW content
hash, so the REGISTERED σ_φ artifact (bound to the DEMO world) is foreign to it and
``engine.resolve_sigma`` would refuse it (STALE — it will not lean on a foreign
world's scale). The correct resolution — exactly what the native pipeline does at
world-freeze — is to MEASURE this corpus's own σ_φ and EMBED it in the world file.
``resolve_sigma``'s precedence is ``--sigma-phi > EMBEDDED (wf.sigma_phi) >
registered``, so an embedded σ_φ is consumed via ``tilt.SigmaPhi.from_mapping`` and
NEVER reaches the registered-artifact staleness guard. ``_calibrate_sigma_phi`` runs
the untilted (u=0) settlement of THIS world and reads per-observable fluctuations,
mirroring ``scripts/run_sigma_phi.py`` [3]-[4] IN-PROCESS (it does NOT write the
registered artifact and never touches ``ets/calibration/sigma_phi.json``). It reuses
that instrument's OWN estimator ``_std`` verbatim (sample std ddof=1; exact 0.0 on
constant input) so identifiability is ``σ>0`` EXACTLY — no invented floor. As on the
founding world, ``density`` and ``gauge`` have zero untilted fluctuation at u=0 and
are recorded non-identifiable → DISARMED (a measured fact, not a fake); ``region``,
``cont``, ``novelty`` are armed. This adds one untilted settlement of compute at
train time (disclosed). If that settlement fails its F-descent certificate on a
corpus, THAT is a real wall (raised loudly), not a scale to fabricate.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

# The ui-v5 engine tree (architecture-v6) — same pin the render bridge enforces.
_ARCH_V6 = str(Path(__file__).resolve().parents[2] / "architecture-v6")

# Audio extensions that route to THIS seam (raw ingest -> tracks). A .npz bundle is
# the geometry-only offline path and is handled by the caller, not here.
AUDIO_EXTS = frozenset({".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aif", ".aiff", ".aac"})


def _pin_archv6() -> None:
    """Force the capped ui-v5 engine tree to the FRONT of sys.path and assert it
    actually resolved — the SAME loud check the render bridge makes. If root
    engine-v1 shadows it we would ingest/build against the wrong tree; fail loud
    rather than silently produce a world the live-capped engine can't own."""
    while _ARCH_V6 in sys.path:
        sys.path.remove(_ARCH_V6)
    sys.path.insert(0, _ARCH_V6)
    import ets.engine.engine as _eng
    if not (hasattr(_eng, "_playback_soft_limit") and hasattr(_eng, "bar_role_activity")):
        raise RuntimeError(
            "train_local resolved the ROOT engine-v1 (missing the live cap + "
            "telemetry). architecture-v6 must own `import ets`; run via "
            "`python -m cloud.companion`. resolved: "
            f"{getattr(_eng, '__file__', '?')}")


def _instrument_std():
    """Return the registered σ_φ instrument's OWN estimator ``_std`` (sample std
    ddof=1, exact 0.0 on constant input — the pre-registered estimator, honest on
    exact constancy). Loaded from ``scripts/run_sigma_phi.py`` by file path so there
    is ONE definition of the estimator, never a re-derived second copy. The script
    is import-safe: its only top-level effects are constant defs + a sys.path insert
    (its filesystem/registry work lives under ``if __name__ == '__main__'``)."""
    import importlib.util
    src = _ARCH_V6 + "/scripts/run_sigma_phi.py"
    spec = importlib.util.spec_from_file_location("_ets_sigma_phi_instrument", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._std


def _calibrate_sigma_phi(world, tracks) -> dict:
    """Measure THIS trained corpus's own σ_φ and return the mapping
    ``ets.writer.tilt.SigmaPhi.from_mapping`` consumes (to embed in the world file).

    Mirrors ``scripts/run_sigma_phi.py`` steps [3]-[4] IN-PROCESS: an untilted (u=0)
    batch settlement of R = corpus-bar-count bars, then the per-bar Layer-0
    observables, then the pre-registered estimator (sample std ddof=1). Identifiable
    := σ>0 EXACTLY (the instrument's ``_std`` is exact-0 on constant input) — NO
    floor. This does NOT write the registered artifact; the result is embedded so
    ``resolve_sigma`` uses it via the EMBEDDED precedence, before the registered
    (demo-world) artifact is ever consulted.
    """
    import numpy as _np
    from ets.writer import OutputGrid, TapeNode, settle_tape, realize
    from ets.writer.tape import S_PHASE
    from ets.connector.phi import phi_bars, role_maps_from_world
    _std = _instrument_std()

    R = int(sum(int(t.units["bar"].max()) + 1 for t in tracks))  # corpus bar count
    grid = OutputGrid(sr=world.sr, tatum_len=world.out_tatum_len, n_slots=R * S_PHASE)
    tape = TapeNode(grid=grid, M=world.M)
    res = settle_tape(world.fstate, tape)            # untilted (u=None): the u=0 form
    if not (res.converged and res.monotone):
        raise RuntimeError(
            "σ_φ calibration: the untilted (u=0) settlement failed its F-descent "
            f"certificate on this corpus (converged={res.converged}, "
            f"monotone={res.monotone}). This is a REAL wall — the calibration is "
            "invalid on a non-settling world; surface it, never fabricate a scale.")
    sched, _meta = realize(res.O, tape, world.fstate, world.index)
    maps = role_maps_from_world(world)
    phis = phi_bars(sched, maps, S_PHASE)  # keys: region,density,continuity,gauge,novelty

    reg = _np.asarray(phis["region"], float)         # (R, M): per-anchor region φ
    sig_region = _np.array([_std(reg[:, k]) for k in range(reg.shape[1])])
    sig = {"density": _std(_np.asarray(phis["density"], float)),
           "cont": _std(_np.asarray(phis["continuity"], float)),  # φ id: cont (=continuity)
           "gauge": _std(_np.asarray(phis["gauge"], float)),
           "novelty": _std(_np.asarray(phis["novelty"], float))}

    # region identifiability collapses all-or-nothing (as resolve_sigma does for the
    # registered artifact and as tilt.is_identifiable('region') reads it).
    identifiable = {"region": bool(_np.all(sig_region > 0.0))}
    for k, v in sig.items():
        identifiable[k] = bool(v > 0.0)

    return {
        "region": [float(v) for v in sig_region],
        "density": float(sig["density"]), "cont": float(sig["cont"]),
        "gauge": float(sig["gauge"]), "novelty": float(sig["novelty"]),
        "identifiable": identifiable,
        "meta": {
            "source": ("cloud.companion.train_local per-corpus σ_φ (untilted "
                       "settlement; mirrors scripts/run_sigma_phi.py [3]-[4], "
                       "in-process; registered artifact NOT written)"),
            "n_bars": int(R),
            "estimator": "sample std ddof=1; identifiable := sigma>0 exactly; no floor",
        },
    }


def _jsonable_receipt(receipt) -> dict:
    """Coerce a decoded receipt (numpy scalars/arrays) to JSON-friendly Python —
    the same shape the geometry-only path returns."""
    out = {}
    for k, v in receipt.items():
        if isinstance(v, bool):
            out[k] = v
        elif hasattr(v, "ndim") and getattr(v, "ndim", 0) != 0:
            out[k] = v.tolist()
        elif hasattr(v, "item"):
            out[k] = v.item()
        elif hasattr(v, "__float__"):
            out[k] = float(v)
        else:
            out[k] = v
    return out


# The REAL, ordered stages the seam walks (design §4A). ``build_trained_world``
# emits each name to ``progress`` at its true boundary — this tuple is the single
# source of truth for the stage sequence the FE renders. It is NOT decorative: each
# entry corresponds to a distinct ``_stage_*`` step below that does real work.
TRAIN_STAGES = ("ingest", "stage3", "cloud_fit", "verify", "build", "sigma_phi", "save")


def _stage_ingest(audio_paths: List[str], seed: int):
    """LOCAL ingest: raw audio -> Track (recipes/provenance stay on device)."""
    from ets.ingestion.pipeline import ingest
    return [ingest(path, i, sr=44100) for i, path in enumerate(audio_paths)]


def _stage_stage3(tracks, seed: int):
    """LOCAL stage-3 prototypes: the ONLY thing that may cross the wire."""
    from ets.geometry import roles
    return [roles.extract_prototypes(t, seed=seed) for t in tracks]


def _stage_cloud_fit(protos, cloud_url: str, seed: int, sweeps: int,
                     sigma: Optional[float]) -> bytes:
    """CLOUD anchor-fit via the guarded, whitelist-encoded SINGLE wire exit."""
    from cloud.common import encode_job
    from cloud.client.cli import post_job          # the SINGLE wire exit
    params = {"seed": seed, "sweeps": sweeps, "sigma": sigma}
    job = encode_job(protos, params)               # stage-3 ONLY (structural)
    return post_job(job, cloud_url)


def _stage_verify(protos, result_bytes: bytes):
    """Decode + verify the receipt (raises on a tampered world)."""
    from cloud.common import decode_result, verify_receipt
    result = decode_result(result_bytes)
    verify_receipt(protos, result)
    return result


def _stage_build(fstate, protos, tracks, audio_paths: List[str], receipt):
    """LOCAL realization index + playable World (never crosses the wire)."""
    from ets.writer import build_index, World, _representative_tatum_len
    index = build_index(fstate, protos, tracks)
    world = World(
        fstate=fstate, protos=protos, tracks=tracks,
        info=(receipt or {}), index=index,
        out_tatum_len=_representative_tatum_len(tracks), sr=int(tracks[0].sr))
    # Source references point at the USER'S LOCAL audio; the engine re-derives unit
    # audio deterministically via ets.render.load_source_units (G0-style recon, no
    # choices). The audio itself is NOT embedded and NEVER left the device.
    sources = {"kind": "corpus",
               "paths": {int(t.track_id): audio_paths[i]
                         for i, t in enumerate(tracks)}}
    return world, sources


def _stage_save(out_path: str, world, sources, sigma_phi) -> None:
    from ets.engine.worldfile import save_world
    save_world(out_path, world, sources, sigma_phi=sigma_phi)


def build_trained_world(audio_paths: List[str], out_path: str,
                        cloud_url: str = "inproc", seed: int = 0,
                        sweeps: int = 8, sigma: Optional[float] = None,
                        progress=None) -> dict:
    """Ingest local audio -> stage-3 -> CLOUD anchor-fit -> verify -> build_index ->
    save a playable ``.etsworld`` at ``out_path``.

    Returns ``{"ok", "world", "receipt", "is_trained": True}``. Raises on any
    verify/transport failure (the caller surfaces it as a 502/400).

    This is faithful reuse of ``ets.writer.build_world_from_tracks``; the ONLY
    divergence is that ``fstate`` is the cloud's anchor-fit result rather than the
    local ``anchors.build_world`` call — that is the whole point of the offload.

    ``progress`` (optional callable ``progress(stage_name)``) is invoked at each REAL
    stage boundary in ``TRAIN_STAGES`` order (design §4A honest progress). It is a
    read-only observer — it never gates or alters the pipeline, so a caller that
    passes None gets the identical computation.
    """
    _pin_archv6()

    def _p(stage: str) -> None:
        if progress is not None:
            progress(stage)

    _p("ingest")
    tracks = _stage_ingest(audio_paths, seed)
    _p("stage3")
    protos = _stage_stage3(tracks, seed)
    _p("cloud_fit")
    result_bytes = _stage_cloud_fit(protos, cloud_url, seed, sweeps, sigma)
    _p("verify")
    result = _stage_verify(protos, result_bytes)
    _p("build")
    world, sources = _stage_build(result.fstate, protos, tracks, audio_paths,
                                  result.receipt)
    # MEASURE this corpus's own σ_φ (untilted settlement) and EMBED it, so the
    # engine plays AND steers the trained world via the embedded precedence — never
    # the demo world's registered artifact. See the module docstring σ_φ RESOLUTION.
    _p("sigma_phi")
    sigma_phi = _stage_sigma_phi(world, tracks)
    _p("save")
    _stage_save(out_path, world, sources, sigma_phi)

    disarmed = sorted(k for k, v in sigma_phi["identifiable"].items() if not v)
    return {"ok": True, "world": out_path,
            "receipt": _jsonable_receipt(result.receipt), "is_trained": True,
            "sigma_phi_disarmed": disarmed}


def _stage_sigma_phi(world, tracks) -> dict:
    """Per-corpus σ_φ calibration (thin alias of ``_calibrate_sigma_phi`` so the
    stage set is uniform and independently injectable in tests)."""
    return _calibrate_sigma_phi(world, tracks)
