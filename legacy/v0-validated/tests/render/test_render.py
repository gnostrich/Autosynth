"""Render smoke/identity tests (spec §11, §13 G0-analogue) + provenance (I-12).

The corpus/cache are gitignored and live only in the MAIN checkout, so these
tests read them by ABSOLUTE path. When they are absent (e.g. a CI box without the
data) the data-backed tests skip; the pure-logic tests still run.

  test_identity_reconstruction  — the DEGENERATE schedule (a track's own units at
      their own slots, identity gauge) reproduces the source track within a stated
      tolerance. This is the render analogue of the G0 reconstruction identity.
  test_identity_provenance_complete — I-12 on that render, plus proof the check
      bites (a dropped segment is caught).
  test_nontrivial_transform     — a compressed output grid forces real time-stretch
      (the rubberband-class stand-in); output length + provenance stay correct.
  test_determinism              — same (schedule, sources) -> identical output.
"""
from __future__ import annotations
import glob
import os
import numpy as np
import pytest

from ets.render import (render, load_source_units, Schedule, Section, Gauge,
                        PLACEMENT_DTYPE, RENDER_STRETCH_BACKEND)

MAIN = "/home/user/Geodesic-Mixing"
CACHE = os.path.join(MAIN, "cache/ingest")
CORPUS = os.path.join(MAIN, "corpus")

# stated identity tolerance (relative L2 over the grid-covered span). The
# degenerate render goes through the identity gauge path (no phase vocoder), so
# it inherits the filterbank partition-of-unity precision — same class as the G0
# reconstruction identity (RECON_TOL_RELL2 = 1e-3). We hold the render to the
# same bar.
IDENTITY_TOL_RELL2 = 1e-3


def _corpus_paths():
    return sorted(glob.glob(os.path.join(CORPUS, "*.mp3")))


def _have_data(track_id: int) -> bool:
    return (os.path.exists(os.path.join(CACHE, f"track_{track_id:02d}.npz"))
            and len(_corpus_paths()) > track_id)


def _load(track_id: int):
    from ets.ingestion.pipeline import load
    import librosa
    track = load(os.path.join(CACHE, f"track_{track_id:02d}.npz"))
    path = _corpus_paths()[track_id]
    y, _ = librosa.load(path, sr=track.sr, mono=True)
    return track, y, path


@pytest.mark.skipif(not _have_data(0), reason="corpus/cache not present in this checkout")
def test_identity_reconstruction():
    """Degenerate schedule reproduces the source track (render G0-analogue)."""
    track, y, path = _load(0)
    # pairing sanity: the cached track's length must match the paired audio.
    assert abs(track.n_samples - len(y)) <= track.sr // 10, (
        f"track/corpus pairing mismatch: cache n_samples={track.n_samples} vs "
        f"audio len={len(y)} for {os.path.basename(path)}")

    sources = load_source_units(track, y)
    sched = Schedule.degenerate(track)

    # identity gauge everywhere (no transpose, no phase shift, unit loudness).
    for sec in sched.sections:
        assert sec.gauge == Gauge(), "degenerate schedule must be identity gauge"

    audio, prov = render(sched, sources)

    gs = int(track.beat_grid.tatum_boundaries[0])
    ge = int(track.beat_grid.tatum_boundaries[-1])
    ref = y[gs:ge]
    rec = audio[gs:ge]
    denom = float(np.sqrt(np.mean(ref ** 2))) + 1e-12
    rel = float(np.sqrt(np.mean((rec - ref) ** 2)) / denom)
    print(f"\n[identity render] backend={RENDER_STRETCH_BACKEND}")
    print(f"[identity render] rel_L2={rel:.3e} ({20*np.log10(rel+1e-300):.1f} dB), "
          f"tol={IDENTITY_TOL_RELL2:.1e}, n_units={len(sched.placements)}, "
          f"covered=[{gs},{ge}] of {len(y)}")
    assert rel <= IDENTITY_TOL_RELL2, f"identity render off by rel_L2={rel:.3e}"


