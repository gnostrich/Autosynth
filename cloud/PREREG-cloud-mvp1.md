# PREREG — cloud MVP-1: hosted TRAINING service (get heavy compute off the local machine)

**Architecture version:** cloud-mvp (a topology change on top of `engine-v1`). Base
engine-v1 is verified (`scripts/verify_version.py`) and IMMUTABLE — this work REUSES its
training code unchanged and adds a service + client layer under `cloud/`. Theory (F, world
def, exam, settlement math) is byte-for-byte the local training; any diff altering a learned
object or F is OUT OF SCOPE → stop and report.

## The boundary (grounded in the code — the load-bearing fact)

`ets/training/world.py` builds the world from **prototype cost matrices + masses**
(`Prototype.cost`, `Prototype.mass`) via entropic-GW; `WorldDef` is "gauge-invariant
intrinsic structure" (D, a, B, theta, couplings). So the stage-3 seam already exists:

- **DEVICE (never leaves):** raw audio (1), stage-2 recipes (2), rendered output. Ingest
  runs locally: raw audio → prototypes = **(cost matrices + masses)** = stage-3.
- **CLOUD (receives only stage-3):** `build_world` (anchor-fit) → NCE `LAMBDA` fit →
  exam (separation on the scramble family) → returns **world + exam receipts**.

Cost matrices are pairwise dimensionless geometry — no raw audio bytes — so uploading them
does not leak raw. This is CS-1..CS-5 by construction.

## MVP-1 scope (build the minimum that removes local training compute)

1. **Cloud training service** `cloud/service/` — stateless request-in/world-out:
   - Input: a JOB payload = list of prototypes `{cost: (n,n) float array, mass: (n,) float}`
     + training params (eps, exam config, seed). Serialized (npz/msgpack). NOTHING else.
   - Runs the EXISTING training: `ets.training.world.build_world(...)` → NCE `LAMBDA` fit →
     exam. Imports root `ets` unchanged; adds no training logic.
   - Output: the world (`.etsworld`-equivalent: D, a, B, theta, couplings, LAMBDA) + exam
     receipts (separation scores, scramble-family config, KILL-condition result).
   - Containerized (Dockerfile), runnable locally as the cloud stand-in for parity tests.
2. **Thin local CLI** `cloud/client/` — `ets-cloud train <corpus>`:
   - Ingest locally → prototypes (cost matrices + masses) → SERIALIZE ONLY stage-3 →
     POST to the service → receive world + receipts → VERIFY receipts locally → write the
     world file locally. Playback stays in the existing local app (unchanged).
   - A guard layer that can ONLY serialize the stage-3 fields (a whitelist encoder); it is
     structurally incapable of putting raw audio / recipes on the wire.
3. **Harness** `cloud/tests/`:
   - **MVP-A raw-never-uploaded** (LOAD-BEARING): static check — the client's upload encoder
     references only the stage-3 whitelist (cost, mass, params); + runtime check — capture
     the actual bytes sent for a real corpus and assert no raw-audio / recipe / rendered
     tensor is present. Prove it BITES: a fixture that tries to attach raw audio FAILS.
   - **MVP-B receipts-verified**: the client refuses a returned world whose exam receipts
     don't verify (re-derive/verify the separation + KILL condition against the received
     world; a tampered receipt is rejected).
   - **MVP-C parity**: train a corpus LOCALLY vs through the service on the SAME stage-3
     input → world is bit-comparable within the exam's tolerance (same relocated training,
     not a drifting reimplementation). Run the service locally to compare.
   - **MVP-D no-decoder**: static check — the service/cloud path imports no renderer/decoder
     and emits no audio; any audio the user hears is stitched LOCAL slices only.

## Hard rules (inherit CS-1..CS-5; a break is a WALL, not a patch)

- Only stage-3 (gauge-invariant cost structure + masses) crosses device→cloud. Raw audio +
  recipes NEVER uploaded. Rendered output stays local. No cloud decoder. World arrives with
  device-verifiable receipts. If shipping-fast tempts uploading raw audio "just for now" →
  STOP and report; ship offline-render instead. Never upload raw to hit a deadline.

## Environment honesty (this sandbox)

Real cloud provisioning needs the operator's cloud account — NOT possible from this sandbox.
Deliverable: the service + client + harness built deploy-ready (Dockerfile + a documented
deploy step), with the FULL flow verified HERE by running the service locally as the cloud
stand-in (MVP-C parity + MVP-A/B/D all runnable locally). The operator then deploys the
container to their cloud with the provided package. State exactly what remains local at each
step.

## Sequencing & discipline

Build MVP-1 → verify MVP-A/B/C/D → the operator can stop training locally. MVP-2 (cloud
settlement + web UI, offline render) and MVP-3 (polish) are separate, later. Prereg before
build; auditor PASS before merge; one-sentence disclosure of any contemplated divergence;
walls surfaced not patched; coverage honesty every report. Persistent versioning agent logs
each step to `LEDGER.md`.
