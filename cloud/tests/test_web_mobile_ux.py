"""MOBILE-UX chrome — two operator-directed features on the companion FE
(cloud/companion/static/index.html), both DISPLAY-ONLY:

  FULLSCREEN SNAP  a ⛶ affordance snaps the field pane over the entire viewport
                   (.field-full: position:fixed inset 0, above tabs/chrome); a
                   visible ✕ collapses it; Esc / the system fullscreen exit also
                   collapses it (fullscreenchange listener — no stuck overlay).
                   Where the platform allows, true Element.requestFullscreen()
                   plus screen.orientation.lock('landscape') are attempted, each
                   try/catch-guarded. WALL (disclosed in the code): iPhone Safari
                   supports neither — there the snap is viewport-fill only.

  ONE-TIME TUTORIAL  the first time a session's world becomes ready (the
                   enableInstrument transition — never before a world exists) and
                   only while the ets_tut_v1 localStorage flag is unset, a static
                   overlay with exactly three short lines (touch vs mouse wording)
                   covers the field area; "got it" sets the flag forever.

Teeth: every new user-input entry point is registered in the WEB-FIELD-INV
checker's INPUT_HANDLERS and must reach NO telemetry/brightness writer AND no
steer emit — chrome is chrome, never a second decision channel.
"""
from __future__ import annotations

import re
from pathlib import Path

from cloud.tests.test_web_field import (
    BRIGHTNESS_WRITERS,
    INPUT_HANDLERS,
    _inline_js,
    _input_handler_violations,
    _js_functions,
    _reach,
)

_INDEX = (Path(__file__).resolve().parents[1] / "companion" / "static"
          / "index.html")

# the new user-input entry points this change introduces
_NEW_HANDLERS = {"fieldExpandToggle", "fieldExpandOpen", "fieldExpandClose",
                 "fieldOnFullscreenChange", "tutDismiss"}


def _css(html: str) -> str:
    m = re.search(r"<style>(.*?)</style>", html, re.S)
    assert m, "no stylesheet in index.html"
    return m.group(1)


def _css_block(css: str, selector_re: str) -> str:
    m = re.search(selector_re + r"\s*\{([^}]*)\}", css)
    assert m, f"CSS rule {selector_re!r} missing"
    return m.group(1)


# --- (a) the expand affordance + the pinned fullscreen geometry ---------------

def test_expand_button_exists_on_the_field_pane():
    html = _INDEX.read_text()
    assert 'id="fieldExpand"' in html, "the ⛶ expand affordance is missing"
    # it lives inside the field pane (#steerSurface), not somewhere in chrome.
    surface = html[html.index('id="steerSurface"'):html.index('id="fieldStatus"')]
    assert 'id="fieldExpand"' in surface, "#fieldExpand must sit inside #steerSurface"


def test_fullscreen_css_pins_fixed_inset_0_above_chrome():
    css = _css(_INDEX.read_text())
    body = _css_block(css, r"#steerSurface\.field-full")
    assert "position:fixed" in body.replace(" ", ""), ".field-full must be position:fixed"
    assert "inset:0" in body.replace(" ", ""), ".field-full must pin inset:0"
    assert "100dvw" in body and "100dvh" in body, ".field-full must fill the dynamic viewport"
    m = re.search(r"z-index:\s*(\d+)", body)
    assert m and int(m.group(1)) > 40, \
        ".field-full must layer above the transport/tabs chrome (z-index 40)"
    # the canvas grows to fill the expanded geometry (flex fill, not the fixed 340px)
    assert re.search(r"#steerSurface\.field-full\s+\.field-canvas\s*\{[^}]*flex:\s*1",
                     css), "the canvas must flex-fill inside .field-full"


def test_expand_handlers_true_fullscreen_landscape_lock_and_redraw():
    funcs = _js_functions(_inline_js())
    for f in ("fieldExpandToggle", "fieldExpandOpen", "fieldExpandClose",
              "fieldExpandApply", "fieldOnFullscreenChange"):
        assert f in funcs, f"missing fullscreen-snap function {f}"
    op = funcs["fieldExpandOpen"]
    assert "requestFullscreen" in op, "expand must attempt true element fullscreen"
    assert 'orientation.lock("landscape")' in op.replace("'", '"'), \
        "expand must attempt the landscape orientation lock inside the fullscreen promise"
    assert "try{" in op.replace(" ", ""), "the fullscreen/lock attempts must be guarded"
    # the WALL (iPhone Safari: no element fullscreen, no orientation lock) is
    # disclosed in the code, not papered over.
    assert re.search(r"WALL.*iPhone Safari", _inline_js(), re.S), \
        "the iPhone-Safari wall must be disclosed in a code comment"
    # the apply step re-fits the canvas (DPR-aware fieldDraw) in the new geometry,
    # and the resize hook keeps redrawing inside the expanded state too.
    assert "fieldDraw" in funcs["fieldExpandApply"], \
        "toggling the snap must re-fit the canvas via fieldDraw"
    assert re.search(r'addEventListener\(\s*"resize"[^)]*fieldDraw', _inline_js().replace("\n", " ")) \
        or re.search(r'addEventListener\("resize",\s*function\(\)\{[^}]*fieldDraw\(\)', _inline_js()), \
        "fieldDraw must be hooked to window resize (rotation inside the snap)"


