"""BR-1 — the check ``cloud/companion/live.py`` cites twice and, until this
file existed, named a test that did not exist (operator ruling, 2026-08-14:
"a cited-but-absent check is worse than an admitted gap").

BR-1's exact wording (``papers/PREREG-live-mode.md``, LIVE BRIDGE v0 CHECKS):

    BR-1 no-intervention: static + runtime — no schedule, corridor, easing, or
         monotonicity logic on the bridge path; the only bridge inputs are the
         fence release and the latched lean.

Amendment 3 (A3.1 R-5) built a ratcheted-corridor bridge mechanism and made it
the DEFAULT. The 2026-08-14 reframe ("LIVE BRIDGE v0 — THE NATURAL
TRANSITION") supersedes that default: B-7 RETIRES the ratchet from the
critical path and keeps it "specced behind a flag for A/B measurement only,
never default" — which is what ``live.py``'s own comment calls "Amendment 3
R-5" dormancy: the corridor/ratchet functions still exist (for an explicit
opt-in A/B run) but nothing on the shipped bridge path may call them.

CRITICAL CONVENTION (operator standing rule, after a check fooled itself by
matching its own explaining prose): a static check asserting the ABSENCE of a
concept walks the AST and reads identifiers / attributes / call targets —
NEVER substring-matches source text. Every static check below does exactly
that: it parses ``ast.parse(...)`` and only ever looks at ``Name.id``,
``Attribute.attr``, ``FunctionDef`` names/args and ``Call.func`` targets.
None of it ever calls ``.find(...)`` / ``in`` / a regex against raw source
text or a docstring's string contents — comments and docstrings are
``ast.Constant`` string nodes that this walk never inspects, so a comment
that correctly explains "no ratchet logic here" cannot make the check that
tests for it pass OR fail on its own prose.

Three checks:
  * ``test_br1_bridge_branch_in_compose_bar_calls_only_the_default_carrier_functions``
    — the PER-BAR bridge branch of ``StreamPlayer._compose_bar`` (the
    ``elif live.get("mode") == "bridge":`` clause — the actual per-bar
    carrier-construction code BR-1 governs) may only call the registered
    release/pull/window primitives.
  * ``test_br1_dormant_ratchet_functions_are_unreachable_from_the_default_bridge_path``
    — every ``live_mod.*`` function ``engine_bridge.py`` calls AT ALL,
    closed over ``live.py``'s own internal call graph, must never reach
    ``corridor_mask`` / ``ratchet_bridge_step`` / ``ratchet_bridge_clamp`` /
    ``track_character`` (the dormant ratchet section's four names).
  * ``test_br1_default_engine_bridge_path_never_calls_the_ratchet`` — the
    RUNTIME proof BR-1 itself asks for ("static + runtime"): monkeypatch the
    three ratchet entry points to raise, drive a REAL bridge (real world,
    real engine, real ``StreamPlayer``) through a straight start, a second
    click on a different track, and several produced bars, and show none of
    the traps fire.

See the bottom of this file's companion report for the revert-proof: wiring
``live_mod.ratchet_bridge_clamp(...)`` into the bridge branch trips all three
checks; removing it restores green. (The revert itself is not committed here
— see the operator report for the pasted before/after pytest output.)
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_LIVE_PATH = _ROOT / "cloud" / "companion" / "live.py"
_BRIDGE_PATH = _ROOT / "cloud" / "companion" / "engine_bridge.py"

_LIVE_SRC = _LIVE_PATH.read_text()
_BRIDGE_SRC = _BRIDGE_PATH.read_text()
_LIVE_TREE = ast.parse(_LIVE_SRC, filename=str(_LIVE_PATH))
_BRIDGE_TREE = ast.parse(_BRIDGE_SRC, filename=str(_BRIDGE_PATH))

# The ratchet corridor's own four names — live.py's "RATCHET CORRIDOR —
# FLAGGED, NON-DEFAULT, MEASUREMENT-ONLY (Amendment 3 R-5)" section.
# track_character is included: its own docstring says it is "DORMANT: only
# the ratchet functions below call this" — i.e. it has no legitimate
# default-path caller either.
_DORMANT_RATCHET_NAMES = frozenset({
    "corridor_mask", "ratchet_bridge_step", "ratchet_bridge_clamp",
    "track_character",
})

# The only live.py functions the bridge branch of _compose_bar is allowed to
# call: release (B-1), pull (B-2), and the shared forward-walking window
# (B-3's own mechanism, reused verbatim from straight play).
_ALLOWED_BRIDGE_BRANCH_CALLS = frozenset({
    "pull_step", "release_clamp", "release_step", "bar_window",
})

_BANNED = re.compile(r"schedule|corridor|easing|monoton|ratchet", re.IGNORECASE)


# --- AST helpers: identifiers / attributes / call targets ONLY -------------

def _find_funcdef(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found")


def _tests_equality_against(test_node: ast.AST, literal: str) -> bool:
    """True iff ``test_node`` is (or AND's together) an ``==`` comparison
    whose OTHER side is the constant ``literal`` — deliberately narrower than
    "the string appears somewhere in the test", which would also match an
    unrelated ``x in ("straight", "bridge")`` membership test elsewhere in
    the same dispatch. Reads ``Compare`` nodes with an ``Eq`` op only."""
    candidates = test_node.values if isinstance(test_node, ast.BoolOp) else [test_node]
    for cand in candidates:
        if not isinstance(cand, ast.Compare) or len(cand.ops) != 1:
            continue
        if not isinstance(cand.ops[0], ast.Eq):
            continue
        sides = [cand.left, cand.comparators[0]]
        if any(isinstance(s, ast.Constant) and s.value == literal for s in sides):
            return True
    return False


def _branch_body_for_string_test(func_node: ast.FunctionDef, literal: str) -> list:
    """The statement list of the ``ast.If`` branch inside ``func_node`` whose
    test is an ``==`` comparison against the string ``literal`` (e.g. the
    ``elif live.get("mode") == "bridge":`` clause) — found by reading the
    Compare node's own operator and constant OPERAND, never by matching
    source text, so neither a comment mentioning "bridge" elsewhere in the
    function NOR an unrelated ``mode in ("straight", "bridge")`` membership
    test can confuse it."""
    matches = [node for node in ast.walk(func_node)
              if isinstance(node, ast.If) and _tests_equality_against(node.test, literal)]
    if not matches:
        raise AssertionError(
            f"no `== {literal!r}` branch found in {func_node.name} — has "
            "the mode dispatch been restructured?")
    if len(matches) > 1:
        raise AssertionError(
            f"more than one `== {literal!r}` branch found in {func_node.name} "
            "— this helper needs to be told which one")
    return matches[0].body


def _call_targets(nodes) -> list:
    """Every call TARGET in a list of AST statements, as ``(base, name)``:
    ``foo(...)`` -> ``(None, "foo")``; ``obj.foo(...)`` -> ``(base_id_or_
    None, "foo")``. Reads ``Call.func`` nodes only."""
    targets = []
    for stmt in nodes:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    targets.append((None, f.id))
                elif isinstance(f, ast.Attribute):
                    base = f.value.id if isinstance(f.value, ast.Name) else None
                    targets.append((base, f.attr))
    return targets


def _identifiers(nodes) -> set:
    """Every ``Name.id`` / ``Attribute.attr`` / function-def name / arg name
    appearing anywhere in ``nodes`` — the identifier vocabulary the code
    actually USES, never its comments or docstrings (those are
    ``ast.Constant`` string nodes, invisible to this walk by construction)."""
    ids = set()
    for stmt in nodes:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Name):
                ids.add(node.id)
            elif isinstance(node, ast.Attribute):
                ids.add(node.attr)
            elif isinstance(node, ast.FunctionDef):
                ids.add(node.name)
                for a in node.args.args:
                    ids.add(a.arg)
            elif isinstance(node, ast.arg):
                ids.add(node.arg)
    return ids


def _banned_identifiers(nodes) -> list:
    return sorted(i for i in _identifiers(nodes) if _BANNED.search(i))


def _live_mod_entry_points(tree: ast.AST) -> set:
    """Every ``live_mod.<name>`` call target anywhere in engine_bridge.py —
    every live.py function the bridge module reaches for AT ALL (straight
    play and bridge alike), harvested from ``Call.func`` nodes."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "live_mod":
                names.add(node.func.attr)
    return names


def _module_funcdefs(tree: ast.AST) -> dict:
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _internal_call_graph(tree: ast.AST) -> dict:
    """``name -> set(names)`` of module-level functions each function calls,
    restricted to ``Name`` call targets that resolve to another function
    DEFINED in this same module (live.py calling itself, not ``ets``/stdlib)."""
    defs = _module_funcdefs(tree)
    graph = {}
    for name, node in defs.items():
        called = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                if sub.func.id in defs:
                    called.add(sub.func.id)
        graph[name] = called
    return graph


def _reachable(graph: dict, entry_points) -> set:
    seen = set()
    stack = [n for n in entry_points if n in graph]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(graph.get(n, ()))
    return seen


# --- non-vacuous guard: the names this file hunts for must actually exist --

def test_the_dormant_ratchet_names_still_exist_in_live_py():
    """If Amendment 3's functions were ever renamed without updating this
    file, the reachability checks below would silently stop testing
    anything. Confirms all four dormant names are real module-level
    functions in live.py right now."""
    defs = _module_funcdefs(_LIVE_TREE)
    missing = sorted(n for n in _DORMANT_RATCHET_NAMES if n not in defs)
    assert not missing, (
        f"expected dormant ratchet function(s) missing from live.py: {missing} "
        "— this file's BR-1 checks need updating, not silently passing")


def test_the_bridge_branch_and_bridge_entry_points_are_non_vacuous():
    """The AST-scoping helpers above must actually find something, or the
    checks that build on them would pass by finding nothing to check."""
    compose_bar = _find_funcdef(_BRIDGE_TREE, "_compose_bar")
    branch = _branch_body_for_string_test(compose_bar, "bridge")
    assert branch, "_compose_bar's bridge branch is empty — nothing to check"
    entries = _live_mod_entry_points(_BRIDGE_TREE)
    assert entries, "no live_mod.* call found anywhere in engine_bridge.py"


# --- BR-1 STATIC SCAN -------------------------------------------------------

def test_br1_bridge_branch_in_compose_bar_calls_only_the_default_carrier_functions():
    """The PER-BAR bridge branch of ``StreamPlayer._compose_bar`` (the
    ``elif live.get("mode") == "bridge":`` clause) is the actual default
    bridge path BR-1 governs — the code that runs once per produced bar
    while a journey is in flight. Walk its AST and read every call target:
    the only ``live_mod.*`` functions it may call are the release/pull/
    window primitives; none of the four dormant ratchet names may appear as
    a call target OR as any other identifier inside this branch."""
    compose_bar = _find_funcdef(_BRIDGE_TREE, "_compose_bar")
    branch = _branch_body_for_string_test(compose_bar, "bridge")

    live_mod_calls = {attr for base, attr in _call_targets(branch) if base == "live_mod"}
    forbidden = live_mod_calls & _DORMANT_RATCHET_NAMES
    assert not forbidden, (
        f"the bridge branch of _compose_bar calls dormant ratchet "
        f"function(s) {sorted(forbidden)} — BR-1 forbids this")
    assert live_mod_calls, (
        "the bridge branch calls nothing in live_mod at all — has "
        "_compose_bar been restructured? this check would be vacuous")
    assert live_mod_calls <= _ALLOWED_BRIDGE_BRANCH_CALLS, (
        f"the bridge branch calls live_mod function(s) outside the "
        f"registered default set: {sorted(live_mod_calls - _ALLOWED_BRIDGE_BRANCH_CALLS)}")

    banned = _banned_identifiers(branch)
    assert not banned, (
        f"identifier(s) {banned} matching schedule/corridor/easing/"
        f"monotonicity/ratchet appear in the bridge branch's own AST")


def test_br1_dormant_ratchet_functions_are_unreachable_from_the_default_bridge_path():
    """Every ``live_mod.*`` function engine_bridge.py calls AT ALL (straight
    play and bridge alike — the full entry surface, harvested from Call
    targets, not guessed), closed over live.py's OWN internal call graph
    (also Call-target based), must never reach ``corridor_mask`` /
    ``ratchet_bridge_step`` / ``ratchet_bridge_clamp`` / ``track_character``.
    Stated as a reachability fact about the AST, not an assertion about
    which lines a human happened to read."""
    entries = _live_mod_entry_points(_BRIDGE_TREE)
    graph = _internal_call_graph(_LIVE_TREE)
    closure = _reachable(graph, entries)
    hit = closure & _DORMANT_RATCHET_NAMES
    assert not hit, (
        f"the default engine_bridge.py entry points reach dormant ratchet "
        f"function(s) {sorted(hit)} via live.py's own call graph. "
        f"full reachable set: {sorted(closure)}")


def test_br1_no_banned_identifiers_in_the_reachable_default_path_closure():
    """Defense in depth beyond named-function reachability: no identifier
    (Name/Attribute/def/arg) matching schedule|corridor|easing|monotonic|
    ratchet appears ANYWHERE in the bodies of the functions the default path
    actually reaches — catching inline logic even if it were never factored
    into one of the four named dormant functions."""
    entries = _live_mod_entry_points(_BRIDGE_TREE)
    defs = _module_funcdefs(_LIVE_TREE)
    graph = _internal_call_graph(_LIVE_TREE)
    closure = _reachable(graph, entries)
    reached_bodies = [defs[n] for n in closure if n in defs]
    banned = _banned_identifiers(reached_bodies)
    assert not banned, (
        f"banned identifier(s) {banned} reachable from the default bridge "
        f"path's own call closure {sorted(closure)}")


# --- BR-1 RUNTIME PROOF ------------------------------------------------------
# "static + runtime" (BR-1's own wording). Out-of-process (the established
# cloud-test pattern, see test_wavemap_fixture.py's module docstring): a real
# StreamPlayer needs the ui-v5 (architecture-v6) engine tree to own `import
# ets`, which the in-process cloud suite cannot guarantee once anything else
# has imported root `ets`. `probe(body)` runs a child with arch-v6 pinned and
# the fixture world built (once, cached on disk across probes).

from cloud.tests.test_wavemap_fixture import probe  # noqa: E402

_BRIDGE_RUNTIME_PROBE = r'''
import cloud.companion.live as live_mod
from cloud.companion.engine_bridge import StreamPlayer

# Trap the three ratchet entry points: if the default bridge path calls any
# of them, the call raises immediately instead of silently doing ratchet
# work, so it surfaces as a produce_one_bar() exception below.
fired = []
def _make_trap(name):
    def _trap(*a, **k):
        fired.append(name)
        raise RuntimeError("RATCHET FIRED ON THE DEFAULT BRIDGE PATH: " + name)
    return _trap

for _name in ("corridor_mask", "ratchet_bridge_step", "ratchet_bridge_clamp"):
    setattr(live_mod, _name, _make_trap(_name))

p = StreamPlayer(WORLD, seed=0, is_trained=True, eigen_n_seed=2, eigen_n_bar=2)
p.start = lambda: None     # no background produce-loop thread: drive bars
                            # by hand, synchronously, in this one process —
                            # produce_one_bar() is the exact per-bar compose
                            # the loop itself calls (see engine_bridge.py's
                            # own _loop), just without real-time pacing.

start = p.live_start(0, 0.0)          # first click: straight play, track 0
straight_states = []
for _ in range(2):                    # a handful of bars (sandbox is ~100x slower)
    p.produce_one_bar()
    straight_states.append(p.live_state())

click = p.live_click(1, 0.3)          # SECOND click, a DIFFERENT track -> THE BRIDGE

bridge_states = []
error = None
try:
    for _ in range(4):                # a handful of bridge bars
        p.produce_one_bar()
        bridge_states.append(p.live_state())
except Exception as e:
    error = type(e).__name__ + ": " + str(e)

emit({
    "start": start, "click": click, "fired": fired, "error": error,
    "straight_modes": [s.get("mode") for s in straight_states],
    "bridge_phases": [s.get("phase") for s in bridge_states],
    "bridge_dest_track": [s.get("dest_track") for s in bridge_states],
    "n_bridge_bars_completed": len(bridge_states),
})
'''


def _d():
    if not hasattr(_d, "_v"):
        _d._v = probe(_BRIDGE_RUNTIME_PROBE)
    return _d._v


def test_br1_default_engine_bridge_path_never_calls_the_ratchet():
    """RUNTIME proof: monkeypatch ``corridor_mask`` / ``ratchet_bridge_step``
    / ``ratchet_bridge_clamp`` to raise, then drive a REAL bridge — a real
    ``StreamPlayer`` against the real ui-v5 engine and a real trained world:
    straight play on track 0, a second click on a DIFFERENT track (which
    enters the bridge per ``live_click``'s own dispatch), and several
    produced bars. None of the three traps may fire — if the default path
    called any of them, ``produce_one_bar()`` would raise and ``error``
    would be non-None below."""
    d = _d()
    assert d["error"] is None, f"the bridge path raised: {d['error']} (probe: {d})"
    assert d["fired"] == [], (
        f"dormant ratchet function(s) fired on the default bridge path: {d['fired']}")


def test_br1_runtime_proof_is_non_vacuous_it_really_drove_a_bridge():
    """The runtime proof above is only meaningful if it actually reached
    bridge mode and produced bars there — never a proof that trivially
    passed because nothing ran. Checked against the SAME probe's own
    telemetry (measured, not asserted): every produced bridge bar reports
    the destination track just clicked and the "blending" phase."""
    d = _d()
    assert d["click"] == {"track": 1, "bridge": True}, d["click"]
    assert d["n_bridge_bars_completed"] == 4, d
    assert d["bridge_phases"] == ["blending"] * 4, d["bridge_phases"]
    assert d["bridge_dest_track"] == [1] * 4, d["bridge_dest_track"]
    assert d["straight_modes"] == ["straight"] * 2, d["straight_modes"]
