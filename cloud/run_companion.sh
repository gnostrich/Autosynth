#!/usr/bin/env bash
# One-command launcher for the ETS companion (local web instrument).
#
#   ./cloud/run_companion.sh
#
# Playing + steering the demo world needs NO token. To train your OWN audio,
# export your Railway token first:  export ETS_TRAIN_TOKEN=<token>
#
# Then open the printed URL in a browser.
set -uo pipefail
cd "$(dirname "$0")/.."                     # repo root (module + engine pin resolve from here)

CLOUD_URL="${ETS_CLOUD_URL:-https://geodesic-mixing-production.up.railway.app}"
PORT="${ETS_COMPANION_PORT:-8770}"
PY="${PYTHON:-python3}"

# Dependency check (the engine assumes these are present; core = play, extra = ingest/train).
"$PY" - <<'PYCHK'
import importlib.util as u, sys
core  = [m for m in ("numpy","scipy","soundfile") if u.find_spec(m) is None]
train = [m for m in ("librosa","beat_this","sklearn") if u.find_spec(m) is None]
if core:
    print("  ! missing PLAY deps:", core); sys.exit(3)
if train:
    print("  (note) training your own audio also needs:", train,
          "\n         pip install librosa beat_this scikit-learn")
PYCHK
if [ $? -eq 3 ]; then
  echo "Install: pip install numpy scipy scikit-learn librosa beat_this soundfile"
  exit 1
fi

echo "ETS companion  ->  http://localhost:${PORT}    (cloud: ${CLOUD_URL})"
if [ -z "${ETS_TRAIN_TOKEN:-}" ]; then
  echo "  mode: DEMO-only (no ETS_TRAIN_TOKEN). Set it to train your own audio."
else
  echo "  mode: training enabled."
fi
exec "$PY" -m cloud.companion --cloud-url "${CLOUD_URL}" --port "${PORT}"
