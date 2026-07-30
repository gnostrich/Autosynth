"""PREREG-waveform-scrub — /api/wavemap END-TO-END verification (standalone).

Proves the READ-ONLY material map by RUNNING it, not by asserting it (the
``cloud/tools/*_verify.py`` pattern). Five checks, each printed PASS/FAIL:

  [1] STORED-q          every served slice's q is the exact indicator of
                        ``world.index.unit_role[(track, unit)]``, and its span/mass
                        are ``provenance_index``/``masses`` exactly — re-read
                        INDEPENDENTLY from the world file, not from the bridge.
  [2] REAL ENVELOPE     the served peaks are reproduced by an INDEPENDENT decode
                        (``soundfile`` + numpy bucketing, a different code path from
                        the bridge's ``librosa.load``) of the user's own file.
  [3] WIRE              GET /api/wavemap returns exactly the bridge's map with the
                        session's honest lane names (the frozen contract shape).
  [4] READ-ONLY         the produced tape is byte-identical with the wavemap never
                        computed / computed / computed-then-deleted.
  [5] NO UNIT TO WRITER a TRACKS-view steer sequence (channel_bias + track_role_bias)
                        reaches the single tilt-construction point with NO unit-id-
                        typed grain; a payload carrying the GRID ``unit_bias`` grain
                        DOES (so the instrument is proven non-vacuous).

A world that cannot yield an honest map (the demo world's EMBEDDED sources, a missing
source file, no stored per-unit role) prints the refusal and exits 0 unless
``--require-map`` — refusing honestly is a correct outcome, not a failure.

Usage:
  python3 cloud/tools/wavemap_verify.py [--world PATH] [--bars N] [--require-map]
Default world: ``$ETS_WAVEMAP_WORLD`` or ``demo.etsworld`` (which will refuse — point
it at a trained world, e.g. a session's ``trained.etsworld``, for the full run).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))   # arch-v6 owns `import ets`

import numpy as np

_RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _RESULTS.append((name, bool(ok), detail))
    print("  [%s] %-22s %s" % ("PASS" if ok else "FAIL", name, detail))
    return bool(ok)


def _player(world: str, is_trained: bool = True):
    from cloud.companion.engine_bridge import StreamPlayer
    return StreamPlayer(world, seed=0, is_trained=is_trained,
                        eigen_n_seed=2, eigen_n_bar=2)


# --- [1] stored q / spans / masses ------------------------------------------

def check_stored(world_path: str, wm: dict) -> None:
    from ets.engine.worldfile import load_world
    w = load_world(world_path).world
    M = int(w.M)
    bad_q = bad_span = bad_mass = 0
    n = 0
    for tr in w.tracks:
        tid = str(int(tr.track_id))
        served = {int(s[2]): s for s in wm["tracks"][tid]["slices"]}
        prov = tr.provenance_index
        for j in range(len(prov)):
            uid = int(prov["unit_id"][j])
            s = served.get(uid)
            if s is None:
                bad_q += 1
                continue
            q = [0.0] * M
            q[int(w.index.unit_role[(int(tr.track_id), uid)])] = 1.0
            n += 1
            if list(s[4]) != q:
                bad_q += 1
            if (s[0] != float(prov["src_start"][j]) / float(tr.sr)
                    or s[1] != float(prov["src_end"][j]) / float(tr.sr)):
                bad_span += 1
            if s[3] != float(tr.masses[j]):
                bad_mass += 1
    check("stored-q", bad_q == 0 and n > 0,
          "%d units compared, %d q mismatches" % (n, bad_q))
    check("stored-spans", bad_span == 0, "%d span mismatches" % bad_span)
    check("stored-masses", bad_mass == 0, "%d mass mismatches" % bad_mass)


# --- [2] independent envelope reproduction ----------------------------------

def check_envelope(world_path: str, wm: dict) -> None:
    import soundfile as sf
    from ets.engine.worldfile import load_world
    wf = load_world(world_path)
    worst = 0.0
    resampled = []
    for tr in wf.world.tracks:
        tid = int(tr.track_id)
        path = wf.sources["paths"][tid]
        y, sr = sf.read(path, dtype="float64", always_2d=True)
        y = y.mean(axis=1)
        if int(sr) != int(tr.sr):
            resampled.append(tid)          # a resampling decode: not comparable exactly
            continue
        n = int(tr.n_samples)
        edges = np.linspace(0, n, len(wm["tracks"][str(tid)]["peaks"]) + 1).astype(int)
        a = np.abs(y)
        mine = [min(1.0, float(a[lo:hi].max())) if hi > lo and lo < len(a) else 0.0
                for lo, hi in zip(edges[:-1], edges[1:])]
        served = wm["tracks"][str(tid)]["peaks"]
        worst = max(worst, float(np.max(np.abs(np.asarray(mine) - np.asarray(served)))))
    check("real-envelope", worst <= 1e-6,
          "max |independent - served| = %.3g%s" % (
              worst, " (skipped resampled tracks %s)" % resampled if resampled else ""))


# --- [3]/[4]/[5] live server + engine ---------------------------------------

def _serve(player, session_dir: str):
    from cloud.companion.app import serve
    httpd = serve(cloud_url="inproc", host="127.0.0.1", port=0,
                  session_dir=session_dir, public=True)
    httpd.hub.playable_for = lambda session: player
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


def _get(base: str, path: str):
    import urllib.error
    try:
        with urllib.request.urlopen(base + path, timeout=600) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def _post(base: str, path: str, payload: dict):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.status


def _bars(p, n: int) -> str:
    h = hashlib.sha256()
    for _ in range(n):
        pcm, _roles = p.produce_one_bar()
        h.update(pcm)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wavemap_verify")
    ap.add_argument("--world", default=os.environ.get("ETS_WAVEMAP_WORLD",
                                                      "demo.etsworld"))
    ap.add_argument("--bars", type=int, default=2)
    ap.add_argument("--require-map", action="store_true",
                    help="treat an honest refusal as a FAILURE (use on a world that "
                         "must serve a map)")
    args = ap.parse_args(argv)
    world = args.world
    print("world: %s" % world)

    p = _player(world)
    wm = p.wavemap()
    if not wm.get("ok"):
        print("  REFUSED (honest): %s" % wm.get("error"))
        if args.require_map:
            check("served", False, "map required but refused")
            return 1
        return 0
    print("  served: M=%d sr=%d tracks=%d slices=%d" % (
        wm["M"], wm["sr"], len(wm["tracks"]),
        sum(len(t["slices"]) for t in wm["tracks"].values())))
    print("  q_source: %s" % wm["q_source"])

    check_stored(world, wm)
    check_envelope(world, wm)

    side = str(world) + ".wavemap.json"
    httpd, base = _serve(p, os.path.join(os.path.dirname(os.path.abspath(world)),
                                         "_wavemap_verify_sess"))
    try:
        # [3] WIRE: the route serves exactly the bridge map + honest lane names.
        status, body = _get(base, "/api/wavemap")
        _, world_info = _get(base, "/api/world")
        names_agree = ({k: v["name"] for k, v in body.get("tracks", {}).items()}
                       == {str(k): v for k, v in (world_info.get("track_names") or {}).items()})
        shape_ok = (status == 200 and set(body) == {"ok", "M", "sr", "q_source", "tracks"}
                    and all(set(t) == {"name", "duration_s", "peaks", "slices"}
                            for t in body["tracks"].values()))
        stripped = {tid: {k: v for k, v in t.items() if k != "name"}
                    for tid, t in body["tracks"].items()}
        bridge_stripped = {tid: {k: v for k, v in t.items() if k != "name"}
                           for tid, t in wm["tracks"].items()}
        check("wire-contract", shape_ok, "status=%s keys ok=%s" % (status, shape_ok))
        check("wire-same-map", stripped == bridge_stripped,
              "route payload == bridge map (names aside)")
        check("wire-names", names_agree, "lane names == /api/world track_names")

        # [4] READ-ONLY: never computed / computed / deleted -> one tape.
        for f in (side, side + ".tmp"):
            if os.path.exists(f):
                os.remove(f)
        h_never = _bars(_player(world), args.bars)
        p2 = _player(world)
        p2.wavemap()
        h_with = _bars(p2, args.bars)
        for f in (side, side + ".tmp"):
            if os.path.exists(f):
                os.remove(f)
        h_del = _bars(_player(world), args.bars)
        check("read-only-audio", h_never == h_with == h_del,
              "%s / %s / %s" % (h_never[:12], h_with[:12], h_del[:12]))

        # [5] NO UNIT-ID TO THE WRITER (instrument the tilt construction).
        def run(payloads):
            pl = _player(world)
            httpd.hub.playable_for = lambda session, _p=pl: _p
            seen = []
            orig = pl.engine._tilt_for

            def spy(u, *a, **kw):
                c = kw.get("channel_logbias")
                seen.append(sorted(c.keys()) if isinstance(c, dict) else None)
                return orig(u, *a, **kw)
            pl.engine._tilt_for = spy
            for payload in payloads:
                _post(base, "/api/steer", payload)
                pl.produce_one_bar()
            return seen, pl._unit_bias

        tracks_view = [{"region": [], "channel_bias": [0.6] + [0.0] * 8,
                        "track_role_bias": [[0, 0, 0.5]]}]
        seen, ub = run(tracks_view)
        check("no-unit-to-writer",
              all(g is None or "unit" not in g for g in seen) and ub is None,
              "grains=%s unit_bias=%s" % (seen, ub))
        seen_v, _ = run([dict(tracks_view[0], unit_bias={"3": 0.9})])
        check("instrument-bites", any(g and "unit" in g for g in seen_v),
              "a unit_bias payload DOES show up as a unit grain: %s" % seen_v)
    finally:
        httpd.shutdown()
        httpd.server_close()

    failed = [n for n, ok, _ in _RESULTS if not ok]
    print("\n%s (%d checks, %d failed)" % ("PASS" if not failed else "FAIL: " + ", ".join(failed),
                                           len(_RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
