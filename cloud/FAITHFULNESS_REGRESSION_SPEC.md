# ETS Companion — Faithfulness Regression Spec (living checklist)

**Status:** source of truth for `cloud/tools/faithfulness_verify.py`. Numbered,
mechanical, and adversarial. Every item is a CHECK-ID with (a) what it asserts,
(b) the exact mechanical method, (c) the tier it runs in. The runner *reads this
file* for the CAPTION REGISTRY (the machine-readable JSON block below) and
*encodes* every other check as a deterministic function that returns
`(id, PASS|FAIL, detail)`.

## Why this exists (the operator's mandate)

We kept shipping faithfulness regressions **despite** LLM-auditor passes, because
an auditor is a judgement call — fallible, non-exhaustive, and not run
mechanically on every change. The fix: convert faithfulness from "an agent
eyeballs the diff" into a **mechanical checklist harness** that re-asserts every
invariant on every edit and **fails loud**. Agents run THIS first, then judge on
top. A check that cannot fail is worthless — every check is proven able to fail
by `faithfulness_verify.py --self-test`, which applies a synthetic mutation to a
temp copy and asserts the check trips.

**Doctrine (the one rule the whole harness serves):**
> **REAL-DATA or DISARMED-AND-LABELED.** Any display surface must either be fed
> by real engine/api data, or be captioned honestly as not-real ("not wired",
> "cosmetic", "illustrative"). A *prettier* synthetic still FAILS. Synthetic data
> under an honest-sounding caption is the exact failure mode that shipped twice.

---

## FABRICATION INCIDENT LOG (hand-maintained; never delete an entry)

### INC-1 — Green-dashboard fabrication in the browser drill-in + tape waveform
- **What shipped:** `cloud/companion/static/index.html` rendered a role drill-in of
  **36 hardcoded synthetic cells** (`var units = 36;` with cosmetic colours
  `TRACK_COLORS[(u*7+i) % ...]`) captioned **"Each cell is one unit, colored by its
  source track"**, and an Output-Tape waveform drawn from **`Math.sin`/`Math.abs`
  art** (`buildWave`) captioned **"settled render"**. BOTH surfaces were fabricated
  data wearing honest-sounding captions.
- **Root cause:** *"fill the surface so it looks real"* — a synthetic generator was
  wired to a display surface and then captioned as if it were engine output. No
  mechanical check asserted the surface's data actually came from an `/api/*` fetch.
- **Remediation:** `CHECK-NO-FABRICATION` (below). Each such surface is registered
  in the CAPTION REGISTRY and must be **REAL-DATA** (backed by a real fetch, with no
  synthetic generator feeding it) **or DISARMED-AND-LABELED** (caption is the
  not-real form). The synthetic-waveform and synthetic-cell *generators* are
  detected structurally so a re-skinned synthetic still trips.

### INC-2 — Image-incompleteness: runtime file-path load not COPY'd into the image
- **What shipped:** `cloud/companion/train_local.py` loads
  `architecture-v6/scripts/run_sigma_phi.py` **by file path** (via
  `importlib.util.spec_from_file_location`, to reuse its `_std` estimator verbatim),
  but the `cloud/companion/Dockerfile` did not `COPY` that file into the image →
  live training raised **`FileNotFoundError`** and the endpoint 502'd in production.
- **Root cause:** a runtime path dependency that is invisible to `import`-graph
  reasoning and was never asserted against the image's `COPY` manifest.
- **Remediation:** `CHECK-IMAGE-COMPLETE` (below) scans `cloud/**/*.py` for
  runtime file-path loads and asserts each referenced repo path is covered by a
  Dockerfile `COPY`. The self-test proves that *removing* the `run_sigma_phi.py`
  COPY line makes the check FAIL (i.e. it would have caught INC-2).

---

