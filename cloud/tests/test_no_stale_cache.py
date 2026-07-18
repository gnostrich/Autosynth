"""Every response must forbid browser caching (Cache-Control: no-store).

Found live 2026-07-18: with no cache headers, a phone browser heuristically
cached the app HTML and kept rendering the RETIRED founding-demo page across
deploys — a stale-surface bug indistinguishable (to the user) from the demo
never having been removed. The app is one small page; always-fresh wins.
"""
import threading
import urllib.request

from cloud.companion.app import serve


def _server(tmp_path):
    httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
                  session_dir=str(tmp_path / "sess"))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def _head(base, path):
    req = urllib.request.Request(base + path, method="GET")
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:                  # gated paths still carry headers
        return e.code, dict(e.headers)


def test_html_and_api_are_never_cacheable(tmp_path):
    httpd, base = _server(tmp_path)
    try:
        # engine-free paths only: /api/world can pull the engine bridge, whose
        # tree-ownership assert trips under full-suite import pollution. The
        # headers come from the shared _send/_json helpers, so "/" (static
        # _send) + two _json endpoints cover every response path.
        for path in ("/", "/api/health", "/api/explore"):
            _, headers = _head(base, path)
            cc = headers.get("Cache-Control", "")
            assert "no-store" in cc, (
                f"{path} served without no-store (Cache-Control={cc!r}) — "
                f"browsers will show a stale app after deploys")
    finally:
        httpd.shutdown()
