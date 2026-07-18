"""WEB-FAB guard — the standing caption->data-source law for the companion web UI.

Doctrine (operator, unchanged): "Every surface either shows REAL data (backed by
the engine) or is disarmed/blank and honestly labeled. No decorative content under
a caption that asserts a data source. Real-or-absent, per surface."

Three data-captioned DECORATIVE surfaces shipped and were remediated (fabrication
class; the tape a REPEAT of the sine-art scar): (1) Output-Tape sine-wave buildWave
under "settled render"; (2) Lane Console hardcoded 62/74/33/55 with inert sliders
under "tolerances & weights"; (3) a role-spread proxy (max-min)*1.4 captioned
"drift". This module is the standing guard so the class cannot reappear a THIRD time.

Teeth (BOTH must BITE — proven by the fixtures below):
  WEB-FAB-1  a caption asserting a live engine data source whose backing value is
             synthetic / hardcoded / placeholder FAILS. Three independent checks:
               (a) the three remediated SCAR phrases may never reappear;
               (b) every remaining data-claim caption is registered in the
                   caption->data-source ALLOWLIST and its backing symbol really
                   exists in the telemetry/world apply path (an unregistered
                   data-claim caption FAILS);
               (c) no hardcoded numeric VALUE literal feeds a lane/meter readout
                   (the LANES `val:62` shape) — lane values must come from telemetry.
  WEB-FAB-2  no `Math.sin/cos/tan/random` procedural art may feed a surface
             captioned as engine output. Layout-geometry trig on a caption-less
             chrome canvas (e.g. the ambient prism on #ambient) is ALLOWED; the
             check distinguishes data-fill (writes a data surface) from layout.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_INDEX = _ROOT / "cloud" / "companion" / "static" / "index.html"


# --- shared extraction (mirrors test_web_field.py) --------------------------

def _inline_main_js(html: str) -> str:
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert blocks, "no inline <script> found in index.html"
    for b in blocks:
        if "FIELD PURE LOGIC" in b:
            return b
    return max(blocks, key=len)


def _js_functions(src: str):
    out = {}
    for m in re.finditer(r"function\s+([A-Za-z_$][\w$]*)\s*\(", src):
        name = m.group(1)
        i = src.index("{", m.end() - 1)
        depth, j = 0, i
        while j < len(src):
            ch = src[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out[name] = src[i + 1:j]
    return out


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"//[^\n]*", " ", src)
    return src


def _unescape(s: str) -> str:
    return (s.replace("&amp;", "&").replace("&#8597;", "↕")
             .replace("&mdash;", "—").replace("&nbsp;", " ")).strip()


# --- the caption -> data-source map (the directive's artifact) --------------

# Tokens that make a caption ASSERT a live engine data source. "disarmed" is a
# real-STATE readout (Theorem A arming corollary): a caption that says a control is
# disarmed asserts a measured fact about the world, so it must be registered and
# backed the same as any other data claim.
_DATA_CLAIM_TOKENS = ("settled", "telemetry", "tolerance", "weight",
                      "drift", "holonomy", "disarmed")

# The three remediated scar phrases — banned verbatim (raw and unescaped).
_SCAR_PHRASES = ("settled render", "tolerances & weights",
                 "tolerances &amp; weights")

# Every data-claim caption legitimately remaining in index.html, mapped to the JS
# symbol that supplies its value. A caption matched by a key here is REAL iff that
# backing symbol is a live function in the main app script (checked below). A
# data-claim caption matched by NO key is unregistered -> FAIL.
_CAPTION_SOURCE_MAP = {
    "settled telemetry": "fieldApplySettled",   # THE FIELD fill (roles telemetry)
    "from telemetry": "updateTape",              # tape playhead (committed-bar time)
    # Theorem A arming corollary (OPEN_ENDS #22): the two field controls that route
    # through the anchor band-profile B disarm on a degenerate (uniform) B. Each
    # refusal caption is a real-state readout backed by the fn that renders it from
    # the measured `profile_armed` flag (/api/world, engine_bridge.anchor_profile_armed).
    "track lean disarmed": "fieldRefuseTrackLean",   # T1 track-lean disarm (uniform B)
    "unit grain disarmed": "fieldRefuseUnitGrain",   # role->unit drill disarm (uniform B)
}


def _captions(html: str):
    caps = []
    for cls in ("hint", "micro", "glbl", "lbl"):
        caps += re.findall(r'<span class="%s"[^>]*>(.*?)</span>' % cls, html, re.S)
    return [_unescape(c) for c in caps]


def _micro_labels(html: str):
    return [_unescape(c) for c in
            re.findall(r'<span class="micro"[^>]*>(.*?)</span>', html, re.S)]


def _data_claim_captions(html: str):
    out = []
    for c in _captions(html):
        low = c.lower()
        if any(tok in low for tok in _DATA_CLAIM_TOKENS):
            out.append(c)
    return out


# --- WEB-FAB-1 violations ----------------------------------------------------

def webfab1_violations(html: str, js: str):
    bad = []
    # (a) the three scar phrases, verbatim, anywhere in the served markup.
    hay = html.lower()
    for phrase in _SCAR_PHRASES:
        if phrase.lower() in hay:
            bad.append(("scar-phrase", phrase))
    # ... and the 'drift' meter label specifically (the E1 scar).
    if any(lbl.lower() == "drift" for lbl in _micro_labels(html)):
        bad.append(("scar-meter-label", "drift"))
    # (b) every data-claim caption must be registered AND really backed.
    funcs = set(_js_functions(js))
    for c in _data_claim_captions(html):
        low = c.lower()
        key = next((k for k in _CAPTION_SOURCE_MAP if k in low), None)
        if key is None:
            bad.append(("unregistered-data-caption", c))
        elif _CAPTION_SOURCE_MAP[key] not in funcs:
            bad.append(("missing-backing", c))
    # (c) no hardcoded numeric value literal feeds a lane/meter readout: the LANES
    #     descriptor array must carry NO `val:<number>` (the exact 62/74/33/55
    #     fabrication), and the lane updater must read the telemetry frame.
    if re.search(r"\bval\s*:\s*\d", js):
        bad.append(("hardcoded-lane-value", "LANES val: literal"))
    return bad


# --- WEB-FAB-2 violations ----------------------------------------------------

# A function WRITES A DATA SURFACE if it touches the tape waveform, a meter value,
# or a lane readout. (The ambient prism writes #ambient — absent here — and bears
# no data caption, so its layout trig is allowed.)
_DATA_SURFACE = re.compile(
    r"\bwav\b|wavEmpty|\bmLoop\b|\bmSlide\b|\.fill\.style|setMeter\s*\(|\.rd\b")
_ART = re.compile(r"Math\.(?:sin|cos|tan|random)\s*\(")


def webfab2_violations(js: str):
    bad = []
    for name, body in _js_functions(js).items():
        b = _strip_comments(body)
        if _DATA_SURFACE.search(b) and _ART.search(b):
            bad.append(name)
    return bad


# ===================== the real served page must be CLEAN ====================

def test_real_page_has_no_webfab1_violation():
    html = _INDEX.read_text()
    js = _inline_main_js(html)
    assert webfab1_violations(html, js) == [], \
        "WEB-FAB-1: a caption asserts data its source does not support"


def test_real_page_has_no_webfab2_violation():
    html = _INDEX.read_text()
    js = _inline_main_js(html)
    assert webfab2_violations(js) == [], \
        "WEB-FAB-2: procedural-art math feeds a data-captioned surface"


def test_caption_source_map_covers_every_data_claim_caption():
    """The allowlist is neither stale nor over-broad: every registered key really
    appears as a data-claim caption in the page, and every data-claim caption in
    the page is coverable by the map (else webfab1 would already fail)."""
    html = _INDEX.read_text()
    present = " ".join(_data_claim_captions(html)).lower()
    for key in _CAPTION_SOURCE_MAP:
        assert key in present, f"stale caption->source key (never rendered): {key!r}"


# --- lane console: read-only must LOOK read-only (no slider affordance) ------

def _stylesheet(html: str) -> str:
    m = re.search(r"<style>(.*?)</style>", html, re.S)
    assert m, "no stylesheet in index.html"
    return m.group(1)


def test_lane_console_has_no_slider_affordance():
    """OPEN_ENDS #21 addendum (operator): the remediation removed the inert
    range inputs, but the lane bars KEPT slider styling (thumb/groove chrome)
    and users still tried to drag them — a residual affordance lie. The lanes
    must be plain meter bars: no range input anywhere, no slider-thumb or
    grab-cursor chrome in the stylesheet, and the bar itself non-interactive."""
    html = _INDEX.read_text()
    js = _inline_main_js(html)
    css = _strip_comments(_stylesheet(html))   # comments aren't chrome
    # no range input ELEMENT in the served markup or the lane builder.
    assert not re.search(r"<input[^>]*type\s*=\s*.?range", html), \
        "a range input is back in the page"
    assert "range" not in _js_functions(js).get("buildLanesOnce", ""), \
        "buildLanesOnce must not create any range input"
    # no slider chrome in the stylesheet (the dead .slider block stays deleted).
    for chrome in ("-webkit-slider-thumb", "-moz-range-thumb", "cursor:grab",
                   "cursor: grab"):
        assert chrome not in css, f"slider chrome is back in the stylesheet: {chrome}"
    assert not re.search(r"\.slider\b", css), ".slider rules must stay deleted"
    # the read-only bar is explicitly non-interactive.
    rbar = re.search(r"\.lane \.rbar\{([^}]*)\}", css.replace("\n", " "))
    assert rbar, ".lane .rbar rule missing"
    body = rbar.group(1).replace(" ", "")
    assert "pointer-events:none" in body and "cursor:default" in body, \
        "the lane meter bar must be visibly/functionally non-interactive"


# ============================ the guards BITE ================================

def test_webfab1_bites_on_scar_phrase():
    html = '<span class="hint">settled render · playhead from telemetry</span>'
    assert any(k == "scar-phrase" for k, _ in webfab1_violations(html, "")), \
        "WEB-FAB-1 failed to bite on the 'settled render' scar caption"


def test_webfab1_bites_on_scar_meter_label():
    html = '<span class="micro">drift</span>'
    assert any(k == "scar-meter-label" for k, _ in webfab1_violations(html, "")), \
        "WEB-FAB-1 failed to bite on the 'drift' meter label"


def test_webfab1_bites_on_unregistered_data_caption():
    # a NEW data-claiming caption with no backing registration must fail.
    html = '<span class="hint">peak envelope · settled amplitude</span>'
    viol = webfab1_violations(html, "")
    assert any(k == "unregistered-data-caption" for k, _ in viol), \
        "WEB-FAB-1 failed to bite on an unregistered data-claim caption"


def test_webfab1_bites_on_hardcoded_lane_value():
    # the exact prior fabrication: a hardcoded value literal for a lane readout.
    js = 'var LANES = [{ key:"region", desc:"tilt spread", val:62 }];'
    assert any(k == "hardcoded-lane-value" for k, _ in webfab1_violations("", js)), \
        "WEB-FAB-1 failed to bite on a hardcoded LANES val: literal"


def test_webfab1_bites_on_synthetic_value_under_data_caption_combined():
    # synthetic VALUE (literal) + data-claiming caption in one surface -> FAIL
    # (the directive's headline fixture: a synthetic value under a data caption).
    html = '<span class="hint">display · tolerances &amp; weights</span>'
    js = 'var LANES=[{key:"novelty",val:33}]; function buildLanes(){ rd.textContent=33; }'
    viol = webfab1_violations(html, js)
    kinds = {k for k, _ in viol}
    assert "scar-phrase" in kinds and "hardcoded-lane-value" in kinds, \
        f"WEB-FAB-1 must bite on synthetic-value-under-data-caption: {viol}"


def test_webfab2_bites_on_procedural_art_feeding_tape():
    # the exact prior scar: Math.sin building the tape waveform surface.
    js = ('function buildWave(){ var wav=document.getElementById("wav");'
          ' wav.innerHTML = "<path d=\\"" + Math.sin(x*0.09) + "\\"/>"; }')
    assert "buildWave" in webfab2_violations(js), \
        "WEB-FAB-2 failed to bite on Math.sin feeding the tape waveform"


def test_webfab2_bites_on_art_feeding_a_meter():
    js = 'function fakeMeter(){ setMeter(m, Math.random()); }'
    assert "fakeMeter" in webfab2_violations(js), \
        "WEB-FAB-2 failed to bite on procedural art feeding a meter"


def test_webfab2_allows_layout_geometry_trig_without_data_caption():
    # legit layout-geometry: positioning dots on a circle for the ambient chrome
    # canvas (#ambient) — NO data surface written, NO data caption -> ALLOWED.
    js = ('function ambientDots(t){ var x = 200 + 80*Math.cos(t), '
          'y = 200 + 80*Math.sin(t); ctxAmbient.arc(x, y, 2, 0, 7); }')
    assert webfab2_violations(js) == [], \
        "WEB-FAB-2 must NOT flag layout-geometry trig on a caption-less canvas"
