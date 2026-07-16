"""Stateless ETS cloud TRAINING service (request-in / world-out).

``app.handle_train`` is the whole service logic: decode a stage-3 JOB, run the
EXISTING anchor-fit ``ets.functional.anchors.build_world`` UNCHANGED, and return
the world + a device-verifiable receipt. ``app.serve`` wraps it in a stdlib HTTP
server so it runs with no third-party dependency; ``python -m cloud.service``
starts it locally as the cloud stand-in.

There is NO decoder/renderer here and NOTHING emits audio (MVP-D): the only root
ETS modules this pulls in are ``ets.functional`` + ``ets.geometry`` (the anchor
geometry), never ``ets.writer`` / ``ets.render`` / the panel / audio I/O.
"""
from .app import handle_train, serve, run_job_inprocess

__all__ = ["handle_train", "serve", "run_job_inprocess"]
