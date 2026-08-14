"""THE RETIRED 0.75 MARK STAYS RETIRED.

The journey trace used to draw a share history against a ``.fj-thresh`` line
pinned at ``bottom:75%`` — a leftover of the arrival-share target the CORRECTION
("A-5 NO TARGET ANYWHERE") and Amendment 6 (commit-to-land, "no comparison of
share to a chosen level") both abolished. The mark also stopped meaning
anything the moment the trace became proportional blend segments rather than a
history strip: there is no axis left for a bottom-75% line to sit on.

This is a static pin on the SHIPPED page (mirrors ``test_dark_only.py``'s
pattern): the class must not appear anywhere in the served HTML, in the CSS
rule, the markup, or the render-loop child-count comment that used to carry
it forward on every re-render.
"""
from __future__ import annotations

from pathlib import Path

_INDEX = (Path(__file__).resolve().parents[1] / "companion" / "static"
          / "index.html")


def test_fj_thresh_class_does_not_exist_anywhere():
    html = _INDEX.read_text()
    assert "fj-thresh" not in html, (
        "the retired 0.75 arrival mark (.fj-thresh) must not exist in any "
        "form: not the CSS rule, not the <div>, not a render-loop comment"
    )


def test_no_bottom_75pct_mark_in_journey_css():
    html = _INDEX.read_text()
    assert "bottom:75%" not in html, (
        "no leftover 75% threshold styling anywhere on the page"
    )
