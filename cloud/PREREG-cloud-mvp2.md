# PREREG — cloud MVP-2: browser instrument (Vercel frontend + Railway backend)

**Status:** PREREG ONLY (pre-staged 2026-07-17). No build yet. Operator chose the
full web-app scope; this pins the boundary BEFORE any code, per the standing
discipline (prereg → auditor PASS → merge; walls surfaced, not patched).

**Architecture version:** `cloud-mvp2`, a topology change on top of `engine-v1`
(verified, immutable) and `ui-v5` (`architecture-v6/`, the current instrument). It
REUSES `cloud-mvp1` (the Railway anchor-fit service) unchanged and adds a browser
UI + a local companion. Theory (F, world def, exam, settlement, render) is
byte-for-byte the local engine; any diff altering a learned object or F is OUT OF
SCOPE → stop and report.

## The load-bearing fact (read this first — it decides the whole topology)

The operator wants cloud hosting "for performance." Our own CS walls decide *which*
compute can actually move:

- **Training / anchor-fit CAN move to the cloud** — that is exactly `cloud-mvp1`
  (Railway), already built and audited. Only stage-3 (gauge-invariant cost matrices
  + masses) crosses. This is the real, ready performance win.
- **Audio RENDERING CANNOT move to the cloud.** Rendering needs the unit slices,
  which are recipe/raw data. Putting them in the cloud breaks **CS-1** (recipes
  never uploaded); rendering them server-side breaks **CS-4** (no cloud decoder).
  CS-1 ∧ CS-4 together make cloud rendering impossible *by our own design* — not an
  inconvenience, a wall. **Rendering stays on the device, always.**

So MVP-2 is honestly: **move the UI to the browser and the training to Railway;
keep rendering on a LOCAL companion.** A browser instrument that "plays from the
cloud" is not buildable without changing a CS wall (a separate, heavy F/faithfulness
decision — explicitly OUT OF SCOPE here). If the operator's performance pain is
*training*, MVP-2 (and already MVP-1) solves it. If it's *real-time playback*, MVP-2
does not move that; only the deferred divergence/sampler work (local engine) can.

## Topology (three parts, one honest data-flow)

```
  ┌─────────────┐   static JS/HTML/WASM (code only, no data)   ┌──────────────┐
  │   BROWSER   │◀──────────────────────────────────────────── │    VERCEL    │
  │ (control +  │                                               │ (static host)│
  │   speaker)  │                                               └──────────────┘
  │             │   audio PCM (HTTP) + telemetry (SSE) over localhost
  │             │◀────────────────────────────┐
  └─────────────┘                             │
        │ gesture (region-tilt taps, transport)│
        ▼                                      │
  ┌──────────────────────────────────────────────────┐   stage-3 ONLY   ┌──────────┐
  │  LOCAL COMPANION  (on the operator's machine)      │────────────────▶│ RAILWAY  │
  │  = engine-v1 render + recipes + LAMBDA + exam      │  (cost+mass)    │ mvp1     │
  │  holds raw audio + recipes; renders PCM locally    │◀────────────────│ anchor-  │
  │  exposes a localhost HTTP API to the browser       │  world+receipt  │ fit only │
  └──────────────────────────────────────────────────┘                  └──────────┘
```

- **Vercel** serves *code* (the static UI bundle). It never receives audio, recipes,
  or raw. Page-origin ≠ data-origin: the page is fetched from Vercel; all data flows
  browser↔local-companion (audio/telemetry/gesture) and device↔Railway (stage-3
  only). No audio or recipe byte ever touches Vercel or Railway.
- **Local companion** = a headless wrapper over the `architecture-v6` engine. It is
  the ONLY thing that holds raw audio + recipes, runs the NCE LAMBDA fit + exam, and
  renders PCM. It streams rendered PCM to the browser over a localhost HTTP stream
  (the browser is a *speaker* playing bytes the local machine rendered — not a
  decoder). It sends stage-3 jobs to Railway for the anchor-fit and verifies the
  returned receipts locally (reusing the mvp1 client guard).
