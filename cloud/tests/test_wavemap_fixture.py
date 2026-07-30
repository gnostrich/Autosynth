"""Shared REAL world fixture + probe harness for the WAVEMAP gates
(PREREG-waveform-scrub, WS-1/WS-2/WS-7/WS-8 backend halves).

The wavemap gates need a world that is real in every way they touch:
  * built by the REAL engine path (``roles.extract_prototypes`` ->
    ``anchors.build_world`` -> ``build_index``), so ``fstate`` / ``index`` /
    ``provenance_index`` are the genuine frozen objects — nothing hand-stitched;
  * sources ``{"kind": "corpus"}`` naming REAL audio files on disk (the train-seam
    shape, ``cloud.companion.train_local._stage_build``), so the envelope path
    decodes actual given material;
  * a NON-DEGENERATE stored role assignment — ``world.index.unit_role`` must use
    more than one role, or WS-1 could pass on a world where every possible q is the
    same vector and a smoothed variant would be indistinguishable.

The source tracks are synthetic (two well-separated timbre families each) so the
fixture runs offline in seconds without the beat model; the WORLD is engine-built
from them, not fabricated. This module's own gates are the fixture's teeth: if the
fixture ever stops being a real, varied, corpus-sourced world, they fail HERE rather
than silently defanging WS-1.

HARNESS: every gate that touches a ``StreamPlayer`` runs OUT OF PROCESS (the
established cloud-test pattern, see test_informative_B_arming), because the bridge
requires the ui-v5 engine tree (architecture-v6) to own ``import ets`` and the
in-process cloud suite has already imported root ``ets``. ``probe(body)`` runs a
child with arch-v6 pinned, the fixture world built (once, cached on disk across
probes), and returns the JSON its last line prints.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_DIR_ENV = "ETS_WAVEMAP_FIXTURE_DIR"


def fixture_dir() -> Path:
    """The per-session dir holding the fixture world + its wavs. Path only — the
    world is BUILT by ``ensure_world`` inside the arch-v6 child."""
    d = os.environ.get(_DIR_ENV)
    if not d:
        d = tempfile.mkdtemp(prefix="ets-wavemap-world-")
        os.environ[_DIR_ENV] = d
    Path(d).mkdir(parents=True, exist_ok=True)
    return Path(d)


# --- world construction (runs in the child; imports ets lazily) --------------

def _make_track(tid: int, n_slots: int = 24, n_bands: int = 8, sr: int = 22050):
    """One real ``Track`` with TWO separated timbre families (so the frozen world's
    role structure is non-degenerate). Same assembly the ingest pipeline uses
    (``pipeline.build_track``); only the descriptors are synthetic."""
    import numpy as np
    from ets.ingestion import beatclock as bc
    from ets.ingestion.pipeline import build_track
    rng = np.random.default_rng(tid)
    n = n_slots * n_bands
    hop = sr // 8
    bounds = np.arange(n_slots + 1, dtype=np.int64) * hop
    slot_ix = np.repeat(np.arange(n_slots), n_bands)
    band_ix = np.tile(np.arange(n_bands), n_slots)
    uid = np.arange(n)
    phase = (slot_ix % 8) / 8.0
    fam = (band_ix >= n_bands // 2).astype(int)
    centers = np.array([[-4.0, -4.0, 0.0, 0.0], [4.0, 4.0, 0.0, 0.0]])
    timbre = centers[fam] + 0.15 * rng.standard_normal((n, 4))
    timbre[:, 2] += 2.0 * (tid % 2)
    chroma = np.full((n, 12), 1.0 / 12) + 0.01 * rng.random((n, 12))
    chroma[fam == 1, 0] += 0.5
    chroma /= chroma.sum(1, keepdims=True)
    masses = 0.2 + 0.8 * rng.random(n)
    units_cols = {"unit_id": uid, "slot": slot_ix, "band": band_ix,
                  "phase": phase, "bar": slot_ix // 8,
                  "level": np.zeros(n, np.int64)}
    prov_cols = {"unit_id": uid, "track_id": np.full(n, tid, np.int64),
                 "src_start": bounds[slot_ix], "src_end": bounds[slot_ix + 1],
                 "band": band_ix}
    grid = bc.BeatGrid(sr=sr, beats=bounds, downbeats=bounds[::8],
                       tatum_boundaries=bounds,
                       tempo_curve=np.full(max(n_slots - 1, 1), 120.0),
                       beats_per_bar=8, tatums_per_beat=1)
    return build_track(tid, units_cols, masses, timbre, chroma, phase, grid,
                       prov_cols, int(bounds[-1]), sr, rng)


def _write_wav(path: str, n_samples: int, sr: int, tid: int) -> None:
    """Real audio for the track: a tone with a slow amplitude envelope, so its
    |peak| envelope is NON-constant (a blank/wrong decode is visible)."""
    import numpy as np
    import soundfile as sf
    t = np.arange(n_samples) / float(sr)
    y = 0.4 * np.sin(2 * np.pi * 110.0 * (1 + tid) * t)
    y *= 0.5 + 0.5 * np.sin(2 * np.pi * 0.7 * t + tid)
    sf.write(str(path), y.astype("float32"), sr)


def ensure_world(d) -> str:
    """Build the fixture world into ``d`` if absent; return the world path. Called
    in the child (after arch-v6 is pinned) so the pickled world is the engine tree
    the bridge loads."""
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    out = d / "trained.etsworld"
    if out.exists():
        return str(out)
    from ets.writer import build_world_from_tracks
    from ets.engine.worldfile import save_world
    # σ_φ: MEASURED for this world by the production train seam's own calibration
    # (cloud.companion.train_local._calibrate_sigma_phi — the registered instrument's
    # estimator, run on THIS world's untilted settlement), then embedded, exactly as a
    # real trained world gets it. Never fabricated, never borrowed from another world
    # (the engine's staleness guard would refuse that, and rightly).
    from cloud.companion.train_local import _calibrate_sigma_phi
    tracks = [_make_track(i) for i in range(4)]
    paths = {}
    for tr in tracks:
        p = d / ("t%d.wav" % tr.track_id)
        _write_wav(str(p), tr.n_samples, tr.sr, int(tr.track_id))
        paths[int(tr.track_id)] = str(p)
    world = build_world_from_tracks(tracks, seed=0)
    sigma_phi = _calibrate_sigma_phi(world, tracks)
    tmp = str(out) + ".tmp"
    save_world(tmp, world, {"kind": "corpus", "paths": paths}, sigma_phi=sigma_phi)
    os.replace(tmp, out)
    return str(out)


# --- out-of-process probe harness -------------------------------------------

_PRELUDE = r'''
import json, os, sys
sys.path.insert(0, r"{root}")
sys.path.insert(0, r"{arch}")          # arch-v6 must OWN `import ets` (bridge asserts)
from cloud.tests.test_wavemap_fixture import ensure_world   # no ets import at import time
WORLD = ensure_world(r"{d}")
WDIR = r"{d}"
def emit(obj):
    print("PROBE " + json.dumps(obj))
'''


def probe(body: str, timeout: int = 1800) -> dict:
    """Run ``body`` in a child with arch-v6 pinned + the fixture world built; return
    the object it passed to ``emit``."""
    src = _PRELUDE.format(root=str(_ROOT), arch=str(_ROOT / "architecture-v6"),
                          d=str(fixture_dir())) + body
    r = subprocess.run([sys.executable, "-c", src], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=timeout)
    assert r.returncode == 0, f"probe failed:\n{r.stdout}\n{r.stderr}"
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("PROBE ")]
    assert lines, f"probe emitted nothing:\n{r.stdout}\n{r.stderr}"
    return json.loads(lines[-1][len("PROBE "):])


# --- the fixture's own teeth -------------------------------------------------

_FIXTURE_PROBE = r'''
from collections import Counter
from pathlib import Path
import librosa
from ets.engine.worldfile import load_world

wf = load_world(WORLD)
w = wf.world
missing_src = [p for p in wf.sources.get("paths", {}).values() if not Path(p).is_file()]
missing_role = [(int(t.track_id), int(u)) for t in w.tracks
                for u in t.provenance_index["unit_id"]
                if (int(t.track_id), int(u)) not in w.index.unit_role]
decode_delta = []
for t in w.tracks:
    y, _ = librosa.load(wf.sources["paths"][int(t.track_id)], sr=t.sr, mono=True)
    decode_delta.append([int(len(y) - t.n_samples), int(0.02 * t.sr)])
emit({"kind": wf.sources.get("kind"),
      "n_paths": len(wf.sources.get("paths", {})), "n_tracks": len(w.tracks),
      "missing_src": missing_src, "n_missing_role": len(missing_role),
      "roles_used": sorted(Counter(w.index.unit_role.values())), "M": int(w.M),
      "decode_delta": decode_delta})
'''


def test_fixture_world_is_real_corpus_sourced_and_role_varied():
    d = probe(_FIXTURE_PROBE)
    assert d["kind"] == "corpus", "fixture must carry the train-seam corpus sources"
    assert d["n_paths"] == d["n_tracks"] and not d["missing_src"], \
        f"every track needs a real source file on disk: {d}"
    assert d["n_missing_role"] == 0, \
        "the fixture world must store a role for EVERY unit (else q is unavailable)"
    assert len(d["roles_used"]) >= 2, (
        "fixture world's stored unit_role uses a single role — WS-1 would not "
        f"discriminate a smoothed q from the stored one: {d['roles_used']}")
    assert d["M"] >= 2


def test_fixture_source_audio_matches_the_stored_sample_length():
    """The envelope is drawn on the world's stored ``n_samples`` axis, so the fixture
    files must really decode to that length — otherwise the wavemap would honestly
    REFUSE and every downstream gate would be vacuous."""
    d = probe(_FIXTURE_PROBE)
    for delta, tol in d["decode_delta"]:
        assert abs(delta) <= max(1, tol), \
            f"fixture audio does not decode to the stored length: {d['decode_delta']}"
