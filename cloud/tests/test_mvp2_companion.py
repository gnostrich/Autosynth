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


def test_steer_is_the_only_settlement_input():
    # MVP2-D (server boundary): the engine's settlement input (the region-tilt lane)
    # is mutated ONLY via set_region, and set_region is reached ONLY from /api/steer.
    # (play/stop are transport, not settlement control.) Static so it runs in the
    # root-ets suite without loading the arch-v6 engine.
    src = (Path(__file__).resolve().parents[1] / "companion" / "app.py").read_text()
    assert src.count(".set_region(") == 1, "set_region must have exactly ONE call site"
    steer = src.index('"/api/steer"')
    call = src.index(".set_region(")
    play = src.index('"/api/play"')
    assert steer < call < play, "set_region must live inside the /api/steer handler only"


def test_fe_single_control_and_no_external_calls():
    # MVP2-D (browser boundary) + CS-1 (no external calls from the page). The served
    # UI's ONLY engine-settlement control is POST /api/steer; every network call is
    # same-origin (the local companion) — the browser never talks to Vercel/Railway.
    import re
    html = (Path(__file__).resolve().parents[1] / "companion" / "static" / "index.html").read_text()
    externals = re.findall(r'(?:fetch|EventSource)\(\s*["\'](https?://[^"\']+)', html)
    assert not externals, f"FE makes external network calls: {externals}"
    targets = re.findall(r'(?:fetch|EventSource)\(\s*["\'](/[^"\'?]*)', html)
    assert targets, "no API calls found in the FE?"
    assert all(t.startswith("/api/") for t in targets), \
        f"unexpected FE call target(s): {[t for t in targets if not t.startswith('/api/')]}"
    assert targets.count("/api/steer") == 1, "steer must be the single engine-control call"


