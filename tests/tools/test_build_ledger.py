"""Append-only guard for scripts/build_ledger.py (LEDGER.md generator).

Incident this guards against: commit ff68a4b regenerated LEDGER.md and
silently deleted a hand-written block (found by audit, not by any check;
recoverable only because the source paper still existed — see LEDGER.md's
restored "TRACKS moving anchor" section and the commit that restored it,
b186ff1). REGISTRY.jsonl and VERSION_LEDGER.jsonl are append-only by
construction; LEDGER.md is a full from-scratch rewrite every run and so had
no such property.

These tests run the real script as a subprocess against a throwaway repo
layout (a copy of build_ledger.py plus fixture LEDGER_DATA.json /
VERSION_LEDGER.jsonl / LEDGER.md under tmp_path) so nothing here ever touches
the real repo's ledger files, and the guard is proven by actually running the
generator and inspecting its exit code, stderr, and the file it did or didn't
write — not by asserting against its source.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT_SRC = os.path.join(REPO, "scripts", "build_ledger.py")

BASE_DATA = {
    "incidents": [
        {"date": "2026-01-01", "id": "inc-a", "note": "first incident"},
        {"date": "2026-01-02", "id": "inc-b", "note": "second incident"},
    ],
    "architectures": [
        {
            "version": "v1",
            "location": "repo root",
            "marker": "tag v1",
            "driving_directive": "founding",
            "audit": "PASS",
        },
    ],
    "instances": [
        {
            "name": "corpus-a",
            "architecture": "v1",
            "corpus": "test corpus",
            "location": "instantiations/corpus-a/",
            "world_content_hash": "deadbeef0000",
            "world_M": 3,
            "lambda": {"T2": 1.0},
            "gates": "PASS",
            "renders": "n/a",
        },
    ],
}

TRAIL_LINES = [
    {"ts": "2026-01-01T00:00:00+00:00", "tool": "Write", "path": "a.py", "head": "h1"},
    {"ts": "2026-01-01T00:01:00+00:00", "tool": "Write", "path": "b.py", "head": "h1"},
    {"ts": "2026-01-02T00:00:00+00:00", "tool": "Edit", "path": "c.py", "head": "h2"},
]


def _make_repo(tmp_path, data=None, trail=None):
    """Lay out a throwaway {tmp_path}/scripts/build_ledger.py + data files
    mirroring the real repo's root, so the script's own REPO/DATA/TRAIL/OUT
    resolution (two dirs up from its own path) lands inside tmp_path."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    shutil.copy(SCRIPT_SRC, scripts_dir / "build_ledger.py")
    (tmp_path / "LEDGER_DATA.json").write_text(
        json.dumps(data if data is not None else BASE_DATA, indent=2))
    lines = trail if trail is not None else TRAIL_LINES
    (tmp_path / "VERSION_LEDGER.jsonl").write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in lines) + ("\n" if lines else ""))
    return scripts_dir / "build_ledger.py"


def _run(script_path):
    return subprocess.run([sys.executable, str(script_path)],
                          capture_output=True, text=True, timeout=30)


def test_first_run_creates_ledger_and_second_run_is_idempotent(tmp_path):
    script = _make_repo(tmp_path)
    r1 = _run(script)
    assert r1.returncode == 0, (r1.stdout, r1.stderr)
    ledger = tmp_path / "LEDGER.md"
    assert ledger.exists()
    first_text = ledger.read_text()
    assert "inc-a" in first_text and "inc-b" in first_text
    assert "corpus-a" in first_text
    assert "### at `h1`" in first_text and "### at `h2`" in first_text

    r2 = _run(script)
    assert r2.returncode == 0, (r2.stdout, r2.stderr)
    assert ledger.read_text() == first_text, "unchanged inputs must regenerate byte-identical output"


