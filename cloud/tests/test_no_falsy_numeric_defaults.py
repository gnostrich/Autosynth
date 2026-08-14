"""`x or <number>` ON AN ID OR INDEX IS A BUG — a static check, because
vigilance already failed twice in one day.

2026-08-14, in code written that same afternoon:

    int(live_now.get("track") or -1)      # track 0 is falsy -> "absent"
    int(self._live.get("track") or -1)

Track 0 is a real track — the FIRST track of every world — so its bridge
window was silently never created and it roamed its whole corpus. The defect
was invisible: the field read as a healthy `-1`/absent exactly as if the
track genuinely were not there. That is the same zero-by-construction class
logged in LEDGER.md hours earlier (a metric that is zero BY CONSTRUCTION reads
identical to one that is zero BY MEASUREMENT), hit again by the same author on
the same day.

THE RULE: an id, index, count or bar number is absent only when it is None.
Compare against None explicitly; never lean on falsiness, because 0 is a
legitimate value of every one of those.

This check reads STRUCTURE, not prose (the standing check-writing convention):
it walks the AST for `BoolOp(Or)` whose right operand is a numeric literal and
whose left operand is a `.get(...)` call or a subscript — the shape that bit
us — and never substring-matches source text, so the comments explaining the
rule cannot satisfy or trip it.
"""
from __future__ import annotations

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Files whose numeric `or` defaults are value-identical (a float `or 0.0`
# yields the same number either way) AND which this build may not edit without
# ratification. Listed rather than skipped silently, so the exemption is visible.
RATIFICATION_GATED = {
    os.path.join(ROOT, "architecture-v6", "ets", "engine", "engine.py"),
}


def _numeric_literal(node) -> bool:
    """A numeric literal INCLUDING a signed one. `-1` parses as UnaryOp(USub,
    Constant(1)), not Constant(-1) — the first draft of this detector missed
    exactly that, i.e. it missed the very defect it was written for, and its
    own non-vacuity arm caught it. That is the arm earning its place."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        node = node.operand
    return (isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool))


def _lookup_shaped(node) -> bool:
    """`d.get(...)`, `d[...]`, or a bare name — the shapes that can carry a
    legitimate 0 and therefore must not be defaulted by falsiness."""
    if isinstance(node, ast.Subscript):
        return True
    if isinstance(node, ast.Call):
        f = node.func
        return isinstance(f, ast.Attribute) and f.attr == "get"
    return False


class Unparseable(Exception):
    """A file the checker cannot read is NOT a file with no offenders.

    The first version returned [] on SyntaxError, so when a sed-style fix broke
    the indentation of four tools on 2026-08-14 this check went GREEN while
    seeing nothing in them — and those four are the tools that produce the
    off-pair-mass, admitted-set and Amendment 7 evidence. A checker that cannot
    parse a file must say so, not score it clean."""


def _offenders(path: str):
    try:
        tree = ast.parse(open(path).read())
    except SyntaxError as exc:
        raise Unparseable("%s: %s" % (path, exc)) from exc
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)):
            continue
        vals = node.values
        if len(vals) < 2:
            continue
        if _numeric_literal(vals[-1]) and _lookup_shaped(vals[-2]):
            out.append((getattr(node, "lineno", "?"),
                        ast.dump(vals[-2])[:60], vals[-1].value))
    return out


def _py_files(*rels):
    for rel in rels:
        base = os.path.join(ROOT, rel)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames
                           if d not in ("__pycache__", ".git", "worktrees")]
            for fn in filenames:
                if fn.endswith(".py"):
                    yield os.path.join(dirpath, fn)


def test_every_scanned_file_actually_parses():
    """The blind-spot guard: unparseable is a FAILURE, never a silent pass."""
    broken = []
    for path in _py_files(os.path.join("cloud", "companion"),
                          os.path.join("cloud", "tools"),
                          os.path.join("architecture-v6", "ets")):
        try:
            ast.parse(open(path).read())
        except SyntaxError as exc:
            broken.append("%s: %s" % (os.path.relpath(path, ROOT), exc))
    assert not broken, ("files the static checks cannot read (so cannot check): %r"
                        % broken)


def test_no_falsy_numeric_default_on_a_lookup():
    bad = {}
    for path in _py_files(os.path.join("cloud", "companion"),
                          os.path.join("cloud", "tools"),
                          os.path.join("architecture-v6", "ets")):
        if path in RATIFICATION_GATED:
            continue
        hits = _offenders(path)
        if hits:
            bad[os.path.relpath(path, ROOT)] = hits
    assert not bad, (
        "`lookup or <number>` found — 0 is a legitimate id/index/count, so this "
        "silently substitutes the default for a real value. Compare against None "
        "explicitly. Offenders: %r" % bad)


def test_the_check_is_non_vacuous():
    """It must actually fire on the exact shape that bit us — otherwise it is a
    green light that proves nothing (the zero-by-construction trap again)."""
    src = "x = int(live.get('track') or -1)\ny = d['k'] or 0\n"
    tree = ast.parse(src)
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)
                and _numeric_literal(node.values[-1])
                and _lookup_shaped(node.values[-2])):
            found.append(node.lineno)
    # ast.walk is breadth-first, not source order, so compare as a set
    assert sorted(found) == [1, 2], (
        "the detector missed the historical defect shape; it would pass the tree "
        "for the wrong reason (found lines %r)" % found)
