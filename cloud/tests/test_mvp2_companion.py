"""MVP-2 phase-1 harness — the sealed companion's CS guards BITE.

MVP2-A  raw/recipes never leave the companion:
  * /api/ingest never contacts the cloud (a tripwire on the wire stays untouched)
  * a real train through the companion puts ONLY stage-3 on the wire
  * the whitelist encoder the companion inherits still refuses smuggled raw audio
MVP2-B  no cloud decoder on the companion's cloud path (static import check)
smoke   the full HTTP surface works offline (inproc): UI + ingest + status + train
"""
import io
import json
import threading
import urllib.request
from pathlib import Path

import numpy as np
import pytest

import cloud.client.cli as client_cli
from cloud.client.cli import save_prototypes
from cloud.common import assert_wire_whitelisted, decode_job, STAGE3_PROTO_FIELDS
from cloud.companion.app import Companion, serve
from cloud.tests.fixtures import make_synthetic_protos


def _bundle(tmp_path) -> Path:
    protos = make_synthetic_protos(n_tracks=4, K=6, seed=0)
    p = tmp_path / "protos.npz"
    save_prototypes(str(p), protos)
    return p


# ---------------- MVP2-A ----------------------------------------------------

def test_ingest_never_touches_the_cloud(tmp_path, monkeypatch):
    tripped = {"hit": False}
    def _tripwire(*a, **k):
        tripped["hit"] = True
        raise AssertionError("ingest must not contact the cloud")
    monkeypatch.setattr(client_cli, "post_job", _tripwire)

    comp = Companion(cloud_url="inproc", session_dir=str(tmp_path / "sess"))
    comp.ingest_bytes("song.wav", b"\x00\x01raw-audio-bytes")
    comp.ingest_bytes("more.wav", b"\xff" * 4096)
    assert tripped["hit"] is False
    assert set(comp.session_files()) == {"song.wav", "more.wav"}


def test_train_puts_only_stage3_on_the_wire(tmp_path, monkeypatch):
    sess = tmp_path / "sess"; sess.mkdir()
    save_prototypes(str(sess / "protos.npz"), make_synthetic_protos(4, 6, 0))

    seen = {}
    real = client_cli.post_job
    def _capture(job_bytes, service):
        seen["bytes"] = job_bytes
        return real(job_bytes, "inproc")
    monkeypatch.setattr(client_cli, "post_job", _capture)

    comp = Companion(cloud_url="inproc", session_dir=str(sess))
    out = comp.run_train(sweeps=3)
    assert out["ok"] is True

    # Inspect the ACTUAL captured wire bytes (not a rebuilt payload). allow_pickle=
    # False also refuses any smuggled object array outright. Every per-prototype key
    # must be a whitelisted stage-3 field; nothing audio-ish; canonical validator agrees.
    with np.load(io.BytesIO(seen["bytes"]), allow_pickle=False) as z:
        wire = {k: np.asarray(z[k]) for k in z.files}
    proto_keys = [k for k in wire if "." in k and k.split(".", 1)[0][:1] == "p"
                  and k.split(".", 1)[0][1:].isdigit()]
    assert proto_keys, "no per-prototype fields crossed the wire?"
    for k in proto_keys:
        assert k.split(".", 1)[1] in STAGE3_PROTO_FIELDS, f"off-whitelist field on wire: {k}"
    assert not any("audio" in k.lower() for k in wire), f"audio reached the wire: {list(wire)}"
    assert_wire_whitelisted(wire)      # the same check decode_job runs, on the real bytes


def test_smuggled_raw_audio_is_refused(tmp_path):
    # the companion inherits cloud.client's whitelist encoder; prove it BITES on the
    # actual wire: a proto carrying a smuggled .audio array must not put audio on the wire.
    from cloud.common import encode_job
    protos = make_synthetic_protos(2, 6, 0)
    protos[0].audio = np.random.randn(2048)          # smuggle attempt
    job = encode_job(protos, {"seed": 0})
    with np.load(io.BytesIO(job), allow_pickle=False) as z:  # object payload would fail here
        wire = {k: np.asarray(z[k]) for k in z.files}
    assert not any("audio" in k.lower() for k in wire), \
        f"smuggled audio reached the wire: {list(wire)}"
    for k in wire:
        if "." in k and k.split(".", 1)[0][:1] == "p" and k.split(".", 1)[0][1:].isdigit():
            assert k.split(".", 1)[1] in STAGE3_PROTO_FIELDS
    assert_wire_whitelisted(wire)      # canonical validator: clean


