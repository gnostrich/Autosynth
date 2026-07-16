"""Coverage tests over the invariant manifest.

These do NOT test features (none exist yet). They enforce the *discipline*:
all 14 invariants are present exactly once, every ENFORCED invariant carries a
runnable check that passes on the current tree, and PENDING invariants are
reported (never silently treated as satisfied). CI runs this on every commit so
an invariant cannot be dropped, duplicated, or faked into a pass.
"""
from __future__ import annotations
import pytest
from tests.invariants.manifest import INVARIANTS, EXPECTED_IDS, Status


def test_all_fourteen_present_exactly_once():
    ids = [inv.id for inv in INVARIANTS]
    assert ids == EXPECTED_IDS, (
        f"invariant manifest must list I-1..I-14 in order, got {ids}")


def test_no_invariant_is_vacuous():
    # Every invariant is either ENFORCED (with a check) or explicitly PENDING.
    # There is no third state — mirrors auditor §1 "there is no (c)".
    for inv in INVARIANTS:
        assert inv.status in (Status.ENFORCED, Status.PENDING)
        if inv.status is Status.ENFORCED:
            assert inv.check is not None, f"{inv.id} ENFORCED without a check"


@pytest.mark.parametrize("inv", [i for i in INVARIANTS if i.status is Status.ENFORCED],
                         ids=lambda i: i.id)
def test_enforced_invariants_hold(inv):
    inv.check()   # raises AssertionError on violation


def test_pending_are_reported(capsys):
    pending = [inv.id for inv in INVARIANTS if inv.status is Status.PENDING]
    # Surface the pending set so a run never hides that guarded features are
    # unbuilt. This is instrumentation, not a pass/fail gate.
    print("PENDING invariants (guarded feature not built yet):", pending)
    assert True
