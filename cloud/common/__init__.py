"""Shared wire protocol for the ETS cloud training seam.

The single source of truth for WHAT may cross device->cloud (the stage-3
whitelist), the encoder/decoder, and the device-verifiable receipt check. The
service and the client both import from here, so there is exactly one definition of
the seam — no second channel, no parallel path.
"""
from .protocol import (
    STAGE3_PROTO_FIELDS,
    STAGE3_PARAM_FIELDS,
    WHITELIST_TAG,
    PARAM_DEFAULTS,
    Stage3Proto,
    WhitelistViolation,
    ReceiptError,
    Result,
    encode_job,
    decode_job,
    encode_result,
    decode_result,
    verify_receipt,
    assert_wire_whitelisted,
    reconstruct_fstate,
)

__all__ = [
    "STAGE3_PROTO_FIELDS",
    "STAGE3_PARAM_FIELDS",
    "WHITELIST_TAG",
    "PARAM_DEFAULTS",
    "Stage3Proto",
    "WhitelistViolation",
    "ReceiptError",
    "Result",
    "encode_job",
    "decode_job",
    "encode_result",
    "decode_result",
    "verify_receipt",
    "assert_wire_whitelisted",
    "reconstruct_fstate",
]
