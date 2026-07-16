"""I-9 (partial, honest): the F term-weights are never MUTATED by any code path.

I-9 has two halves: (1) F term-weights are frozen after training and run-time
controls are tilt-only; (2) no code path edits the weights at run time. Half (1)
requires training to PRODUCE a frozen weight artifact — which is WALLED at step d
(the contrastive estimator does not separate real from the full fixed family; see
PREREG "Training — real-tracks-are-equilibria" and the step-d report). Until that
wall is resolved and LAMBDA is loaded from a registered artifact, I-9 stays PENDING
in the invariant manifest (its guarded feature is not built).

Half (2) is enforceable NOW and enforced here: a structural AST scan proving that
NO ets module assigns to ``LAMBDA`` (as a name, an attribute ``*.LAMBDA``, or a
subscript ``LAMBDA[...]``) — except the single definition site in
``ets/functional/f.py``. This forward-guard bites the moment the writer/panel
(steps f/g) is built and something tries to reweight F instead of tilting it.
"""
from __future__ import annotations
import ast
import os
import pathlib

ETS_ROOT = pathlib.Path(__file__).resolve().parents[2] / "ets"
DEFINITION_SITE = ETS_ROOT / "functional" / "f.py"


def _lambda_writes(src: str) -> list:
    """Line numbers of any assignment whose target writes LAMBDA (name / attr /
    subscript). Reads (``ff.LAMBDA["T2"]`` on the right of an expression) are NOT
    flagged — only writes."""
    hits = []
    tree = ast.parse(src)
    targets = []

    def _is_lambda_target(node) -> bool:
        if isinstance(node, ast.Name):
            return node.id == "LAMBDA"
        if isinstance(node, ast.Attribute):
            return node.attr == "LAMBDA"
        if isinstance(node, ast.Subscript):
            base = node.value
            return (isinstance(base, ast.Name) and base.id == "LAMBDA") or \
                   (isinstance(base, ast.Attribute) and base.attr == "LAMBDA")
        return False

    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            targets = n.targets
        elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
            targets = [n.target]
        else:
            continue
        for tgt in targets:
            for sub in ast.walk(tgt):
                if _is_lambda_target(sub):
                    hits.append(n.lineno)
    return hits


def test_no_module_mutates_lambda_except_definition():
    offenders = {}
    for path in ETS_ROOT.rglob("*.py"):
        src = path.read_text()
        writes = _lambda_writes(src)
        if not writes:
            continue
        if path == DEFINITION_SITE:
            # the ONLY sanctioned write is the single module-level definition
            assert len(writes) >= 1
            continue
        offenders[str(path.relative_to(ETS_ROOT))] = writes
    assert not offenders, (
        f"I-9: F term-weights mutated outside the definition site: {offenders}")


def test_scanner_is_non_vacuous():
    # a run-time reweighting must be caught (name, attribute, and subscript forms)
    assert _lambda_writes("LAMBDA = {'T2': 9.0}\n")
    assert _lambda_writes("import ets.functional.f as ff\nff.LAMBDA = {}\n")
    assert _lambda_writes("ff.LAMBDA['T2'] = 3.0\n")
    # a READ of LAMBDA is not a mutation and must NOT be flagged
    assert not _lambda_writes("x = ff.LAMBDA['T2'] * cost\n")
