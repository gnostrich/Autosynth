#!/usr/bin/env python3
"""Canonical-version verifier — an airtight reproducibility contract for the v1
psytech version (the engine + calibration + recipe that produces the music).

It answers one question with a cryptographic yes/no: **is the version doing the
rendering byte-for-byte the same version we blessed, and does it still produce the
exact same audio?** Three layers, all pinned in `verification/canonical_manifest.json`:

  1. VERSION INTEGRITY — sha256 of every version-defining file (the whole `ets/`
     engine tree, the σ_φ calibration, and the genre-set recipe). Any changed byte
     in the code/weights/recipe is named and fails. This is "the version doing it".
  2. WORLD HASH — the frozen corpus world's determinism hash (H-8). Guards the
     trained artifact / corpus.
  3. BEHAVIORAL PROOF — re-render a pinned reference (seed + journey + seconds) and
     check the raw-audio sha256 bit-for-bit. This transitively covers everything
     that affects output (engine, sampler, corpus, calibration, recipe). Verified
     bit-deterministic across repeat renders.

Usage:
    python3 scripts/verify_version.py            # verify against the manifest -> exit 0/1
    python3 scripts/verify_version.py --update   # (re)generate the manifest (deliberate version bless)

"Walls are information": a FAIL is a true report that the canonical version drifted,
not a nuisance. Do not "fix" a FAIL by re-running --update unless the change was
intended and re-blessed.
"""
from __future__ import annotations
import argparse, glob, hashlib, json, os, sys, time

MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(MAIN, "verification", "canonical_manifest.json")

# The reference render that behaviorally pins the version (short, deterministic).
REF = {"seed": 31, "knobs": "samples/genre_set/recipes/k_driving.json", "seconds": 20.0}

# Version-defining files. Globs expand to sorted tracked paths; the whole ets/
# engine tree + calibration + the committed genre recipe.
PIN_GLOBS = ["ets/**/*.py"]
PIN_FILES = [
    "ets/calibration/sigma_phi.json",
    "samples/genre_set/recipes/batch_render.py",
    "samples/genre_set/recipes/batch_journeys.json",
    "samples/genre_set/recipes/k_driving.json",
    "samples/genre_set/recipes/k_spacious.json",
    "samples/genre_set/recipes/k_shifting.json",
    "samples/genre_set/recipes/k_deep.json",
]


def _sha_file(rel: str) -> str:
    with open(os.path.join(MAIN, rel), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _version_files() -> list[str]:
    seen = set()
    for g in PIN_GLOBS:
        for p in glob.glob(os.path.join(MAIN, g), recursive=True):
            seen.add(os.path.relpath(p, MAIN))
    for p in PIN_FILES:
        if os.path.exists(os.path.join(MAIN, p)):
            seen.add(p)
    return sorted(seen)


def _world_hash() -> str:
    sys.path.insert(0, MAIN)
    from ets.engine.worldfile import load_world
    return load_world(os.path.join(MAIN, "corpus.etsworld")).world_hash


def _reference_audio_sha() -> str:
    os.environ.setdefault("ETS_BANK_CACHE", os.path.join(MAIN, "cache", "units"))
    sys.path.insert(0, MAIN)
    import numpy as np
    from ets.engine.engine import Engine, build_bank, resolve_sigma
    from ets.engine.worldfile import load_world
    wf = load_world(os.path.join(MAIN, "corpus.etsworld"))
    sigma = resolve_sigma(wf, None)
    bank = build_bank(wf)
    eng = Engine(wf, seed=REF["seed"], sigma=sigma)
    res = eng.render_offline(REF["seconds"], knob_script=os.path.join(MAIN, REF["knobs"]), bank=bank)
    a = np.ascontiguousarray(np.asarray(res.audio), dtype=np.float32)
    return hashlib.sha256(a.tobytes()).hexdigest()


def compute() -> dict:
    files = {rel: _sha_file(rel) for rel in _version_files()}
    return {
        "version": "v1-psytech-canonical",
        "reference_render": dict(REF),
        "world_hash": _world_hash(),
        "reference_audio_sha256": _reference_audio_sha(),
        "file_count": len(files),
        "files": files,
    }


def do_update():
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    m = compute()
    with open(MANIFEST, "w") as f:
        json.dump(m, f, indent=2, sort_keys=True)
    print(f"[update] wrote {MANIFEST}")
    print(f"[update] {m['file_count']} files, world_hash={m['world_hash'][:16]}, "
          f"ref_audio={m['reference_audio_sha256'][:16]}")


def do_verify() -> int:
    if not os.path.exists(MANIFEST):
        print("FAIL: no manifest — run --update to bless the current version first.")
        return 1
    exp = json.load(open(MANIFEST))
    fails = []

    # 1. version integrity (file-by-file)
    cur_files = {rel: _sha_file(rel) for rel in _version_files()}
    exp_files = exp["files"]
    for rel, h in exp_files.items():
        if rel not in cur_files:
            fails.append(f"missing version file: {rel}")
        elif cur_files[rel] != h:
            fails.append(f"CHANGED: {rel}\n    expected {h[:16]} got {cur_files[rel][:16]}")
    for rel in cur_files:
        if rel not in exp_files:
            fails.append(f"new/untracked version file present: {rel}")
    print(f"[1/3] version integrity: {len(exp_files)} pinned files "
          f"-> {'OK' if not fails else str(len(fails)) + ' issue(s)'}")

    # 2. world hash
    wh = _world_hash()
    wh_ok = (wh == exp["world_hash"])
    if not wh_ok:
        fails.append(f"world_hash changed: expected {exp['world_hash'][:16]} got {wh[:16]}")
    print(f"[2/3] world hash: {'OK' if wh_ok else 'CHANGED'}")

    # 3. behavioral proof (determinism replay)
    ra = _reference_audio_sha()
    ra_ok = (ra == exp["reference_audio_sha256"])
    if not ra_ok:
        fails.append(f"reference audio changed: expected "
                     f"{exp['reference_audio_sha256'][:16]} got {ra[:16]} "
                     f"(seed {REF['seed']}, {REF['knobs']}, {REF['seconds']}s)")
    print(f"[3/3] behavioral proof (render replay): {'OK' if ra_ok else 'CHANGED'}")

    print("-" * 60)
    if fails:
        print(f"VERSION VERIFY: FAIL ({len(fails)} issue(s)) — the canonical version drifted:")
        for x in fails:
            print("  - " + x)
        return 1
    print("VERSION VERIFY: PASS — canonical v1 version is airtight "
          "(files + world + reproduced audio all match the blessed manifest).")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true",
                    help="regenerate the manifest (deliberate version bless)")
    args = ap.parse_args()
    t0 = time.time()
    rc = 0
    if args.update:
        do_update()
    else:
        rc = do_verify()
    print(f"({time.time()-t0:.0f}s)")
    sys.exit(rc)


if __name__ == "__main__":
    main()