def test_hand_written_section_survives_regeneration(tmp_path):
    """The actual fix for item 3's root cause: a `## ` section this generator
    does not produce must be carried forward, not erased, on the next run."""
    script = _make_repo(tmp_path)
    assert _run(script).returncode == 0
    ledger = tmp_path / "LEDGER.md"
    foreign_block = (
        "\n## 2026-01-03 — a hand-written note (not in LEDGER_DATA.json)\n\n"
        "- this line only exists because someone hand-wrote it directly into "
        "LEDGER.md, the same way the TRACKS moving anchor block did\n"
    )
    ledger.write_text(ledger.read_text() + foreign_block)
    before = ledger.read_text()

    r = _run(script)
    assert r.returncode == 0, (r.stdout, r.stderr)
    after = ledger.read_text()
    assert "## 2026-01-03 — a hand-written note" in after
    assert "this line only exists because someone hand-wrote it" in after
    # idempotent once the foreign section is present too
    assert _run(script).returncode == 0
    assert ledger.read_text() == after


def test_guard_aborts_when_an_incident_row_is_removed_from_input(tmp_path):
    """Construct the exact failure: current LEDGER.md has both incidents;
    LEDGER_DATA.json is then edited to drop one, which would make the whole
    Incidents section (in this fixture, since it goes to zero rows) vanish on
    regeneration. The guard must abort instead of writing."""
    script = _make_repo(tmp_path)
    assert _run(script).returncode == 0
    ledger = tmp_path / "LEDGER.md"
    before = ledger.read_text()
    assert "Incidents (fabrication-class, on the record)" in before

    trimmed = json.loads(json.dumps(BASE_DATA))
    trimmed["incidents"] = []
    (tmp_path / "LEDGER_DATA.json").write_text(json.dumps(trimmed, indent=2))

    r = _run(script)
    assert r.returncode == 1, (r.stdout, r.stderr)
    assert "DROP" in r.stderr
    assert "Incidents (fabrication-class, on the record)" in r.stderr
    assert ledger.read_text() == before, "a rejected regeneration must not touch the file"


def test_guard_aborts_when_a_trail_head_group_is_removed_from_input(tmp_path):
    """Same shape, at row granularity inside the auto per-edit trail: a
    head-group with a single line disappearing from VERSION_LEDGER.jsonl must
    abort the write rather than silently drop `### at `h2``."""
    script = _make_repo(tmp_path)
    assert _run(script).returncode == 0
    ledger = tmp_path / "LEDGER.md"
    before = ledger.read_text()
    assert "### at `h2`" in before

    trimmed_trail = [e for e in TRAIL_LINES if e["head"] != "h2"]
    (tmp_path / "VERSION_LEDGER.jsonl").write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in trimmed_trail) + "\n")

    r = _run(script)
    assert r.returncode == 1, (r.stdout, r.stderr)
    assert "DROP" in r.stderr
    assert "at `h2`" in r.stderr
    assert ledger.read_text() == before, "a rejected regeneration must not touch the file"


def test_guard_recovers_once_input_is_restored(tmp_path):
    """After a rejected regeneration, restoring the original input must let a
    normal regeneration succeed again (this is the exact restore-and-retry
    flow an operator would use after the guard fires)."""
    script = _make_repo(tmp_path)
    assert _run(script).returncode == 0
    ledger = tmp_path / "LEDGER.md"
    original = ledger.read_text()

    trimmed = json.loads(json.dumps(BASE_DATA))
    trimmed["incidents"] = []          # drop to zero rows: the whole section vanishes
    (tmp_path / "LEDGER_DATA.json").write_text(json.dumps(trimmed, indent=2))
    assert _run(script).returncode == 1
    assert ledger.read_text() == original

    (tmp_path / "LEDGER_DATA.json").write_text(json.dumps(BASE_DATA, indent=2))
    r = _run(script)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert ledger.read_text() == original


def test_engine_edit_disclosures_key_is_rendered(tmp_path):
    """LEDGER_DATA.json's engine_edit_disclosures key must render into its
    own section instead of requiring a hand-written block (item 3)."""
    data = json.loads(json.dumps(BASE_DATA))
    data["engine_edit_disclosures"] = [
        {"date": "2026-01-04", "id": "disc-a", "note": "an undisclosed engine edit, on the record"},
    ]
    script = _make_repo(tmp_path, data=data)
    r = _run(script)
    assert r.returncode == 0, (r.stdout, r.stderr)
    text = (tmp_path / "LEDGER.md").read_text()
    assert "## Engine-edit disclosures (undisclosed-at-landing, on the record)" in text
    assert "disc-a" in text
    assert "an undisclosed engine edit, on the record" in text