def test_reset_clears_the_corpus(tmp_path):
    # account-free "new corpus": one corpus at a time; reset wipes the session.
    comp = Companion(cloud_url="inproc", session_dir=str(tmp_path / "sess"))
    comp.ingest_bytes("a.wav", b"aaa")
    comp.ingest_bytes("b.wav", b"bbb")
    comp.last_receipt = {"n_anchors": 3}
    assert comp.session_files() == ["a.wav", "b.wav"]
    out = comp.reset()
    assert out["ok"] is True and out["cleared"] >= 2
    assert comp.session_files() == []
    assert comp.last_receipt is None


def test_serve_refuses_non_loopback():
    # the sealed-box invariant is structural, not just a default: a public bind is refused.
    with pytest.raises(SystemExit):
        serve(cloud_url="inproc", host="0.0.0.0", port=0)
    with pytest.raises(SystemExit):
        serve(cloud_url="inproc", host="10.0.0.5", port=0)
    # loopback forms are accepted
    httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0)
    httpd.server_close()


# ---------------- MVP2-B ----------------------------------------------------

def _imported_modules(py_path: Path):
    """Collect the dotted module names actually IMPORTED by a source file (AST —
    so prose/comments that merely mention a renderer don't trip the check)."""
    import ast
    mods = set()
    tree = ast.parse(py_path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                mods.add(n.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
            for n in node.names:
                mods.add(node.module + "." + n.name)
    return mods


def test_companion_cloud_path_imports_no_decoder():
    # CS-4: the companion + the guarded client import NO renderer/decoder. (Local
    # playback in phase 2 is a LOCAL decoder in its own module — never on this
    # cloud path — so the guarantee is "no CLOUD decoder", checked here by import.)
    cli = Path(client_cli.__file__).with_name("cli.py")
    comp = Path(__file__).resolve().parents[1] / "companion" / "app.py"
    banned = {"ets.render", "ets.writer", "soundfile", "sounddevice", "pyaudio"}
    banned_leaf = {"build_index"}
    for path in (cli, comp):
        mods = _imported_modules(path)
        hit = {m for m in mods if m in banned
               or any(m == b or m.startswith(b + ".") for b in banned)
               or m.rsplit(".", 1)[-1] in banned_leaf}
        assert not hit, f"{path.name} imports a renderer/decoder on the cloud path: {hit}"


# ---------------- HTTP smoke (offline / inproc) -----------------------------

@pytest.fixture
def companion_server(tmp_path):
    httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
                  session_dir=str(tmp_path / "sess"))
    t = threading.Thread(target=httpd.serve_forever, daemon=True); t.start()
    yield "http://127.0.0.1:%d" % httpd.server_address[1]
    httpd.shutdown(); httpd.server_close()


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.status, r.read()

def _post(url, body, headers):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, r.read()


def test_http_surface_end_to_end(companion_server, tmp_path):
    base = companion_server
    # UI served
    code, html = _get(base + "/")
    assert code == 200 and b"ETS" in html and b"<!doctype html>" in html.lower()
    # health
    code, h = _get(base + "/api/health")
    assert code == 200 and json.loads(h)["ok"] is True
    # ingest a stage-3 bundle (stands in for locally-ingested audio)
    save_prototypes(str(tmp_path / "protos.npz"), make_synthetic_protos(4, 6, 0))
    payload = (tmp_path / "protos.npz").read_bytes()
    code, resp = _post(base + "/api/ingest", payload,
                       {"X-Filename": "protos.npz", "Content-Type": "application/octet-stream"})
    assert code == 200 and "protos.npz" in json.loads(resp)["files"]
    # status reflects it
    code, s = _get(base + "/api/status")
    assert code == 200 and "protos.npz" in json.loads(s)["files"]
    # train (inproc) -> verified world
    code, tr = _post(base + "/api/train", b"{}", {"Content-Type": "application/json"})
    body = json.loads(tr)
    assert code == 200 and body["ok"] is True and "receipt" in body
    assert int(body["receipt"]["n_anchors"]) >= 1
    # reset -> corpus cleared (account-free "new corpus")
    code, rs = _post(base + "/api/reset", b"", {})
    assert code == 200 and json.loads(rs)["files"] == []
