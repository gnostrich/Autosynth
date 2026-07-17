"""Thin local ETS cloud client.

`ets-cloud train <corpus>`: ingest locally -> prototypes -> whitelist-encode ONLY
stage-3 -> POST to the service -> receive world + receipt -> VERIFY the receipt
locally -> write the world file locally. Playback stays in the existing local app.
"""
from .cli import main, train, load_prototypes, post_job

__all__ = ["main", "train", "load_prototypes", "post_job"]
