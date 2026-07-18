"""WEB-SCALAR — the scalar force lane family (paper2 §2 conjugate controls; the
Phase-1A typing table rows D9–D13). Each armed lane is TWO marks on one track
(Theorem D(iii)): a draggable HANDLE (user target force) and a read-only MACHINE
MARK (the achieved conjugate observable, from telemetry). Force reaches the engine
ONLY through the widened /api/steer force vector — each lane its ONE datum (its
bridge setter), mirroring the desktop panel's _push. Arming is gated on the world's
MEASURED σ_φ; a lane that cannot lean renders greyed AND inert.

Teeth (all must BITE):
  SCALAR-FORCE   scalarForce is a pure handle-space deflection (released → 0, no
                 meter-in-force feedback); clamped to the lane's ±3 range.
  SCALAR-ONE     each armed direction lane emits through its ONE datum; a DISARMED
                 lane emits NOTHING; CHAOS emits temperature; TEMPO emits nothing.
  SCALAR-MARK    the machine mark is a real telemetry read (real-or-absent), never
                 the handle — they can differ.
  SCALAR-REL     release makes the handle FOLLOW the mark, a direct assignment with
                 no timer / ease / tween (Theorem C').
  SCALAR-CEIL    the "at ceiling" note is derived purely from the telemetry mark
                 history (observable pinned under sustained push) — no per-lane flag.
  SCALAR-TEMPO   TEMPO (T5 clock) renders disabled/not-wired and drives no engine.
  SCALAR-PATH    (real engine, subprocess) each lane setter stages its ONE lane-
                 vector datum; armed lanes tilt, the degenerate gauge lane stays the
                 exact identity — the honest arming matches world_info.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_INDEX = _ROOT / "cloud" / "companion" / "static" / "index.html"
_APP = _ROOT / "cloud" / "companion" / "app.py"
_BRIDGE = _ROOT / "cloud" / "companion" / "engine_bridge.py"

_NODE = shutil.which("node")


# ---- shared extraction (mirrors test_web_field.py) --------------------------

def _inline_js() -> str:
    html = _INDEX.read_text()
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert blocks, "no inline <script> found in index.html"
    for b in blocks:
        if "SCALAR LANE PURE LOGIC" in b:
            return b
    return max(blocks, key=len)


def _scalar_block() -> str:
    js = _inline_js()
    m = re.search(r"/\* ===== SCALAR LANE PURE LOGIC.*?"
                  r"/\* ===== END SCALAR LANE PURE LOGIC ===== \*/", js, re.S)
    assert m, "the test-extractable SCALAR LANE PURE LOGIC block is missing/renamed"
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
    return _run_node(_scalar_block() + "\n" + body)


# --- SCALAR-FORCE : pure handle-space deflection, released = 0, clamped ------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_scalar_force_released_is_zero_and_clamped():
    driver = """
    // released lane never leans (unforced equilibrium), whatever the handle is.
    if(scalarForce(0.9, 0.3, false) !== 0){ console.log('FAIL released'); process.exit(1); }
    // held: proportional deflection from grab, then clamped to the ±3 lane range.
    var up = scalarForce(0.75, 0.5, true);        // Δ=+0.25 -> +1.5
    if(Math.abs(up - 1.5) > 1e-9){ console.log('FAIL up ' + up); process.exit(1); }
    var dn = scalarForce(0.25, 0.5, true);        // Δ=-0.25 -> -1.5
    if(Math.abs(dn + 1.5) > 1e-9){ console.log('FAIL dn ' + dn); process.exit(1); }
    var hi = scalarForce(1.0, 0.0, true);         // Δ=+1 -> +6 -> clamp +3
    if(hi !== SCALAR_U_SCALE){ console.log('FAIL clamp ' + hi); process.exit(1); }
    var lo = scalarForce(0.0, 1.0, true);         // Δ=-1 -> -6 -> clamp -3
    if(lo !== -SCALAR_U_SCALE){ console.log('FAIL clamplo ' + lo); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"//[^\n]*", " ", src)
    return src


