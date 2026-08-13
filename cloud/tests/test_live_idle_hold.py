"""LM-9 — LIVE IDLES SILENT (papers/PREREG-live-mode.md AMENDMENT 2, B-0 /
A2.3): "in LIVE with no fence, zero slices are cast and the tape does not
advance (fixture); any unfenced settlement audible in LIVE FAILS."

Driven exactly like cloud/tests/test_stream_pacing.py and
cloud/tests/test_bridge_loop_honesty.py: ``StreamPlayer._loop`` on a bare
skeleton (``object.__new__``, no world, no engine) with a call-counting
``produce_one_bar`` stub — this checks the TRANSPORT behavior only (does the
loop ever cast a bar while held?), which is exactly what A2.3 requires: idle
silence is a TRANSPORT-GATED HOLD ("the produce loop does not cast slices"),
never a neutral/empty ClampTerms and never a muted/zeroed buffer.
"""
from __future__ import annotations

import queue
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "companion"))

from engine_bridge import StreamPlayer  # noqa: E402


def _bare_player(sr: int = 8000) -> StreamPlayer:
    p = object.__new__(StreamPlayer)
    p.sr = sr
    p._playing = threading.Event()
    p._thread = None
    p._sub_lock = threading.Lock()
    p._subscribers = set()
    p._live = {"mode": "off", "clamp": None, "track": None, "uid_index": {},
              "current_unit": None, "current_slice_index": None,
              "starved": False}
    p._live_lock = threading.Lock()
    return p


def test_lm9_idle_mode_casts_zero_slices_the_tape_does_not_advance():
    """Straight from AMENDMENT 2's own wording: while ``mode == "idle"``, the
    produce loop must NEVER call produce_one_bar and NEVER emit a byte to any
    subscriber, no matter how long a listener stays connected."""
    calls = {"n": 0}
    bar = b"\x01\x02" * 100

    p = _bare_player()

    def counting_bar():
        calls["n"] += 1
        return bar, None

    p.produce_one_bar = counting_bar
    p._live["mode"] = "idle"          # AMENDMENT 2 B-0: entered LIVE, no fence yet

    q = p.subscribe()                 # a listener IS connected (n_subs > 0):
    try:                              # the hold must bite regardless
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            try:
                item = q.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                continue
            raise AssertionError(
                f"LIVE idle emitted a byte chunk while held: {item!r}")
    finally:
        p.stop()
        p.unsubscribe(q)

    assert calls["n"] == 0, (
        "LIVE idle must cast ZERO slices — produce_one_bar was called "
        f"{calls['n']} time(s) while mode=='idle'")


def test_lm9_any_unfenced_settlement_would_be_audible_iff_the_hold_is_removed():
    """A NEGATIVE control proving the fixture actually bites: the SAME bare
    player with NO hold engaged (``mode: "off"``, exactly what a GRID/TRACKS
    session looks like — LIVE never touched) DOES produce and DOES emit
    bytes. This is the regression guard: if some future edit made the hold
    check unconditional (always skip production), THIS test would catch it,
    the same way a deliberate-violation fixture must bite for LM-5."""
    calls = {"n": 0}
    bar = b"\x01\x02" * 100
    p = _bare_player()

    def counting_bar():
        calls["n"] += 1
        return bar, None

    p.produce_one_bar = counting_bar
    # p._live["mode"] stays "off" (default) — GRID/TRACKS never call a
    # /api/live/* route, so this is their exact, untouched code path.

    q = p.subscribe()
    got = None
    deadline = time.monotonic() + 3.0
    while got is None and time.monotonic() < deadline:
        try:
            got = q.get(timeout=0.25)
        except queue.Empty:
            continue
    p.stop()
    p.unsubscribe(q)

    assert got == bar, "an un-held player (mode='off') must still play normally"
    assert calls["n"] >= 1


def test_lm9_hold_releases_the_instant_a_fence_is_set_no_restart_needed():
    """LM-10's shape, isolated at the transport level: the SAME running loop
    (never stopped/restarted) resumes producing the moment ``mode`` flips to
    "straight" — the hold is released in place, not by tearing down the
    thread. (A real fence's CONTENT is exercised in test_live_carrier.py /
    the write_bar clamp-kwarg plumbing; here only the transport gate.)"""
    calls = {"n": 0}
    bar = b"\x01\x02" * 100
    p = _bare_player()

    def counting_bar():
        calls["n"] += 1
        return bar, None

    p.produce_one_bar = counting_bar
    p._live["mode"] = "idle"

    q = p.subscribe()
    time.sleep(0.3)
    assert calls["n"] == 0, "must still be held before the fence is set"

    with p._live_lock:
        p._live["mode"] = "straight"       # simulates live_start's own transition

    got = None
    deadline = time.monotonic() + 3.0
    while got is None and time.monotonic() < deadline:
        try:
            got = q.get(timeout=0.25)
        except queue.Empty:
            continue
    p.stop()
    p.unsubscribe(q)

    assert got == bar, "production must resume once mode == 'straight'"
    assert calls["n"] >= 1
