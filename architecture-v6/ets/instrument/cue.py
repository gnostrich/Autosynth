"""Cue / PFL (F3.5) — a private second output that monitors the settled-but-
unplayed L-bar frontier, and (optionally) auditions a pad's contribution.

MONITOR-ONLY, structurally: `CueMonitor` takes the ALREADY-PRODUCED output audio
and its provenance and returns a SEPARATE cue buffer. It holds no handle to the
writer, the emitter, or the main output — so nothing it does can change a settled
sample or a main-out byte (F3-E). Cue/audition/solo/mute reach settlement, F, and
provenance-generation through NO path.

Frontier monitor: the cue plays the region AHEAD of the playhead that is already
settled (committed) but not yet heard — [playhead, committed_frontier).

Pad audition — HONEST SUBSET + DISCLOSED WALL. Auditioning a pad's TRUE isolated
contribution would require re-rendering just that track's placements, i.e. a call
into the render path (the trained object) — out of scope (PREREG "if that can't
be done cleanly, ship cue as frontier-monitor only and report"). So audition here
is a MONITOR-SIDE emphasis on the summed frontier audio, derived from provenance
coverage: samples covered by an auditioned track keep full gain, the rest are
attenuated to `duck`. This is a preview filter on already-produced audio, NOT a
per-source isolation, and it is labelled as such — it never re-renders and never
touches main. When no pad is auditioned, cue is a plain frontier monitor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

import numpy as np

from ets.instrument.model import _as_prov_array


@dataclass
class CueMonitor:
    """A read-only cue bus. `render_cue` derives the cue buffer from produced
    audio + provenance; it never writes into the audio it was given."""
    active: bool = False
    duck: float = 0.0                       # gain for non-auditioned samples
    auditioned: Set[int] = field(default_factory=set)   # source-track ids

    def set_active(self, on: bool) -> None:
        self.active = bool(on)

    def audition(self, track_id: int) -> None:
        self.auditioned.add(int(track_id))

    def unaudition(self, track_id: int) -> None:
        self.auditioned.discard(int(track_id))

    def clear_audition(self) -> None:
        self.auditioned.clear()

    def render_cue(self, audio, segments, playhead: int,
                   committed_frontier: int) -> np.ndarray:
        """Cue buffer for [playhead, committed_frontier): the settled-but-unplayed
        frontier. `audio` is the produced output; it is READ, never mutated.
        Auditioned tracks (if any) keep full gain via a provenance coverage mask;
        everything else is ducked. Returns a fresh array (a private copy)."""
        a = np.asarray(audio)
        lo = int(max(0, min(len(a), playhead)))
        hi = int(max(lo, min(len(a), committed_frontier)))
        if not self.active or hi <= lo:
            return np.zeros(0, dtype=a.dtype)
        cue = a[lo:hi].copy()               # copy: main-out is never touched
        if self.auditioned:
            seg = _as_prov_array(segments)
            keep = np.zeros(hi - lo, dtype=bool)
            for r in seg:
                if int(r["src_track"]) in self.auditioned:
                    s0 = max(lo, int(r["out_start"])) - lo
                    s1 = min(hi, int(r["out_end"])) - lo
                    if s1 > s0:
                        keep[s0:s1] = True
            gain = np.where(keep, 1.0, self.duck).astype(cue.dtype)
            cue = cue * gain
        return cue
