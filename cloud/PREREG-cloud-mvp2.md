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
  │             │   audio PCM + telemetry over localhost WS
  │             │◀────────────────────────────┐
  └─────────────┘                             │
        │ gesture (region-tilt taps, transport)│
        ▼                                      │
  ┌──────────────────────────────────────────────────┐   stage-3 ONLY   ┌──────────┐
  │  LOCAL COMPANION  (on the operator's machine)      │────────────────▶│ RAILWAY  │
  │  = engine-v1 render + recipes + LAMBDA + exam      │  (cost+mass)    │ mvp1     │
  │  holds raw audio + recipes; renders PCM locally    │◀────────────────│ anchor-  │
  │  exposes a localhost web/WS API to the browser     │  world+receipt  │ fit only │
  └──────────────────────────────────────────────────┘                  └──────────┘
```

- **Vercel** serves *code* (the static UI bundle). It never receives audio, recipes,
  or raw. Page-origin ≠ data-origin: the page is fetched from Vercel; all data flows
  browser↔local-companion (audio/telemetry/gesture) and device↔Railway (stage-3
  only). No audio or recipe byte ever touches Vercel or Railway.
- **Local companion** = a headless wrapper over the `architecture-v6` engine. It is
  the ONLY thing that holds raw audio + recipes, runs the NCE LAMBDA fit + exam, and
  renders PCM. It streams rendered PCM to the browser over a localhost websocket
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
