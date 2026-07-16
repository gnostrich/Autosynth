"""Connector package (ets-connector-v0.md): the panel-to-writer stack.

Currently holds the Layer-0 tilt OBSERVABLES phi_i (``phi.py``) — the normative
arrangement statistics the h-transform tilt acts on. The tilt map itself
(lambda_i = u_i / sigma_phi_i applied inside the settlement) is a separate
build; the sigma_phi_i normalizers are the registered calibration instrument in
``ets.calibration``.
"""
from .phi import PHI_NAMES, LANE_PHI, RoleMaps, role_maps_from_world, phi_bars

__all__ = ["PHI_NAMES", "LANE_PHI", "RoleMaps", "role_maps_from_world", "phi_bars"]
