"""Stream pacing — the produce loop emits bars at ~realtime, not host speed.

Found live 2026-07-18: the hosted deploy rendered 10.8x faster than realtime
(599s of audio delivered in 55s), so a realtime listener (the browser) buffered
ever further behind "live" and region steering became audible minutes late.
The fix paces bar EMISSION (never render content) with a small fixed lead.

These tests drive ``StreamPlayer._loop`` directly with a stubbed
``produce_one_bar`` (no world, no engine) so they check exactly the transport
behavior and nothing else:

  PACE-A  a fast producer is throttled to ~realtime (plus the fixed lead)
  PACE-B  a slow producer is never slept (under-run behavior unchanged)
  PACE-C  emitted bytes are the stub's bytes verbatim (pacing changes WHEN,
          never WHAT)
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "companion"))

from engine_bridge import StreamPlayer  # noqa: E402


def _bare_player(sr: int) -> StreamPlayer:
    """A StreamPlayer skeleton with only the transport attributes _loop needs —
    no world load, no engine import."""
    p = object.__new__(StreamPlayer)
    p.sr = sr
    p._playing = threading.Event()
    p._thread = None
    p._sub_lock = threading.Lock()
    p._subscribers = set()
    return p


def _run_loop_collect(p: StreamPlayer, n_bars: int, timeout: float):
    """Start the loop, collect n_bars arrival times from a subscriber queue,
    then stop. Returns (arrival_monotonic_times, chunks)."""
    q = p.subscribe()
    times, chunks = [], []
    deadline = time.monotonic() + timeout
    while len(times) < n_bars and time.monotonic() < deadline:
        try:
            chunk = q.get(timeout=0.25)
        except Exception:
            continue
        times.append(time.monotonic())
        chunks.append(chunk)
    p.stop()
    p.unsubscribe(q)
    return times, chunks


def test_pace_a_fast_producer_is_throttled_to_realtime():
    sr = 8000
    bar = b"\x01\x02" * 2000            # 2000 samples = 0.25 s per bar
    p = _bare_player(sr)
    p.produce_one_bar = lambda: (bar, None)   # renders instantly (fast host)

    n = 10                               # 10 bars = 2.5 s of audio
    t0 = time.monotonic()
    times, chunks = _run_loop_collect(p, n, timeout=6.0)
    assert len(times) == n, f"expected {n} bars, got {len(times)}"

    audio_seconds = n * 2000 / sr        # 2.5
    elapsed = times[-1] - t0
    # Unpaced this completes in ~0 s. Paced, bar n is emitted right after the
    # sleep that follows bar n-1, i.e. no earlier than (n-1) bar-slots minus
    # the fixed lead.
    floor = (n - 1) * (2000 / sr) - StreamPlayer.PACE_LEAD_SECONDS - 0.15
    assert elapsed >= floor, (
        f"loop free-ran: {n} bars ({audio_seconds}s of audio) in {elapsed:.2f}s "
        f"(floor {floor:.2f}s) — pacing regressed")
    # And it must not be throttled to slower than realtime either.
    assert elapsed <= audio_seconds + 1.0, f"over-throttled: {elapsed:.2f}s"


def test_pace_b_slow_producer_never_slept():
    sr = 8000
    bar = b"\x01\x02" * 800              # 800 samples = 0.1 s per bar
    render_cost = 0.25                   # renders 2.5x SLOWER than realtime

    p = _bare_player(sr)
    def slow_bar():
        time.sleep(render_cost)
        return bar, None
    p.produce_one_bar = slow_bar

    n = 4
    t0 = time.monotonic()
    times, _ = _run_loop_collect(p, n, timeout=6.0)
    assert len(times) == n
    elapsed = times[-1] - t0
    # An under-running host must pay ONLY its render cost — no added sleeps.
    assert elapsed <= n * render_cost + 0.5, (
        f"slow host was slept: {elapsed:.2f}s for {n} bars "
        f"(render-only floor {n * render_cost:.2f}s)")


def test_pace_d_stop_interrupts_the_pacing_sleep():
    """Auditor note 2: stop() must not have to out-wait a bar-slot sleep —
    otherwise a quick stop->start silently fails to restart the loop."""
    sr = 8000
    bar = b"\x01\x02" * (sr * 3)         # 3 s per bar -> a LONG pacing sleep
    p = _bare_player(sr)
    p.produce_one_bar = lambda: (bar, None)
    q = p.subscribe()
    # wait until the loop is inside the pacing sleep (2 bars emitted = lead
    # exhausted, so it must now be sleeping toward the next slot)
    got = 0
    deadline = time.monotonic() + 3.0
    while got < 2 and time.monotonic() < deadline:
        try:
            q.get(timeout=0.25)
            got += 1
        except Exception:
            continue
    assert got == 2
    t_stop = time.monotonic()
    p.stop()
    p._thread.join(timeout=1.0)
    assert not p._thread.is_alive(), "loop kept sleeping through stop()"
    assert time.monotonic() - t_stop < 1.0
    p.unsubscribe(q)


def test_pace_e_warmup_and_stalls_reanchor_instead_of_bursting():
    """Auditor note 1: a slow first bar (warmup) or mid-stream stall must NOT
    be repaid as a host-speed catch-up burst (which would sit in the client's
    buffer as permanent extra steering latency). The schedule re-anchors."""
    sr = 8000
    bar = b"\x01\x02" * 2000             # 0.25 s per bar
    stall = StreamPlayer.PACE_REANCHOR_SECONDS + 1.0
    calls = {"n": 0}
    p = _bare_player(sr)

    def bar_with_warmup_then_stall():
        calls["n"] += 1
        if calls["n"] == 1:
            time.sleep(stall)            # first-bar warmup (e.g. _ensure_bank)
        return bar, None

    p.produce_one_bar = bar_with_warmup_then_stall
    n = 8                                # 2 s of audio after the warmup bar
    times, _ = _run_loop_collect(p, n, timeout=stall + 6.0)
    assert len(times) == n
    # After the warmup bar arrives, the rest must be PACED (~0.25 s apart once
    # the lead is spent), not a burst. Unre-anchored, bars 2..8 would all
    # arrive within ~0 s of bar 1.
    post = [times[i + 1] - times[i] for i in range(1, n - 1)]
    paced = [d for d in post if d > 0.15]
    assert len(paced) >= 3, (
        f"warmup was repaid as a catch-up burst (gaps {['%.2f' % d for d in post]}) "
        f"— re-anchor regressed")


def test_pace_c_bytes_verbatim():
    sr = 8000
    bar = bytes(range(256)) * 8          # arbitrary recognizable payload
    p = _bare_player(sr)
    p.produce_one_bar = lambda: (bar, None)
    _, chunks = _run_loop_collect(p, 3, timeout=4.0)
    assert chunks and all(c == bar for c in chunks), \
        "pacing altered emitted bytes — it may only change timing"
