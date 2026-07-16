"""ETS cloud MVP-1 — a hosted TRAINING service that offloads the heavy anchor-fit.

This package is a SERVICE + CLIENT + HARNESS layer built STRICTLY on top of the
verified engine-v1 (`ets`). It imports root `ets` training code UNCHANGED and adds
NO training logic and NO learned object: the world it returns is byte-identical to
what local training produces on the same stage-3 input.

The one rule that cannot bend (CS-1..CS-5): ONLY stage-3 — gauge-invariant
prototype cost matrices + masses (+ the two prototype histograms the anchor-fit
consumes) + declared training params — may cross device->cloud. Raw audio and
stage-2 recipes are NEVER serialized. There is no decoder/renderer in the cloud
path; playback stays in the existing local app.

See cloud/PREREG-cloud-mvp1.md (authoritative) and cloud/service/README.md.
"""
