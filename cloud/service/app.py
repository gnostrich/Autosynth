"""The cloud training service: POST /train -> {world, receipt}.

Stateless. Each request carries its own stage-3 JOB; nothing persists between
requests. The heavy compute offloaded here is the anchor-fit's block-coordinate
barycenter solve (``anchors.build_world``); the returned world is byte-identical to
what the same call produces locally on the same input.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Root ETS anchor-fit, imported UNCHANGED. This is the ONLY training call the
# service makes. (No ets.writer / ets.render / audio anywhere.)
from ets.functional import anchors as an

from cloud.common import decode_job, encode_result


def handle_train(job_bytes: bytes) -> bytes:
    """Run the anchor-fit on a stage-3 JOB and return the encoded world+receipt.

    This is the pure, transport-agnostic core (used directly by in-process parity
    tests and by the HTTP handler alike — one code path, no 'hard input' fork)."""
    protos, params = decode_job(job_bytes)
    sigma = params.get("sigma", None)      # None means: use this set's median
    seed = int(params.get("seed", 0))
    sweeps = int(params.get("sweeps", 8))

    # EXISTING training, unchanged: self-size anchors + settle their supports (D,a)
    # to an F-descent certificate. info carries that certificate (F_final,
    # F_monotone, effective_rank) — the device-verifiable receipt.
    state, info = an.build_world(protos, seed=seed, sweeps=sweeps, sigma=sigma)
    return encode_result(state, info)


# ``run_job_inprocess`` is the same handle_train under a name the client uses when
# its --service target is the in-process stand-in (parity tests, offline runs).
run_job_inprocess = handle_train


class _TrainHandler(BaseHTTPRequestHandler):
    server_version = "ets-cloud/mvp1"

    def _send(self, code: int, body: bytes, ctype="application/octet-stream"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 (stdlib naming)
        if self.path.rstrip("/") != "/train":
            self._send(404, b"unknown endpoint (only POST /train)", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        job_bytes = self.rfile.read(length)
        try:
            result = handle_train(job_bytes)
        except Exception as exc:  # decode/whitelist/training error -> 400
            self._send(400, f"train failed: {exc}".encode(), "text/plain")
            return
        self._send(200, result)

    def do_GET(self):  # noqa: N802 — a trivial liveness probe
        if self.path.rstrip("/") in ("", "/health"):
            self._send(200, b"ets-cloud training service: POST /train", "text/plain")
        else:
            self._send(404, b"only POST /train", "text/plain")

    def log_message(self, *_a):  # keep the stand-in quiet during tests
        pass


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = ThreadingHTTPServer((host, port), _TrainHandler)
    print(f"ETS cloud training service listening on http://{host}:{port}  "
          f"(POST /train)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


def main() -> None:
    ap = argparse.ArgumentParser(description="ETS cloud training service (stand-in)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    serve(**vars(ap.parse_args()))


if __name__ == "__main__":
    main()
