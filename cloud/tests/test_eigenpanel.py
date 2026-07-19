"""EIGENPANEL / RADIAL harness (OPEN_ENDS #23) — the object's NATIVE control
surface. Bridge: engine_bridge.compute_eigenmodes (the symmetrized RESPONSE
KERNEL eigenbasis, paper1 Thm A/B — NOT the marginal covariance; see that
function's docstring for the P5-covariance trap and the redundant-"fill" wall,
both resolved there). FE: cloud/companion/static/index.html RADIAL PURE LOGIC
(mode values / force projection / achieved projection / color law).

Teeth (all must BITE):
  EP-1  gains == emitted eigenvalues — no hand-set sensitivity (deterministic,
        JSON round-trip exact, reproducible from the SAME probes).
  EP-2  orthogonality — eigh on a real-symmetric Ksym is orthonormal by
        construction; pushing mode-i's axis alone projects ~zero onto mode-j
        (both the backend matrix, on real demo-world data, and the FE force-
        projection math on a synthetic orthonormal fixture).
  EP-4  no-new-authority — the radial force reaches settlement ONLY via the
        existing /api/steer scalar-lane setters (continuity/novelty/density/
        region); no new fetch, no new setter, no new route.
  EP-5  annotation honesty — badge/composition always present; earned_word
        only inside the off-by-default tooltip; no English on the surface.
  EP-6  outboard — the radial's REST state (center = equilibrium = zero force)
        contributes NOTHING to the steer payload; deleting/never-touching the
        panel leaves settlement identical.
  CH-1  color is a pure function of (rank, eigenvalue, loadings) only — no
        hand-set / injected color on a mode-specific element.
  CH-2  saturation fades to 0 exactly at the measured floor (never negative,
        never a grey-out-but-present below-floor mode).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[2]
_INDEX = _ROOT / "cloud" / "companion" / "static" / "index.html"
_APP = _ROOT / "cloud" / "companion" / "app.py"
_BRIDGE = _ROOT / "cloud" / "companion" / "engine_bridge.py"

_NODE = shutil.which("node")


# ---- JS extraction (mirrors test_web_field.py / test_web_scalar_lanes.py) ---

def _inline_js() -> str:
    html = _INDEX.read_text()
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert blocks, "no inline <script> found in index.html"
    for b in blocks:
        if "RADIAL PURE LOGIC" in b:
            return b
    return max(blocks, key=len)


def _radial_block() -> str:
    js = _inline_js()
    m = re.search(r"/\* ===== RADIAL PURE LOGIC.*?/\* ===== END RADIAL PURE LOGIC ===== \*/",
                  js, re.S)
    assert m, "the test-extractable RADIAL PURE LOGIC block is missing/renamed"
    return m.group(0)


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


def _run_node(script: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        r = subprocess.run([_NODE, path], capture_output=True, text=True, timeout=60)
    finally:
        Path(path).unlink(missing_ok=True)
    assert r.returncode == 0, f"node failed: {r.stdout}\n{r.stderr}"
    return r.stdout.strip()


def _run(body: str) -> str:
    return _run_node(_radial_block() + "\n" + body)


# ---- bridge: real-engine dump (subprocess; keeps arch-v6 out of the test proc) --

_DUMP = r"""
import sys, json
sys.path.insert(0, r"%s")
from cloud.companion.engine_bridge import (StreamPlayer, compute_eigenmodes,
                                           _eigen_lane_vector, _eigen_node_means,
                                           _eigen_obs_names)
p = StreamPlayer("demo.etsworld", seed=0, eigen_n_seed=3, eigen_n_bar=3)
# BOOT-ENSEMBLE (OPEN_ENDS #23 item 5): the real ensemble now computes in a
# background thread so it never blocks first audio; wait for it to land before
# reading modes deterministically (the async SCHEDULING is what changed, not
# the math/determinism under test here).
assert p.wait_eigen(timeout=120), "eigenmode background thread did not land in time"
info = p.world_info()
assert info["eigen_pending"] is False