### INC-3 — stale privacy claim after the R3(b) audio-boundary lock
- **What happened:** on 2026-07-17 the operator LOCKED R3 to **R3(b)** — in the
  hosted app the raw audio uploads to Railway BY DESIGN (so drag-and-drop works; a
  "raw never leaves device" private mode is a recorded FUTURE upgrade). The UI still
  carried the earlier sealed-design captions: "sealed on-device box" and "Only …
  stage-3 … leave this box — raw audio and recipes never do". Under R3(b) those are
  **privacy claims that are now false** — a fabrication by the same "honest-sounding
  caption over an untrue claim" mechanism as INC-1.
- **Root cause:** a product-boundary decision changed the truth of a caption; nothing
  mechanically re-checked the UI's privacy language against the live invariant.
- **Remediation:** `CHECK-AUDIO-BOUNDARY-HONEST` (armed by the invariant itself; it
  disarms only if R3 flips back to R3(a)). Caught as a live finding; the concurrent
  index.html fix relabels the surface as cloud-processed.

## Tiers (by speed, so the harness runs "relentlessly")

| Tier | When | Budget | Contents |
|------|------|--------|----------|
| `--tier 0` | every edit to `cloud/` or an engine tree | < ~5 s | pure static/structural checks; no rendering, no server, no engine import |
| `--tier 1` | pre-commit | seconds | tier-0 + `pytest cloud/tests -q` + the fail-closed public-gate probe |
| `--tier 2` | pre-merge / release | may be minutes | tier-1 + engine byte-verify (`scripts/verify_version.py`) + `cloud/tools/seam_verify.py` + `cloud/tools/instrument_verify.py` |
| `--self-test` | CI + before trusting the harness | seconds | for EACH check, mutate a temp copy that SHOULD trip it and assert it FAILS |

The runner prints a table and **exits non-zero if ANY check fails**.

---

## CHECKS

### CHECK-ENGINE-IMMUTABLE — tier 0 (fast) / escalates tier 2
- **Asserts:** ZERO byte changes under `ets/` and `architecture-v6/ets/` vs the
  committed baseline. The engine + theory are byte-verified and immutable; no edit
  to F / settlement / render / world-definition without a prereg + operator sign-off.
- **Method (tier 0/1):** `git -C <root> diff --quiet HEAD -- ets architecture-v6/ets`
  AND no untracked files under those trees. Non-clean ⇒ FAIL, naming the paths.
- **Method (tier 2 / merge gate):** additionally `git diff --quiet origin/main -- ets
  architecture-v6/ets` and run `scripts/verify_version.py` (full byte + world +
  behavioural replay). See `CHECK-ENGINE-BYTEVERIFY`.
- **Self-test:** build a throwaway git repo with a committed `ets/` file, dirty it,
  and assert the check FAILs on that repo.

### CHECK-IMAGE-COMPLETE — tier 0
- **Asserts:** every repo path that `cloud/**/*.py` loads **by file path at runtime**
  is covered by a `COPY` in `cloud/companion/Dockerfile`. (Catches the INC-2 class.)
- **Method:** parse the Dockerfile `COPY <src> <dst>` lines into a set of covered
  source paths (a file covers itself; a dir/trailing-slash source covers everything
  beneath it). Scan `cloud/**/*.py` for runtime path-load signatures:
  `_ARCH_V6 + "<literal>"`, `_REPO_ROOT ... / "<literal>"`,
  `spec_from_file_location(..., <path>)`, and `/scripts/<file>` literals that are
  opened/exec'd. Resolve each to a repo-relative path. Any referenced path **not**
  covered by a COPY ⇒ FAIL, listing it. (Guarded existence-probes over a *tuple* of
  optional assets — e.g. the `demo.etsworld`/`corpus.etsworld` dev fallback — are
  dynamic, not literal path-concat loads, and are intentionally out of scope.)
- **Self-test:** remove the `run_sigma_phi.py` COPY line from a temp Dockerfile copy
  and assert the check FAILs (proving it catches INC-2).

