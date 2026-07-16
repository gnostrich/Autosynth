#!/usr/bin/env python3
"""Persistent versioning ledger — PostToolUse hook.

Appends ONE line to VERSION_LEDGER.jsonl for every Write/Edit/MultiEdit that
lands on a tracked file in this repo. Deterministic, free, and guaranteed to
fire on every edit (a command hook, not an LLM call) — so the ledger can never
silently miss an edit. Each entry: UTC timestamp, tool, repo-relative path, and
the git HEAD the edit was made against.

Contract with the harness: reads the PostToolUse event JSON on stdin, NEVER
fails the tool call (always exits 0), and only records edits to files under the
repo root (skips the scratchpad, .git, and anything outside the tree). This is
provenance only; it does not read, alter, or gate the edit itself.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(REPO, "VERSION_LEDGER.jsonl")
_TRACKED_TOOLS = {"Write", "Edit", "MultiEdit"}


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _rel_if_tracked(path: str):
    """Return the repo-relative path iff `path` is a real file inside the repo
    tree (and not under .git). Otherwise None — the edit is out of scope."""
    try:
        ap = os.path.abspath(path)
    except Exception:
        return None
    rp = os.path.realpath(REPO)
    ra = os.path.realpath(ap)
    if ra != rp and not ra.startswith(rp + os.sep):
        return None                      # outside the repo (e.g. scratchpad, /tmp)
    rel = os.path.relpath(ra, rp)
    if rel.split(os.sep, 1)[0] == ".git":
        return None
    return rel


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0                         # never break the tool call

    tool = event.get("tool_name", "")
    if tool not in _TRACKED_TOOLS:
        return 0

    path = (event.get("tool_input") or {}).get("file_path")
    if not path:
        return 0
    rel = _rel_if_tracked(path)
    if rel is None or rel == os.path.basename(LEDGER):
        return 0                         # skip out-of-tree edits and self-writes

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": tool,
        "path": rel,
        "head": _git_head(),
    }
    try:
        with open(LEDGER, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