# --- (b) exiting fullscreen (Esc / system gesture) collapses the overlay ------

def test_fullscreenchange_collapse_handler_exists_and_collapses():
    js = _inline_js()
    assert re.search(r'document\.addEventListener\(\s*"fullscreenchange"\s*,\s*fieldOnFullscreenChange\s*\)',
                     js), "the fullscreenchange listener must be registered on document"
    body = _js_functions(js)["fieldOnFullscreenChange"]
    assert "fullscreenElement" in body, "collapse must key off document.fullscreenElement"
    assert "fieldExpandApply(false)" in body.replace(" ", ""), \
        "leaving fullscreen must collapse the viewport-fill state (no stuck overlay)"


# --- (c) the one-time tutorial: gating + dismissal ----------------------------

def test_tutorial_gated_on_flag_and_world_ready():
    html = _INDEX.read_text()
    js = _inline_js()
    funcs = _js_functions(js)
    # the overlay ships HIDDEN — the empty Play state stays exactly as-is.
    assert re.search(r'<div class="field-tut" id="fieldTut" hidden', html), \
        "the tutorial overlay must ship with the hidden attribute"
    # localStorage gate: show only while unset; dismiss sets it forever.
    assert 'getItem("ets_tut_v1")' in funcs["tutDismissed"].replace("'", '"')
    assert "tutDismissed()" in funcs["tutShowIfFirst"], \
        "tutShowIfFirst must gate on the localStorage flag"
    assert 'setItem("ets_tut_v1", "done")' in funcs["tutDismiss"].replace("'", '"'), \
        "dismiss must write the ets_tut_v1 flag"
    # world-ready gate: the ONE call site is enableInstrument (the ready transition)
    # — never on load, never before a world exists.
    assert "tutShowIfFirst" in funcs["enableInstrument"], \
        "the tutorial must be triggered by the world.ready transition"
    call_sites = re.findall(r"(?<!function )tutShowIfFirst\s*\(", js)
    assert len(call_sites) == 1, \
        f"tutShowIfFirst must have exactly one call site (enableInstrument), got {len(call_sites)}"


def test_tutorial_exactly_three_lines_both_wordings_and_touch_check():
    html = _INDEX.read_text()
    js = _inline_js()
    # exactly three line slots in the overlay markup.
    tut = re.search(r'id="fieldTut".*?</div>\s*<button', html, re.S).group(0)
    assert len(re.findall(r"<p\b", tut)) == 3, "the tutorial must have exactly three lines"
    # coarse input check + both wordings, verbatim per the operator's direction.
    assert '"ontouchstart" in window' in js.replace("'", '"')
    for line in ("drag up/down on a square — more / less of it",
                 "pinch — zoom in/out (tap header to back out)",
                 "scroll on a square — more / less of it",
                 "Ctrl+scroll or click — zoom (header backs out)",
                 "fill = the engine's answer · ring = your push"):
        assert line in js, f"tutorial wording missing: {line!r}"


def test_tutorial_overlay_is_static_no_animation():
    css = _css(_INDEX.read_text())
    body = _css_block(css, r"\.field-tut")
    assert "animation" not in body and "transition" not in body, \
        "the tutorial overlay must be reduced-motion-safe: no animation at all"


# --- (d) invariant registration: chrome reaches no writer, no steer -----------

def test_new_handlers_registered_in_input_handlers():
    src = _inline_js()
    funcs = _js_functions(src)
    assert _NEW_HANDLERS <= INPUT_HANDLERS, \
        f"unregistered mobile-UX handlers: {_NEW_HANDLERS - INPUT_HANDLERS}"
    assert _NEW_HANDLERS <= set(funcs), \
        f"registered handlers missing from the page: {_NEW_HANDLERS - set(funcs)}"


def test_chrome_reaches_no_brightness_writer_and_no_steer():
    src = _inline_js()
    # the existing transitive checker, over the FULL handler set (incl. the new ones).
    assert _input_handler_violations(src) == [], \
        "WEB-FIELD-INV: a mobile-UX handler reaches a telemetry store/writer"
    # stronger than the field gestures: this chrome is DISPLAY-ONLY, so it must not
    # even reach the steer path (fieldAddBias/sendSteer) — no second decision channel.
    for h in sorted(_NEW_HANDLERS | {"tutShowIfFirst", "fieldExpandApply"}):
        reach = _reach(src, h)
        assert not (reach & BRIGHTNESS_WRITERS), f"{h} reaches a brightness writer"
        assert "sendSteer" not in reach and "fieldAddBias" not in reach, \
            f"{h} must not emit a steer (display-only chrome)"
        assert "fetch" not in reach, f"{h} must not call any /api endpoint"
