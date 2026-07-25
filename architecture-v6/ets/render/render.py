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
from collections import OrderedDict
from typing import Optional, Tuple
from weakref import WeakKeyDictionary
import os
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


# ---- the fitted-unit memo (implementation only; NO semantic content) -------
#
# `_apply_gauge(x, sr, out_len, semitones, loudness)` splits exactly in two: a
# PURE function of (the unit's audio, sr, out_len, semitones) — pitch shift,
# time-stretch, fix_length — followed by ONE scalar multiply by `loudness`
# (`if loudness != 1.0`). The loudness factor (gauge loudness x the placement's
# settled mass) is the only input that varies per placement; the expensive half
# does not depend on it. Every placement of the same unit at the same slot length
# therefore recomputes an IDENTICAL phase-vocoder stretch. Measured on a
# 6192-unit multi-tempo world: 9600 placements over 150 bars carry only 2657
# distinct (unit, out_len) inputs (steady-state repeat rate 92%), while one
# `librosa.time_stretch` per placement (~4 ms x 64/bar) is 92% of the bar.
#
# So this memoizes that pure half, per BANK. The MISS path is the original
# `_apply_gauge` call VERBATIM (with loudness=1.0, which its own `!= 1.0` guard
# turns into the identity), and the multiply is then applied by the same
# expression as before — so a hit returns exactly the array a miss would have
# built and the audio is byte-identical with the memo on or off (gated: G2).
# It is not a second render path and it takes no decision (I-11): nothing is
# scored, ranked or selected; a key either was computed before or was not.
#
# `ETS_STRETCH_CACHE=0|false|off` bypasses the memo entirely (the verbatim
# pre-memo call), selected per render call. `ETS_STRETCH_CACHE_MB` (default 128)
# bounds the memory: least-recently-used entries are dropped when the budget is
# exceeded, and a dropped entry is simply recomputed — the bound is a MEMORY
# bound, never a semantic one. The memo is held per SourceUnitBank in a weak
# map, so it lives and dies with the world's material (no cross-world key
# collision: (track, unit) ids are per world) and adds no global state.
_CACHE_OFF = ("0", "false", "off", "no")
_DEFAULT_CACHE_MB = 128.0


def stretch_cache_enabled() -> bool:
    """True iff the fitted-unit memo is selected (default). Read at call time."""
    return os.environ.get("ETS_STRETCH_CACHE", "1").strip().lower() not in _CACHE_OFF


def stretch_cache_budget_bytes() -> int:
    """The memo's memory budget per bank (ETS_STRETCH_CACHE_MB, default 128)."""
    return int(float(os.environ.get("ETS_STRETCH_CACHE_MB",
                                    _DEFAULT_CACHE_MB)) * 1e6)


class _FittedMemo:
    """Least-recently-used memo of `_apply_gauge(..., loudness=1.0)` results.

    Keyed by the COMPLETE input tuple of that call: (track, unit) identifies the
    unit's audio inside this bank (the bank is built once and immutable), plus
    sr, out_len and the section's transposition. Values are (fitted audio, the
    stretch ratio the provenance records). Eviction is by insertion/use order
    only — no ranking, no scoring (I-11)."""

    def __init__(self, budget_bytes: int):
        self._d: "OrderedDict[tuple, Tuple[np.ndarray, float]]" = OrderedDict()
        self._bytes = 0
        self.budget = int(budget_bytes)
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, key) -> Optional[Tuple[np.ndarray, float]]:
        got = self._d.get(key)
        if got is None:
            self.misses += 1
            return None
        self.hits += 1
        self._d.move_to_end(key)
        return got

    def put(self, key, value: Tuple[np.ndarray, float]) -> None:
        self._d[key] = value
        self._bytes += int(value[0].nbytes)
        while self._bytes > self.budget and len(self._d) > 1:
            _k, v = self._d.popitem(last=False)
            self._bytes -= int(v[0].nbytes)
            self.evictions += 1

    def stats(self) -> dict:
        n = self.hits + self.misses
        return {"entries": len(self._d), "bytes": self._bytes,
                "budget_bytes": self.budget, "hits": self.hits,
                "misses": self.misses, "evictions": self.evictions,
                "hit_rate": (self.hits / n) if n else 0.0}


_MEMOS: "WeakKeyDictionary[SourceUnitBank, _FittedMemo]" = WeakKeyDictionary()


def _memo_for(sources: SourceUnitBank) -> _FittedMemo:
    memo = _MEMOS.get(sources)
    if memo is None:
        memo = _FittedMemo(stretch_cache_budget_bytes())
        _MEMOS[sources] = memo
    return memo


def stretch_memo_stats(sources: SourceUnitBank) -> Optional[dict]:
    """Read-only instrument: this bank's memo counters (None if never used).

    An INSTRUMENT, never an input to anything the engine decides (I-14): no
    code path reads these numbers back into the render, the writer or F."""
    memo = _MEMOS.get(sources)
    return None if memo is None else memo.stats()


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
    memo = _memo_for(sources) if stretch_cache_enabled() else None

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
        if memo is None:
            y, ratio = _apply_gauge(su.audio, schedule.sr, out_len,
                                    gauge.transpose_semitones,
                                    gauge.loudness_scale * mass)
        else:
            # the SAME call, with its loudness-independent half memoized: the
            # miss path IS the line above with loudness=1.0 (its `!= 1.0` guard
            # makes that the identity), and the multiply below is the same
            # expression `_apply_gauge` would have applied.
            key = (int(p["src_track"]), int(p["src_unit"]), int(schedule.sr),
                   out_len, float(gauge.transpose_semitones))
            got = memo.get(key)
            if got is None:
                got = _apply_gauge(su.audio, schedule.sr, out_len,
                                   gauge.transpose_semitones, 1.0)
                memo.put(key, got)
            fitted, ratio = got
            loudness = gauge.loudness_scale * mass
            y = (fitted * loudness) if loudness != 1.0 else fitted

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
