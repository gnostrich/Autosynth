"""Transport (F3.4) — play / stop / pause / seek over ALREADY-PRODUCED output.

Transport moves the PLAYHEAD (WHEN you listen), never WHAT the writer settles.
It holds a position into a produced buffer (offline render, or the streamed
frontier once produced) and advances it while playing; pausing freezes the
position; seeking jumps it. It calls NOTHING on the writer/engine/render — there
is deliberately no method here that could re-settle a bar. That is the whole of
F3-D (transport neutrality): the writer's output is fixed before the transport
ever touches it, so pause/seek cannot change a settled sample.

Offline render-to-file is retained by the engine (ets.engine.render_offline);
this transport is the live/preview playhead over that same deterministic output.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Transport:
    """A pure playhead. `n_samples`/`sr` describe the produced buffer; `position`
    is the current output sample. No trained-object handle exists here."""
    n_samples: int = 0
    sr: int = 1
    position: int = 0
    playing: bool = False

    def load(self, n_samples: int, sr: int) -> None:
        self.n_samples = int(n_samples)
        self.sr = int(sr)
        self.position = 0
        self.playing = False

    # --- transport controls (playhead only) ---------------------------------
    def play(self) -> None:
        self.playing = True

    def pause(self) -> None:
        self.playing = False

    def stop(self) -> None:
        self.playing = False
        self.position = 0

    def seek(self, sample: int) -> None:
        self.position = int(max(0, min(self.n_samples, sample)))

    def seek_seconds(self, seconds: float) -> None:
        self.seek(int(round(seconds * self.sr)))

    def tick(self, dt: float) -> int:
        """Advance the playhead by `dt` seconds if playing; return the new
        position. Clamps at the end (stops); never wraps into the writer."""
        if self.playing:
            self.position += int(round(dt * self.sr))
            if self.position >= self.n_samples:
                self.position = self.n_samples
                self.playing = False
        return self.position

    @property
    def seconds(self) -> float:
        return self.position / self.sr if self.sr else 0.0
