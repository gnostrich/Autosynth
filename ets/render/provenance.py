"""Provenance stream for rendered output (spec §11 last sentence; invariant I-12).

"Every output sample carries provenance (track, unit, transform applied)."

Representation: a list of PROVENANCE SEGMENTS, each recording that one source
unit contributed to output samples [out_start, out_end) under a stated transform.
This is "aligned to output samples" by *sample index*, not by one-row-per-sample:
the output is an overlap-ADD of transformed units, so a single output sample is a
SUM of contributions from a SET of units — a per-sample scalar label would be a
lie. The segment set records exactly that many-to-one structure and stays O(#
placements), not O(# samples).

Completeness (I-12) is executable: every output sample that carries any signal
must be covered by at least one segment, and every segment's transform is fully
recorded. ``assert_complete`` bites — a dropped segment leaves a nonzero sample
untraceable and raises.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

# One contribution: source unit -> output span, with the transform the render
# applied to it (the gauge, resolved to concrete numbers). This is the whole of
# "(track, unit, transform applied)" the spec requires per sample.
PROV_SEG_DTYPE = np.dtype([
    ("out_start", np.int64),          # output sample span [out_start, out_end)
    ("out_end", np.int64),
    ("src_track", np.int64),
    ("src_unit", np.int64),
    ("stretch_ratio", np.float64),    # in_len / out_len applied (1.0 == no stretch)
    ("pitch_semitones", np.float64),  # transposition applied
    ("loudness_scale", np.float64),   # section-global gauge loudness applied
    ("mass", np.float64),             # placement's settled mass applied (amplitude;
                                      # settlement output, not gauge — schedule.py)
    ("phase_shift_samples", np.int64),# beat-phase shift resolved to samples
])


@dataclass
class ProvenanceStream:
    """The provenance of a rendered buffer: segments + output length + sr."""
    segments: np.ndarray   # PROV_SEG_DTYPE
    n_samples: int
    sr: int

    def __post_init__(self):
        self.segments = np.ascontiguousarray(self.segments, dtype=PROV_SEG_DTYPE)
        self.n_samples = int(self.n_samples)

    def coverage(self) -> np.ndarray:
        """Boolean (n_samples,): True where >= 1 unit contributed."""
        cov = np.zeros(self.n_samples, dtype=bool)
        s = self.segments
        for a, b in zip(s["out_start"], s["out_end"]):
            cov[int(a):int(b)] = True
        return cov

    def assert_complete(self, audio: np.ndarray, eps: float = 1e-8) -> None:
        """I-12: every nonzero output sample is traceable to a (track, unit,
        transform) segment, and every segment is well-formed and fully labeled.
        Raises AssertionError on any gap."""
        n = self.n_samples
        assert len(audio) == n, "provenance n_samples != rendered length"
        s = self.segments
        assert np.all(s["out_start"] >= 0), "segment starts before output"
        assert np.all(s["out_end"] <= n), "segment ends past output"
        assert np.all(s["out_start"] < s["out_end"]), "empty/negative segment span"
        assert np.all(np.isfinite(s["stretch_ratio"])), "non-finite stretch in provenance"
        assert np.all(np.isfinite(s["pitch_semitones"])), "non-finite pitch in provenance"
        assert np.all(s["loudness_scale"] >= 0), "negative loudness in provenance"
        assert np.all(np.isfinite(s["mass"]) & (s["mass"] >= 0)), \
            "non-finite/negative settled mass in provenance"

        cov = self.coverage()
        active = np.abs(audio) > eps
        missing = int(np.sum(active & ~cov))
        assert missing == 0, (
            f"{missing} nonzero output samples carry no provenance (I-12 violated)")
