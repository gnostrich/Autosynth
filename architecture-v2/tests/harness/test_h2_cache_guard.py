"""H-2 replay-path divergence guard (auditor finding, A1 re-derivation item 2).

DECLARED DIVERGENCE: the frozen snapshot's replay script
(legacy/v0-validated/scripts/generate_batch.py) reads the LIVE cache at
/home/user/Geodesic-Mixing/cache/ingest — those lines are frozen bytes and
cannot be edited under H-1 law. Today live == frozen (verified at snapshot
time). This guard makes that equality a standing CI assertion: if the live
cache is ever re-ingested or altered, this test FAILS LOUDLY, so "replay from
the snapshot" can never silently consume different inputs while H-1 stays
green. On failure the correct remediations are (a) restore the live cache from
the frozen copy, or (b) an explicit, registered decision to re-point replay —
never editing legacy/.
"""
from __future__ import annotations
import hashlib
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIVE = os.path.join(ROOT, "cache", "ingest")
FROZEN = os.path.join(ROOT, "legacy", "v0-validated", "cache-ingest-frozen")


def _hashes(d):
    out = {}
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".npz"):
            with open(os.path.join(d, fn), "rb") as fh:
                out[fn] = hashlib.sha256(fh.read()).hexdigest()
    return out


def test_live_cache_matches_frozen_snapshot():
    if not os.path.isdir(LIVE):
        # A cacheless checkout (fresh clone without data) cannot replay at all,
        # so the divergence this guards cannot occur there. The frozen copy is
        # the recovery source, and its integrity is H-1's job, not this guard's.
        import pytest
        pytest.skip("no live cache in this checkout; replay impossible here")
    frozen = _hashes(FROZEN)
    live = _hashes(LIVE)
    assert frozen, "frozen cache copy is empty — H-1/A1 broken"
    assert live == frozen, (
        "LIVE cache/ingest has DIVERGED from the frozen validated inputs. "
        "The legacy replay path reads the live cache (frozen script, "
        "undeclarable-in-place). Restore live from "
        "legacy/v0-validated/cache-ingest-frozen/ or register an explicit "
        "re-point decision. Do NOT edit legacy/.")
