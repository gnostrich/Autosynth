#!/usr/bin/env python3
"""Session MEMORY guard (PostToolUse hook) — the crashed-session lesson,
institutionalized (operator directive 2026-07-17): the session that died had
been told to add memory safeguards and still filled its container. This hook
runs after every significant action (Bash/Write/Edit) and SHOUTS while there
is still headroom to act, instead of dying silently at the wall.

Checks /proc/meminfo MemAvailable and the process tree's biggest consumers.
Silent when healthy (hooks should not spam); loud, actionable output when the
container approaches the kill zone. Thresholds are conservative: warn at 25%
available, alarm at 12%.
"""
import sys


def meminfo():
    d = {}
    with open("/proc/meminfo") as fh:
        for line in fh:
            k, v = line.split(":", 1)
            d[k] = int(v.strip().split()[0])          # kB
    return d


def top_procs(n=3):
    import glob
    procs = []
    for p in glob.glob("/proc/[0-9]*/status"):
        try:
            pid = p.split("/")[2]
            name = rss = None
            with open(p) as fh:
                for line in fh:
                    if line.startswith("Name:"):
                        name = line.split()[1]
                    elif line.startswith("VmRSS:"):
                        rss = int(line.split()[1])
                        break
            if name and rss:
                procs.append((rss, pid, name))
        except OSError:
            continue
    return sorted(procs, reverse=True)[:n]


def main():
    m = meminfo()
    total = m.get("MemTotal", 1)
    avail = m.get("MemAvailable", total)
    frac = avail / total
    if frac >= 0.25:
        return 0                                       # healthy: stay silent
    gb = avail / 1024 / 1024
    level = "MEMORY ALARM" if frac < 0.12 else "memory warning"
    top = ", ".join(f"{name}(pid {pid}) {rss//1024}MB"
                    for rss, pid, name in top_procs())
    print(f"[mem-guard] {level}: {gb:.1f}GB available "
          f"({frac:.0%} of {total//1024//1024}GB). Top consumers: {top}. "
          f"ACT NOW: stop/reduce the biggest consumer, avoid loading worlds/"
          f"banks in-process, prefer subprocess isolation for engine tests — "
          f"the previous session DIED from exactly this.", file=sys.stderr)
    return 0                                           # never block the action


if __name__ == "__main__":
    sys.exit(main())
