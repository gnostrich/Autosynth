"""ETS local companion (MVP-2) — the sealed on-device box.

Phase 1 (this module): a localhost HTTP server that (a) serves the browser
instrument UI and (b) performs the GUARDED training round-trip to the cloud
anchor-fit endpoint. It is the sole holder of the user's raw audio; the ONLY exit
to the cloud is the stage-3 whitelist encoder in ``cloud.client`` — raw audio and
stage-2 recipes never leave the machine. It imports no renderer on the cloud path
(no cloud decoder). Region-tilt is the only engine-control gesture (added phase 2).

Run:  python -m cloud.companion --cloud-url https://<railway-service>/  [--port 8770]
"""
from cloud.companion.app import Companion, serve, main  # noqa: F401
