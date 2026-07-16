# ETS cloud training service (MVP-1)

A stateless HTTP service that offloads the **heavy anchor-fit** — the
block-coordinate barycenter solve inside `ets.functional.anchors.build_world` —
off the local machine. It imports root `ets` **unchanged** and adds no training
logic or learned object.

## What crosses the wire (and what never does)

Only **stage-3** crosses device -> cloud (CS-1..CS-5):

- a JOB = a list of prototypes, each reduced to exactly
  `{cost, mass, slot_hist, band_profile}` (gauge-invariant, dimensionless), plus
  declared params `{seed, sweeps, sigma}`. Serialized as an `npz` (no pickle).
- the RESULT = the world (`D, a, B, theta`, the per-track anchor couplings, and
  the gauge offsets) + a **device-verifiable receipt** (`F_final`, `F_monotone`,
  `effective_rank`, `n_anchors`, `sigma`).

**Never crosses:** raw audio (stage 1), stage-2 recipes (provenance, source spans,
unit coordinates), the private timbre/chroma descriptors, or any rendered tensor.
The wire encoder (`cloud/common/protocol.py`) is *structurally* incapable of
emitting them — see MVP-A in `cloud/tests/`.

There is **no decoder/renderer in the cloud path** and nothing here emits audio
(MVP-D). Playback stays entirely in the existing local app.

## Run locally (the cloud stand-in)

From the repo root:

```bash
python -m cloud.service --host 127.0.0.1 --port 8765
```

Health check: `GET /health`. Training: `POST /train` with the `npz` job bytes as
the raw body; the response body is the `npz` result.

## Deploy (operator step)

Real cloud provisioning needs the operator's cloud account and is not done from
the build sandbox. The container is deploy-ready:

```bash
# from the repo root (build context = repo root)
docker build -f cloud/service/Dockerfile -t ets-cloud-train .
docker run --rm -p 8765:8765 ets-cloud-train
# then push to your registry and run on your host / serverless container platform:
#   docker tag ets-cloud-train <registry>/ets-cloud-train:mvp1
#   docker push <registry>/ets-cloud-train:mvp1
# point the client at it:  ets-cloud train <corpus> --service https://<host>/
```

The service is stateless, so it scales horizontally with no shared state and needs
no GPU (numpy only).

## What remains local at each step

1. **Ingest** raw audio -> prototypes (needs the audio; stays on the device).
2. **Upload** stage-3 prototypes -> **cloud** runs the anchor-fit -> returns
   world + receipt.
3. **Verify** the receipt locally, then attach the **realization index**
   (`ets.writer.build_index`, needs the tracks) and save the playable
   `.etsworld` — all local. **Playback** is local, always.

## Wall (reported, not patched)

The NCE `LAMBDA` fit and the scramble **exam** (`ets.training.nce` +
`ets.training.scramble` + `ets.training.fiber`) consume full `Track` objects —
stage-2 recipe data (provenance `src_start/src_end`, per-unit phases, per-unit
descriptors). Under CS-1 they **cannot** be offloaded, so they stay local. MVP-1
offloads the one stage whose input is purely stage-3: the anchor-fit. See the
session report for the first-principles analysis.
