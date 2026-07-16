"""H-5 — directive-v1 Feature 2 Stage 1 (operator amendment
stage1-delete-conflated-jack): two non-vacuous structural sweeps.

  (a) TYPING SWEEP — no decision-adjacent package (writer, engine, render,
      functional, planner) imports ``ets.meters.gauge_slide`` /
      ``ets.meters.gauge_loop`` directly; any future consumer must go
      through the typed registry (``ets.meters.contract``). Proven to bite
      on a planted fixture import. The registry's own shape enforcement
      (float-only for slide, bool-only for loop) is covered behaviourally in
      tests/meters/test_contract.py.

  (b) ZERO-REFERENCES SWEEP — no *.py file under ets/, scripts/, tests/ (the
      LIVE surfaces; legacy/ is frozen evidence per H-1 and analysis/ is the
      frozen one-shot instrument run per REGISTRY
      conflation-regression-stage1-2026-07-15 — neither is a live/editable
      surface, so neither is in scope here) references the deleted
      conflated jack's symbols or OSC address. Proven to bite on a planted
      fixture file. The sweep also runs against the GIT-TRACKED file list
      (not just the working tree) so a fresh clone is covered the same way
      (closes the a1-untracked-npz lesson: an acceptance check must see what
      a clone actually receives).
"""
from __future__ import annotations
import ast
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
ETS = ROOT / "ets"

DECISION_PACKAGES = ("writer", "engine", "render", "functional", "planner")


# --------------------------------------------------------------------------
# (a) typing sweep — no decision-adjacent package imports slide/loop directly
# --------------------------------------------------------------------------

def _imported_modules(src: str) -> set:
    mods = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return mods
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            base = ("." * n.level) + (n.module or "")
            mods.add(base)
            mods |= {base + "." + a.name for a in n.names}
    return mods


_SLIDE_LOOP_MODULES = ("gauge_slide", "gauge_loop")


def _typing_leaks(mods: set) -> set:
    return {m for m in mods
            for tail in _SLIDE_LOOP_MODULES if m.split(".")[-1] == tail}


def typing_violations(pkg_root: pathlib.Path):
    """Every (path, leaked-modules) pair where a .py file under ``pkg_root``
    imports gauge_slide/gauge_loop directly (bypassing ets.meters.contract)."""
    hits = []
    for pkg in DECISION_PACKAGES:
        d = pkg_root / pkg
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.py")):
            leaks = _typing_leaks(_imported_modules(p.read_text()))
            if leaks:
                hits.append((str(p), sorted(leaks)))
    return hits


def test_h5a_no_decision_package_imports_slide_or_loop_directly():
    hits = typing_violations(ETS)
    assert not hits, (
        "a decision-adjacent package imports slide[g]/loop[g] directly, "
        f"bypassing the typed contract (ets.meters.contract): {hits}")


def test_h5a_typing_sweep_bites_on_a_planted_direct_import(tmp_path):
    """Non-vacuity: a synthetic decision package importing gauge_loop
    directly (as if it were about to fork a decision off the raw jack,
    bypassing registration) IS caught by the same scanning function."""
    fake_root = tmp_path / "ets"
    (fake_root / "writer").mkdir(parents=True)
    (fake_root / "writer" / "sneaky.py").write_text(
        "from ets.meters import gauge_loop\n"
        "def decide(O, s_phase):\n"
        "    return gauge_loop.loop_g(O, s_phase)\n"
    )
    hits = typing_violations(fake_root)
    assert hits, "H-5a typing sweep is vacuous"
    assert any("gauge_loop" in m for _, leaks in hits for m in leaks)


def test_h5a_typing_sweep_bites_on_a_planted_slide_import(tmp_path):
    fake_root = tmp_path / "ets"
    (fake_root / "engine").mkdir(parents=True)
    (fake_root / "engine" / "sneaky2.py").write_text(
        "from ets.meters.gauge_slide import slide_phase\n"
    )
    hits = typing_violations(fake_root)
    assert hits
    assert any("gauge_slide" in m for _, leaks in hits for m in leaks)


def test_h5a_registered_contract_module_is_the_sanctioned_reader():
    """ets.meters.contract itself is, correctly, not scanned as a 'decision
    package' (it lives under ets.meters, not writer/engine/render/functional/
    planner) — it is the ONE place slide/loop readings may be typed for a
    decision. It does not import gauge_slide/gauge_loop at all (the ending
    predicate takes plain readings, not the meter modules)."""
    from ets.meters import contract as C
    import inspect
    src = inspect.getsource(C)
    assert not _typing_leaks(_imported_modules(src)), (
        "ets.meters.contract imports the meter modules directly instead of "
        "typing plain readings")


# --------------------------------------------------------------------------
# (b) zero-references sweep — the deleted conflated jack leaves no trace
# --------------------------------------------------------------------------