def test_scalar_force_reads_no_observable():
    """SCALAR-FORCE / TETHER T-1 (operator amendment): the force is
    f(handle - mark_CURRENT), so `mark` is now a plain PARAMETER (the caller
    passes whatever the live mark is THIS tick) — but scalarForce's own CODE
    must still never independently FETCH an observable store (no meter-in-force
    feedback loop reaching past its parameters)."""
    m = re.search(r"function\s+scalarForce\s*\(([^)]*)\)", _scalar_block())
    assert m, "scalarForce missing"
    params = [p.strip() for p in m.group(1).split(",") if p.strip()]
    assert params == ["handle", "mark", "held"], params
    code = _strip_comments(_js_functions(_scalar_block()).get("scalarForce", ""))
    for banned in ("lanes", "telemetry", "scalarMark"):
        assert banned not in code, f"scalarForce code must not read an observable ({banned})"


# --- SCALAR-ONE : each armed lane one datum; disarmed emits nothing ----------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_scalar_payload_one_datum_per_armed_lane_disarmed_silent():
    driver = """
    var lanes = {
      continuity:  { armed:true,  handle:0.8, mark:0.5, held:true  },  // pushing
      novelty:     { armed:true,  handle:0.5, mark:0.5, held:false },  // released -> 0
      density:     { armed:false, handle:0.9, mark:0.2, held:true  },  // DISARMED -> absent
      gauge:       { armed:false, handle:0.9, mark:0.2, held:true  },  // degenerate -> absent
      temperature: { armed:true,  handle:0.5 }
    };
    var p = scalarPayload(lanes);
    var keys = Object.keys(p).sort();
    // continuity (held+armed), novelty (armed, released->0), temperature. NO density/gauge.
    if(JSON.stringify(keys) !== JSON.stringify(["continuity","novelty","temperature"])){
      console.log('FAIL keys ' + JSON.stringify(keys)); process.exit(1); }
    if(!(p.continuity > 0)){ console.log('FAIL cont force ' + p.continuity); process.exit(1); }
    if(p.novelty !== 0){ console.log('FAIL novelty not 0 ' + p.novelty); process.exit(1); }
    if(!(p.temperature > 0)){ console.log('FAIL temp'); process.exit(1); }
    // a lane with no state at all emits nothing.
    var q = scalarPayload({ temperature:{ armed:true, handle:0.25 } });
    if(Object.keys(q).length !== 1 || !('temperature' in q)){
      console.log('FAIL empty ' + JSON.stringify(q)); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_scalar_lane_setter_map_is_the_four_direction_lanes_no_tempo():
    js = _scalar_block()
    m = re.search(r"SCALAR_LANE_SETTER\s*=\s*\{([^}]*)\}", js)
    assert m, "SCALAR_LANE_SETTER missing"
    keys = set(re.findall(r"(\w+)\s*:", m.group(1)))
    assert keys == {"continuity", "novelty", "density", "gauge"}, keys
    assert "tempo" not in keys, "TEMPO (T5) must not route to any engine datum"
    assert "temperature" not in keys, "CHAOS (T2) is handled separately, not as a lean"


def test_scalar_mark_obs_excludes_gauge():
    """SCALAR-MARK: gauge (KEY LOCK, T3) has NO single machine mark — its conjugate
    is the slide/loop PAIR (metered separately, never summed). So it is absent from
    the single-mark observable map."""
    js = _scalar_block()
    m = re.search(r"SCALAR_MARK_OBS\s*=\s*\{([^}]*)\}", js)
    assert m, "SCALAR_MARK_OBS missing"
    keys = set(re.findall(r"(\w+)\s*:", m.group(1)))
    assert keys == {"continuity", "novelty", "density"}, keys
    assert "gauge" not in keys


# --- SCALAR-MARK : the mark is a telemetry read, never the handle -----------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_scalar_mark_reads_telemetry_real_or_absent():
    driver = """
    // present observable -> the telemetry value (clamped [0,1]); NOT the handle.
    if(scalarMark({continuity:0.83}, "continuity") !== 0.83){ console.log('FAIL val'); process.exit(1); }
    if(scalarMark({continuity:1.7}, "continuity") !== 1){ console.log('FAIL clamp'); process.exit(1); }
    // absent -> null (honest-absent), never a fabricated number.
    if(scalarMark({}, "continuity") !== null){ console.log('FAIL absent'); process.exit(1); }
    if(scalarMark(null, "continuity") !== null){ console.log('FAIL null'); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_scalar_mark_signature_has_no_handle():
    """The mark function reads (lanes, obsKey) only — it CANNOT echo the handle."""
    m = re.search(r"function\s+scalarMark\s*\(([^)]*)\)", _scalar_block())
    assert m, "scalarMark missing"
    params = [p.strip() for p in m.group(1).split(",") if p.strip()]
    assert params == ["lanes", "obsKey"], params


# --- SCALAR-REL : release follows the mark, no timer / ease -----------------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_scalar_follow_release_tracks_mark_held_keeps_target():
    driver = """
    // released: the handle IS the machine mark (follows telemetry).
    if(scalarFollow(0.2, 0.83, false) !== 0.83){ console.log('FAIL follow'); process.exit(1); }
    // held: the handle keeps the user's target (mark and handle may differ).
    if(scalarFollow(0.2, 0.83, true) !== 0.2){ console.log('FAIL held'); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_scalar_release_path_has_no_timer_or_easing():
    """SCALAR-REL: NO ease/tween/lerp/timer anywhere in the scalar-lane control path
    (Theorem C' / WEB-FAB P6). The gap and the release are engine-driven, not UI."""
    funcs = _js_functions(_inline_js())
    watched = ("scalarFollow", "scalarDraw", "updateScalarLanes",
               "scalarOnUp", "scalarOnMove", "scalarOnDown")
    banned = ("setTimeout", "setInterval", "requestAnimationFrame",
              "lerp", "tween", "easing", "ease(")
    for name in watched:
        body = _strip_comments(funcs.get(name, ""))   # comments may name the ban
        assert body.strip() != "" or name == "scalarFollow", f"{name} missing"
        for tok in banned:
            assert tok not in body, f"{name} uses forbidden easing/timer token {tok!r}"
    # the follow is a DIRECT assignment (handle := mark on release), not a step toward.
    assert "scalarFollow(L.handle, mk, L.held)" in funcs.get("updateScalarLanes", ""), \
        "the release-follow must assign the mark directly (no incremental easing)"


def test_temp_fluctuation_meter_is_telemetry_entropy_display_only():
    """TEMP (T2) has no negotiation mark, but its CONJUGATE readout is the live
    fluctuation magnitude = the normalized entropy of the settled role distribution
    (the H that eps weights in F). Meter-class: telemetry-derived (recomputed from the
    real roles vector every frame, never a constant), no easing/timer, and DISPLAY-ONLY
    — it must never feed a control/steer path (delete it -> produced audio byte-identical)."""
    js = _inline_js()
    body = _js_functions(js).get("updateTempFluct", "")
    assert body.strip(), "updateTempFluct missing"
    # derived from the telemetry `roles` vector via entropy (Math.log), not a constant.
    assert "roles" in body and "Math.log" in body, "must compute entropy from the roles vector"
    assert ".fluct.textContent" in body, "must write the read-only readout element"
    b = _strip_comments(body)
    for tok in ("setTimeout", "setInterval", "requestAnimationFrame", "lerp", "tween", "easing"):
        assert tok not in b, f"the meter must have no easing/timer ({tok!r})"
    # DISPLAY-ONLY: the meter must not touch any control/steer/send path.
    for tok in ("sendSteer", "/api/steer", "payload", "set_temperature", "scalarForce", "scalarPayload"):
        assert tok not in b, f"the fluctuation meter must not feed the control path ({tok!r})"
    # and it is driven from the telemetry frame, not a page-load constant.
    assert "updateTempFluct(roles)" in js, "applyTelemetry must drive the meter from live roles"


# --- SCALAR-CEIL : the ceiling note comes from telemetry, not a flag --------

@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_scalar_at_ceiling_from_pinned_telemetry_only():
    driver = """
    var pinned = [0.910, 0.911, 0.910, 0.912, 0.910];   // observable not moving
    var moving = [0.20, 0.35, 0.55, 0.72, 0.90];         // observable responding
    // held + sustained deflection + pinned mark -> at ceiling.
    if(scalarAtCeiling(pinned, true, 0.9, 0.5) !== true){ console.log('FAIL pinned'); process.exit(1); }
    // moving mark -> NOT at ceiling (real response).
    if(scalarAtCeiling(moving, true, 0.9, 0.5) !== false){ console.log('FAIL moving'); process.exit(1); }
    // not held -> never (a released lane is unforced).
    if(scalarAtCeiling(pinned, false, 0.9, 0.5) !== false){ console.log('FAIL held'); process.exit(1); }
    // small deflection -> not really pushing -> no claim.
    if(scalarAtCeiling(pinned, true, 0.52, 0.5) !== false){ console.log('FAIL defl'); process.exit(1); }
    // too little history -> honest-absent (no claim).
    if(scalarAtCeiling([0.91,0.91], true, 0.9, 0.5) !== false){ console.log('FAIL hist'); process.exit(1); }
    console.log('OK');
    """
    assert _run(driver) == "OK"


def test_scalar_ceiling_note_is_data_backed_not_hardcoded():
    """The ceiling affordance is toggled from scalarAtCeiling (a telemetry read), never
    a per-lane boolean literal set in the descriptor."""
    js = _inline_js()
    # the note is driven by L.atCeiling, itself set from scalarAtCeiling(markHist, ...).
    assert "scalarAtCeiling(L.markHist" in js, "atCeiling must come from the mark history"
    # no hardcoded per-lane 'inert'/'atCeiling' truth in the descriptor array.
    m = re.search(r"SCALAR_LANES\s*=\s*\[(.*?)\];", js, re.S)
    assert m, "SCALAR_LANES descriptor missing"
    assert "atCeiling:true" not in m.group(1).replace(" ", ""), \
        "no hardcoded per-lane inert/ceiling flag (real-or-absent)"


# --- SCALAR-TEMPO : honest not-wired ----------------------------------------

def test_tempo_lane_is_fully_removed_from_the_outboard():
    # OPERATOR CHANGE (2026-07-18): the not-wired TEMPO lane was removed entirely
    # from the outboard strip (it emitted no force and confused operators). This
    # test replaces the old "tempo is honestly not-wired" guard: it now asserts
    # TEMPO is GONE — no SCALAR_LANES entry, no tempo flag, no notwired styling —
    # and that removing it never opened a fake time-stretch channel.
    js = _inline_js()
    html = _INDEX.read_text()
    m = re.search(r"SCALAR_LANES\s*=\s*\[(.*?)\];", js, re.S)
    assert m, "SCALAR_LANES table must exist"
    lanes = m.group(1)
    assert "tempo" not in lanes.lower() and "TEMPO" not in lanes, \
        "TEMPO lane must be gone from SCALAR_LANES"
    assert "tempo:true" not in js.replace(" ", ""), "no tempo:true flag anywhere"
    assert "notwired" not in js, "the .notwired (TEMPO) render path must be gone"
    # the surviving outboard gestures are exactly KEY LOCK (gauge) + TEMP (throttle).
    assert '"gauge"' in lanes and '"temperature"' in lanes, \
        "KEY LOCK / GAUGE and TEMP throttle must survive"
    # removing TEMPO must not have fabricated any time-stretch channel.
    for fake in ("timeStretch", "time_stretch", "stretcher", "resample"):
        assert fake not in js, f"no fabricated time-stretch ({fake})"


# --- bridge / app wiring (static) -------------------------------------------

def test_bridge_has_one_setter_per_scalar_lane_and_assembles_the_vector():
    src = _BRIDGE.read_text()
    for setter in ("set_continuity", "set_novelty", "set_density", "set_gauge",
                   "set_temperature"):
        assert ("def %s(" % setter) in src, f"bridge missing {setter}"
    # _current_lane assembles EVERY scalar datum into the single LaneVector.
    lane = src[src.index("def _current_lane("):]
    lane = lane[:lane.index("\n    def ", 1)] if "\n    def " in lane[1:] else lane
    for datum in ("u_continuity", "u_novelty", "u_density", "u_gauge", "T_s"):
        assert datum in lane, f"_current_lane must stage {datum} into the lane vector"
    # the engine's ONE control entry is still _tilt_for (no parallel channel).
    assert "_tilt_for(" in src


def test_bridge_world_info_reports_degenerate_and_steerable():
    src = _BRIDGE.read_text()
    assert '"degenerate":' in src and '"steerable":' in src, \
        "world_info must report degenerate + steerable (honest arming for the lanes)"


# --- SCALAR-PATH : the real engine, each lane through its ONE datum ----------

_DUMP = r"""
import sys, json
sys.path.insert(0, r"%s")
from cloud.companion.engine_bridge import StreamPlayer   # puts arch-v6 on path
p = StreamPlayer("demo.etsworld", seed=0)
info = p.world_info()
# stage each scalar lane through its ONE bridge setter
p.set_continuity(2.5); p.set_novelty(-1.5); p.set_density(2.0)
p.set_gauge(1.0); p.set_temperature(1.7)
u = p._current_lane()
t = p.engine._tilt_for(u)
p.set_continuity(99.0)      # clamp check
print(json.dumps({
  "armed": info["armed"], "disarmed": info["disarmed"],
  "degenerate": info["degenerate"], "steerable": info["steerable"],
  "u": [u.u_continuity, u.u_novelty, u.u_density, u.u_gauge, u.T_s],
  "lam": [t.lam_cont, t.lam_novelty, t.lam_density, t.lam_gauge], "T_s": t.T_s,
  "tilt_degenerate": list(t.degenerate), "tilt_disarmed": list(t.disarmed),
  "clamp_hi": p._current_lane().u_continuity,
  "lane_keys": sorted(p.telemetry["lanes"].keys()),
}))
""" % str(_ROOT)


def _dump():
    r = subprocess.run([sys.executable, "-c", _DUMP], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"subprocess failed:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_scalar_force_path_each_lane_hits_its_datum():
    d = _dump()
    # each lane setter staged its ONE datum into the lane vector.
    assert d["u"][0] == 2.5 and d["u"][1] == -1.5 and d["u"][2] == 2.0 \
        and d["u"][3] == 1.0, d["u"]
    assert abs(d["u"][4] - 1.7) < 1e-6, d["u"][4]                 # T_s carried through
    assert d["clamp_hi"] == 3.0, "the setter must clamp to the lane's ±3 range"


def test_scalar_armed_lanes_tilt_degenerate_gauge_is_identity():
    d = _dump()
    lam_cont, lam_novelty, lam_density, lam_gauge = d["lam"]
    # steerable direction lanes apply a REAL tilt (nonzero λ = u/σ_φ).
    assert lam_cont != 0.0 and lam_novelty != 0.0 and lam_density != 0.0, d["lam"]
    # the degenerate gauge lane is the EXACT identity (λ=0), and the engine says so.
    assert lam_gauge == 0.0, "degenerate gauge must be the exact identity tilt"
    assert "gauge" in d["tilt_degenerate"], "the engine must flag gauge degenerate"
    # the FE arming mirrors this: gauge degenerate (greyed), the rest steerable.
    assert "gauge" in d["degenerate"] and "gauge" not in d["steerable"], d
    assert set(d["steerable"]) == {"region", "cont", "novelty", "density"}, d["steerable"]


def test_scalar_machine_mark_source_exists_in_telemetry():
    """SCALAR-MARK (backend): the machine-mark observables (continuity/novelty/density)
    are real telemetry keys the bridge emits — the FE reads these, never the handle."""
    d = _dump()
    for obs in ("continuity", "novelty", "density"):
        assert obs in d["lane_keys"], f"telemetry.lanes must carry {obs} (the machine mark)"