### CHECK-NO-FABRICATION — tier 0 (the anti-green-dashboard core)
- **Asserts:** no synthetic-data generator feeds a display surface of
  `cloud/companion/static/index.html` under a real-data caption; every caption that
  asserts/implies a data source is either REAL-DATA-backed or DISARMED-AND-LABELED.
- **Method — (a) DENYLIST (structural, caption-independent):**
  - `Math.random` anywhere in the file ⇒ FAIL (random noise never feeds a faithful
    display; there is no legitimate use).
  - **`synthetic_waveform`** signature: a coordinate-pair push `push([...])` whose
    preceding lines compute the coordinate with `Math.sin`/`Math.cos`/`Math.abs`, and
    whose array is emitted as an SVG `<path d=...>`. This is the `buildWave` tape art.
    (Pure layout geometry — e.g. positioning a *single* element via
    `el.style.left = ...Math.cos(theta)...` — pushes an object, not a coordinate
    array into a path, and is NOT flagged.)
  - **`synthetic_cells`** signature: a `for` loop bounded by a **hardcoded integer
    literal** assigned to a `units`/`cells`/`tracks`/`slots`/`nodes`/`grid`-named
    variable, whose body `createElement`s and sets `className = "unit"|"cell"|"track"`.
    This is the `var units = 36` drill grid. (A real grid sets the bound from
    `data.length` of a fetch, so no integer literal appears — it is NOT flagged. The
    meter widget's `N = 14` builds unclassed `<i>` LED bars, not unit/cell/track
    elements — NOT flagged.)
- **Method — (b) CAPTION REGISTRY (allowlist, machine-readable below):** each
  registered surface has real-data captions, disarmed captions, the fabrication
  signature that must be absent when it claims real, and the `/api/*` fetch(es) that
  must back it. Per-surface verdict (the doctrine, mechanised):
  - real caption present ⇒ **PASS iff** (a backing fetch is present AND the
    fabrication signature is absent); otherwise **FAIL** (claims real but is
    synthetic or unbacked — the INC-1 state).
  - else disarmed caption present ⇒ **PASS** (honestly labelled not-real; a
    synthetic generator MAY remain because it no longer lies).
  - else (neither) ⇒ **FAIL if** the fabrication signature is present (an unlabelled
    synthetic surface must be labelled), otherwise PASS.
  The overall check FAILs if any registry surface FAILs or the denylist trips.
- **Self-test:** (i) inject `Math.random` into a temp copy ⇒ FAIL; and the registry
  logic is exercised against the live tree (currently FAILing on both surfaces until
  the concurrent index.html fix lands — that real inventory is a deliverable).

### CHECK-SINGLE-CONTROL — tier 0
- **Asserts:** the ONLY settlement-mutating engine-control call from the UI is
  `POST /api/steer`; there is no second decision channel.
- **Method:** enumerate every `fetch("<path>")` / `new EventSource("<path>")` target
  in index.html. `/api/steer` must be present. The full endpoint set must be a subset
  of the vetted API allowlist (`/api/health,status,world,ingest,reset,train,steer,
  telemetry,stream,play,stop,auth`) — the only settlement-mutating member of which is
  `/api/steer`. Any endpoint outside the allowlist is a potential second control
  channel ⇒ FAIL, listing it. (Adding a genuinely new endpoint requires updating this
  spec's allowlist under review — the point is that a new control path can never slip
  in unnoticed.)
- **Self-test:** inject a `fetch("/api/settle2", ...)` into a temp copy ⇒ FAIL.

### CHECK-EARDRUM-CAP — tier 0
- **Asserts:** `cloud/companion/engine_bridge.py` `produce_one_bar` applies
  `_playback_soft_limit(...)` to the produced audio on the **per-bar** path — the
  loudness/blow-up cap is present and unweakened on EVERY bar.
- **Method:** locate `def produce_one_bar`, take its body to the next same-indent
  `def`, and assert it contains `audio = _playback_soft_limit(audio)` (or an
  assignment applying `_playback_soft_limit` to the bar audio) before the PCM is
  emitted. Absent ⇒ FAIL.
