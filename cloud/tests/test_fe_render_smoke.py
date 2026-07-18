"""RENDER SMOKE — the served page actually RENDERS (a static check would not catch
a CSS-outside-</style> regression: HTML parses, node --check passes, tag counts
balance, yet the browser paints the stylesheet as visible body text and no styling
applies). This gate loads / in headless chromium and asserts real rendered facts.

Standing requirement for any FE-touching change (operator directive, 2026-07-17).

It also pins the FIELD REMOVAL (OPEN_ENDS item 2, 2026-07-18) at the render level:
the FIELD canvas is GONE and the radial eigen-mode pad hero is present instead.
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

    def __init__(self, tmp_path, public=False, keys=None):
        self.port = _free_port()
        self.url = "http://127.0.0.1:%d" % self.port
        argv = [sys.executable, "-m", "cloud.companion", "--cloud-url", "inproc",
                "--host", "127.0.0.1", "--port", str(self.port),
                "--session-dir", str(tmp_path / "sess")]
        if public:
            # PUBLIC (hosted) bind, kept on loopback for the test. In public mode the
            # founding demo is NOT surfaced (OPEN_ENDS #16(c)) -> the empty Play state.
            argv.append("--public")
        import os
        env = dict(os.environ)
        if keys:
            env["ETS_ACCESS_KEYS"] = ",".join(keys)
        else:
            env.pop("ETS_ACCESS_KEYS", None)
        self.proc = subprocess.Popen(
            argv, cwd=str(_ROOT), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

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

            # (5) the FIELD is GONE; the radial eigen-mode pad hero is present instead
            # (OPEN_ENDS item 2). The field's canvas/legend/drill/tutorial surface must
            # not exist anywhere in the served markup.
            page.click("#tabPlay")
            assert page.query_selector("#padHero") is not None, "pad hero missing"
            assert page.query_selector("#radialWrap") is not None, "radial pad mount missing"
            for gone_id in ("steerSurface", "fieldCanvas", "fieldLegend", "fieldExpand",
                            "fieldTut", "fieldStatus", "padRow", "xyPad", "puck", "drillBack"):
                assert page.query_selector("#" + gone_id) is None, \
                    f"removed field/legacy element still present: #{gone_id}"

            # (7) REBRAND: the wordmark is "autosynth", the inline logo mark is present,
            # and the old ETS header/subtext is gone (no "Equilibrium Tape Synth", no
            # "steer the terrain"). Ambient prism chrome canvas is present.
            wordmark = page.eval_on_selector(".mark .wordmark", "el => el.textContent.trim()")
            assert wordmark == "autosynth", f"wordmark must be 'autosynth', got {wordmark!r}"
            assert "autosynth" in body_text, "wordmark 'autosynth' not visible in the page"
            for gone in ("Equilibrium Tape Synth", "steer the terrain", "ETS —"):
                assert gone not in body_text, f"old ETS branding still present: {gone!r}"
            logo_svg = page.query_selector(".mark .logo svg")
            assert logo_svg is not None, "inline logo SVG mark missing from the header"
            # LOGO (item 4): concept C "Two-Mode Superposition" — two overlaid mode
            # paths (E1 blue + E2 magenta) + two white node-cap circles.
            paths = page.eval_on_selector_all(".mark .logo svg path", "els => els.length")
            assert paths == 2, f"logo mark should be the two-mode-superposition glyph (2 paths), got {paths}"
            caps = page.eval_on_selector_all(".mark .logo svg circle", "els => els.length")
            assert caps == 2, f"logo mark should have 2 node-cap circles, got {caps}"
            assert page.query_selector("#ambient") is not None, "ambient prism canvas missing"

            # (8) DARK ONLY (operator, 2026-07-18): the theme toggle is GONE, the
            # page renders dark regardless of OS scheme, and the ambient canvas is
            # actually displayed (no longer theme-gated).
            assert page.query_selector("#themeBtn") is None, "theme toggle must be gone"
            body_bg = page.eval_on_selector(
                "body", "el => getComputedStyle(el).backgroundColor")
            assert body_bg == "rgb(5, 6, 11)", f"body must be obsidian dark: {body_bg}"
            amb_disp = page.eval_on_selector(
                "#ambient", "el => getComputedStyle(el).display")
            assert amb_disp == "block", f"ambient must always run, got {amb_disp}"

            # the pad hero is actually laid out (non-zero box) — really rendered, and
            # is the dominant element (the star of the page, item 4 layout intent).
            box = page.eval_on_selector("#padHero",
                                        "el => { const r = el.getBoundingClientRect();"
                                        " return {w: r.width, h: r.height}; }")
            assert box["w"] > 100 and box["h"] > 100, f"pad hero not laid out: {box}"

            # (9) WEB-FAB REMEDIATION — the three remediated surfaces render HONEST:
            #  Fix 1 (tape): the sine-art SVG waveform (#wav) is GONE; the lane shows
            #  the honest-empty "waveform not wired" note; the "settled render" caption
            #  clause is stripped (playhead/clock stay).
            assert page.query_selector("#wav") is None, \
                "the cosmetic tape waveform (#wav sine-art) must be removed"
            assert page.query_selector("#wavEmpty") is not None, \
                "the honest-empty 'waveform not wired' note must be present"
            assert "waveform not wired" in body_text, "honest-empty tape label missing"
            assert "settled render" not in body_text, \
                "the 'settled render' caption clause must be stripped from the tape"

            #  Fix 2 (lane console): the "tolerances & weights" caption is gone; there
            #  are no interactive lane sliders (read-only), and no hardcoded number is
            #  shown under a weights caption.
            assert "tolerances" not in body_text.lower(), \
                "the 'tolerances & weights' Lane-Console caption must be gone"
            n_range = page.eval_on_selector_all(
                "#lanes input[type=range]", "els => els.length")
            assert n_range == 0, f"Lane Console must have no interactive sliders, got {n_range}"

            #  Fix 3 (drift -> slide/loop): the 'drift' meter label is gone; the gauge[g]
            #  slide/loop read-only pair renders (never collapsed to one 'drift' number).
            micro = page.eval_on_selector_all(
                ".meter .micro", "els => els.map(e => e.textContent.trim())")
            assert "drift" not in micro, f"the 'drift' meter label must be gone: {micro}"
            assert page.query_selector("#mSlide") is not None, "slide[g] readout missing"
            assert page.query_selector("#mLoop") is not None, "loop[g] readout missing"

            # (6) screenshot to the pytest tmp dir for the report.
            shot = tmp_path / "fe_render_smoke.png"
            page.screenshot(path=str(shot), full_page=True)
            assert shot.exists() and shot.stat().st_size > 0
            print(f"[render-smoke] screenshot: {shot}")
            browser.close()
    finally:
        server.close()


def test_fe_public_empty_state_no_demo_surfaced(tmp_path):
    """OPEN_ENDS #16(c) render smoke: a PUBLIC (hosted) keyless visitor lands on the
    app (NOT the access page), the Play pane shows the HONEST empty-state text
    (pointer to Explore), and the pad hero renders empty (no world loaded, no
    fabricated modes/pucks). The instrument stays NOT-ready until a set is
    opened/trained."""
    server = _ServerProc(tmp_path, public=True)
    try:
        server.wait_healthy()
        with sync_playwright() as p:
            browser = _launch(p)
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            page.goto(server.url, wait_until="load", timeout=30000)
            # the APP is served, not the access wall (keyless-public serves index).
            page.wait_for_selector("#tabs", timeout=15000)
            assert page.query_selector("#panePlay") is not None, "not the app page"

            # the Play pane shows the empty-state text (from /api/world ready:false,
            # loaded:false) — polled in, so wait for it to appear.
            page.click("#tabPlay")
            page.wait_for_function(
                "() => { const el = document.getElementById('instLock');"
                " return el && /No set loaded/i.test(el.innerText); }",
                timeout=20000)
            lock_text = page.eval_on_selector("#instLock", "el => el.innerText")
            assert "No set loaded" in lock_text, lock_text
            assert "Explore" in lock_text, lock_text

            # the instrument is NOT ready -> the radial pad is never built (no world,
            # no telemetry), so it carries no fabricated modes/puck (empty = empty).
            cls = page.eval_on_selector("#instrument", "el => el.className")
            assert "ready" not in cls.split(), f"instrument must be un-ready: {cls!r}"

            # the pad-hero element still EXISTS and is laid out (honest empty surface,
            # not a removed one) — it just carries the "no world loaded" placeholder.
            assert page.query_selector("#padHero") is not None, "pad hero missing"
            assert page.query_selector("#radialWrap") is not None, "radial pad mount missing"
            wrap_text = page.eval_on_selector("#radialWrap", "el => el.textContent")
            assert "no world loaded" in wrap_text.lower(), \
                f"radial pad must show an honest empty state, got {wrap_text!r}"

            shot = tmp_path / "fe_public_empty_state.png"
            page.screenshot(path=str(shot), full_page=True)
            assert shot.exists() and shot.stat().st_size > 0
            print(f"[render-smoke] empty-state screenshot: {shot}")
            browser.close()
    finally:
        server.close()


def test_fe_keyed_public_visitor_sees_unlock_affordance(tmp_path):
    """OPEN_ENDS #16 render smoke: a keyless visitor on a KEYED+PUBLIC deploy lands
    on the app (no access wall), Train is hidden (visitor), and the in-app
    "Unlock training" affordance is present. Clicking it opens the key prompt."""
    server = _ServerProc(tmp_path, public=True, keys=["k1"])
    try:
        server.wait_healthy()
        with sync_playwright() as p:
            browser = _launch(p)
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            page.goto(server.url, wait_until="load", timeout=30000)
            # the APP is served (not an access wall).
            page.wait_for_selector("#tabs", timeout=15000)
            assert page.query_selector("#accessGate") is None, "access wall must be gone"

            # visitor: the unlock affordance appears (polled in from /api/world.keyed),
            # and the Train tab is hidden.
            page.wait_for_function(
                "() => { const b = document.getElementById('unlockBtn');"
                " return b && !b.hidden; }", timeout=20000)
            assert page.query_selector("#tabTrain").is_hidden(), \
                "Train tab must be hidden for a keyless visitor"

            # clicking the affordance opens the in-app key prompt (no navigation).
            page.click("#unlockBtn")
            page.wait_for_selector("#keyModal:not([hidden])", timeout=5000)
            assert page.query_selector("#keyInput") is not None, "key prompt missing"
            assert server.url in page.url, "unlock must not navigate away from the app"

            shot = tmp_path / "fe_keyed_public_unlock.png"
            page.screenshot(path=str(shot), full_page=True)
            assert shot.exists() and shot.stat().st_size > 0
            print(f"[render-smoke] unlock-affordance screenshot: {shot}")
            browser.close()
    finally:
        server.close()
