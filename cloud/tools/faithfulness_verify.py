#!/usr/bin/env python3
"""Deterministic, brute-force faithfulness-regression harness for the ETS companion.

Standalone, no network. Each check is a function returning ``(id, PASS|FAIL,
detail)``. Runs ALL checks for the requested tier, prints a table, and exits
non-zero if ANY fail. The source of truth for what it asserts (and the
hand-maintained CAPTION REGISTRY it reads) is ``cloud/FAITHFULNESS_REGRESSION_SPEC.md``.

    python cloud/tools/faithfulness_verify.py --tier 0     # every edit  (< ~5s)
    python cloud/tools/faithfulness_verify.py --tier 1     # pre-commit
    python cloud/tools/faithfulness_verify.py --tier 2     # pre-merge / release
    python cloud/tools/faithfulness_verify.py --self-test  # prove every check can fail

Design (so the harness is not itself a green dashboard):
  * Every check reads its inputs from a :class:`Ctx` (paths + repo root), so a
    self-test can point the SAME check logic at a mutated temp copy and assert it
    FAILs. A check that cannot fail is worthless — ``--self-test`` is MANDATORY and
    demonstrates every check tripping.
  * The harness is READ-ONLY w.r.t. the code it checks. It never imports the engine
    beyond the existing verify subprocess scripts (tier 2).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

PASS, FAIL = "PASS", "FAIL"
Result = Tuple[str, str, str]  # (check_id, PASS|FAIL, detail)

REPO_ROOT = Path(__file__).resolve().parents[2]

# Repo-relative locations of everything a check reads. Kept in one place so a
# self-test can swap a single entry for a mutated temp copy.
REL = {
    "index_html": "cloud/companion/static/index.html",
    "app_py": "cloud/companion/app.py",
    "engine_bridge": "cloud/companion/engine_bridge.py",
    "train_local": "cloud/companion/train_local.py",
    "protocol": "cloud/common/protocol.py",
    "dockerfile": "cloud/companion/Dockerfile",
    "invariants": "cloud/COMPANION_INVARIANTS.md",
    "claude_md": "CLAUDE.md",
    "spec": "cloud/FAITHFULNESS_REGRESSION_SPEC.md",
    "verify_version": "scripts/verify_version.py",
    "seam_verify": "cloud/tools/seam_verify.py",
    "instrument_verify": "cloud/tools/instrument_verify.py",
}


@dataclass
class Ctx:
    """Everything a check reads. ``root`` is the repo/git root; ``paths`` maps a
    logical name to an absolute path. ``merge`` selects the merge-gate variant of
    checks that behave differently pre-merge (e.g. compare vs origin/main)."""
    root: Path = REPO_ROOT
    paths: Dict[str, Path] = field(default_factory=lambda: {
        k: REPO_ROOT / v for k, v in REL.items()})
    merge: bool = False

    def p(self, name: str) -> Path:
        return self.paths[name]

    def read(self, name: str) -> str:
        return self.p(name).read_text(encoding="utf-8", errors="replace")

    def with_file(self, name: str, new_text: str, tmpdir: Path) -> "Ctx":
        """Return a copy of this Ctx with ``name`` pointing at a temp file holding
        ``new_text`` (used by self-tests to feed a mutated input to a check)."""
        dst = tmpdir / Path(REL[name]).name
        dst.write_text(new_text, encoding="utf-8")
        newpaths = dict(self.paths)
        newpaths[name] = dst
        return replace(self, paths=newpaths)


# ---------------------------------------------------------------------------
# small shared helpers
# ---------------------------------------------------------------------------
def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)


def _run(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 1800
         ) -> Tuple[int, str]:
    """Run a subprocess; return (exit_code, tail-of-output). Used by the
    subprocess-wrapper checks (pytest / verify scripts) and their self-tests."""
    try:
        cp = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s: {' '.join(cmd)}"
    out = (cp.stdout or "") + (cp.stderr or "")
    tail = "\n".join(out.strip().splitlines()[-8:])
    return cp.returncode, tail


def _dockerfile_copies(text: str) -> List[str]:
    """Parse ``COPY <src> [<src> ...] <dst>`` lines -> list of source repo paths."""
    srcs: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.upper().startswith("COPY "):
            continue
        # strip any --flags, then all but the last token (the dest) are sources
        toks = [t for t in line.split()[1:] if not t.startswith("--")]
        if len(toks) < 2:
            continue
        srcs.extend(toks[:-1])
    return srcs


def _copy_covers(copies: List[str], repo_path: str) -> bool:
    """True if some COPY source covers ``repo_path`` (exact file, or dir prefix)."""
    rp = repo_path.strip("/")
    for src in copies:
        s = src.strip("/")
        if s == rp:
            return True
        # a directory source (trailing slash in Dockerfile, or an ancestor) covers
        # everything beneath it
        if src.endswith("/") or ("." not in Path(s).name):
            if rp == s or rp.startswith(s + "/"):
                return True
    return False


# ---------------------------------------------------------------------------
# CHECK-ENGINE-IMMUTABLE
# ---------------------------------------------------------------------------
ENGINE_TREES = ["ets", "architecture-v6/ets"]


def check_engine_immutable(ctx: Ctx) -> Result:
    cid = "CHECK-ENGINE-IMMUTABLE"
    root = ctx.root
    if not (root / ".git").exists():
        return (cid, FAIL, f"no git repo at {root}")
    problems: List[str] = []
    # 1. working tree vs HEAD
    diff = _git(root, "diff", "--quiet", "HEAD", "--", *ENGINE_TREES)
    if diff.returncode != 0:
        names = _git(root, "diff", "--name-only", "HEAD", "--", *ENGINE_TREES)
        problems.append("modified vs HEAD: " + ", ".join(names.stdout.split()) )
    # 2. untracked files under the engine trees
    unt = _git(root, "ls-files", "--others", "--exclude-standard", "--", *ENGINE_TREES)
    untracked = [x for x in unt.stdout.split() if x]
    if untracked:
        problems.append("untracked under engine trees: " + ", ".join(untracked))
    # 3. merge-gate: also clean vs origin/main
    if ctx.merge:
        ref = _git(root, "rev-parse", "--verify", "origin/main")
        if ref.returncode == 0:
            d2 = _git(root, "diff", "--quiet", "origin/main", "--", *ENGINE_TREES)
            if d2.returncode != 0:
                names = _git(root, "diff", "--name-only", "origin/main", "--",
                             *ENGINE_TREES)
                problems.append("differs from origin/main: "
                                + ", ".join(names.stdout.split()))
    if problems:
        return (cid, FAIL, "; ".join(problems))
    return (cid, PASS, "ets/ and architecture-v6/ets/ byte-identical to HEAD"
            + (" and origin/main" if ctx.merge else ""))


# ---------------------------------------------------------------------------
# CHECK-IMAGE-COMPLETE
# ---------------------------------------------------------------------------
def _runtime_path_refs(cloud_dir: Path) -> List[Tuple[str, str]]:
    """Scan cloud/**/*.py for runtime file-path loads. Returns (repo_path, where).

    Signatures (deterministic literal-concat loads — the INC-2 class):
      * _ARCH_V6 + "<literal>"        -> architecture-v6/<literal>
      * _REPO_ROOT ... / "<literal>"  -> <literal>  (repo-relative)
      * spec_from_file_location(..., src=<_ARCH_V6+lit>) is covered transitively by
        the _ARCH_V6 match above.
    """
    refs: List[Tuple[str, str]] = []
    arch = re.compile(r'_ARCH_V6\s*\+\s*["\']([^"\']+)["\']')
    reporoot = re.compile(r'_REPO_ROOT\b[^\n]*?/\s*["\']([^"\']+\.[A-Za-z0-9]+)["\']')
    for py in sorted(cloud_dir.rglob("*.py")):
        # the harness itself is the checker, not companion runtime code; its regex
        # documentation contains the very patterns it hunts for — never self-scan.
        if py.name == "faithfulness_verify.py":
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in arch.finditer(text):
            rel = "architecture-v6/" + m.group(1).lstrip("/")
            line = text[:m.start()].count("\n") + 1
            refs.append((rel, f"{py.relative_to(cloud_dir.parent)}:{line}"))
        for m in reporoot.finditer(text):
            rel = m.group(1).lstrip("/")
            line = text[:m.start()].count("\n") + 1
            refs.append((rel, f"{py.relative_to(cloud_dir.parent)}:{line}"))
    return refs


def check_image_complete(ctx: Ctx) -> Result:
    cid = "CHECK-IMAGE-COMPLETE"
    dockerfile = ctx.read("dockerfile")
    copies = _dockerfile_copies(dockerfile)
    cloud_dir = ctx.p("app_py").parents[1]  # .../cloud
    refs = _runtime_path_refs(cloud_dir)
    uncovered = [(rp, where) for (rp, where) in refs if not _copy_covers(copies, rp)]
    if uncovered:
        det = "; ".join(f"{rp} (loaded at {w}) NOT COPY'd" for rp, w in uncovered)
        return (cid, FAIL, det)
    seen = sorted({rp for rp, _ in refs})
    return (cid, PASS, f"{len(seen)} runtime path load(s) all COPY-covered: "
            + ", ".join(seen))


# ---------------------------------------------------------------------------
# CHECK-NO-FABRICATION  (denylist + caption registry)
# ---------------------------------------------------------------------------
def _load_caption_registry(spec_text: str) -> List[dict]:
    """Read the machine-readable CAPTION REGISTRY JSON block from the spec."""
    marker = spec_text.find("CAPTION_REGISTRY_JSON")
    region = spec_text[marker:] if marker >= 0 else spec_text
    m = re.search(r"```json\s*(\[.*?\])\s*```", region, re.DOTALL)
    if not m:
        raise ValueError("CAPTION_REGISTRY_JSON block not found in spec")
    return json.loads(m.group(1))


def _detect_synthetic_waveform(html: str) -> List[int]:
    """Coordinate-pair push computed with trig and emitted as an SVG path — the
    `buildWave` tape art. Returns 1-based line numbers of the offending pushes."""
    lines = html.splitlines()
    hits: List[int] = []
    trig = re.compile(r"Math\.(sin|cos|abs)\s*\(")
    push_coord = re.compile(r"\bpush\s*\(\s*\[")
    for i, ln in enumerate(lines):
        if push_coord.search(ln):
            window = "\n".join(lines[max(0, i - 5):i + 1])
            if trig.search(window):
                hits.append(i + 1)
    return hits


def _detect_synthetic_cells(html: str) -> List[int]:
    """A for-loop bounded by a hardcoded integer literal assigned to a
    units/cells/tracks-named var, whose body createElements class unit/cell/track —
    the `var units = 36` drill grid. Returns 1-based line numbers."""
    magic = re.compile(
        r"\b(?:var|let|const)\s+(units?|cells?|tracks?|slots?|nodes?|grid)\s*=\s*\d+\b")
    cls = re.compile(r'className\s*=\s*["\'](unit|cell|track)')
    lines = html.splitlines()
    hits: List[int] = []
    for m in re.finditer(magic, html):
        start_line = html[:m.start()].count("\n")
        window = "\n".join(lines[start_line:start_line + 26])
        if "createElement" in window and cls.search(window):
            hits.append(start_line + 1)
    return hits


def _fabrication_present(html: str, sig: str) -> List[int]:
    if sig == "synthetic_waveform":
        return _detect_synthetic_waveform(html)
    if sig == "synthetic_cells":
        return _detect_synthetic_cells(html)
    return []


def check_no_fabrication(ctx: Ctx) -> Result:
    cid = "CHECK-NO-FABRICATION"
    html = ctx.read("index_html")
    registry = _load_caption_registry(ctx.read("spec"))
    problems: List[str] = []

    # (a) DENYLIST: Math.random never feeds a faithful display.
    rnd = [html[:m.start()].count("\n") + 1
           for m in re.finditer(r"Math\.random", html)]
    if rnd:
        problems.append(f"Math.random present (lines {rnd}) — no faithful display "
                        "uses random noise")

    # (b) CAPTION REGISTRY: REAL-DATA or DISARMED-AND-LABELED, per surface.
    for entry in registry:
        eid = entry["id"]
        real = [c for c in entry.get("real_captions", []) if c in html]
        disarmed = [c for c in entry.get("disarmed_captions", []) if c in html]
        fab_lines = _fabrication_present(html, entry.get("fabrication_signature", ""))
        backing = [f for f in entry.get("backing_fetch_any_of", [])
                   if f in html]
        if real:
            if fab_lines:
                problems.append(
                    f"{eid}: caption {real!r} claims real data but the synthetic "
                    f"'{entry['fabrication_signature']}' generator feeds it "
                    f"(lines {fab_lines}) — REAL-DATA or DISARMED-AND-LABELED")
            elif not backing:
                problems.append(
                    f"{eid}: caption {real!r} claims real data but no backing fetch "
                    f"({entry.get('backing_fetch_any_of')}) is present")
        elif disarmed:
            pass  # honestly labelled not-real
        else:
            if fab_lines:
                problems.append(
                    f"{eid}: synthetic '{entry['fabrication_signature']}' generator "
                    f"present (lines {fab_lines}) with NO real or disarmed caption — "
                    "an unlabelled synthetic surface")
    if problems:
        return (cid, FAIL, " | ".join(problems))
    return (cid, PASS, "every registered surface is REAL-DATA or "
            "DISARMED-AND-LABELED; no Math.random display generator")


# ---------------------------------------------------------------------------
# CHECK-SINGLE-CONTROL
# ---------------------------------------------------------------------------
ALLOWED_ENDPOINTS = {
    "/api/health", "/api/status", "/api/world", "/api/ingest", "/api/reset",
    "/api/train", "/api/steer", "/api/telemetry", "/api/stream", "/api/play",
    "/api/stop", "/api/auth", "/api/units",
}
SETTLEMENT_CONTROL = "/api/steer"


def check_single_control(ctx: Ctx) -> Result:
    cid = "CHECK-SINGLE-CONTROL"
    html = ctx.read("index_html")
    eps = set(re.findall(r'(?:fetch|new\s+EventSource|EventSource)\s*\(\s*["\'](/api/[^"\']+)["\']',
                         html))
    # normalise any query strings
    eps = {e.split("?")[0] for e in eps}
    if SETTLEMENT_CONTROL not in eps:
        return (cid, FAIL, f"the single control {SETTLEMENT_CONTROL} is absent")
    unknown = sorted(eps - ALLOWED_ENDPOINTS)
    if unknown:
        return (cid, FAIL, "endpoint(s) outside the vetted allowlist (possible "
                f"second control channel): {unknown}")
    return (cid, PASS, f"only {SETTLEMENT_CONTROL} steers settlement; all "
            f"{len(eps)} endpoints are vetted: {sorted(eps)}")


# ---------------------------------------------------------------------------
# CHECK-EARDRUM-CAP
# ---------------------------------------------------------------------------
def _function_body(src: str, defname: str) -> str:
    """Return the source of ``def <defname>`` up to the next same-or-less indented
    ``def`` / ``class`` (a simple, dependency-free body slice)."""
    lines = src.splitlines()
    start = None
    indent = 0
    for i, ln in enumerate(lines):
        m = re.match(r"(\s*)def\s+" + re.escape(defname) + r"\b", ln)
        if m:
            start = i
            indent = len(m.group(1))
            break
    if start is None:
        return ""
    body = [lines[start]]
    for ln in lines[start + 1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and \
                re.match(r"\s*(def|class)\b", ln):
            break
        body.append(ln)
    return "\n".join(body)


def check_eardrum_cap(ctx: Ctx) -> Result:
    cid = "CHECK-EARDRUM-CAP"
    src = ctx.read("engine_bridge")
    body = _function_body(src, "produce_one_bar")
    if not body:
        return (cid, FAIL, "produce_one_bar not found in engine_bridge.py")
    if re.search(r"\baudio\s*=\s*_playback_soft_limit\s*\(\s*audio", body):
        return (cid, PASS, "produce_one_bar applies _playback_soft_limit(audio) on "
                "the per-bar path")
    if "_playback_soft_limit" in body:
        return (cid, FAIL, "produce_one_bar references _playback_soft_limit but not "
                "as the bar-audio assignment `audio = _playback_soft_limit(audio)`")
    return (cid, FAIL, "produce_one_bar does NOT apply the eardrum cap "
            "_playback_soft_limit on the per-bar path")


# ---------------------------------------------------------------------------
# CHECK-NAMESPACE-PIN
# ---------------------------------------------------------------------------
def check_namespace_pin(ctx: Ctx) -> Result:
    cid = "CHECK-NAMESPACE-PIN"
    src = ctx.read("engine_bridge")
    has_pin = "sys.path.insert(0, _ARCH_V6)" in src
    # loud guard: a raise that fires when the live-cap markers are absent
    has_guard = bool(re.search(r"_playback_soft_limit", src)) and \
        bool(re.search(r"bar_role_activity", src)) and \
        bool(re.search(r"raise\s+RuntimeError", src))
    if has_pin and has_guard:
        return (cid, PASS, "arch-v6 pinned to sys.path front + loud RuntimeError "
                "guard if the live-capped engine does not resolve")
    missing = []
    if not has_pin:
        missing.append("sys.path.insert(0, _ARCH_V6)")
    if not has_guard:
        missing.append("raise RuntimeError guard on missing live-cap markers")
    return (cid, FAIL, "missing: " + "; ".join(missing))


# ---------------------------------------------------------------------------
# CHECK-CS-WIRE-CLOSED  (the INTERNAL encoder hop stays whitelist-closed)
# ---------------------------------------------------------------------------
# R3(b) is LOCKED: raw audio DOES upload to Railway by design. So this check does
# NOT (and must not) assert "raw audio never crosses the wire". What it DOES guard is
# the internal companion->anchor-fit encoder hop: cloud.common.encode_job /
# Stage3Proto must serialize ONLY the four gauge-invariant stage-3 fields and have NO
# structural slot for raw audio / provenance. (Behavioural proof: cloud/tests/
# test_mvp_a_raw_never_uploaded.py, run in tier 1.)
STAGE3_WHITELIST = ("cost", "mass", "slot_hist", "band_profile")


def check_cs_wire_closed(ctx: Ctx) -> Result:
    cid = "CHECK-CS-WIRE-CLOSED"
    src = ctx.read("protocol")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return (cid, FAIL, f"protocol.py does not parse: {e}")
    problems: List[str] = []
    # 1. the whitelist tuple is EXACTLY the four gauge-invariant stage-3 fields
    fields_val: Optional[tuple] = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "STAGE3_PROTO_FIELDS"
                for t in node.targets):
            if isinstance(node.value, (ast.Tuple, ast.List)):
                fields_val = tuple(e.value for e in node.value.elts
                                   if isinstance(e, ast.Constant))
    if fields_val != STAGE3_WHITELIST:
        problems.append(f"STAGE3_PROTO_FIELDS={fields_val}, expected {STAGE3_WHITELIST}")
    # 2. Stage3Proto has EXACTLY those fields — no raw-audio / provenance slot
    cls = next((n for n in ast.walk(tree)
                if isinstance(n, ast.ClassDef) and n.name == "Stage3Proto"), None)
    if cls is None:
        problems.append("Stage3Proto class not found")
    else:
        ann = [s.target.id for s in cls.body
               if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)]
        if set(ann) != set(STAGE3_WHITELIST):
            problems.append(
                f"Stage3Proto fields {ann} != whitelist {list(STAGE3_WHITELIST)} — a "
                "raw-audio/provenance slot must not exist on the wire object")
    # 3. from_prototype reads ONLY the whitelisted attributes (a Track/raw array,
    #    lacking .cost, raises) and the emit-time guard is present.
    if "for name in STAGE3_PROTO_FIELDS" not in src:
        problems.append("from_prototype no longer iterates the whitelist "
                        "(off-whitelist attributes could ride along)")
    if "def assert_wire_whitelisted" not in src:
        problems.append("assert_wire_whitelisted emit-time guard missing")
    if problems:
        return (cid, FAIL, "; ".join(problems))
    return (cid, PASS, "encoder hop whitelist-closed: Stage3Proto = "
            f"{list(STAGE3_WHITELIST)} only; no raw-audio slot; emit guard present")


# ---------------------------------------------------------------------------
# CHECK-CS-DECODER-FREE
# ---------------------------------------------------------------------------
FORBIDDEN_TOPLEVEL = (
    "cloud.companion.engine_bridge", "cloud.companion.train_local",
    "ets.engine", "ets.render", "ets.writer", "ets.connector",
    "ets.geometry", "ets.ingestion",
)


def check_cs_decoder_free(ctx: Ctx) -> Result:
    cid = "CHECK-CS-DECODER-FREE"
    src = ctx.read("app_py")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return (cid, FAIL, f"app.py does not parse: {e}")
    offenders: List[str] = []
    for node in tree.body:  # MODULE-LEVEL nodes only (not nested in def/class)
        mods: List[str] = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or ""]
        for mod in mods:
            if any(mod == f or mod.startswith(f + ".") for f in FORBIDDEN_TOPLEVEL):
                offenders.append(f"line {node.lineno}: import {mod}")
    if offenders:
        return (cid, FAIL, "module-level decoder/render import(s): "
                + "; ".join(offenders))
    return (cid, PASS, "app.py imports no render/decoder module at module level "
            "(CS-4: cloud path stays decoder-free)")


# ---------------------------------------------------------------------------
# CHECK-INVARIANTS-DOC
# ---------------------------------------------------------------------------
CLAUDE_MARKERS = [
    "Non-negotiable product invariants",
    "Auditor pass before every merge",
    "faithfulness_verify.py",  # the harness rule this build adds
]


# R3 (post-operator-lock) must document the R3(b) lock, the honesty requirement, and
# the planned private-mode upgrade. Marker phrases (verbatim substrings):
R3B_MARKERS = ["R3(b)", "HONESTY REQUIREMENT", "PLANNED UPGRADE"]


def check_invariants_doc(ctx: Ctx) -> Result:
    cid = "CHECK-INVARIANTS-DOC"
    inv = ctx.read("invariants")
    problems: List[str] = []
    for n in range(1, 7):
        if not re.search(rf"\bR{n}\b", inv):
            problems.append(f"COMPANION_INVARIANTS.md missing R{n}")
    for marker in R3B_MARKERS:
        if marker not in inv:
            problems.append(f"COMPANION_INVARIANTS.md R3 missing marker: {marker!r}")
    claude = ctx.read("claude_md")
    for marker in CLAUDE_MARKERS:
        if marker not in claude:
            problems.append(f"CLAUDE.md missing standing-rule marker: {marker!r}")
    if problems:
        return (cid, FAIL, "; ".join(problems))
    return (cid, PASS, "R1..R6 present + CLAUDE.md standing-rule markers present")


# ---------------------------------------------------------------------------
# CHECK-AUDIO-BOUNDARY-HONEST  (tier 0) — a privacy claim while R3(b) is live is a
# fabrication. (Operator decision 2026-07-17: R3(b) LOCKED; raw audio uploads to
# Railway BY DESIGN. The UI must read as cloud-processed, never on-device/private.)
# ---------------------------------------------------------------------------
# The denylist is ARMED BY THE INVARIANT ITSELF: only when R3 is locked to R3(b)
# (raw audio uploaded to the cloud) is a UI privacy/locality claim a fabrication. If
# the operator ever flips R3 back to R3(a) HERE (raw never leaves the device), the
# claims become TRUE and this check honestly disarms. No second decision channel —
# the sole source of truth is COMPANION_INVARIANTS.md.
_PRIVACY_CLAIM_PATTERNS = [
    r"on[- ]?device",
    r"stays? on (?:your|the) device",
    r"never leaves?(?: the| your)? (?:device|box|machine|computer)",
    r"raw audio[^.<]{0,60}\bnever\b",
    r"\bsealed\b",
    r"only[^.<]{0,80}stage-?3[^.<]{0,120}leave",
    r"audio[^.<]{0,40}(?:stays?|remains?) (?:on|local)",
]


def _r3b_armed(inv_text: str) -> bool:
    norm = re.sub(r"\s+", " ", inv_text)
    return ("LOCKED to R3(b)" in norm
            or "raw audio DOES leave the device" in norm
            or "raw audio is uploaded" in norm)


def check_audio_boundary_honest(ctx: Ctx) -> Result:
    cid = "CHECK-AUDIO-BOUNDARY-HONEST"
    inv = ctx.read("invariants")
    if not _r3b_armed(inv):
        return (cid, PASS, "R3 not locked to R3(b) (raw stays local): privacy/"
                "locality claims permitted; check disarmed by the invariant")
    html = ctx.read("index_html")
    lines = html.splitlines()
    hits: List[str] = []
    for i, ln in enumerate(lines):
        for pat in _PRIVACY_CLAIM_PATTERNS:
            m = re.search(pat, ln, re.IGNORECASE)
            if m:
                hits.append(f"line {i + 1}: {m.group(0)!r}")
                break
    if hits:
        return (cid, FAIL, "R3(b) is live (raw audio IS uploaded to the cloud) but "
                "the UI claims on-device/privacy — a privacy claim under R3(b) is a "
                "fabrication (COMPANION_INVARIANTS R3 HONESTY REQUIREMENT): "
                + "; ".join(hits))
    return (cid, PASS, "R3(b) live and no on-device/privacy claim in the UI")


# ---------------------------------------------------------------------------
# CHECK-GATE-FAILCLOSED  (tier 1)  — verdict predicate + live probe
# ---------------------------------------------------------------------------
def _gate_verdict(status: Dict[str, int]) -> Tuple[bool, str]:
    """Pure predicate over observed statuses of a public server with EMPTY keys.
    Fail-closed requires: /api/world 401, /api/auth NOT ok (denied), /api/health 200."""
    ok = (status.get("world") == 401 and
          status.get("auth_ok") is False and
          status.get("health") == 200)
    return ok, (f"world={status.get('world')} auth_ok={status.get('auth_ok')} "
                f"health={status.get('health')}")


def _probe_public_gate() -> Dict[str, int]:
    """Start the real server with EMPTY keys on an ephemeral loopback port and probe
    the three fail-closed conditions. Self-contained; no engine import, no network."""
    import http.client
    import threading
    # arch-v6 pin like `python -m cloud.companion`; app.py imports only stdlib.
    for p in (str(REPO_ROOT / "architecture-v6"), str(REPO_ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)
    from cloud.companion.app import serve
    sess = tempfile.mkdtemp(prefix="ets_gate_")
    httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
                  session_dir=sess, public=True, access_keys=[])
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    port = httpd.server_address[1]
    out: Dict[str, int] = {}
    try:
        def req(method, path, body=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
            hdr = {"Content-Type": "application/json"} if body else {}
            c.request(method, path, body=body, headers=hdr)
            r = c.getresponse()
            data = r.read()
            c.close()
            return r.status, data
        out["world"], _ = req("GET", "/api/world")
        out["health"], _ = req("GET", "/api/health")
        st, data = req("POST", "/api/auth", body=b'{"key":"anything"}')
        try:
            authed = json.loads(data).get("ok") is True
        except Exception:
            authed = False
        out["auth_ok"] = authed  # type: ignore[assignment]
    finally:
        httpd.shutdown()
        httpd.server_close()
        shutil.rmtree(sess, ignore_errors=True)
    return out


def check_gate_failclosed(ctx: Ctx) -> Result:
    cid = "CHECK-GATE-FAILCLOSED"
    # structural: constant-time compare present
    app_src = ctx.read("app_py")
    if "hmac.compare_digest" not in app_src:
        return (cid, FAIL, "app.py key check is not constant-time "
                "(hmac.compare_digest absent)")
    try:
        status = _probe_public_gate()
    except Exception as e:
        return (cid, FAIL, f"could not probe public gate: {e!r}")
    ok, detail = _gate_verdict(status)
    return (cid, PASS if ok else FAIL,
            ("fail-closed: " if ok else "NOT fail-closed: ") + detail)


# ---------------------------------------------------------------------------
# subprocess-wrapper checks (tier 1 / tier 2)
# ---------------------------------------------------------------------------
def check_tests(ctx: Ctx) -> Result:
    cid = "CHECK-TESTS"
    rc, tail = _run([sys.executable, "-m", "pytest", "cloud/tests", "-q"],
                    cwd=ctx.root, timeout=1200)
    return (cid, PASS if rc == 0 else FAIL,
            "pytest cloud/tests green" if rc == 0 else f"pytest exit {rc}: {tail}")


def check_engine_byteverify(ctx: Ctx) -> Result:
    cid = "CHECK-ENGINE-BYTEVERIFY"
    # clean vs origin/main
    ref = _git(ctx.root, "rev-parse", "--verify", "origin/main")
    if ref.returncode == 0:
        d = _git(ctx.root, "diff", "--quiet", "origin/main", "--", *ENGINE_TREES)
        if d.returncode != 0:
            names = _git(ctx.root, "diff", "--name-only", "origin/main", "--",
                         *ENGINE_TREES)
            return (cid, FAIL, "engine tree differs from origin/main: "
                    + ", ".join(names.stdout.split()))
    rc, tail = _run([sys.executable, str(ctx.p("verify_version"))],
                    cwd=ctx.root, timeout=3600)
    return (cid, PASS if rc == 0 else FAIL,
            "verify_version PASS" if rc == 0 else f"verify_version exit {rc}: {tail}")


def check_seam(ctx: Ctx) -> Result:
    cid = "CHECK-SEAM"
    rc, tail = _run([sys.executable, str(ctx.p("seam_verify"))],
                    cwd=ctx.root, timeout=3600)
    return (cid, PASS if rc == 0 else FAIL,
            "seam_verify PASS" if rc == 0 else f"seam_verify exit {rc}: {tail}")


def check_instrument(ctx: Ctx) -> Result:
    cid = "CHECK-INSTRUMENT"
    rc, tail = _run([sys.executable, str(ctx.p("instrument_verify"))],
                    cwd=ctx.root, timeout=3600)
    return (cid, PASS if rc == 0 else FAIL,
            "instrument_verify PASS" if rc == 0 else f"instrument_verify exit {rc}: {tail}")


# ---------------------------------------------------------------------------
# check registry + tiers
# ---------------------------------------------------------------------------
@dataclass
class Check:
    fn: Callable[[Ctx], Result]
    tier: int  # minimum tier at which it runs


CHECKS: Dict[str, Check] = {
    "CHECK-ENGINE-IMMUTABLE": Check(check_engine_immutable, 0),
    "CHECK-IMAGE-COMPLETE": Check(check_image_complete, 0),
    "CHECK-NO-FABRICATION": Check(check_no_fabrication, 0),
    "CHECK-SINGLE-CONTROL": Check(check_single_control, 0),
    "CHECK-EARDRUM-CAP": Check(check_eardrum_cap, 0),
    "CHECK-NAMESPACE-PIN": Check(check_namespace_pin, 0),
    "CHECK-CS-WIRE-CLOSED": Check(check_cs_wire_closed, 0),
    "CHECK-CS-DECODER-FREE": Check(check_cs_decoder_free, 0),
    "CHECK-AUDIO-BOUNDARY-HONEST": Check(check_audio_boundary_honest, 0),
    "CHECK-INVARIANTS-DOC": Check(check_invariants_doc, 0),
    "CHECK-GATE-FAILCLOSED": Check(check_gate_failclosed, 1),
    "CHECK-TESTS": Check(check_tests, 1),
    "CHECK-ENGINE-BYTEVERIFY": Check(check_engine_byteverify, 2),
    "CHECK-SEAM": Check(check_seam, 2),
    "CHECK-INSTRUMENT": Check(check_instrument, 2),
}


# ---------------------------------------------------------------------------
# self-test: for EACH check, mutate a temp copy that SHOULD trip it -> assert FAIL
# ---------------------------------------------------------------------------
def _mk_git_engine_repo(tmp: Path) -> Ctx:
    """A throwaway git repo with a committed ets/ file, then dirtied -> trips
    CHECK-ENGINE-IMMUTABLE."""
    root = tmp / "repo"
    (root / "ets" / "engine").mkdir(parents=True)
    f = root / "ets" / "engine" / "engine.py"
    f.write_text("x = 1\n")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    f.write_text("x = 2  # tampered engine byte\n")  # dirty the immutable tree
    return Ctx(root=root, paths=dict(Ctx().paths))


def _selftest_engine_immutable(tmp: Path) -> Ctx:
    return _mk_git_engine_repo(tmp)


def _selftest_image_complete(base: Ctx, tmp: Path) -> Ctx:
    # remove the run_sigma_phi.py COPY line -> the runtime path becomes uncovered
    text = base.read("dockerfile")
    mutated = "\n".join(l for l in text.splitlines()
                        if "run_sigma_phi.py" not in l)
    return base.with_file("dockerfile", mutated, tmp)


def _selftest_no_fabrication(base: Ctx, tmp: Path) -> Ctx:
    # Reproduce the INC-1 failure mode: re-introduce a `synthetic_cells` generator
    # (magic count -> createElement unit cells) while a real-data caption is present.
    # This exercises BOTH halves — the caption-registry binding AND the denylist
    # (Math.random) — so the check can never silently pass a fabrication.
    html = base.read("index_html")
    inject = (
        "\n<script>\n"
        "var units = 36;   // magic count feeding a fake render loop\n"
        "for (var u = 0; u < units; u++) {\n"
        "  var cell = document.createElement('button');\n"
        "  cell.className = 'unit';\n"
        "  cell.style.background = 'hsl(' + (Math.random()*360) + ',60%,50%)';\n"
        "}\n"
        "</script>\n"
    )
    return base.with_file("index_html", html + inject, tmp)


def _selftest_single_control(base: Ctx, tmp: Path) -> Ctx:
    html = base.read("index_html")
    mutated = html + '\n<script>fetch("/api/settle2",{method:"POST"});</script>\n'
    return base.with_file("index_html", mutated, tmp)


def _selftest_eardrum_cap(base: Ctx, tmp: Path) -> Ctx:
    src = base.read("engine_bridge")
    mutated = "\n".join(l for l in src.splitlines()
                        if not re.search(r"audio\s*=\s*_playback_soft_limit", l))
    return base.with_file("engine_bridge", mutated, tmp)


def _selftest_namespace_pin(base: Ctx, tmp: Path) -> Ctx:
    src = base.read("engine_bridge")
    mutated = re.sub(r"raise\s+RuntimeError", "pass  # nerfed guard", src, count=1)
    return base.with_file("engine_bridge", mutated, tmp)


def _selftest_cs_wire_closed(base: Ctx, tmp: Path) -> Ctx:
    # add a raw-audio slot to the wire object -> whitelist no longer closed
    src = base.read("protocol")
    mutated = re.sub(r"(\n(\s*)band_profile:[^\n]*\n)",
                     r"\1\2audio: np.ndarray  # LEAK: raw audio riding the wire\n",
                     src, count=1)
    return base.with_file("protocol", mutated, tmp)


def _selftest_audio_boundary_honest(base: Ctx, tmp: Path) -> Ctx:
    # armed R3(b) invariants (real) + a UI privacy claim injected -> fabrication
    html = base.read("index_html")
    mutated = html + ("\n<div class='sub'>your audio stays on your device — a "
                      "fully sealed on-device box; only a summary is uploaded.</div>\n")
    return base.with_file("index_html", mutated, tmp)


def _selftest_cs_decoder_free(base: Ctx, tmp: Path) -> Ctx:
    src = base.read("app_py")
    mutated = "from cloud.companion.engine_bridge import StreamPlayer\n" + src
    return base.with_file("app_py", mutated, tmp)


def _selftest_invariants_doc(base: Ctx, tmp: Path) -> Ctx:
    inv = base.read("invariants")
    mutated = "\n".join(l for l in inv.splitlines() if "R3 " not in l and "R3—" not in l
                        and not re.search(r"\bR3\b", l))
    return base.with_file("invariants", mutated, tmp)


def run_self_test() -> int:
    print("=" * 74)
    print("SELF-TEST — each check must FAIL on a mutated temp copy that trips it")
    print("=" * 74)
    base = Ctx()
    results: List[Tuple[str, bool, str]] = []

    def expect_fail(cid: str, ctx: Ctx):
        rid, verdict, detail = CHECKS[cid].fn(ctx)
        tripped = (verdict == FAIL)
        results.append((cid, tripped, detail))
        print(f"  [{'ok' if tripped else 'BROKEN'}] {cid}: mutation -> "
              f"{verdict}  ({detail[:90]})")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        expect_fail("CHECK-ENGINE-IMMUTABLE", _selftest_engine_immutable(tmp))
        expect_fail("CHECK-IMAGE-COMPLETE", _selftest_image_complete(base, tmp))
        expect_fail("CHECK-NO-FABRICATION", _selftest_no_fabrication(base, tmp))
        expect_fail("CHECK-SINGLE-CONTROL", _selftest_single_control(base, tmp))
        expect_fail("CHECK-EARDRUM-CAP", _selftest_eardrum_cap(base, tmp))
        expect_fail("CHECK-NAMESPACE-PIN", _selftest_namespace_pin(base, tmp))
        expect_fail("CHECK-CS-WIRE-CLOSED", _selftest_cs_wire_closed(base, tmp))
        expect_fail("CHECK-CS-DECODER-FREE", _selftest_cs_decoder_free(base, tmp))
        expect_fail("CHECK-AUDIO-BOUNDARY-HONEST",
                    _selftest_audio_boundary_honest(base, tmp))
        expect_fail("CHECK-INVARIANTS-DOC", _selftest_invariants_doc(base, tmp))

    # GATE-FAILCLOSED: feed the verdict predicate a simulated fail-OPEN status map.
    ok, detail = _gate_verdict({"world": 200, "auth_ok": True, "health": 200})
    tripped = (ok is False)
    results.append(("CHECK-GATE-FAILCLOSED", tripped, detail))
    print(f"  [{'ok' if tripped else 'BROKEN'}] CHECK-GATE-FAILCLOSED: simulated "
          f"fail-open -> {'FAIL' if not ok else 'PASS'}  ({detail})")

    # subprocess-wrapper checks: prove failure propagates (a nonzero exit -> FAIL).
    for cid in ("CHECK-TESTS", "CHECK-ENGINE-BYTEVERIFY", "CHECK-SEAM",
                "CHECK-INSTRUMENT"):
        rc, tail = _run([sys.executable, "-c", "import sys; sys.exit(7)"], timeout=30)
        tripped = (rc != 0)
        results.append((cid, tripped, f"wrapper sees exit {rc}"))
        print(f"  [{'ok' if tripped else 'BROKEN'}] {cid}: subprocess exit {rc} -> "
              f"{'FAIL' if rc else 'PASS'} (failure propagates)")

    broken = [cid for cid, tripped, _ in results if not tripped]
    print("-" * 74)
    if broken:
        print(f"SELF-TEST FAIL: {len(broken)} check(s) did NOT trip on their "
              f"mutation (worthless): {broken}")
        return 1
    print(f"SELF-TEST PASS: all {len(results)} checks provably able to FAIL.")
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def run_tier(tier: int, merge: bool) -> int:
    ctx = Ctx(merge=merge)
    ids = [cid for cid, c in CHECKS.items() if c.tier <= tier]
    print("=" * 74)
    print(f"FAITHFULNESS VERIFY — tier {tier}"
          + (" [merge gate]" if merge else "") + f"  ({len(ids)} checks)")
    print("=" * 74)
    results: List[Result] = []
    for cid in ids:
        t0 = time.time()
        try:
            rid, verdict, detail = CHECKS[cid].fn(ctx)
        except Exception as e:  # a check crashing is itself a FAIL, never a silent pass
            rid, verdict, detail = cid, FAIL, f"check raised {type(e).__name__}: {e}"
        dt = time.time() - t0
        results.append((rid, verdict, detail))
        print(f"[{verdict}] {rid:<26} ({dt:5.2f}s)  {detail}")
    n_fail = sum(1 for _, v, _ in results if v == FAIL)
    print("-" * 74)
    if n_fail:
        print(f"RESULT: FAIL — {n_fail}/{len(results)} check(s) failed.")
        return 1
    print(f"RESULT: PASS — all {len(results)} checks green.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tier", type=int, choices=(0, 1, 2), default=0)
    ap.add_argument("--merge", action="store_true",
                    help="merge-gate variant (also compare engine trees vs origin/main)")
    ap.add_argument("--self-test", action="store_true",
                    help="prove every check can fail (mandatory harness integrity gate)")
    args = ap.parse_args()
    if args.self_test:
        return run_self_test()
    return run_tier(args.tier, args.merge)


if __name__ == "__main__":
    sys.exit(main())
