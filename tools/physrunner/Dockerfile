# ETS PHYSICS RUNNER — a TEMPORARY, isolated Railway compute surface for heavy
# conjugacy-physics ensembles (papers/DIRECTIVE-conjugacy-reconciliation.md §1B).
# Deploy this to a THROWAWAY Railway project, never alongside the live ets-web
# service. It is a THEORY INSTRUMENT on committed corpora: it settles committed
# worlds and returns NUMBERS ONLY (no audio, no recipes, no user-audio path).
#
# Build context is the REPO ROOT:
#     docker build -f tools/physrunner/Dockerfile -t ets-physrunner .
#     docker run --rm -e PORT=8790 -e RUNNER_TOKEN=secret -p 8790:8790 ets-physrunner
FROM python:3.11-slim

# System lib: libsndfile1 backs `soundfile`, which `librosa` imports at load. No
# ffmpeg (the runner never decodes audio — it only settles frozen worlds).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Runtime deps for the SETTLE path ONLY. Verified: `import ets.engine.engine`
# top-levels `librosa` (ets.render) + `python-osc` (ets.engine.osc_io), and the
# embedded demo world unpickles a SourceUnitBank via ets.render.sources ->
# ets.ingestion.filterbank -> `librosa`; librosa in turn brings numpy/scipy/
# soundfile/numba as its own deps. write_bar() itself uses numpy only (measured:
# a full settle pulls no scipy/numba/sklearn at runtime). NO torch / beat_this /
# scikit-learn — there is no training or geometry-fit path in the runner.
RUN pip install --no-cache-dir numpy scipy soundfile python-osc librosa

WORKDIR /app

# Copy ONLY what the settle path needs; nothing heavy, no user corpora:
#   * architecture-v6/ets/  — the ui-v5 engine tree the runner pins first on
#     sys.path (writer + settle + connector φ + embedded σ_φ calibration loader).
#   * ets/                  — root engine-v1 (parity; the runner forces arch-v6
#     first so `import ets` is never this one, but it is committed alongside).
#   * demo.etsworld         — the committed, self-contained demo world (the only
#     corpus shipped; synthetic fixtures, if added, go under tools/physrunner/).
#   * tools/physrunner/     — the runner service itself.
# Explicitly NOT copied: corpus.etsworld, corpus/, samples/, cache/, cloud/, the
# other architecture-v* trees.
COPY architecture-v6/ets/ /app/architecture-v6/ets/
COPY ets/ /app/ets/
COPY demo.etsworld /app/demo.etsworld
COPY tools/physrunner/ /app/tools/physrunner/

# Railway injects $PORT; the runner reads it. RUNNER_TOKEN MUST be set at deploy
# (an unset token fails closed — every /job is refused). Bind 0.0.0.0 (the token
# is the gate; this is a deliberately public, throwaway compute box).
ENV HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1
EXPOSE 8790
CMD ["python", "tools/physrunner/runner.py"]
