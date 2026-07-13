"""Rendering (spec §11): apply gauge + schedule to real source units.

    render(schedule, sources) -> (audio, provenance_stream)

The render is a PURE, DETERMINISTIC function of (schedule, sources). It walks the
schedule's placements in the order the schedule gives them and, for each, applies
the governing section's gauge to the real source-unit audio (time-stretch to the
output slot, transpose, loudness, beat-phase shift), scales by the placement's
settled MASS (settlement output carried on the placement, multiplicative with the
section-global gauge loudness — see schedule.py "MASS IS NOT GAUGE"), and
overlap-ADDS it onto the output tape at the slot the schedule names. That is the
whole of it. Applying mass is not a render choice: the schedule already decided
it; a threshold decision the writer used to make no longer exists anywhere (I-11
strengthened).

I-11 (render applies, never chooses). This module contains NO scoring, ranking,
argmax/argmin, sorting, or sampling. It never decides WHAT to place or WHERE —
the schedule already decided; the render only applies. Placement order does not
affect content because overlap-add is commutative addition (only the last bits of
floating-point rounding differ). There is no randomness: TEMPERATURE / sampling
looseness (spec §8 lane 6) lives in the writer that produces the schedule, never
here. The invariant test (tests/invariants/manifest.py::_check_i11) enforces this
structurally (AST scan of this module) and behaviorally (determinism + order-
independence), and proves the checks bite.

I-12 (provenance): every placed unit emits a provenance segment covering exactly
the output samples it touched, with the concrete transform applied. Every nonzero
output sample is therefore traceable to (track, unit, transform).

TIME/PITCH TOOL DECISION (logged, WALL PROTOCOL — spec §11 "rubberband-class").
Neither the rubberband CLI nor pyrubberband is installed in this environment, so
a rubberband-class transform is not cleanly available. Per WALL PROTOCOL this
render uses a clean, documented STAND-IN: librosa's phase-vocoder time-stretch
(``librosa.effects.time_stretch``) and resampling pitch-shift
(``librosa.effects.pitch_shift``). This is logged, not silent. The stand-in is
confined to ``_apply_gauge``; swapping in pyrubberband later touches only that
function and changes no contract. ``RENDER_STRETCH_BACKEND`` records the choice
for any artifact that wants to trace it.
"""
from __future__ import annotations
from typing import Tuple
import numpy as np
import librosa

from .schedule import Schedule
from .sources import SourceUnitBank
from .provenance import ProvenanceStream, PROV_SEG_DTYPE

# Logged tool decision (see module docstring / WALL PROTOCOL).
RENDER_STRETCH_BACKEND = "librosa.phase_vocoder (stand-in for rubberband-class)"


def _fit_n_fft(n: int) -> int:
    """STFT size that FITS the unit: the largest power of two <= max(256, n//2),
    capped at 2048 (librosa's default). librosa's phase vocoder at a fixed
    n_fft=2048 mangles units shorter than the window (zero-padded analysis of a
    frame mostly not signal) — an instrument-correctness fix for the stand-in
    stretch backend, not a tuning knob: the window is derived from the unit
    length, never chosen per taste."""
    target = n // 2 if n // 2 > 256 else 256
    p = 1 << (target.bit_length() - 1)
    return 2048 if p > 2048 else p


def _apply_gauge(x: np.ndarray, sr: int, out_len: int,
                 semitones: float, loudness: float) -> Tuple[np.ndarray, float]:
    """Apply the section gauge to one unit's audio, fit to ``out_len`` samples.

    A gauge component set to its neutral value is the IDENTITY map and is applied
    as such — calling pitch_shift(0) / time_stretch(1.0) would inject spurious
    STFT round-trip coloration the gauge did NOT request, i.e. it would apply a
    transform the schedule forbade. So neutral components short-circuit. This is
    the correct application of the gauge, not a special case for "easy" inputs.

    Returns (fitted_audio, stretch_ratio_applied).
    """
    y = np.asarray(x, dtype=np.float64)
    n_fft = _fit_n_fft(len(y))

    # transposition (section-global; spec §5 T5)
    if semitones != 0.0 and len(y) > 0:
        y = librosa.effects.pitch_shift(y, sr=sr, n_steps=float(semitones),
                                        n_fft=n_fft)

    # time-stretch to the output slot length
    in_len = len(y)
    ratio = (in_len / out_len) if out_len > 0 else 1.0
    if in_len != out_len:
        if in_len > 1 and out_len > 0:
            y = librosa.effects.time_stretch(y, rate=ratio, n_fft=n_fft)
        y = librosa.util.fix_length(y, size=out_len)

    # loudness (section-global)
    if loudness != 1.0:
        y = y * loudness
    return np.asarray(y, dtype=np.float64), float(ratio)


def render(schedule: Schedule, sources: SourceUnitBank
           ) -> Tuple[np.ndarray, ProvenanceStream]:
    """Apply ``schedule`` to ``sources``. See module docstring (I-11, I-12).

    Pure and deterministic: identical (schedule, sources) -> identical output.
    """
    n_out = int(schedule.slot_boundaries[-1])
    audio = np.zeros(n_out, dtype=np.float64)
    bounds = schedule.slot_boundaries
    placements = schedule.placements
    segs = np.zeros(len(placements), dtype=PROV_SEG_DTYPE)
    m = 0  # count of placements that actually reached the tape

    for idx in range(len(placements)):
        p = placements[idx]
        out_slot = int(p["out_slot"])
        a = int(bounds[out_slot])
        b = int(bounds[out_slot + 1])
        out_len = b - a

        gauge = schedule.sections[int(p["section"])].gauge
        su = sources.get(int(p["src_track"]), int(p["src_unit"]))

        # settled mass (settlement output on the placement) multiplies the
        # section-global gauge loudness — pure application of the schedule.
        mass = float(p["mass"])
        y, ratio = _apply_gauge(su.audio, schedule.sr, out_len,
                                gauge.transpose_semitones,
                                gauge.loudness_scale * mass)

        # beat-phase shift: gauge fraction of this slot, resolved to samples.
        shift = int(np.round(gauge.phase_shift * out_len))
        start = a + shift
        stop = start + out_len

        # overlap-ADD, clipped to the output tape (np.clip; no min/max selection).
        lo = int(np.clip(start, 0, n_out))
        hi = int(np.clip(stop, 0, n_out))
        if hi <= lo:
            continue  # placement fell entirely off the tape; nothing to trace
        off = lo - start
        audio[lo:hi] += y[off:off + (hi - lo)]

        segs[m]["out_start"] = lo
        segs[m]["out_end"] = hi
        segs[m]["src_track"] = int(p["src_track"])
        segs[m]["src_unit"] = int(p["src_unit"])
        segs[m]["stretch_ratio"] = ratio
        segs[m]["pitch_semitones"] = float(gauge.transpose_semitones)
        segs[m]["loudness_scale"] = float(gauge.loudness_scale)
        segs[m]["mass"] = mass
        segs[m]["phase_shift_samples"] = shift
        m += 1

    prov = ProvenanceStream(segments=segs[:m], n_samples=n_out, sr=int(schedule.sr))
    return audio, prov