# EP-1: determinism — recompute with the SAME parameters/rng on the SAME world;
# gains must match bit-for-bit (derived reproducibly, never hand-set).
info2 = compute_eigenmodes(p.world, p.engine.sigma, p.M, n_seed=3, n_bar=3)
det_ok = ([m["gain"] for m in info["modes"]] == [m["gain"] for m in p._eigen["modes"]]
          and [round(m["gain"], 9) for m in info["modes"]]
          == [round(m["gain"], 9) for m in info2["modes"]])
# JSON round-trip exactness: what /api/world would actually serialize.
json_ok = json.loads(json.dumps(info["modes"])) == info["modes"]

# EP-2 (backend): reconstruct Ksym via the SAME production helpers (small, fast
# ensemble; only the orthonormality PROPERTY is under test, not precision) and
# check the FULL eigenvector set is mutually orthonormal on REAL demo-world data.
import numpy as np
M = p.M
names = _eigen_obs_names(M)
D = M + 3
sigma = p.engine.sigma
sig = np.concatenate([np.asarray(sigma.region, float).reshape(-1)[:M],
                      [sigma.density, sigma.cont, sigma.novelty]])
sig_safe = np.where(sig > 0, sig, 1.0)
h = 0.5
R = np.zeros((D, D))
for i in range(M):
    mp = _eigen_node_means(p.world, sigma, lambda ii=i: _eigen_lane_vector(M, region_idx=ii, region_val=+h), M, 90000+i*100, 2, 2)
    mm = _eigen_node_means(p.world, sigma, lambda ii=i: _eigen_lane_vector(M, region_idx=ii, region_val=-h), M, 90000+i*100+50, 2, 2)
    R[:, i] = (mp.mean(0) - mm.mean(0)) / (2*h)
mp = _eigen_node_means(p.world, sigma, lambda: _eigen_lane_vector(M, density=+h), M, 91000, 2, 2)
mm = _eigen_node_means(p.world, sigma, lambda: _eigen_lane_vector(M, density=-h), M, 91050, 2, 2)
R[:, M] = (mp.mean(0) - mm.mean(0)) / (2*h)
mp = _eigen_node_means(p.world, sigma, lambda: _eigen_lane_vector(M, cont=+h), M, 92000, 2, 2)
mm = _eigen_node_means(p.world, sigma, lambda: _eigen_lane_vector(M, cont=-h), M, 92050, 2, 2)
R[:, M+1] = (mp.mean(0) - mm.mean(0)) / (2*h)
mp = _eigen_node_means(p.world, sigma, lambda: _eigen_lane_vector(M, novelty=+h), M, 93000, 2, 2)
mm = _eigen_node_means(p.world, sigma, lambda: _eigen_lane_vector(M, novelty=-h), M, 93050, 2, 2)
R[:, M+2] = (mp.mean(0) - mm.mean(0)) / (2*h)
K = R / sig_safe[:, None]
K[sig <= 0, :] = 0.0
Ksym = 0.5 * (K + K.T)
w_eig, V = np.linalg.eigh(Ksym)
orthonormal_err = float(np.max(np.abs(V.T @ V - np.eye(D))))
symmetric_ok = bool(np.allclose(Ksym, Ksym.T))