- **Railway** = the unchanged `cloud-mvp1` service (anchor-fit; `$PORT`-ready).

## What genuinely offloads vs. stays local

| Step | Where | Why |
|---|---|---|
| Ingest (raw audio → prototypes) | LOCAL companion | raw never leaves (CS-1) |
| Anchor-fit (GW barycenter) | **RAILWAY** | stage-3 only; the heavy step; CS-clean |
| NCE LAMBDA fit + scramble exam | LOCAL companion | consume recipe data (CS-1 wall) |
| Render / playback | LOCAL companion | no cloud decoder (CS-4); recipes (CS-1) |
| UI (pads / XY / tape / transport / drill-in) | **BROWSER (Vercel)** | pure control surface |

## Hard rules (inherit CS-1..CS-5; a break is a WALL, not a patch)

- **CS-1** only stage-3 crosses device→cloud. The browser upload path to Railway can
  ONLY serialize the stage-3 whitelist (reuse the mvp1 whitelist encoder). Raw audio
  + recipes NEVER uploaded — not to Railway, not to Vercel.
- **CS-4** no cloud decoder. The Vercel bundle and the Railway image import no
  renderer and emit no audio; every sample the operator hears was rendered by the
  LOCAL companion. Browser playback is speaker-only (Web Audio plays local PCM).
- Receipts device-verifiable (reuse mvp1 receipt verify in the companion).
- Single region-tilt authority (the `ui-v5` f3b door invariant) carries over: the
  browser's ONLY engine-control path is the region-tilt tap, over the localhost API;
  telemetry is read-only. A second control path is a WALL.
- If shipping-fast tempts rendering in the cloud or uploading raw "just for now" →
  STOP and report. Ship the local-companion render instead.

## Harness `cloud/tests/` (extend the mvp1 suite)

- **MVP2-A raw/recipe-never-uploaded (web path)**: capture the actual bytes the
  browser client sends to Railway for a real corpus → assert only stage-3 present.
  Prove it BITES: a fixture attaching raw/recipe FAILS.
- **MVP2-B no-cloud-decoder (both hosts)**: static check — neither the Vercel bundle
  build nor the Railway image references a renderer/decoder or ships audio.
- **MVP2-C render-parity**: PCM rendered by the local companion is byte-identical to
  `architecture-v6` engine offline render on the same world+journey (the companion
  adds transport, not new DSP).
- **MVP2-D single-authority (web door)**: the browser→companion API exposes ONLY the
  region-tilt tap as a control path; port the f3b door test to the web boundary and
  prove it bites.
- **MVP2-E receipts-verified**: the companion refuses a Railway world whose exam
  receipts don't verify (reuse mvp1-B).

## Deploy shape

- **Railway**: `cloud/service/Dockerfile` (already `$PORT`-ready as of 2026-07-17).
  Point Railway at the repo, build context = repo root, Dockerfile path
  `cloud/service/Dockerfile`. Health probe: `GET /health`.
- **Vercel**: static export of the browser UI (framework TBD at build — plain
  Vite/React static bundle is enough; no server functions needed since all data is
  local or Railway). Set the Railway service URL + local-companion URL as build/env
  config.
- **Local companion**: packaged from `architecture-v6` (a `--serve` headless mode
  over the existing engine). This is the piece the operator still runs locally; it is
  the honest cost of the no-cloud-decoder guarantee.

## Environment honesty

Real provisioning (a Railway account, a Vercel project) is the operator's step — not
possible from this sandbox. Deliverable next session: the browser UI + local
companion + extended harness, built deploy-ready and verified HERE with Railway stood
in locally (as mvp1 already is) and the companion↔browser loop exercised headlessly.
State exactly what stays local at each step.

## Sequencing & discipline