@pytest.mark.skipif(not _have_data(0), reason="corpus/cache not present in this checkout")
def test_identity_provenance_complete():
    """I-12: every nonzero rendered sample is traceable; and the check bites."""
    track, y, _ = _load(0)
    sources = load_source_units(track, y)
    audio, prov = render(Schedule.degenerate(track), sources)

    # well-formed render passes
    prov.assert_complete(audio)

    # every segment resolves to a real source unit (track, unit) it references
    for seg in prov.segments[:200]:
        assert (int(seg["src_track"]), int(seg["src_unit"])) in sources

    # the check BITES. The identity schedule lays all 8 bands of a slot on the
    # SAME span, so dropping one segment still leaves 7 siblings covering it.
    # To open a true gap, remove EVERY segment overlapping one nonzero output
    # sample x (i.e. hole out that whole slot) -> x becomes untraceable.
    from ets.render.provenance import ProvenanceStream
    nz = np.where(np.abs(audio) > 1e-6)[0]
    assert len(nz), "rendered identity is silent?"
    x = int(nz[len(nz) // 2])
    keep = ~((prov.segments["out_start"] <= x) & (prov.segments["out_end"] > x))
    assert keep.sum() < len(prov.segments), "expected some segment to cover x"
    holed = ProvenanceStream(segments=prov.segments[keep],
                             n_samples=prov.n_samples, sr=prov.sr)
    with pytest.raises(AssertionError):
        holed.assert_complete(audio)


@pytest.mark.skipif(not _have_data(0), reason="corpus/cache not present in this checkout")
def test_nontrivial_transform():
    """A compressed output grid forces real time-stretch (rubberband-class
    stand-in). Exercised on a subset of slots to keep the smoke test quick."""
    track, y, _ = _load(0)
    sources = load_source_units(track, y)

    bounds_full = np.asarray(track.beat_grid.tatum_boundaries, np.int64)
    n_use = min(40, len(bounds_full) - 1)
    src_bounds = bounds_full[:n_use + 1]
    # output grid: same slots at HALF duration (2x tempo) -> stretch ratio ~2.
    lengths = np.diff(src_bounds)
    out_lengths = np.maximum(lengths // 2, 1)
    out_bounds = np.concatenate([[0], np.cumsum(out_lengths)]).astype(np.int64)

    u = track.units
    keep = u["slot"] < n_use
    p = np.zeros(int(keep.sum()), dtype=PLACEMENT_DTYPE)
    p["out_slot"] = u["slot"][keep]
    p["src_track"] = track.track_id
    p["src_unit"] = u["unit_id"][keep]
    p["section"] = 0
    sections = (Section(0, 0, n_use, Gauge(transpose_semitones=0.0)),)
    sched = Schedule(sr=track.sr, slot_boundaries=out_bounds,
                     placements=p, sections=sections)

    audio, prov = render(sched, sources)
    assert len(audio) == int(out_bounds[-1]), "output length != output grid extent"
    prov.assert_complete(audio)
    # the schedule asked for a stretch -> provenance must record ratio != 1.
    ratios = prov.segments["stretch_ratio"]
    assert np.median(ratios) > 1.5, f"expected ~2x stretch recorded, got median {np.median(ratios):.2f}"
    print(f"\n[nontrivial] slots={n_use}, median stretch_ratio={np.median(ratios):.2f}, "
          f"out_len={len(audio)}")


@pytest.mark.skipif(not _have_data(0), reason="corpus/cache not present in this checkout")
def test_determinism():
    """Same (schedule, sources) -> identical output (I-11 behavioral, on real audio)."""
    track, y, _ = _load(0)
    sources = load_source_units(track, y)
    sched = Schedule.degenerate(track)
    a1, p1 = render(sched, sources)
    a2, p2 = render(sched, sources)
    assert np.array_equal(a1, a2)
    assert np.array_equal(p1.segments, p2.segments)
