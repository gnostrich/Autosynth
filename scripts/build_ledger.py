#!/usr/bin/env python3
"""Compose LEDGER.md — the both-axes versioning ledger. DOCUMENTS ONLY.

Two inputs, one output:
  LEDGER_DATA.json     curated both-axes facts (architecture entries + instance
                       entries: world hash, LAMBDA, gates, renders)
  VERSION_LEDGER.jsonl the append-only per-edit trail (written by the every-edit
                       PostToolUse hook, scripts/ledger_hook.py)
  -> LEDGER.md         human-readable ledger: architecture table, instances per
                       architecture, and the per-edit trail.

This never builds or audits and never edits code — it only renders a document.
The hook calls it after each edit so LEDGER.md tracks BOTH axes at every edit.

APPEND-ONLY GUARD (2026-08-14, ops incident: commit ff68a4b silently deleted a
hand-written LEDGER.md block on regeneration; found by audit, not by any
check). LEDGER.md is regenerated from scratch every run, but parts of it have
always been hand-written directly into the file (dated notes such as the
"TRACKS moving anchor" capture, or a disclosures section added before this
generator learned to render it) because they don't yet have a home in
LEDGER_DATA.json. A plain from-scratch rewrite destroys those the moment
someone reruns the generator. Two layers fix that:

  1. CARRY FORWARD: any top-level (`## `) section already present in the
     current LEDGER.md whose heading this generator does not itself produce
     is copied into the new output verbatim, after the generated sections.
     This is the actual fix for "hand-written sections destroyed by
     regeneration" — the generator becomes append-only for content it
     doesn't understand, instead of erasing it.
  2. GUARD: as a backstop for whatever the carry-forward step doesn't catch
     (a heading text edited out from under it, a future bug), the final
     composed text is diffed against the current file at two structural
     granularities before anything is written:
       - every `## ` heading present before must be present after;
       - inside "Per-edit trail (auto, append-only)", every `### at
         \\`<head>\\`` sub-heading present before must be present after (this
         section's rows come from the append-only VERSION_LEDGER.jsonl, so a
         head-group vanishing is a real regression, not an editorial choice).
     A miss aborts the write with a message naming exactly what would have
     been lost. Table rows / bullet items inside a surviving section are NOT
     diffed line-by-line: LEDGER_DATA.json is hand-curated prose that can be
     legitimately reworded in place, and word-level diffing of prose can't
     tell an edit from a delete-and-recreate without a stable per-row id
     that doesn't exist here. Structural (heading-level) identity is what the
     incident actually broke and what the guard can check without guessing
     at prose semantics.
"""
from __future__ import annotations
import json
import os
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "LEDGER_DATA.json")
TRAIL = os.path.join(REPO, "VERSION_LEDGER.jsonl")
OUT = os.path.join(REPO, "LEDGER.md")

TRAIL_HEADING = "Per-edit trail (auto, append-only)"

# Every heading this generator is authoritative for. Used two ways: (a) to
# decide which existing "## " sections in the current LEDGER.md are "foreign"
# (hand-written / not yet data-driven) and so must be carried forward
# verbatim rather than silently dropped; (b) as documentation of what a
# regeneration is actually allowed to regenerate.
GENERATED_HEADINGS = {
    "Incidents (fabrication-class, on the record)",
    "Engine-edit disclosures (undisclosed-at-landing, on the record)",
    "Axis 1 — architecture / implementation versions",
    "Axis 2 — instances (corpus → trained model), per architecture",
    TRAIL_HEADING,
}


class LedgerRegressionError(RuntimeError):
    """Regeneration would drop something present in the current LEDGER.md.
    Raised in place of writing the file — the caller must not write on this
    path."""


def _lam(d: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in d.items())


def _h2_sections(text: str) -> dict[str, str]:
    """Map each top-level (`## `) heading in a LEDGER.md-shaped document to
    its full body text (from that heading line through, but not including,
    the next `## ` heading or EOF). Order of first appearance is preserved
    via dict insertion order. Used only for the carry-forward/guard checks
    below — never for anything that feeds back into rendered content."""
    sections: dict[str, list[str]] = {}
    current = None
    for ln in text.split("\n"):
        if ln.startswith("## "):
            current = ln[3:].strip()
            sections.setdefault(current, [])
        if current is not None:
            sections[current].append(ln)
    return {k: "\n".join(v).rstrip("\n") for k, v in sections.items()}


def _h3_subheadings(section_body: str) -> set[str]:
    return {ln[4:].strip() for ln in section_body.split("\n") if ln.startswith("### ")}


def check_append_only(old_text: str, new_text: str) -> None:
    """Raise LedgerRegressionError if `new_text` would, on write, drop a
    section or per-edit-trail row that `old_text` has. Never mutates
    anything; the caller decides what to do with the exception (abort the
    write)."""
    old_sections = _h2_sections(old_text)
    new_sections = _h2_sections(new_text)

    missing_sections = [h for h in old_sections if h not in new_sections]
    if missing_sections:
        raise LedgerRegressionError(
            "build_ledger: refusing to write LEDGER.md — regeneration would "
            f"DROP the following section(s) present in the current file: "
            f"{missing_sections!r}. Aborting write; nothing was overwritten. "
            "If this section is hand-written and not yet in LEDGER_DATA.json, "
            "it should have been carried forward automatically — this is a "
            "generator bug, not an expected outcome. Restore the section by "
            "hand and/or fix the carry-forward step before rerunning."
        )

    if TRAIL_HEADING in old_sections and TRAIL_HEADING in new_sections:
        old_heads = _h3_subheadings(old_sections[TRAIL_HEADING])
        new_heads = _h3_subheadings(new_sections[TRAIL_HEADING])
        missing_heads = sorted(old_heads - new_heads)
        if missing_heads:
            raise LedgerRegressionError(
                "build_ledger: refusing to write LEDGER.md — regeneration "
                "would DROP the following per-edit-trail block(s) "
                f"(`### at ...`) present in the current file: "
                f"{missing_heads!r}. Aborting write; nothing was overwritten. "
                "VERSION_LEDGER.jsonl is append-only, so a head-group that "
                "existed before must still exist after — check whether "
                "VERSION_LEDGER.jsonl itself lost lines."
            )