Recommended order next session: (1) local companion headless mode + MVP2-C/D/E, (2)
browser UI on the companion (localhost) + MVP2-A/B, (3) wire the browser's train
button to Railway, (4) Vercel static build. Prereg (this file) before build; auditor
PASS before merge; one-sentence disclosure of any contemplated divergence; walls
surfaced not patched; coverage honesty every report. Versioning agent logs each step
to `LEDGER.md`; the release tuple gains a `deployment: cloud-mvp2` pin on merge.

## MVP-2 amendment — front-end + sandbox decisions (2026-07-17)

Operator confirmed: KEEP the Vercel web UI (mirroring the ui-v5 desktop layout,
beautified), and asked whether a graphical UX can "spawn out of Docker so safety is
guaranteed." These resolve to ONE architecture:

- **The browser is how the sealed container shows its face.** Do NOT surface the GUI
  by X11/display-socket passthrough (`-v /tmp/.X11-unix`, `DISPLAY=...`) or host-audio
  passthrough — those punch holes in the sandbox (a container holding the host X
  socket can snoop/inject host input; that is the OPPOSITE of "safety guaranteed").
  Instead the container speaks HTTP + WebSocket to a browser; the browser is the
  display AND the speaker. The container needs NO host display and NO host audio dev.
- **Sealed-container contract.** The local companion is a Docker container whose ONLY
  host contact is (a) one localhost port (serves/streams the UI + PCM + telemetry,
  receives gestures) and (b) a mounted DROP FOLDER for the user's audio. Ingest +
  render run inside; only stage-3 leaves (the whitelist guard is the sole wire exit);
  receipts verified inside. Two-way safety: the host is isolated from untrusted
  ingest, and the user's raw audio is isolated from the network.
- **Audio path.** The container renders PCM locally and streams it to the browser
  over **chunked HTTP** (`GET /api/stream`, a streaming WAV) with **SSE**
  telemetry (`GET /api/telemetry`) — NOT a raw WebSocket (the earlier "WS" wording
  above is superseded; functionally equivalent and CS-clean). The browser plays the
  PCM via Web Audio (AudioWorklet). CS-4 holds: the decoder is local (in-container),
  never cloud. The live loudness/eardrum cap rides in the engine render, so it
  carries to the streamed output.
