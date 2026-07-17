"""Companion entry point.

Pin the ui-v5 engine tree (architecture-v6/ets = engine-v1 + the live playback
cap + read-only telemetry) FIRST on sys.path, before anything imports `ets`, so
the whole process runs on ONE consistent engine — both the local render bridge and
the cloud-train geometry (architecture-v6 is a full fork of engine-v1, so the
prototypes it computes match the root-engine service the receipt verifies against).
"""
import sys
from pathlib import Path

_ARCH_V6 = str(Path(__file__).resolve().parents[2] / "architecture-v6")
if _ARCH_V6 not in sys.path:
    sys.path.insert(0, _ARCH_V6)

from cloud.companion.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
