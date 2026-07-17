# psytech — pointer to the founding instantiation (embedded at the repo root)

**This folder is a signpost, not a copy.** The `psytech` instantiation — the first
trained model of the v1 architecture (first corpus) — physically lives at the
**repo root**, embedded in the working tree:

| artifact | location (repo root) |
|---|---|
| world | `corpus.etsworld` |
| LAMBDA (F weights) | `ets/functional/f.py` (`LAMBDA`) |
| σ_φ calibration | `ets/calibration/sigma_phi.json` |
| corpus | `corpus/` |
| exam receipts | `training_results.json`, `g*_results.json` |

## Why it is here and not physically moved into this folder

`psytech` is the **founding** instantiation: the v1 architecture and its first
trained model grew up together in the root tree, and that tree is the
byte-for-byte **protected v1** ("what worked"). Relocating it would not be free:

- `corpus.etsworld` embeds absolute paths to the root `corpus/` and its H-8 world
  hash is the sha256 of the pickled bytes — a move forces a re-pickle, which
  **changes the determinism hash**. That is mutating the exact thing v1
  immutability protects.
- ~9 harness/test files assert the current hashes/paths (`test_h8_determinism`,
  `test_h1_h2`, `legacy_manifest.sha256`, `test_calibration_consumer`, …), and
  `pyproject.toml` discovers `ets` at the root; a move breaks all of them.

So the founding instantiation is **grandfathered in place**, and this pointer
exists only so both instantiations are discoverable under `instantiations/`.

## Go-forward rule

Every instantiation *after* psytech lands in its own `instantiations/<corpus>/`
subfolder from the start (as `futuregarage` did). The asymmetry is a one-time
consequence of psytech being the founding, embedded model — not the pattern.
