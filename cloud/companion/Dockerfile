# ETS companion — PUBLIC Railway web app (R6 phase 1).
#
# Serves the browser instrument UI + /api/* for the COMMITTED self-contained
# demo world (demo.etsworld: embedded audio, no external files, no copyright).
# Play + steer + telemetry render SERVER-SIDE, in this container (cloud_url=inproc:
# this box IS the server, no external calls). Uploading the user's own audio
# (ingest/train) is a LATER phase and is intentionally NOT enabled here — so this
# image installs numpy/scipy/soundfile ONLY (no torch/librosa/beat_this), keeping
# it small and the first deploy fast.
#
# Build context is the REPO ROOT:
#     docker build -f cloud/companion/Dockerfile -t ets-companion .
#     docker run --rm -e PORT=8080 -p 8080:8080 ets-companion
FROM python:3.11-slim

# System libs: libsndfile for soundfile; ffmpeg/llvm for librosa's audio backend.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Phase-1 PLAY deps. The arch-v6 engine loads these at import time on the play path:
# python-osc (ets.engine.osc_io), librosa (ets.render.render), scikit-learn
# (geometry). NOT torch/beat_this — those are ingest/train only (a later phase),
# kept out to avoid a ~2GB image.
RUN pip install --no-cache-dir numpy scipy soundfile python-osc librosa scikit-learn beat_this

WORKDIR /app

# Copy ONLY what phase-1 play/steer/telemetry needs, and nothing heavy:
#   * architecture-v6/ets/  — the ui-v5 engine tree (live cap + telemetry); the
#     render bridge pins it first on sys.path. (NOT architecture-v6/cache|instances.)
#   * ets/                  — root engine-v1, needed for cloud.* imports.
#   * cloud/                — the companion server + UI (static/index.html) + client.
#   * demo.etsworld         — the committed, self-contained demo world.
# Explicitly EXCLUDED (never copied): corpus.etsworld, corpus/, samples/,
# instantiations/, cache/, and the other architecture-v* trees.
COPY architecture-v6/ets/ /app/architecture-v6/ets/
COPY architecture-v6/scripts/ /app/architecture-v6/scripts/
COPY ets/ /app/ets/
COPY cloud/ /app/cloud/
COPY demo.etsworld /app/demo.etsworld

# Public mode is the ONLY sanctioned non-loopback bind and exists for THIS deploy
# only. cloud_url stays inproc (no external calls — this container is the server).
ENV HOST=0.0.0.0 \
    ETS_PUBLIC=1 \
    ETS_CLOUD_URL=inproc \
    PYTHONUNBUFFERED=1

# Railway injects $PORT; python -m cloud.companion reads it in public mode.
# EXPOSE is documentation only.
EXPOSE 8080
CMD ["python", "-m", "cloud.companion"]
