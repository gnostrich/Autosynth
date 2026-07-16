"""ETS — Equilibrium Tape Synth. Engine package.

Single authority: ets-spec-v0.md at the repo root. This package implements the
engine (spec §12): ingestion, gauge/anchor geometry, the one functional F, the
streaming writer, meters, planner, and render. The PySide6 panel (spec §8) is a
separate process communicating over OSC.
"""
__version__ = "0.0.0"
