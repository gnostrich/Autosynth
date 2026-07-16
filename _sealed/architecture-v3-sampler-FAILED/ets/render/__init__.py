"""Rendering (spec §11): beat-synchronous stretch/shift + overlap-add of real
source units. Applies gauge/schedule, makes no choices (I-11); provenance per
sample (I-12).

Public surface:
  Schedule, Section, Gauge, IDENTITY, PLACEMENT_DTYPE  — the render input contract
  SourceUnit, SourceUnitBank, load_source_units         — the source material
  render                                                — the render itself
  ProvenanceStream, PROV_SEG_DTYPE                       — output provenance (I-12)
  RENDER_STRETCH_BACKEND                                 — logged time/pitch tool
"""
from .schedule import (Schedule, Section, Gauge, IDENTITY, PLACEMENT_DTYPE)
from .sources import (SourceUnit, SourceUnitBank, load_source_units)
from .provenance import (ProvenanceStream, PROV_SEG_DTYPE)
from .render import (render, RENDER_STRETCH_BACKEND)

__all__ = [
    "Schedule", "Section", "Gauge", "IDENTITY", "PLACEMENT_DTYPE",
    "SourceUnit", "SourceUnitBank", "load_source_units",
    "ProvenanceStream", "PROV_SEG_DTYPE",
    "render", "RENDER_STRETCH_BACKEND",
]