def _carry_forward_foreign_sections(old_text: str | None) -> list[str]:
    """Return, verbatim, the text of every `## ` section in the current
    LEDGER.md that this generator does not itself produce (hand-written
    notes, or data-file keys the generator hasn't learned to render yet).
    Preserves their relative order. Empty list if there is no prior file or
    it has no such sections."""
    if not old_text:
        return []
    out: list[str] = []
    for heading, body in _h2_sections(old_text).items():
        if heading not in GENERATED_HEADINGS:
            out.append(body)
    return out


def build(old_text: str | None = None) -> str:
    data = json.load(open(DATA, encoding="utf-8"))
    lines = []
    lines.append("# LEDGER — both-axes versioning record")
    lines.append("")
    lines.append("Auto-generated by `scripts/build_ledger.py` (documents only; never "
                 "builds or audits). Curated facts live in `LEDGER_DATA.json`; the "
                 "per-edit trail is appended by the every-edit hook "
                 "(`scripts/ledger_hook.py` → `VERSION_LEDGER.jsonl`). Two axes: "
                 "**architecture/implementation versions** and the **instances** "
                 "(corpus/genre trained models) under each.")
    lines.append("")

    # --- Incidents (fabrication-class remediations, on the record) ---
    incidents = data.get("incidents", [])
    if incidents:
        lines.append("## Incidents (fabrication-class, on the record)")
        lines.append("")
        for inc in incidents:
            lines.append(f"- **{inc.get('date','')} — {inc.get('id','')}**: "
                         f"{inc.get('note','')}")
        lines.append("")

    # --- Engine-edit disclosures (undisclosed-at-landing, on the record) ---
    disclosures = data.get("engine_edit_disclosures", [])
    if disclosures:
        lines.append("## Engine-edit disclosures (undisclosed-at-landing, on the record)")
        lines.append("")
        for d in disclosures:
            lines.append(f"- **{d.get('date','')} — {d.get('id','')}**: "
                         f"{d.get('note','')}")
        lines.append("")

    # --- Axis 1: architecture versions ---
    lines.append("## Axis 1 — architecture / implementation versions")
    lines.append("")
    lines.append("| Version | Location | Marker | Driving directive | Audit |")
    lines.append("|---|---|---|---|---|")
    for a in data.get("architectures", []):
        lines.append(f"| **{a['version']}** | {a['location']} | {a['marker']} | "
                     f"{a['driving_directive']} | {a['audit']} |")
    lines.append("")

    # --- Axis 2: instances, grouped under their architecture ---
    lines.append("## Axis 2 — instances (corpus → trained model), per architecture")
    lines.append("")
    by_arch = defaultdict(list)
    for i in data.get("instances", []):
        by_arch[i["architecture"]].append(i)
    for arch in by_arch:
        lines.append(f"### under {arch}")
        lines.append("")
        for i in by_arch[arch]:
            lines.append(f"- **{i['name']}** — corpus: {i['corpus']}")
            if i.get("role"):
                lines.append(f"  - role: {i['role']}")
            lines.append(f"  - location: {i['location']}")
            lines.append(f"  - world: content-hash `{i['world_content_hash']}`, "
                         f"M={i['world_M']} anchors")
            lines.append(f"  - LAMBDA: {_lam(i['lambda'])}")
            lines.append(f"  - gates: {i['gates']}")
            lines.append(f"  - renders: {i['renders']}")
        lines.append("")

    # --- per-edit trail (auto) ---
    lines.append("## Per-edit trail (auto, append-only)")
    lines.append("")
    lines.append("Every tracked-file edit, newest last, grouped by the git HEAD it "
                 "was made against. Notes (pivots, renames) are interleaved.")
    lines.append("")
    entries = []
    if os.path.exists(TRAIL):
        for ln in open(TRAIL, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                entries.append(json.loads(ln))
            except Exception:
                continue
    by_head = defaultdict(list)
    order = []
    for e in entries:
        h = e.get("head", "?")
        if h not in by_head:
            order.append(h)
        by_head[h].append(e)
    for h in order:
        lines.append(f"### at `{h}`")
        for e in by_head[h]:
            ts = e.get("ts", "")
            if e.get("tool") in ("note", "genesis"):
                lines.append(f"- _{e.get('tool')}_ ({ts}): {e.get('note', '')}")
            else:
                lines.append(f"- `{e.get('tool')}` {e.get('path','')} ({ts})")
        lines.append("")

    md = "\n".join(lines).rstrip() + "\n"

    # --- carry forward anything hand-written this generator doesn't produce ---
    foreign = _carry_forward_foreign_sections(old_text)
    if foreign:
        md = md.rstrip("\n") + "\n\n" + "\n\n".join(s.rstrip("\n") for s in foreign) + "\n"

    return md


def main() -> int:
    old_text = None
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as fh:
                old_text = fh.read()
        except Exception:
            old_text = None

    try:
        md = build(old_text)
    except Exception as exc:            # never break a caller (e.g. the hook)
        print(f"build_ledger: {exc}", file=sys.stderr)
        return 0

    if old_text is not None:
        try:
            check_append_only(old_text, md)
        except LedgerRegressionError as exc:
            print(str(exc), file=sys.stderr)
            return 1                    # hard abort: do NOT write

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
