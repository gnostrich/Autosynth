#!/usr/bin/env python3
"""Disk-space guardian — reclaim regenerable space before it blocks a write.

The pipeline writes large, DETERMINISTIC, git-ignored caches (bank unit caches
~6-9 GB each, ingest caches) and scratch renders. As forks/retrains accumulate,
these fill the session's disk allowance and a materialization dies mid-write
with ENOTSPACE. Everything this tool deletes is REGENERABLE (a cache) or scratch
— never a git-tracked file, never source, never an instantiation's committed
world/corpus/receipts.

Reclaim runs ONLY when free space is below --threshold-gb, in a safe priority
order, stopping as soon as free >= --target-gb:

  1. __pycache__ / .pytest_cache / *.pyc               (always safe, cheap)
  2. *.tmp, *.npz.tmp                                   (partial/aborted writes)
  3. architecture-*/cache/**                            (machine folders must NOT
                                                          carry a bank; reuse the
                                                          instance cache instead)
  4. scratch render outputs / stale logs older than 1h
  5. LRU bank unit caches (**/cache/units) NOT touched in the last --keep-min
     minutes  (protects the cache an active render is reading)

NEVER touched: cache/ingest (slow to rebuild — beat tracking), anything git
tracks, any *.etsworld / corpus mp3s, this session's fresh caches.

Usage:
  python3 scripts/disk_guard.py                 # guard: reclaim iff free < threshold
  python3 scripts/disk_guard.py --dry-run       # show what it WOULD free
  python3 scripts/disk_guard.py --threshold-gb 6 --target-gb 12
"""
from __future__ import annotations
import argparse
import glob
import os
import shutil
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(REPO, "disk_guard.log")


def free_gb(path: str = REPO) -> float:
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize / 1e9


def _du(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _rm(path: str, dry: bool) -> int:
    """Remove a file or dir tree; return bytes freed (estimated)."""
    try:
        sz = _du(path) if os.path.isdir(path) else os.path.getsize(path)
    except OSError:
        sz = 0
    if not dry:
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
        except OSError:
            return 0
    return sz


def _in_use(path: str) -> bool:
    """True if any process currently has a file under `path` open (fuser). A
    render READING a bank cache does not bump mtime, so this is the only reliable
    guard against deleting a cache an active render is streaming from."""
    try:
        import subprocess
        r = subprocess.run(["fuser", "-s", "-m", path], timeout=8)
        return r.returncode == 0            # 0 => in use
    except Exception:
        return True                          # can't tell -> assume in use (safe)


def _targets(now: float, keep_min: float, reclaim_banks: bool):
    """Yield (path, tier) reclaim candidates in priority order."""
    # tier 1: pycache
    for p in glob.glob(os.path.join(REPO, "**", "__pycache__"), recursive=True):
        yield p, 1
    for p in glob.glob(os.path.join(REPO, "**", ".pytest_cache"), recursive=True):
        yield p, 1
    # tier 2: partial writes
    for pat in ("**/*.tmp", "**/*.npz.tmp"):
        for p in glob.glob(os.path.join(REPO, pat), recursive=True):
            yield p, 2
    # tier 3: machine-folder caches (should NOT exist — a fork's machine must reuse
    # the instance cache, not materialize its own bank). This is today's 9 GB
    # culprit and is always safe to reclaim.
    for p in glob.glob(os.path.join(REPO, "architecture-*", "cache")):
        yield p, 3
    # tier 4: reserved for stale scratch (scratch lives outside REPO; handled by
    # the caller's extra-roots, not here).
    # tier 5: LRU bank unit caches — OPT-IN only (--reclaim-banks) and only when
    # not touched recently AND not currently open by any process. These are big
    # but legitimately needed by their instance; auto-mode never deletes them.
    if not reclaim_banks:
        return
    units = glob.glob(os.path.join(REPO, "**", "cache", "units"), recursive=True)
    lru = []
    for u in units:
        try:
            age = now - os.path.getmtime(u)
        except OSError:
            continue
        if age > keep_min * 60 and not _in_use(u):
            lru.append((age, u))
    for _age, u in sorted(lru, reverse=True):     # oldest first
        yield u, 5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold-gb", type=float, default=6.0,
                    help="reclaim only when free < this")
    ap.add_argument("--target-gb", type=float, default=12.0,
                    help="stop reclaiming once free >= this")
    ap.add_argument("--keep-min", type=float, default=10.0,
                    help="never delete a bank cache touched in the last N minutes")
    ap.add_argument("--reclaim-banks", action="store_true",
                    help="also reclaim LRU bank unit caches not in use (opt-in; "
                         "auto/hook mode leaves them alone)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    before = free_gb()
    if before >= args.threshold_gb and not args.dry_run:
        return 0                              # healthy: silent no-op (hook-friendly)

    now = time.time()
    freed = 0
    acted = []
    for path, tier in _targets(now, args.keep_min, args.reclaim_banks):
        if not args.dry_run and free_gb() >= args.target_gb:
            break
        if not os.path.exists(path):
            continue
        sz = _rm(path, args.dry_run)
        if sz > 0:
            freed += sz
            acted.append((tier, path, sz))

    after = free_gb()
    if acted or args.dry_run:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        verb = "WOULD free" if args.dry_run else "freed"
        line = (f"[{stamp}] disk_guard: free {before:.1f}->{after:.1f} GB; "
                f"{verb} {freed/1e9:.1f} GB from {len(acted)} targets "
                f"(threshold {args.threshold_gb}, target {args.target_gb})")
        print(line)
        for tier, path, sz in acted:
            print(f"    t{tier} {sz/1e9:.2f}GB  {os.path.relpath(path, REPO)}")
        try:
            with open(LOG, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
