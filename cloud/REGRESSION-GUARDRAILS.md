# Serving regressions — what went wrong 2026-07-18, and the guards so it never recurs

This session shipped the consolidated instrument redesign and hit five distinct
regressions. Each is recorded here with the root cause and the guard that now
prevents it. Read this before touching `cloud/companion/`.

## R-1 — Silent playback: boot eigen ensemble starved the audio loop  **(worst)**
- **Symptom:** `warmed=true` but the `/api/stream` produced only a WAV header then
  silence; `k` stuck at 0. Operator: "I can't hear the sets."
- **Root cause:** the redesign set the *boot* eigenmode ensemble to the
  **authoritative** `24×32` (768 settlement runs, ~32× the compute). It runs at boot
  in a daemon thread; on the single-core container it starved the realtime produce
  loop, so the engine rendered fine but never got CPU.
- **The core engine was NOT changed** — `tests/invariants/test_manifest.py` and
  `cloud/tests/test_freeze_only_byte_identity.py` passed 18/18. The fault was 100% in
  the serving wrapper (`engine_bridge.py`).
- **Fix:** the *boot* ensemble is `_EIGEN_BOOT_N_SEED=4 / _EIGEN_BOOT_N_BAR=6` (cheap).
  The authoritative `_EIGEN_N_SEED=24 / _EIGEN_N_BAR=32` are for **offline tools only**,
  passed explicitly. Audio is non-negotiable; k≥2 at boot is not worth starving sound.
- **GUARD:** `test_serving_regressions.py::test_boot_eigen_ensemble_is_cheap`.

## R-2 — Merge duplicated DOM → broke JS (also silent audio contributor)
- **Symptom:** the live `index.html` had **duplicate** `id="outboard"`, `#legacyDrawer`,
  `#slanes`. Duplicate IDs make `getElementById` pick the first → steer/play wiring
  broke.
- **Root cause:** a `git merge -X theirs` of the redesign over a branch that still had
  the old Play sections **kept both** sides' non-conflicting hunks → duplication.
- **Fix:** rebuild `index.html` from the builder's clean file; never hand-merge two
  divergent copies of the same big HTML.
- **GUARD:** `test_serving_regressions.py::test_no_duplicate_ids_in_index`.

## R-3 — Deploy race reverted a fix
- **Symptom:** audio worked (393 KB streamed), then went silent again.
- **Root cause:** three deploys fired in quick succession (declutter → layout →
  audio-fix). Railway builds finished **out of order**; an earlier build (still buggy)
  landed *after* the fix and overwrote it.
- **Rule:** fire deploys **serially** — wait for one to go live before firing the next,
  or only ever deploy the newest **superset** commit and confirm the live version is
  the intended SHA before declaring done. Every commit is a superset of the prior
  (linear history), so deploy the tip, once.

## R-4 — Cold container after every deploy → first play is silent until warmed
- **Symptom:** right after any deploy, the first Play shows the warming banner and no
  sound for a while.
- **Root cause:** each deploy restarts the container cold; the engine warms on first
  produced bar. Expected, but reads as "broken."
- **Rule:** after a deploy, **warm the shared set server-side** (open→play→stream once)
  before telling the operator to try it, so their first Play is instant.

## R-5 — Play page cluttered / heterogeneous / empty void
- **Spec (DESIGN-SPEC.md):** Play = **two components**: the steering pad (hero) +
  the knobs strip. Nothing else. The tracklist lives on the **Object** tab (renamed
  from Train; posting stays owner/key-gated, read-only from Explore).
- **What went wrong:** the redesign left LANE CONSOLE / LEGACY LANES / SOURCE LIBRARY /
  OUTPUT TAPE on Play (different panel classes → heterogeneous look), and after hiding
  them the pad collapsed to content height, leaving an empty void.
- **Fix:** hide the legacy panels on Play; pad `min-height:72vh` fills the viewport.
- **GUARD:** `test_serving_regressions.py::test_play_page_is_two_components`.

## Standing rules for any `cloud/companion/` change
1. **Audio-first.** Nothing at boot may block/starve the produce loop. Heavy measurement
   is deferred or cheap. Verify with a live stream byte count (>300 KB/15s = real audio).
2. **Core is frozen.** Run `tests/invariants/test_manifest.py` +
   `cloud/tests/test_freeze_only_byte_identity.py` after any engine-adjacent change.
3. **One deploy, serial.** Deploy the tip commit; confirm the live SHA; warm the set.
4. **Run `cloud/tests/test_serving_regressions.py`** before every companion deploy.