print(json.dumps({
    "M": M, "k": info["k"], "eigen_floor": info["eigen_floor"], "basis": info["basis"],
    "modes": info["modes"], "det_ok": det_ok, "json_ok": json_ok,
    "orthonormal_err": orthonormal_err, "symmetric_ok": symmetric_ok,
    "observable_names": info["observable_names"],
}))
""" % str(_ROOT)


@pytest.fixture(scope="module")
def dump():
    r = subprocess.run([sys.executable, "-c", _DUMP], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"subprocess failed:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


# ---- EP-1 : gains == emitted eigenvalues, no hand-set sensitivity -----------

def test_ep1_gains_are_deterministic_and_json_exact(dump):
    assert dump["det_ok"], "recomputing with the SAME probes must give the SAME gains"
    assert dump["json_ok"], "world_info's modes must survive a JSON round-trip exactly"
    assert dump["basis"] == "response_kernel_sym"


def test_ep1_no_hand_set_gain_literal_in_source():
    src = _BRIDGE.read_text()
    # the gain is ALWAYS float(w_eig[r]) from eigh — never a literal number assigned
    # to a "gain"/"eigenvalue" field anywhere in the module.
    assert re.search(r'"gain":\s*gain', src) or re.search(r'"gain":\s*float\(w_eig', src)
    assert not re.search(r'"gain":\s*-?\d', src), "gain must never be a literal constant"


# ---- EP-2 : orthogonality ----------------------------------------------------

def test_ep2_backend_kernel_is_symmetric_and_orthonormal(dump):
    assert dump["symmetric_ok"], "Ksym must be exactly symmetric by construction"
    assert dump["orthonormal_err"] < 1e-8, \
        f"eigh(Ksym) must be orthonormal (V^T V = I); err={dump['orthonormal_err']}"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ep2_fe_force_projection_is_orthogonal_on_a_synthetic_pair():
    """Two hand-built ORTHONORMAL modes over {density, cont, novelty} (a rotated
    basis, exactly analogous to what eigh would return): pushing mode 0 alone must
    project ~0 onto mode 1's own composition, and vice versa — the force-projection
    math must not introduce cross-talk beyond what the eigenvectors already forbid."""
    driver = """
    var s = Math.SQRT1_2;
    var modes = [
      { gain: 3.0, composition: { density: s, cont: s, novelty: 0, fill: 0 } },
      { gain: 1.0, composition: { density: s, cont: -s, novelty: 0, fill: 0 } }
    ];
    function dot(force, comp){
      return force.continuity*comp.cont + force.novelty*comp.novelty + force.density*comp.density;
    }
    // push mode 0 alone -> project onto mode 1.
    var f0 = radialForceVector(modes, [1, 0], 0);
    var p01 = dot(f0, modes[1].composition);
    // push mode 1 alone -> project onto mode 0.
    var f1 = radialForceVector(modes, [0, 1], 0);
    var p10 = dot(f1, modes[0].composition);
    if(Math.abs(p01) > 1e-9){ console.log('FAIL p01 ' + p01); process.exit(1); }
    if(Math.abs(p10) > 1e-9){ console.log('FAIL p10 ' + p10); process.exit(1); }
    // and a mode DOES project fully onto ITSELF (sanity: the math isn't just zero).
    var self0 = dot(f0, modes[0].composition);
    if(Math.abs(self0) < 1e-6){ console.log('FAIL self0 ' + self0); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


# ---- EP-4 : no new authority --------------------------------------------------

def test_ep4_radial_force_vector_only_has_existing_lane_keys():
    """radialForceVector's output must be EXACTLY the existing /api/steer datums
    (continuity/novelty/density/region) — no new key, whatever the mode content."""
    m = re.search(r"function\s+radialForceVector\s*\(([^)]*)\)", _radial_block())
    assert m, "radialForceVector missing"
    code = _js_functions(_radial_block()).get("radialForceVector", "")
    for banned in ("fetch(", "XMLHttpRequest", "/api/"):
        assert banned not in code, f"radialForceVector must not touch the network ({banned})"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ep4_force_vector_keys_are_closed():
    driver = """
    var modes = [{ gain: 2.0, composition: { region0: 0.5, region1: -0.5, density: 0.4,
                                             cont: 0.3, novelty: 0.5, fill: 0.0 } }];
    var f = radialForceVector(modes, [1], 2);
    var keys = Object.keys(f).sort();
    if(JSON.stringify(keys) !== JSON.stringify(["continuity","density","novelty","region"])){
      console.log('FAIL keys ' + JSON.stringify(keys)); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_ep4_no_new_fetch_in_radial_handlers():
    """The radial input handlers reach the engine ONLY through sendSteerNow ->
    sendSteer (the ONE /api/steer call) — never a direct fetch of their own."""
    funcs = _js_functions(_inline_js())
    for h in ("radialPadDown", "radialPadMove", "radialPadUp",
              "radialStripDown", "radialStripMove", "radialStripUp"):
        body = _strip_comments(funcs.get(h, ""))
        assert body.strip() != "", f"{h} missing"
        assert "fetch(" not in body, f"{h} must not call fetch directly"
        assert "sendSteerNow" in body, f"{h} must reach the engine via sendSteerNow"


def test_ep4_no_new_post_route_or_setter():
    app_src = _APP.read_text()
    bridge_src = _BRIDGE.read_text()
    # set_region remains the single call site (WEB-FIELD-D's own invariant, still
    # true after the radial fold-in — no radial-specific engine setter exists).
    assert app_src.count(".set_region(") == 1
    for banned in ("radial_steer", "/api/radial", "def set_radial", "set_mode("):
        assert banned not in app_src and banned not in bridge_src, \
            f"no new radial-specific route/setter ({banned})"
    # the payload keys the radial folds into are exactly the pre-existing ones.
    js = _inline_js()
    assert 'payload.continuity = (payload.continuity || 0) + rf.continuity' in js
    assert 'payload.novelty    = (payload.novelty    || 0) + rf.novelty' in js
    assert 'payload.density    = (payload.density    || 0) + rf.density' in js


# ---- EP-5 : annotation honesty -----------------------------------------------

def test_ep5_badge_and_composition_string_are_math_native():
    """The composition string is numbers + real observable key names only — no
    English word (earned_word is a SEPARATE, gated field, never inlined here)."""
    code = _js_functions(_radial_block()).get("radialCompositionString", "")
    assert code.strip(), "radialCompositionString missing"
    assert "earned_word" not in code, \
        "the composition string (the surface label) must never read earned_word"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ep5_composition_string_contains_only_known_keys_and_numbers():
    driver = """
    var s = radialCompositionString({ density: 0.62, cont: 0.0, novelty: -0.19, region0: 0.31, fill: 0.9 });
    // must mention only real keys, never "fill" (display-derived, excluded on purpose)
    // and never an English word.
    if(s.indexOf("fill") !== -1){ console.log('FAIL fill leaked ' + s); process.exit(1); }
    var words = s.replace(/[-+0-9.\\s]/g, ' ').split(/\\s+/).filter(Boolean);
    var known = { density:1, cont:1, novelty:1, region:1 };   // digits stripped from regionN
    for(var i=0;i<words.length;i++){
      if(!known[words[i]]){ console.log('FAIL unknown token ' + words[i] + ' in ' + s); process.exit(1); }
    }
    console.log('OK');
    """
    assert _run(driver) == "OK"


# EP5 RETIRED (PREREG-field-bias-REV3 Phase B, 2026-07-19): the earned-word toggle
# lived in the XY pad's foot (radialWordToggle + the "your force / achieved" legend).
# The pad was socket-swapped out for the field, so its foot — and the earned-word
# reveal toggle it hosted — went with it (operator: "do NOT leave dead toggles"). The
# radialLabelBadges writer stays (guarded, inert without a pad), but there is no toggle
# markup to assert; the test whose whole subject is that removed toggle is retired
# rather than left asserting a deliberately-removed element.


def test_ep5_badge_elements_always_created_for_every_rendered_mode():
    src = _inline_js()
    build_fn = _js_functions(src).get("buildRadialOnce", "")
    assert "rp-badge" in build_fn, "the pad axes and every strip must carry a badge element"


# ---- EP-6 : outboard (rest state contributes nothing) -----------------------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ep6_centered_radial_contributes_zero_force():
    """center = equilibrium = zero force (spec): with every mode value at 0 (the
    puck/strips at rest), the radial force vector is EXACTLY zero regardless of
    the modes' composition — deleting/never touching the panel changes nothing."""
    driver = """
    var modes = [
      { gain: 5.0, composition: { density: 0.9, cont: 0.1, novelty: 0.3, region0: 0.2, fill: 0.9 } },
      { gain: 2.0, composition: { density: -0.2, cont: 0.8, novelty: 0.1, region0: -0.5, fill: -0.2 } }
    ];
    var f = radialForceVector(modes, [0, 0], 1);
    var zero = (f.continuity === 0 && f.novelty === 0 && f.density === 0
               && f.region.every(function(v){ return v === 0; }));
    if(!zero){ console.log('FAIL ' + JSON.stringify(f)); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_ep6_send_steer_now_gates_the_radial_fold_in_on_k():
    js = _inline_js()
    body = _js_functions(js).get("sendSteerNow", "")
    assert "if(radialK > 0){" in body, \
        "sendSteerNow must skip the radial fold-in entirely when k=0 (no panel)"


# ---- CH-1 : color derives only from (rank, eigenvalue, loadings) ------------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ch1_hue_is_a_deterministic_function_of_rank_and_k():
    driver = """
    if(radialHueForRank(0, 4) !== 0){ console.log('FAIL rank0'); process.exit(1); }
    if(Math.abs(radialHueForRank(3, 4) - 270) > 1e-9){ console.log('FAIL rank3'); process.exit(1); }
    // monotonic across rank.
    var prev = -1;
    for(var r=0; r<4; r++){
      var h = radialHueForRank(r, 4);
      if(h <= prev){ console.log('FAIL monotonic at ' + r); process.exit(1); }
      prev = h;
    }
    console.log('OK');
    """
    assert _run(driver) == "OK"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ch1_badge_color_is_the_weighted_primary_mix():
    driver = """
    // pure density -> pure red.
    var c1 = radialBadgeColor({ density: 1.0, fill: 1.0 });
    if(c1[0] !== 255 || c1[1] !== 0 || c1[2] !== 0){ console.log('FAIL pure ' + c1); process.exit(1); }
    // equal density/novelty -> an even red/blue mix.
    var c2 = radialBadgeColor({ density: 0.5, novelty: -0.5, fill: 0 });
    if(Math.abs(c2[0]-128) > 2 || c2[1] !== 0 || Math.abs(c2[2]-128) > 2){
      console.log('FAIL mix ' + c2); process.exit(1); }
    // an injected hand-set color must NOT reproduce by coincidence for an
    // unrelated composition (proves the mix is really data-derived).
    var c3 = radialBadgeColor({ cont: 1.0, fill: 0 });
    if(c3[0] === c1[0] && c3[1] === c1[1] && c3[2] === c1[2]){
      console.log('FAIL not derived'); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_ch1_no_hardcoded_hex_color_on_mode_specific_elements():
    """No hex-literal color is assigned to a badge/pad/mark element — every
    mode-specific color must route through radialBadgeColor/radialAxisColor/
    radialPadColorAt (an 'injected hand-set color' would show up here)."""
    src = _inline_js()
    funcs = _js_functions(src)
    for name in ("radialDrawPad", "radialLabelBadges", "buildRadialOnce"):
        body = _strip_comments(funcs.get(name, ""))
        for m in re.finditer(r"\.style\.(background|borderColor|color)\s*=\s*(\"#[0-9a-fA-F]{3,6}\"|'#[0-9a-fA-F]{3,6}')", body):
            pytest.fail(f"{name} sets a hand-set hex color: {m.group(0)}")
    # the user puck stays neutral/white — via CSS only, never JS-colored.
    html = _INDEX.read_text()
    assert ".rp-puck{" in html or ".rp-puck {" in html


# ---- CH-2 : saturation fades to 0 exactly at the floor -----------------------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ch2_saturation_zero_at_floor_and_never_negative():
    driver = """
    if(radialSatForGain(0.5, 0.5, 2.0) !== 0){ console.log('FAIL at floor'); process.exit(1); }
    if(radialSatForGain(0.2, 0.5, 2.0) !== 0){ console.log('FAIL below floor negative-clamped'); process.exit(1); }
    var s = radialSatForGain(2.0, 0.5, 2.0);
    if(Math.abs(s - 1) > 1e-9){ console.log('FAIL at max ' + s); process.exit(1); }
    var mid = radialSatForGain(1.25, 0.5, 2.0);
    if(!(mid > 0 && mid < 1)){ console.log('FAIL mid ' + mid); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_ch2_pad_texture_desaturates_toward_center():
    driver = """
    var colorA = [255,0,0], colorB = [0,0,255];
    var center = radialPadColorAt(0.0, 0.0, colorA, 1.0, colorB, 1.0);
    var rim = radialPadColorAt(1.0, 0.0, colorA, 1.0, colorB, 1.0);
    // center must be closer to neutral grey than the rim.
    function distGrey(c){ return Math.abs(c[0]-128)+Math.abs(c[1]-128)+Math.abs(c[2]-128); }
    if(distGrey(center) >= distGrey(rim)){ console.log('FAIL ' + JSON.stringify([center,rim])); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_ch2_survives_bridge_disclosure_of_floor_semantics():
    """The bridge's floor is the SAME quantity CH-2 fades against — one number,
    not a second hand-set display threshold."""
    src = _BRIDGE.read_text()
    assert '"eigen_floor": floor' in src or '"eigen_floor": self._eigen' in src


# ---- wiring sanity: legacy drawer + outboard exist and stay functional ------

def test_legacy_drawer_and_outboard_exist():
    html = _INDEX.read_text()
    assert 'id="legacyDrawer"' in html and "<summary>" in html
    assert 'id="outboard"' in html
    # the XY pad mount (#radialWrap) was socket-swapped out for the FIELD as the single
    # Play steering surface (PREREG-field-bias-REV3 Phase B); the field canvas is now
    # the steering surface that must exist and stay functional.
    assert 'id="fieldCanvas"' in html


def test_scalar_lanes_still_route_through_the_same_one_datum(dump):
    # unaffected by the radial refactor: continuity/novelty/density/gauge/temperature
    # each still stage through their ONE bridge setter (byte-identical to before).
    src = _BRIDGE.read_text()
    for setter in ("set_continuity", "set_novelty", "set_density", "set_gauge",
                   "set_temperature"):
        assert ("def %s(" % setter) in src


# ---- BOOT-ENSEMBLE (OPEN_ENDS #23 item 5): async, real defaults, k>=2 -------
# Slow (real ~40s ensemble in this sandbox, in a background thread) — pinned
# here, deliberately separate from the fast n_seed=3 dump above, because this
# is the ONLY test that exercises the ACTUAL production defaults (the ones a
# real listener's boot uses) end-to-end.

_BOOT_DUMP = r"""
import sys, json
sys.path.insert(0, r"%s")
from cloud.companion.engine_bridge import StreamPlayer

# construction 1: default eigen_n_seed/eigen_n_bar (the REAL production ensemble).
p = StreamPlayer("demo.etsworld", seed=0)
info_before_wait = p.world_info()          # must be honest-pending, not fabricated.
assert p.wait_eigen(timeout=300), "boot ensemble did not land within 300s"
info1 = p.world_info()

# construction 2 ("reload"): a FRESH StreamPlayer, same world, same defaults.
p2 = StreamPlayer("demo.etsworld", seed=0)
assert p2.wait_eigen(timeout=300)
info2 = p2.world_info()

print(json.dumps({
    "pending_before_wait": info_before_wait["eigen_pending"],
    "k_before_wait": info_before_wait["k"],
    "k1": info1["k"], "k2": info2["k"],
    "gains1": [m["gain"] for m in info1["modes"]],
    "gains2": [m["gain"] for m in info2["modes"]],
    "pending_after": info1["eigen_pending"],
}))
""" % str(_ROOT)


@pytest.fixture(scope="module")
def boot_dump():
    r = subprocess.run([sys.executable, "-c", _BOOT_DUMP], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=400)
    assert r.returncode == 0, f"subprocess failed:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_boot_ensemble_reports_honest_pending_before_the_thread_lands(boot_dump):
    # immediately after construction (before wait_eigen), the world MUST report
    # an honest "still measuring" state — never a fabricated k to force a pad.
    assert boot_dump["pending_before_wait"] is True
    assert boot_dump["k_before_wait"] == 0


def test_boot_ensemble_resolves_k_ge_2_with_the_real_defaults(boot_dump):
    # THE WALL THIS FIXES: at the old small ensemble (n_seed=4, n_bar=6) the
    # demo collapsed to k=1 (floor inflated ~22x). With the real production
    # defaults (now 24/32, run async) it must resolve k>=2 — an XY pad, not a
    # single strip — on this informative-B demo world.
    assert boot_dump["k1"] >= 2, boot_dump
    assert boot_dump["pending_after"] is False


def test_boot_ensemble_is_deterministic_across_reloads(boot_dump):
    # "no flicker across reloads" (item 5 disclosure requirement): two
    # independent StreamPlayer constructions against the SAME world produce
    # BIT-IDENTICAL gains (same fixed rng_seed, same estimator — never a
    # per-boot-random ensemble).
    assert boot_dump["k1"] == boot_dump["k2"]
    assert boot_dump["gains1"] == boot_dump["gains2"]
