"""DARK ONLY — light mode is removed entirely (operator direction, 2026-07-18:
"light mode to be removed … its dark by default").

Static pins on the served page:
  * no theme toggle (``#themeBtn`` / ``data-theme`` switching) anywhere;
  * no light-scheme stylesheet (``prefers-color-scheme: light`` gone);
  * the #ambient prism chrome is UNGATED (it used to be dark-theme-gated; with
    dark permanent it simply always runs) and keeps its reduced-motion freeze.
"""
from __future__ import annotations

import re
from pathlib import Path

_INDEX = (Path(__file__).resolve().parents[1] / "companion" / "static"
          / "index.html")


def test_no_theme_toggle_or_theme_switching():
    html = _INDEX.read_text()
    assert "themeBtn" not in html, "the theme toggle button must be gone"
    assert "themeLbl" not in html, "the theme toggle label must be gone"
    assert "data-theme" not in html, "no data-theme switching — the page is dark, period"


def test_no_light_scheme_styles():
    html = _INDEX.read_text()
    assert "prefers-color-scheme" not in html, \
        "no OS-scheme-dependent styling — one permanent dark look"


def test_ambient_prism_is_ungated_and_keeps_reduced_motion_freeze():
    html = _INDEX.read_text()
    assert '<canvas id="ambient"' in html, "ambient prism canvas missing"
    # the ambient rule is no longer display:none behind a theme gate.
    m = re.search(r"#ambient\{[^}]*\}", html)
    assert m, "the #ambient CSS rule is missing"
    assert "display:none" not in m.group(0), \
        "#ambient must always run (dark is permanent — no theme gate)"
    # the reduced-motion freeze in the ambient script stays.
    assert "prefers-reduced-motion" in html, \
        "the ambient's reduced-motion freeze must be kept"