def test_entrypoint_resolves_archv6_engine():
    # The pin bug the auditor caught: under the -m import order, root engine-v1
    # could shadow architecture-v6 (no live cap). Run the REAL import order in a
    # subprocess (can't in-process — the root-ets suite already imported ets) and
    # assert the capped arch-v6 engine wins.
    import subprocess
    import sys
    import textwrap
    code = textwrap.dedent('''
        import cloud.companion                 # __init__ imports app (appends repo-root)
        import cloud.companion.__main__        # runs the arch-v6 pin (like -m)
        import ets.engine.engine as e
        assert hasattr(e, "_playback_soft_limit") and hasattr(e, "bar_role_activity"), e.__file__
        print("PIN_OK", e.__file__)
    ''')
    root = str(Path(__file__).resolve().parents[2])
    r = subprocess.run([sys.executable, "-c", code], cwd=root,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "PIN_OK" in r.stdout and "architecture-v6" in r.stdout, r.stdout


def test_streaming_and_control_routes_present():
    src = (Path(__file__).resolve().parents[1] / "companion" / "app.py").read_text()
    for route in ('"/api/world"', '"/api/steer"', '"/api/play"', '"/api/stop"',
                  '"/api/stream"', '"/api/telemetry"'):
        assert route in src, f"missing instrument route {route}"


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


def test_train_routes_audio_to_seam_and_npz_to_geometry():
    # The train->play seam is the ONLY new branch. Prove the routing statically (no
    # arch-v6 load): run_train reaches cloud.companion.train_local's build_trained_world
    # when raw audio is present, and the geometry-only cloud.client.train otherwise.
    src = (Path(__file__).resolve().parents[1] / "companion" / "app.py").read_text()
    # audio branch delegates to the lazily-imported seam module
    assert "cloud.companion.train_local" in src and "build_trained_world" in src, \
        "run_train must delegate the audio branch to train_local.build_trained_world"
    # the geometry-only branch is still the guarded cloud.client.train
    assert "from cloud.client.cli import train" in src, \
        "the .npz/offline branch must keep the geometry-only cloud.client.train path"
    # routing is by extension (raw audio vs bundle), single decision channel
    assert "_AUDIO_EXTS" in src, "run_train must route by audio extension"


def test_run_train_routes_audio_to_seam_runtime(tmp_path, monkeypatch):
    # RUNTIME (not just static): raw audio actually drives the seam and repoints to
    # the trained world. Monkeypatch the seam builder + the player so it runs in the
    # root-ets suite (no arch-v6 load) yet exercises the real branch logic.
    import cloud.companion.train_local as tl
    import cloud.companion.engine_bridge as eb
    calls = {}
    def fake_build(audio_paths, out_path, cloud_url, **kw):
        calls["audio"] = list(audio_paths); calls["out"] = out_path
        return {"receipt": {"n_anchors": 3}, "sigma_phi_disarmed": []}
    class FakePlayer:
        def __init__(self, path, seed=0, is_trained=False):
            calls["player_path"] = path; calls["is_trained"] = is_trained
        def start(self):                       # pre-warm target (OPEN_ENDS #21d)
            calls["prewarmed"] = True
    monkeypatch.setattr(tl, "build_trained_world", fake_build)
    monkeypatch.setattr(eb, "StreamPlayer", FakePlayer)

    comp = Companion(cloud_url="inproc", session_dir=str(tmp_path / "s"))
    comp.ingest_bytes("clip.wav", b"RIFF0000WAVE")     # audio extension
    out = comp.run_train()
    assert out["ok"] and out["is_trained"] is True and out["playback"] == "live"
    assert calls.get("audio") and calls.get("is_trained") is True
    assert comp._is_trained is True and comp.play_world == str(comp.trained_world_path)


def test_run_train_routes_npz_away_from_seam_runtime(tmp_path, monkeypatch):
    # RUNTIME: a .npz bundle takes the geometry-only path and NEVER calls the seam.
    import cloud.companion.train_local as tl
    tripped = {"seam": False}
    monkeypatch.setattr(tl, "build_trained_world",
                        lambda *a, **k: tripped.__setitem__("seam", True) or {})
    sess = tmp_path / "s"; sess.mkdir()
    save_prototypes(str(sess / "protos.npz"), make_synthetic_protos(4, 6, 0))
    comp = Companion(cloud_url="inproc", session_dir=str(sess))
    out = comp.run_train(sweeps=3)
    assert out["ok"] and not out.get("is_trained")
    assert tripped["seam"] is False, "the .npz path must NOT invoke the audio seam"


def test_seam_module_wire_exit_is_only_post_job():
    # CS-1 for the seam: the ONLY thing train_local puts on the wire is the stage-3
    # job via the guarded post_job. It must NOT call cloud.client.cli.train (which
    # re-ingests) and must NOT serialize tracks/audio. Static import check.
    tl = Path(__file__).resolve().parents[1] / "companion" / "train_local.py"
    mods = _imported_modules(tl)
    assert "cloud.client.cli.post_job" in mods or "cloud.client.cli" in mods, \
        "train_local must reach the cloud through post_job"
    assert "cloud.client.cli.train" not in mods, \
        "train_local must NOT use the re-ingesting train(); only the whitelist exit"
    # the wire encoder is the shared whitelist encoder — the single seam definition
    assert "cloud.common.encode_job" in mods or "cloud.common" in mods


def test_reset_reverts_trained_state(tmp_path):
    # reset is the operator's "reset button and all": after a trained repoint, reset
    # must revert play_world to the demo, drop the cached player, and clear is_trained.
    comp = Companion(cloud_url="inproc", session_dir=str(tmp_path / "sess"))
    demo = comp.play_world
    # simulate a completed audio train having repointed the instrument
    comp.play_world = str(comp.trained_world_path)
    comp._is_trained = True
    comp._player = object()          # a stale cached player
    comp.last_receipt = {"n_anchors": 3}
    out = comp.reset()
    assert out["ok"] is True
    assert comp._is_trained is False, "reset must clear the trained flag"
    assert comp.play_world == demo, "reset must revert play_world to the demo world"
    assert comp._player is None, "reset must drop the cached player"
    assert comp.last_receipt is None


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
