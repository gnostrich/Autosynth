# ETS cloud training service (MVP-1) — the anchor-fit, offloaded.
#
# Build context is the REPO ROOT (the service reuses root `ets` by import):
#     docker build -f cloud/service/Dockerfile -t ets-cloud-train .
#     docker run --rm -p 8765:8765 ets-cloud-train
#
# The image contains ONLY the engine geometry needed for the anchor-fit and the
# stateless HTTP wrapper. No renderer/decoder, no audio libraries, no PortAudio —
# nothing in the cloud path emits audio (MVP-D). numpy is the sole runtime dep;
# scikit-learn/librosa/beat_this (ingestion) are NOT installed because ingestion
# runs on the device, never here.
FROM python:3.11-slim

RUN pip install --no-cache-dir "numpy>=1.24"

WORKDIR /srv
# Reuse root `ets` UNCHANGED (read-only), plus the cloud layer.
COPY ets/ /srv/ets/
COPY cloud/ /srv/cloud/

ENV PYTHONUNBUFFERED=1
# Bind to all interfaces inside the container; a PaaS (Railway/Fly/etc.) injects
# $PORT and the service picks it up (see app.main). EXPOSE is documentation only.
ENV HOST=0.0.0.0
EXPOSE 8765
CMD ["python", "-m", "cloud.service"]
