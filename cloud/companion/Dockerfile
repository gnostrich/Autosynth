# ETS companion — PUBLIC Railway web app (R6 phase 2).
#
# Serves the browser instrument UI + /api/* behind a per-visitor session registry
# and an access-key gate (ETS_ACCESS_KEYS). Ships with the COMMITTED self-contained
# demo world (demo.etsworld: embedded audio, no external files, no copyright) and
# ALSO enables upload-your-own-tracks: a key-holder drops audio, trains in this
# container (cloud_url=inproc: this box IS the server, no external calls), and plays
# their own corpus. Play/steer/telemetry render SERVER-SIDE.
#
# Because ingest is enabled, this image installs the INGEST-only beat-clock stack
# (torch CPU wheel + beat_this) ON TOP of the play deps (numpy/scipy/soundfile/
# librosa/scikit-learn/python-osc). torch is used ONLY on the ingestion path (beat
# detection); the theory/generative render loop stays torch-free.
#
# Build context is the REPO ROOT:
#     docker build -f cloud/companion/Dockerfile -t ets-companion .
#     docker run --rm -e PORT=8080 -e ETS_ACCESS_KEYS=... -p 8080:8080 ets-companion
FROM python:3.11-slim

# System libs: libsndfile for soundfile; ffmpeg/llvm for librosa's audio backend.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# PLAY deps: the arch-v6 engine loads these at import on the play path —
# python-osc (osc_io), librosa (render), scikit-learn (geometry).
RUN pip install --no-cache-dir numpy scipy soundfile python-osc librosa scikit-learn

# PHASE-2 INGEST deps (upload-your-own-tracks): the CPU-only torch + torchaudio
# pair + beat_this for the beat clock. torchaudio MUST be installed here from the
# CPU wheel index alongside torch — beat_this imports torchaudio, and if it isn't
# already present pip pulls the DEFAULT-PyPI (CUDA) torchaudio, which drags in a
# CUDA torch and then fails at import with `libcudart.so.13: cannot open shared
# object file` (no CUDA in this slim image). Pinning both to the CPU-verified pair
# keeps the whole stack CPU-only and reproducible. These add ~1.5 GB / slow the
# build; they are what makes hosted training possible.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch==2.13.0+cpu torchaudio==2.11.0+cpu
RUN pip install --no-cache-dir beat_this
# BAKE the beat_this checkpoint into the image (it is NOT bundled and otherwise
# downloads at runtime — which would stall/fail the first training on Railway).
RUN python -c "from beat_this.inference import File2Beats; File2Beats(checkpoint_path='final0', dbn=False)"

WORKDIR /app

# Copy ONLY what phase-1 play/steer/telemetry needs, and nothing heavy:
#   * architecture-v6/ets/  — the ui-v5 engine tree (live cap + telemetry); the
#     render bridge pins it first on sys.path. (NOT architecture-v6/cache|instances.)
#   * architecture-v6/scripts/run_sigma_phi.py — the REGISTERED σ_φ estimator. The
#     train->play seam (cloud.companion.train_local._instrument_std) loads this file
#     by path to reuse its `_std` VERBATIM when it measures + embeds the trained
#     corpus's own σ_φ. Without it, training raises FileNotFoundError. It is
#     self-contained (stdlib + numpy) and loading it defines `_std` only — its
#     calibration main() runs only under __main__, never here.
#   * ets/                  — root engine-v1, needed for cloud.* imports.
#   * cloud/                — the companion server + UI (static/index.html) + client.
#   * demo.etsworld         — the committed, self-contained demo world.
# Explicitly EXCLUDED (never copied): corpus.etsworld, corpus/, samples/,
# instantiations/, cache/, and the other architecture-v* trees.
COPY architecture-v6/ets/ /app/architecture-v6/ets/
COPY architecture-v6/scripts/run_sigma_phi.py /app/architecture-v6/scripts/run_sigma_phi.py
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
