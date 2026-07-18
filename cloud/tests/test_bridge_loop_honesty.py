"""PRODUCE-LOOP HONESTY (OPEN_ENDS #21c) — a failing engine must be LOUD.

The old ``except Exception: break`` around ``produce_one_bar`` in
``StreamPlayer._loop`` died SILENTLY: no log, no state, and every /api/stream
listener then hung forever on an empty queue. The fix keeps the break (a
failing engine must not spin) but:

  * logs the FULL traceback via logging.exception on "ets.companion.bridge";
  * records a timestamped ``last_error`` string on the bridge, mirrored into
    the telemetry frame and world_info(), so /api/world reports an honest
    "engine failed: <type>" instead of infinite silence.

Driven exactly like cloud/tests/test_stream_pacing.py: ``_loop`` on a bare
StreamPlayer skeleton with a raising ``produce_one_bar`` stub — transport
behavior only, no world, no engine.
"""
from __future__ import annotations

import logging
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "companion"))

from engine_bridge import StreamPlayer  # noqa: E402

_BRIDGE_SRC = (Path(__file__).resolve().parents[1] / "companion"
               / "engine_bridge.py").read_text()


def _bare_player(sr: int = 8000) -> StreamPlayer:
    """A StreamPlayer skeleton with only the attributes _loop touches — no world
    load, no engine import (the test_stream_pacing pattern, plus the honesty
    state the failure path records into)."""
    p = object.__new__(StreamPlayer)
    p.sr = sr
    p._playing = threading.Event()
    p._thread = None
    p._sub_lock = threading.Lock()
    p._subscribers = set()
    p.telemetry = {"roles": [], "t": 0.0, "bar": 0}
    p.last_error = None
    p._warmed = False
    return p


def test_loop_failure_logs_traceback_records_last_error_and_exits(caplog):
    p = _bare_player()
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("bank exploded mid-render")

    p.produce_one_bar = boom
    p._playing.set()
    with caplog.at_level(logging.ERROR, logger="ets.companion.bridge"):
        t = threading.Thread(target=p._loop, daemon=True)
        t.start()
        t.join(timeout=3.0)

    # the loop EXITS (break) — no retry spin: produce was called exactly once.
    assert not t.is_alive(), "the loop must exit after an engine failure"
    assert calls["n"] == 1, "a failing engine must not be retried in a spin loop"

    # the FULL traceback is logged on the bridge logger.
    recs = [r for r in caplog.records if r.name == "ets.companion.bridge"]
    assert recs, "the failure must be logged on ets.companion.bridge"
    assert any(r.exc_info for r in recs), "logging.exception must carry exc_info"
    assert "Traceback" in caplog.text and "RuntimeError" in caplog.text \
        and "bank exploded mid-render" in caplog.text, \
        "the log must contain the full traceback"

    # last_error: timestamped "<time> <type>: <msg>", exposed for world_info.
    assert p.last_error is not None
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z RuntimeError: ",
                    p.last_error), p.last_error
    assert "bank exploded mid-render" in p.last_error

    # ... and mirrored into the telemetry frame (the SSE surface).
    assert p.telemetry.get("last_error") == p.last_error

    # a failed engine is NOT warm.
    assert p._warmed is False


def test_healthy_loop_records_no_error(caplog):
    p = _bare_player()
    p.produce_one_bar = lambda: (b"\x01\x02" * 400, None)
    q = p.subscribe()
    got = None
    deadline = time.monotonic() + 3.0
    while got is None and time.monotonic() < deadline:
        try:
            got = q.get(timeout=0.25)
        except Exception:
            continue
    p.stop()
    p.unsubscribe(q)
    assert got is not None
    assert p.last_error is None
    assert "last_error" not in p.telemetry or p.telemetry["last_error"] is None
    assert not [r for r in caplog.records if r.name == "ets.companion.bridge"]


def test_world_info_exposes_the_honesty_flags_statically():
    # world_info() must carry both readouts (the /api/world surface); checked
    # statically because constructing a real StreamPlayer loads the engine.
    m = re.search(r"def world_info.*?bar_seconds", _BRIDGE_SRC, re.S)
    assert m, "world_info missing?"
    body = m.group(0)
    assert '"warmed"' in body and '"last_error"' in body, \
        "world_info must expose warmed + last_error"


def test_no_bare_silent_except_remains_around_produce():
    # the scar itself: a bare `except Exception:` followed immediately by `break`
    # (no logging) must not reappear in _loop.
    m = re.search(r"def _loop.*?def start", _BRIDGE_SRC, re.S)
    assert m, "_loop missing?"
    body = m.group(0)
    assert not re.search(r"except Exception:\s*\n\s*break", body), \
        "the silent except->break scar is back"
    assert "logger.exception" in body, "_loop must log the traceback loudly"