- **Self-test:** delete the `_playback_soft_limit` line from a temp copy ⇒ FAIL.

### CHECK-NAMESPACE-PIN — tier 0
- **Asserts:** `engine_bridge.py` forces `architecture-v6` to the FRONT of `sys.path`
  and fails loud if the wrong engine resolves (root engine-v1 must not shadow the
  live-capped ui-v5 engine).
- **Method:** assert `engine_bridge.py` contains `sys.path.insert(0, _ARCH_V6)` AND a
  `raise RuntimeError(` guarded by the absence of the live-cap markers
  (`_playback_soft_limit` / `bar_role_activity`). Missing either ⇒ FAIL.
- **Self-test:** remove the `raise RuntimeError` guard from a temp copy ⇒ FAIL.

### CHECK-CS-WIRE-CLOSED — tier 0
- **Asserts:** the INTERNAL companion→anchor-fit encoder hop stays whitelist-closed.
  **R3(b) is LOCKED — raw audio DOES upload to Railway by design — so this check does
  NOT assert "raw audio never crosses the wire" (that is now false by design).** What
  it guards is that `cloud.common.encode_job` / `Stage3Proto` serialize ONLY the four
  gauge-invariant stage-3 fields and have no structural slot for raw audio /
  provenance.
- **Method:** `ast.parse` `cloud/common/protocol.py`; assert
  `STAGE3_PROTO_FIELDS == ("cost","mass","slot_hist","band_profile")` exactly; assert
  the `Stage3Proto` dataclass fields are exactly that set (no raw-audio/provenance
  slot); assert `from_prototype` iterates the whitelist (`for name in
  STAGE3_PROTO_FIELDS`, so a `Track`/raw array lacking `.cost` raises) and the
  emit-time `assert_wire_whitelisted` guard is present. (Behavioural proof:
  `cloud/tests/test_mvp_a_raw_never_uploaded.py`, run in tier 1.)
- **Self-test:** add an `audio: np.ndarray` field to a temp copy of `Stage3Proto`
  and assert the check FAILs (the wire object grew a raw-audio slot).

### CHECK-CS-DECODER-FREE — tier 0 (CS-4)
- **Asserts:** `cloud/companion/app.py` imports no render/decoder module at module
  level — the decoder lives only in the lazily-imported `engine_bridge`/`train_local`,
  so the cloud path stays provably decoder-free.
- **Method:** `ast.parse` app.py; collect module-level `import`/`from` statements
  (only those in `module.body`, not nested in a function/class); assert none resolve
  to a forbidden decoder/render module (`cloud.companion.engine_bridge`,
  `cloud.companion.train_local`, `ets.engine`, `ets.render`, `ets.writer`,
  `ets.connector`, `ets.geometry`, `ets.ingestion`). Any at module level ⇒ FAIL.
- **Self-test:** insert a top-level `from cloud.companion.engine_bridge import
  StreamPlayer` into a temp copy ⇒ FAIL.

### CHECK-AUDIO-BOUNDARY-HONEST — tier 0
- **Asserts:** while **R3 is locked to R3(b)** (raw audio uploads to the cloud by
  design), **no** user-facing surface/caption/label/comment in
  `cloud/companion/static/index.html` claims the audio is private / sealed / stays
  on-device / "only a summary uploaded". Under R3(b) such a claim is itself a
  fabrication (COMPANION_INVARIANTS R3 HONESTY REQUIREMENT); the UI must read as
  cloud-processed ("Train on cloud").
