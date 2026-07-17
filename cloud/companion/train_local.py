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

σ_φ WALL (honest, surfaced not patched): the world is saved with ``sigma_phi=None``
— exactly as the reference standalone ``build_world_from_tracks`` does. Contrary to
the literal MVP-2 plan, the engine's ``resolve_sigma`` does NOT fall back to the
registered σ_φ artifact for a freshly-trained world: the artifact is bound to the
DEMO world's content hash, and a trained world has a NEW hash, so ``resolve_sigma``
RAISES ``STALE CALIBRATION`` (it will not lean on a foreign world's scale). That
raise fires at LOAD, so the trained world cannot even play untilted. This BUILD step
is therefore honest and complete (it produces a verified, CS-clean world file), but
PLAY is blocked at the σ_φ resolution step — handled by ``Companion.run_train``
(reports ``playback: blocked``; keeps the calibrated demo live; invents no scale).
The clean fix is a ``resolve_sigma`` precedence revision (foreign-hash artifact →
treat as absent → untilted-only) plus, for live steering, a per-corpus σ_φ
calibration — both DEFERRED and disclosed in PREREG-cloud-mvp2 (Phase-2 seam: BUILD
wired, PLAY blocked). We do NOT fabricate a σ_φ artifact or embed an all-disarmed one
here (each would be a fake measurement / a silent-fallback steer no-op).
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


def build_trained_world(audio_paths: List[str], out_path: str,
                        cloud_url: str = "inproc", seed: int = 0,
                        sweeps: int = 8, sigma: Optional[float] = None) -> dict:
    """Ingest local audio -> stage-3 -> CLOUD anchor-fit -> verify -> build_index ->
    save a playable ``.etsworld`` at ``out_path``.

    Returns ``{"ok", "world", "receipt", "is_trained": True}``. Raises on any
    verify/transport failure (the caller surfaces it as a 502/400).

    This is faithful reuse of ``ets.writer.build_world_from_tracks``; the ONLY
    divergence is that ``fstate`` is the cloud's anchor-fit result rather than the
    local ``anchors.build_world`` call — that is the whole point of the offload.
    """
    _pin_archv6()

    # --- LOCAL ingest: raw audio -> Track (recipes/provenance stay on device) ---
    from ets.ingestion.pipeline import ingest
    from ets.geometry import roles
    tracks = [ingest(path, i, sr=44100) for i, path in enumerate(audio_paths)]

    # --- LOCAL stage-3: the ONLY thing that may cross the wire ------------------
    protos = [roles.extract_prototypes(t, seed=seed) for t in tracks]

    # --- CLOUD anchor-fit (the guarded, whitelist-encoded wire exit) -----------
    from cloud.common import encode_job, decode_result, verify_receipt
    from cloud.client.cli import post_job          # the SINGLE wire exit
    params = {"seed": seed, "sweeps": sweeps, "sigma": sigma}
    job = encode_job(protos, params)               # stage-3 ONLY (structural)
    result_bytes = post_job(job, cloud_url)
    result = decode_result(result_bytes)
    verify_receipt(protos, result)                 # raises on a tampered world
    fstate = result.fstate

    # --- LOCAL: realization index + playable world (never crosses the wire) ----
    from ets.writer import build_index, World, _representative_tatum_len
    from ets.engine.worldfile import save_world
    index = build_index(fstate, protos, tracks)
    world = World(
        fstate=fstate, protos=protos, tracks=tracks,
        info=(result.receipt or {}), index=index,
        out_tatum_len=_representative_tatum_len(tracks), sr=int(tracks[0].sr))

    # Source references point at the USER'S LOCAL audio; the engine re-derives unit
    # audio deterministically via ets.render.load_source_units (G0-style recon, no
    # choices). The audio itself is NOT embedded and NEVER left the device.
    sources = {"kind": "corpus",
               "paths": {int(t.track_id): audio_paths[i]
                         for i, t in enumerate(tracks)}}

    # sigma_phi=None (matches build_world_from_tracks). NOTE the σ_φ WALL in the
    # module docstring: this makes a VERIFIED, CS-clean world file, but the engine
    # refuses to PLAY it until the resolve_sigma precedence revision + per-corpus
    # σ_φ calibration land (both deferred/disclosed). We deliberately do NOT embed a
    # fabricated or all-disarmed σ_φ here — that would fake a measurement.
    save_world(out_path, world, sources, sigma_phi=None)

    return {"ok": True, "world": out_path,
            "receipt": _jsonable_receipt(result.receipt), "is_trained": True}
