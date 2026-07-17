"""RENDER SMOKE — the served page actually RENDERS (a static check would not catch
a CSS-outside-</style> regression: HTML parses, node --check passes, tag counts
balance, yet the browser paints the stylesheet as visible body text and no styling
applies). This gate loads / in headless chromium and asserts real rendered facts.

Standing requirement for any FE-touching change (operator directive, 2026-07-17).

It also pins the FIELD swap at the render level: the FIELD canvas is present and the
role-pads / XY vector-pad elements are GONE.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="playwright not installed")
from playwright.sync_api import sync_playwright  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]

# candidate chromium executables (PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers).
_CHROMIUM_CANDIDATES = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium/chrome-linux/chrome",
    "/opt/pw-browsers/chromium",
]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _ServerProc:
    """The companion served in a SUBPROCESS (keyless, loopback). Running it out of
    process keeps the real engine/render/librosa imports out of the pytest
    interpreter, so the in-process import-graph invariants (test_mvp_d) stay
    order-independent — the render gate never pollutes another test's sys.modules."""

    def __init__(self, tmp_path):
        self.port = _free_port()
        self.url = "http://127.0.0.1:%d" % self.port
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "cloud.companion", "--cloud-url", "inproc",
             "--host", "127.0.0.1", "--port", str(self.port),
             "--session-dir", str(tmp_path / "sess")],
            cwd=str(_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def wait_healthy(self, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                out = self.proc.stdout.read().decode(errors="replace")
                raise RuntimeError(f"companion subprocess exited early:\n{out}")
            try:
                with urllib.request.urlopen(self.url + "/api/health", timeout=2) as r:
                    if r.status == 200:
                        return
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        raise TimeoutError("companion subprocess did not become healthy")

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self.proc.kill()


def _launch(p):
    """Launch chromium, trying the default resolution first, then explicit
    executablePath fallbacks. Skip LOUDLY (not silently) if none launch."""
    last = None
    try:
        return p.chromium.launch(headless=True, args=["--no-sandbox"])
    except Exception as exc:  # noqa: BLE001
        last = exc
    import os
    for path in _CHROMIUM_CANDIDATES:
        if os.path.exists(path):
            try:
                return p.chromium.launch(headless=True, executable_path=path,
                                         args=["--no-sandbox"])
            except Exception as exc:  # noqa: BLE001
                last = exc
    pytest.skip(f"chromium genuinely unavailable for the render gate: {last}")


def test_fe_renders_no_css_leak_tabs_and_field(tmp_path):
    server = _ServerProc(tmp_path)
    try:
        server.wait_healthy()
        url = server.url
        with sync_playwright() as p:
            browser = _launch(p)
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            page.goto(url, wait_until="load", timeout=30000)
            page.wait_for_selector("#tabs", timeout=15000)

            # (3) NO CSS leaks into visible text — the exact regression class.
            body_text = page.eval_on_selector("body", "el => el.innerText")
            for sig in ("display:", "::after", "border-radius:", "var(--"):
                assert sig not in body_text, \
                    f"CSS leaked into visible page text (found {sig!r}) — stylesheet " \
                    f"is rendering as body text"

            # (4) the tab bar exists and each tab shows EXACTLY ONE active pane.
            for tab_id, pane_id in (("tabPlay", "panePlay"),
                                    ("tabTrain", "paneTrain"),
                                    ("tabExplore", "paneExplore")):
                page.click(f"#{tab_id}")
                shown = page.eval_on_selector_all(
                    ".pane",
                    "els => els.filter(e => getComputedStyle(e).display !== 'none')"
                    ".map(e => e.id)")
                assert shown == [pane_id], \
                    f"clicking #{tab_id} should show exactly [{pane_id}], got {shown}"

            # (5) the FIELD surface is present; role-pads / XY are GONE.
            page.click("#tabPlay")
            assert page.query_selector("#steerSurface") is not None, "field slot missing"
            assert page.query_selector("#fieldCanvas") is not None, "field canvas missing"
            assert page.query_selector("#padRow") is None, "role pads still present"
            assert page.query_selector("#xyPad") is None, "XY vector pad still present"
            assert page.query_selector("#puck") is None, "XY puck still present"
            assert page.query_selector("#drillBack") is None, "drill overlay still present"

            # the field canvas is actually laid out (non-zero box) — really rendered.
            box = page.eval_on_selector("#fieldCanvas",
                                        "el => { const r = el.getBoundingClientRect();"
                                        " return {w: r.width, h: r.height}; }")
            assert box["w"] > 100 and box["h"] > 100, f"field canvas not laid out: {box}"

            # (6) screenshot to the pytest tmp dir for the report.
            shot = tmp_path / "fe_render_smoke.png"
            page.screenshot(path=str(shot), full_page=True)
            assert shot.exists() and shot.stat().st_size > 0
            print(f"[render-smoke] screenshot: {shot}")
            browser.close()
    finally:
        server.close()