- **Method:** the denylist is **armed by the invariant itself** — parse
  `COMPANION_INVARIANTS.md`; if R3(b) is locked (`"LOCKED to R3(b)"` /
  `"raw audio DOES leave the device"` / `"raw audio is uploaded"`), scan index.html
  for privacy/locality phrases (`on-device`, `stays on your device`,
  `never leaves the device/box`, `raw audio … never`, `sealed`, `only … stage-3 …
  leave`). Any hit ⇒ FAIL, listing line + phrase. If R3 is NOT R3(b) (e.g. flips to
  the recorded R3(a) private-mode upgrade), the claims become TRUE and the check
  **honestly disarms** — the invariant is the single source of truth, not a second
  channel.
- **Self-test:** with the (real, armed) R3(b) invariant, inject "your audio stays on
  your device … sealed on-device box …" into a temp copy of index.html ⇒ FAIL.
- **Live finding (2026-07-17):** with R3(b) newly locked, index.html currently
  asserts "sealed on-device box" and "Only … stage-3 … leave this box — raw audio …
  never" — a **live R3(b) fabrication** this check FLAGS until the concurrent
  index.html fix relabels the surface as cloud-processed. Honest current inventory.

### CHECK-INVARIANTS-DOC — tier 0
- **Asserts:** the product invariants and standing rules are present in the record.
- **Method:** `cloud/COMPANION_INVARIANTS.md` contains `R1`..`R6` **and** the R3(b)
  markers (`R3(b)`, `HONESTY REQUIREMENT`, `PLANNED UPGRADE`); `CLAUDE.md` contains
  the standing-rule markers (`Non-negotiable product invariants`, `Auditor pass
  before every merge`, and the faithfulness-harness rule / incident-log pointer added
  by this build). Any missing ⇒ FAIL.
- **Self-test:** strip an `R#` line from a temp copy of the invariants ⇒ FAIL.

### CHECK-GATE-FAILCLOSED — tier 1
- **Asserts:** with empty `ETS_ACCESS_KEYS`, nothing is authorised; only
  `/api/health` and `/api/auth` are un-gated; `/api/auth` denies even a well-formed
  key (fail closed). Key compare is constant-time (`hmac.compare_digest`).
- **Method:** start `cloud.companion.app.serve(public=True, access_keys=[])` on an
  ephemeral loopback port; assert `GET /api/world` ⇒ 401, `POST /api/auth` ⇒ denied
  (not 200-ok), `GET /api/health` ⇒ 200. The verdict is a pure predicate over the
  observed statuses, so it can be self-tested against a simulated regression. Also
  assert `hmac.compare_digest` is used in app.py's key check (structural).
- **Self-test:** feed the verdict predicate a simulated **fail-open** status map
  (`/api/world` ⇒ 200 unauthenticated) and assert it returns FAIL.

### CHECK-TESTS — tier 1
- **Asserts:** the committed companion test suite is green.
- **Method:** subprocess `python -m pytest cloud/tests -q`; PASS iff exit 0.
- **Self-test:** run the same subprocess wrapper on a command that exits non-zero and
  assert the wrapper reports FAIL (failure-propagation proof).

### CHECK-ENGINE-BYTEVERIFY — tier 2
- **Asserts:** the full canonical-version contract (engine bytes + world hash +
  behavioural render replay) still matches the blessed manifest, and the engine trees
  are clean vs `origin/main`.
- **Method:** `git diff --quiet origin/main -- ets architecture-v6/ets` AND subprocess
  `python scripts/verify_version.py` (exit 0). Slow (real render) — tier 2 only.
- **Self-test:** wrapper failure-propagation (as CHECK-TESTS).

### CHECK-SEAM — tier 2
- **Asserts:** the train→play seam produces a valid, CS-clean, playable
  `.etsworld` with a measured (not fabricated) embedded σ_φ.
- **Method:** subprocess `python cloud/tools/seam_verify.py`; PASS iff exit 0. Slow.
- **Self-test:** wrapper failure-propagation.

### CHECK-INSTRUMENT — tier 2
- **Asserts:** the render-path instrument (single-control door, WAV header, one
  capped bar) holds end to end.
- **Method:** subprocess `python cloud/tools/instrument_verify.py`; PASS iff exit 0.
  Slow (real engine bar).
