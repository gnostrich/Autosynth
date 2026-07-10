"""Launch the M4 panel (build M4 only after M3 outcome (a) — see LEDGER).

    python scripts/run_panel.py [--port 8765]

Opens a tiny stdlib HTTP+WebSocket server; visit the printed URL, click
'enable audio', and steer the orbit live.
"""

from __future__ import annotations

import argparse

import _bootstrap as boot


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    from basin.panel.server import serve
    serve(boot.project_dir(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