_DELETED_SYMBOLS = frozenset({
    "drift_cv", "DriftCV", "DriftReadout", "key_drift", "phase_drift",
    "timbre_drift", "KEY_MODULUS", "TIMBRE_MODULUS", "circular_holonomy",
    "ADDR_METER_DRIFT", "encode_drift", "drift_key", "drift_phase_feel",
    "drift_timbre", "DRIFT_COMPONENTS",
})
_DELETED_OSC_ADDR = "/ets/meter/drift"

_LIVE_SCAN_DIRS = ("ets", "scripts", "tests")


def _identifiers_and_strings(src: str):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set(), set()
    idents = set()
    strings = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            idents.add(n.id)
        elif isinstance(n, ast.Attribute):
            idents.add(n.attr)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            idents.add(n.name)
        elif isinstance(n, ast.arg):
            idents.add(n.arg)
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                idents.add(a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                idents.add(a.name.split(".")[-1])
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            strings.add(n.value)
    return idents, strings


def zero_references_violations(paths):
    """Every (path, bad-symbols) pair for the given iterable of .py file
    paths (pathlib.Path or str) where a deleted symbol identifier or the
    deleted OSC address literal appears AS CODE (an AST Name/Attribute/def/
    import target, or a string constant EXACTLY equal to the deleted
    address) — never merely as text inside a larger string constant, so a
    docstring or a bite-test's multi-line source fixture that MENTIONS the
    deleted symbol/address in prose or as an embedded code sample (this
    file's own planted-fixture tests; manifest.py's I-14 mutant strings)
    does not trip it, exactly like the repo's existing `_forbidden_hits`
    idiom (tests/invariants/manifest.py) distinguishes identifiers from
    string/comment text. Excludes THIS test file itself, whose own
    module-level `_DELETED_OSC_ADDR` constant legitimately holds the exact
    address string for comparison."""
    hits = []
    self_path = str(pathlib.Path(__file__).resolve())
    for p in paths:
        p = pathlib.Path(p)
        rp = str(p.resolve())
        if rp == self_path:
            continue
        try:
            src = p.read_text()
        except (FileNotFoundError, UnicodeDecodeError):
            continue
        idents, strings = _identifiers_and_strings(src)
        bad = set(idents) & _DELETED_SYMBOLS
        if _DELETED_OSC_ADDR in strings:
            bad = bad | {_DELETED_OSC_ADDR}
        if bad:
            hits.append((str(p), sorted(bad)))
    return hits


def _tracked_py_files():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--", "*.py"],
                         capture_output=True, text=True, check=True)
    return [ROOT / rel for rel in out.stdout.splitlines() if rel.strip()]


def _live_scope(paths):
    live = []
    for p in paths:
        rel = p.resolve().relative_to(ROOT)
        top = rel.parts[0] if rel.parts else ""
        if top in _LIVE_SCAN_DIRS:
            live.append(p)
    return live


def test_h5b_zero_references_in_working_tree():
    paths = []
    for d in _LIVE_SCAN_DIRS:
        paths.extend((ROOT / d).rglob("*.py"))
    hits = zero_references_violations(paths)
    assert not hits, (
        "dangling reference(s) to the deleted conflated jack: "
        f"{hits}")


def test_h5b_zero_references_in_git_tracked_tree():
    """Fresh-clone-clean: the same sweep over exactly the files `git
    ls-files` reports (what a fresh clone actually receives), not just
    whatever happens to sit in the working tree."""
    tracked = _live_scope(_tracked_py_files())
    assert tracked, "git ls-files returned no live-scope .py files -- sweep misconfigured"
    hits = zero_references_violations(tracked)
    assert not hits, (
        "dangling reference(s) to the deleted conflated jack in the "
        f"GIT-TRACKED tree: {hits}")


def test_h5b_zero_references_sweep_bites_on_a_planted_symbol(tmp_path):
    bad = tmp_path / "reintroduced_symbol.py"
    bad.write_text(
        "from ets.meters.drift_cv import drift_cv\n"
        "def f():\n    return drift_cv([0], [0], 8)\n"
    )
    hits = zero_references_violations([bad])
    assert hits, "H-5b zero-references sweep is vacuous on a symbol reference"
    assert any("drift_cv" in b for _, b in hits)


def test_h5b_zero_references_sweep_bites_on_a_planted_osc_address(tmp_path):
    bad = tmp_path / "reintroduced_addr.py"
    bad.write_text(
        "ADDR = '/ets/meter/drift'\n"
        "def send(client):\n    client.send_message(ADDR, [0.0, 0.0, 0.0])\n"
    )
    hits = zero_references_violations([bad])
    assert hits, "H-5b zero-references sweep is vacuous on the OSC address literal"
    assert any(_DELETED_OSC_ADDR in b for _, b in hits)