- **Self-test:** wrapper failure-propagation.

---

## CAPTION REGISTRY (machine-readable — the runner parses the JSON block below)

Hand-maintained allowlist. Add a surface here the moment a caption in the UI
**asserts or implies** a data source. `real_captions` are verbatim substrings that
claim real data; `disarmed_captions` are verbatim substrings that honestly label a
surface as not-real; `fabrication_signature` is the denylist signature that must be
absent when the surface claims real; `backing_fetch_any_of` are the `/api/*`
endpoints, at least one of which must appear when the surface claims real.

<!-- CAPTION_REGISTRY_JSON -->
```json
[
  {
    "id": "TAPE_WAVEFORM",
    "surface": "Output Tape waveform (#wav / tape envelope)",
    "real_captions": ["settled-render audio", "settled render"],
    "disarmed_captions": [
      "cosmetic tape",
      "not the settled render",
      "waveform not wired",
      "illustrative waveform",
      "not wired"
    ],
    "fabrication_signature": "synthetic_waveform",
    "backing_fetch_any_of": ["/api/stream", "/api/telemetry", "/api/units"]
  },
  {
    "id": "ROLE_DRILL_GRID",
    "surface": "Role drill-in unit grid (#unitGrid cells)",
    "real_captions": [
      "real source track",
      "colored by its real source track",
      "from render provenance",
      "colored by its source track"
    ],
    "disarmed_captions": [
      "illustrative",
      "not wired",
      "cosmetic makeup",
      "display view of the role",
      "makeup view"
    ],
    "fabrication_signature": "synthetic_cells",
    "backing_fetch_any_of": ["/api/units"]
  }
]
```

> Note (2026-07-17): the INC-1 fabrications have been resolved to REAL-DATA in the
> live tree. TAPE_WAVEFORM's envelope is now drawn from the decoded `/api/stream`
> PCM under the caption "settled-render audio", and ROLE_DRILL_GRID's cells are
> built from `/api/units` render provenance (`u.unit_id`/`u.track_id`) under the
> caption "colored by its real source track ... from render provenance". Both real
> captions are registered above so the binding stays **live**: if a future edit
> re-introduces a `synthetic_waveform`/`synthetic_cells` generator under these
> captions, or removes the backing fetch, `CHECK-NO-FABRICATION` FAILs. The
> `--self-test` re-injects the INC-1 `synthetic_cells` generator to prove exactly
> that. If a future edit disarms a surface instead, it must use one of the
> `disarmed_captions` above (or add its wording here — the registry is the contract).

## SINGLE-CONTROL ALLOWLIST (vetted UI → API surface)

`/api/health`, `/api/status`, `/api/world`, `/api/ingest`, `/api/reset`,
`/api/train`, `/api/steer`, `/api/telemetry`, `/api/stream`, `/api/play`,
`/api/stop`, `/api/auth`, `/api/units`. **Only `/api/steer` mutates settlement**
(`/api/units`, `/api/telemetry`, `/api/stream`, `/api/status`, `/api/world` are
read-only; `/api/play`/`/api/stop` are transport; `/api/ingest`/`/api/reset`/
`/api/train` manage the corpus). Adding an endpoint requires editing this list
under review.

## Running the harness

```
python cloud/tools/faithfulness_verify.py --tier 0     # every edit  (< ~5s)
python cloud/tools/faithfulness_verify.py --tier 1     # pre-commit
python cloud/tools/faithfulness_verify.py --tier 2     # pre-merge / release
python cloud/tools/faithfulness_verify.py --self-test  # prove every check can fail
```

Wired to run relentlessly via `.githooks/pre-commit` (tier 1) and
`.githooks/pre-push` (tier 2); enable with `git config core.hooksPath .githooks`.
The ets-auditor MUST run the harness FIRST and paste its output before any
judgement review (see `CLAUDE.md`).
</content>
</invoke>
