"""The Basin — offline instrument-builder + orbit-renderer over a playlist.

An instrument is built from a corpus (folder of audio, one micro-genre) in
three modules:

* M1 (:mod:`basin.features`, :mod:`basin.atlas`, :mod:`basin.operator`)
  builds the index — windows, charts, transfer operator, spectrum, basins.
* M2 (:mod:`basin.orbit`, :mod:`basin.render`) walks the index (PULL +
  knob bias) and realizes audio by concatenative grain read.
* M3 (:mod:`basin.kernel`) fits the memory kernel and adds it to the orbit;
  the K-on/K-off ablation is the falsifiability gate.

No neural networks anywhere. Theory reference: ``the_basin.md``.
"""

from __future__ import annotations

__all__ = [
    "features",
    "atlas",
    "operator",
    "orbit",
    "render",
    "kernel",
]