- **Web UI is a NEW front-end, not a change to the native instrument.** The desktop
  `architecture-v6` instrument carries invariant **I-13** ("native Qt + OSC only, no
  web tech"); it stays untouched. The web UI is its own bundle (own folder) mirroring
  the LAYOUT — role pads, XY vector pad, drill-in, panel/meters, source library, output
  tape, transport — and talks to the same local container. Native desktop and
  web-in-browser are two faces on one sealed local engine; both are CS-clean.
- **Aesthetics.** The web layout is taken 1:1 from the desktop instrument and
  beautified via a design pass (design subagent, Opus-4.8-or-lower) — a modern dark
  synth/DAW look. A static design-direction mockup is produced first for sign-off
  before the functional build.

Net: Vercel serves the pretty UI code; the sealed local Docker container renders +
holds data + couriers stage-3 to Railway; Railway does the anchor-fit. Nothing here
weakens CS-1..CS-5 — it strengthens the ingest-safety story by sandboxing it.

**Ingest-drop decision (2026-07-17):** PRIMARY = **in-browser drag-and-drop / file-
select** (operator's call — most user-friendly). The browser reads the dropped files
and streams the bytes to the LOCAL container over localhost (127.0.0.1) — a hop
*within the machine*, never an internet upload; the bytes reach neither Vercel nor
Railway. Folder-drop (OS file manager → mounted volume, browser never touches the
bytes) is retained as a max-sealed FALLBACK for power users, not the default. Either
way only stage-3 leaves, through the one whitelist guard.

**Front-end hosting decision (2026-07-17):** the web UI is served by the **LOCAL
container itself** on localhost — NOT by Vercel, NOT by Railway. Rationale: the UI
only functions while talking to the local container (audio + data live there), so a
public FE URL would have nothing to connect to from any other machine — hosting it
publicly buys nothing for single-user. So: no Vercel and no Railway-for-FE in the
near term; **Railway hosts ONLY the anchor-fit training endpoint.** A hosted FE
(Railway static site OR Vercel — either works) is deferred to the **multi-user TBD**,
where many users load one shared UI bundle and each points it at their own local
container. Until then the container is the sole FE origin.

**Auth decision (2026-07-17):** MVP-2 ships **SINGLE-USER** first. Auth = one shared
bearer secret: the operator sets a token in the Railway service env; the local
container sends it on every POST /train; the service rejects requests without it.
This closes the open-compute-endpoint risk (a public `/train` = an open bill) with
minimal machinery — no user store, service stays stateless. **Multi-user is a later
expansion (TBD), sequenced AFTER one more upgrade** (see `OPEN_ENDS.md`): it needs key
issuance / revocation / per-key quotas + a store, and a call on single-tenant-per-
deploy ("their cloud" = each user hosts their own Railway) vs. one shared multi-tenant
service. Not built now; logged so it isn't lost.

## Phase-2 seam disclosure (2026-07-17, honest wall — surfaced by the auditor)

The phase-2 web instrument **plays a fixed founding/demo world** (`corpus.etsworld`),
which the user can steer live. It does **NOT** yet play the user's freshly cloud-
trained corpus. That seam is real and unbuilt: the cloud train returns anchor
GEOMETRY (`world.npz`); turning it into a playable world needs the LOCAL `build_index`
step — materialize the source bank / realization index from the trained artifact +
the user's local tracks — which is not wired. **The instrument therefore demos on the
founding world, and the UI + `/api/world` (`is_trained:false`) say so plainly** —
training shows a verified receipt but does not change what plays. Wiring
train→play-your-corpus (local ingest → tracks → `build_index` → playable world) is the
next phase-2 seam. This is a faithfulness disclosure, not a CS issue: rendering stays
local (CS-4 intact); nothing is presented as the user's world when it is not.

## Phase-2 seam FULLY WIRED — build + play + steer (2026-07-17, amendment)

Append-only amendment; the disclosure above records the honest prior state and is
not rewritten. The train→YOUR-corpus seam is now **fully wired**: raw audio →
build + verify + **measure this corpus's own σ_φ** → embed it → the instrument plays
AND steers the user's trained world.

**The σ_φ wall and its resolution (measured, not fabricated).** The literal MVP-2
plan assumed `save_world(..., sigma_phi=None)` would let `resolve_sigma` **fall back**
to the registered σ_φ calibration; it does **not** — that artifact is bound to the
DEMO world's content hash, and a freshly-trained world has a NEW hash, so
`resolve_sigma` would **refuse** it (STALE; it will not lean on a foreign world's
scale). The correct resolution — exactly what the native pipeline does at
world-freeze — is to MEASURE the trained corpus's own σ_φ and **embed** it. The
precedence `--sigma-phi > EMBEDDED (wf.sigma_phi) > registered` means an embedded σ_φ
is consumed via `tilt.SigmaPhi.from_mapping` and NEVER reaches the staleness guard.
`train_local._calibrate_sigma_phi` runs the untilted (u=0) settlement of the trained
world and reads per-observable fluctuations, mirroring `scripts/run_sigma_phi.py`
[3]-[4] IN-PROCESS (it does NOT write `ets/calibration/sigma_phi.json` and never
touches the registered artifact). It reuses that instrument's OWN estimator `_std`
verbatim (sample std ddof=1, exact 0.0 on constant input), so identifiability is
`σ>0` EXACTLY — **no invented floor**. `density` and `gauge` have zero untilted
fluctuation at u=0 → recorded non-identifiable → DISARMED (a measured fact, identical
to the founding world); `region`, `continuity`, `novelty` are armed. Cost: one
untilted settlement of compute added at train time (disclosed). If that settlement
fails its F-descent certificate on some corpus, THAT is a real wall (raised loudly),
never a scale to fabricate.

### BUILD + calibrate + play (faithful reuse; no engine/theory/F edits)
- New module `cloud/companion/train_local.py::build_trained_world` — the LOCAL half
  of a cloud train. It mirrors `ets.writer.build_world_from_tracks` VERBATIM with a
  single substitution: `fstate` comes from the CLOUD anchor-fit, not local
  `anchors.build_world`. Steps: local `ets.ingestion.pipeline.ingest` → stage-3
  `roles.extract_prototypes` → **the one guarded wire exit** `cloud.common.encode_job`
  + `cloud.client.cli.post_job` → `decode_result` + `verify_receipt` → local
  `ets.writer.build_index` + `World` → `ets.engine.worldfile.save_world` (a
  `.etsworld` referencing the user's LOCAL audio). Imported LAZILY (only when raw
  audio is present), engine imports deferred to call time, so `app.py`/`cli.py` stay
  decoder-free (CS-4).
- `train_local._calibrate_sigma_phi` — the per-corpus σ_φ measurement (see the wall
  paragraph above): untilted settlement → `phi_bars` → the instrument's own `_std`;
  identifiable := `σ>0` exactly. Embedded via `save_world(..., sigma_phi=<mapping>)`.
- `Companion.run_train` routes by extension: raw audio → the BUILD+calibrate+play
  seam (repoints `play_world`/player at the trained world, `is_trained=True`); `.npz`
  bundle / dir of cached tracks → the geometry-only verify (unchanged offline/test
  path). `StreamPlayer` gains an honest `is_trained` flag; `world_info()` reports it.
  A genuine UNEXPECTED failure bringing the world live is surfaced (`playback:error`)
  and keeps the demo live — never hidden.
- `Companion.reset` fully reverts: clears session + trained world, repoints to the
  founding demo world, drops the cached player, `is_trained→False`.

**CS-1 intact.** The ONLY thing crossing device→cloud is the stage-3 whitelist via
the unchanged `encode_job`→`post_job` exit. Tracks, raw audio, provenance, and the
realization index are never serialized and never leave the device. The σ_φ
calibration runs entirely LOCALLY (on-device settlement); nothing about it crosses
the wire. `seam_verify.py` captures the exact bytes handed to `post_job` and asserts
only `p{i}.{cost|mass|slot_hist|band_profile}` + params crossed — no
track/audio/provenance key.

### Verified (seam_verify.py, own process, arch-v6 first, LIVE Railway)
1) BUILD against LIVE Railway → a verified trained `.etsworld`. 2) CS-1: the exact
`post_job` bytes decode to ONLY stage-3. 3) `load_world(trained)` → `resolve_sigma`
returns the **EMBEDDED** σ_φ (NO STALE raise). 4) `StreamPlayer(trained,
is_trained=True).world_info()["is_trained"]` is True. 5) a u=0 bar AND a nonzero
region-steer bar both render finite + eardrum-capped (peak ≤ 0.61), and the steered
arrangement DIFFERS from u=0 (steering is LIVE — the embedded σ_φ armed the region
lane), with `density`/`gauge` disarmed at u=0 (measured, same as the founding world).

### Rejected non-solutions (each an auto-reject under the operating rules)
(a) faking a σ_φ artifact — fabricated measurement; (b) re-stamping the demo
artifact's hash onto the trained world — forging the world binding to bypass the
staleness guard; (c) embedding an all-non-identifiable σ_φ — makes leans *silently
disarm* (`_lam` returns λ=0 for non-identifiable lanes; it does not raise), a
silent-fallback steer no-op. The shipped path avoids all three: it MEASURES the
corpus's own σ_φ (identifiable lanes are armed with real scales; only the genuinely
zero-fluctuation lanes disarm) and embeds it via the documented precedence — an
engine-free resolution that reuses the registered instrument's own estimator.
