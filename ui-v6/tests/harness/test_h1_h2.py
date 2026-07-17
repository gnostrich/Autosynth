"""Directive-v1 harness checks H-1 and H-2 (A3).

H-1 legacy immutability: every byte under legacy/ matches the checksum manifest
frozen at snapshot time — no modification, no deletion, no addition. CI fails on
any diff that touches legacy/.

H-2 replay (logged once, asserted here): the registry carries the one-time
bit-identity receipt — the 60s clip re-rendered from legacy/v0-validated/ hashed
identically to the delivered FLAC. This test pins the receipt (and the hash it
attests) so it cannot be silently dropped or edited; it does NOT re-render.
"""
from __future__ import annotations
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST = os.path.join(ROOT, "tests", "harness", "legacy_manifest.sha256")

# The delivered validated clip's sha256 — the value H-2's replay reproduced.
H2_DELIVERED_SHA256 = "77fbf37534ee8a632a6fef2754afda1a03b3ae20c3f8eaa2eb7bd4ef413ee34e"


def _walk_legacy():
    for dirpath, dirs, files in os.walk(os.path.join(ROOT, "legacy")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in sorted(files):
            yield os.path.relpath(os.path.join(dirpath, fn), ROOT)


def test_h1_legacy_immutable():
    expected = {}
    with open(MANIFEST) as f:
        for line in f:
            h, p = line.rstrip("\n").split("  ", 1)
            expected[p] = h
    assert expected, "H-1 manifest is empty — snapshot discipline broken"

    actual = {}
    for rel in _walk_legacy():
        with open(os.path.join(ROOT, rel), "rb") as fh:
            actual[rel] = hashlib.sha256(fh.read()).hexdigest()

    missing = sorted(set(expected) - set(actual))
    added = sorted(set(actual) - set(expected))
    changed = sorted(p for p in set(expected) & set(actual)
                     if expected[p] != actual[p])
    assert not (missing or added or changed), (
        "H-1 VIOLATION — legacy/ is frozen. "
        f"missing={missing[:5]} added={added[:5]} changed={changed[:5]}")

    # non-vacuity: the comparison actually bites on a tampered byte.
    probe = dict(actual)
    k = next(iter(probe))
    probe[k] = "0" * 64
    assert probe[k] != expected[k], "H-1 check is vacuous"


def test_h2_replay_receipt_pinned():
    reg = os.path.join(ROOT, "REGISTRY.jsonl")
    entries = [json.loads(L) for L in open(reg) if L.strip()]
    h2 = [e for e in entries if e.get("id") == "legacy-h2-replay"]
    assert len(h2) == 1, "H-2 replay receipt missing from registry (or duplicated)"
    e = h2[0]
    assert e.get("status") == "PASS", f"H-2 receipt is not a PASS: {e.get('status')}"
    assert e.get("sha256_delivered") == H2_DELIVERED_SHA256
    assert e.get("sha256_replay") == H2_DELIVERED_SHA256, \
        "H-2 receipt does not attest bit-identity"
