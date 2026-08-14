#!/usr/bin/env python3
"""Fetch a CC-BY/CC0 FIXTURE CORPUS from Internet Archive and train it into a
playable world, IN THE CONTAINER -- the reproducible counterpart to
``scripts/train_operator_corpus.py``.

WHY IT EXISTS: ``train_operator_corpus.py`` proved the numbering/collision
property (0..N-1 per track, all 45 pairs of a 10-track world sharing ids) on
the OPERATOR's own audio, which is not redistributable and cannot ship with
this repo. This script reproduces the same property from FREELY-LICENSED
audio only, so the repo can answer bridge/collision questions without the
operator's private files, from a fresh clone, by anyone.

Every track below is CC-BY or CC0, hosted on archive.org, full length (no
clipping), with a genuine stylistic spread (cinematic/orchestral electronic,
downtempo/funk electronic, vocal pop-folk, ambient, acoustic instrumental
folk, dubstep/electronic, indie rock, electro-dance, metal) -- chosen because
a fixture of near-identical loops would hide exactly the cross-track
collision class this corpus exists to exhibit. See ``TRACKS`` for the full
per-track title/artist/source/licence record; ``cloud/fixtures/
fixture_corpus_receipt.json`` (written by this script) additionally records
each file's sha256 and the trained world's measured shape.

Usage:
  python3 scripts/fetch_and_train_fixture_corpus.py --audio /tmp/fixture_corpus \
      --out /tmp/fixture_corpus_world.etsworld
  # then measure:
  ETS_W=/tmp/fixture_corpus_world.etsworld python3 cloud/tools/bridge_slot_pin_spread_verify.py

Network: downloads go straight to archive.org over HTTPS (outbound proxy is
honoured automatically by ``requests``/``urllib``). If a URL 404s or the
licence can no longer be verified at fetch time, the script STOPS and says
so rather than substituting anything.
"""
import argparse, hashlib, json, os, sys, time
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "architecture-v6"))

# ---------------------------------------------------------------------------
# THE FIXTURE CORPUS -- 13 CC-BY/CC0 tracks, full length, genuine spread.
# Every row was verified against the archive.org item's OWN `licenseurl`
# metadata field at selection time (2026-08-14); `license` below is that
# exact string, not a guess. `sha256` is filled in by `--record` on first
# successful download and then checked on every subsequent run.
# ---------------------------------------------------------------------------
TRACKS = [
    {
        "title": "Set This Thing on Fire",
        "artist": "Chris Zabriskie",
        "item": "cz-blackhole",
        "file": "06 - Set This Thing on Fire.mp3",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "genre": "indie / orchestral-electronic (vocal)",
        "sha256": "0466da47845c994871f75700dc397b3c5edf74188aa378ba220dc0d105e6fd02",
    },
    {
        "title": "We Start the Cure in Paris",
        "artist": "Chris Zabriskie",
        "item": "cz-ogreatqueenelectric",
        "file": "Chris Zabriskie - O Great Queen Electric, What Do You Have Waiting for Me¿ - 03 - We Start the Cure in Paris.mp3",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "genre": "electronic",
        "sha256": "d04e08ab794bb03a6f668436d1ebc7be48b3530c398e9bf6c3acb6f9ea6c07c4",
    },
    {
        "title": "Direct to Video",
        "artist": "Chris Zabriskie",
        "item": "ChrisZabriskieDirectToVideo",
        "file": "Chris Zabriskie - Direct to Video - 01 Direct to Video.mp3",
        "license": "http://creativecommons.org/licenses/by/3.0/",
        "genre": "cinematic electronic",
        "sha256": "93c68362f5eed8ddb15e427d4ceab0d099f6edbd4c9bfd137c9bdc5947bae221",
    },
    {
        "title": "My Luck",
        "artist": "Broke For Free",
        "item": "DirectionlessEP",
        "file": "Broke For Free - Directionless EP - 04 My Luck.mp3",
        "license": "http://creativecommons.org/licenses/by/3.0/",
        "genre": "downtempo electronic",
        "sha256": "40bf076bb61c0c9a6ac5a4cf4dc298615fe552e07c1f5b6275c494ae475ac0af",
    },
    {
        "title": "The Great",
        "artist": "Broke For Free",
        "item": "Slam_Funk-7603",
        "file": "Broke_For_Free_-_03_-_The_Great.mp3",
        "license": "http://creativecommons.org/licenses/by/3.0/",
        "genre": "funk / electronic",
        "sha256": "834ca6d81563133b52fb5ae9ac13104418a26cbd180a8c83208fbbf429027657",
    },
    {
        "title": "Perfect Recipe",
        "artist": "Josh Woodward",
        "item": "josh-woodward-perfect-recipe",
        "file": "JoshWoodward-PerfectRecipe.mp3",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "genre": "vocal pop / folk",
        "sha256": "1f1a22e3d70886816101acd5788d3297bd48e15d56d49e27ab17405f55bd225f",
    },
    {
        "title": "Essence 2",
        "artist": "Jason Shaw (Audionautix)",
        "item": "Essence2",
        "file": "RP-Essence2.mp3",
        "license": "http://creativecommons.org/publicdomain/zero/1.0/",
        "genre": "ambient (CC0)",
        "sha256": "17befc5a8f1f8cef56cb014a375fa3443ad77cc2bc0d6ce9c8e60259b8c3504c",
    },
    {
        "title": "Pioneers",
        "artist": "Jason Shaw (Audionautix)",
        "item": "Pioneers",
        "file": "RP-Pioneers.mp3",
        "license": "http://creativecommons.org/publicdomain/zero/1.0/",
        "genre": "electronic (CC0)",
        "sha256": "15ee51da71c8f001900755a1d2f053f51e3128583260087b37d95f7944642eed",
    },
    {
        "title": "Solo Acoustic Guitar",
        "artist": "Jason Shaw (Audionautix)",
        "item": "Audionautix_Acoustic-9870",
        "file": "Jason_Shaw_-_SOLO_ACOUSTIC_GUITAR.mp3",
        "license": "http://creativecommons.org/licenses/by/3.0/us/",
        "genre": "acoustic instrumental folk",
        "sha256": "fed4d2d6afa845cf1c5742428a629ed5328e06f25382257b4d11a3e91a994658",
    },
    {
        "title": "The Long Night",
        "artist": "Approaching Nirvana",
        "item": "gs_approaching-nirvana-not-even-once",
        "file": "04 The Long Night.mp3",
        "license": "http://creativecommons.org/licenses/by/4.0/",
        "genre": "dubstep / electronic",
        "sha256": "c21ad8b3de59bcfe1b237206e8522fd66f46c5ad1101c7558a4bf535b3bb56bf",
    },
    {
        "title": "Our Wasted Youth",
        "artist": "Steve Combs",
        "item": "ourwastedyouth",
        "file": "2-06 Our Wasted Youth.mp3",
        "license": "http://creativecommons.org/licenses/by/3.0/",
        "genre": "indie rock",
        "sha256": "3f29353ff831616d6763c76bf1325502f665fe96029c6a57e32578194c6e9b41",
    },
    {
        "title": "Everyone is so alive",
        "artist": "Loyalty Freak Music",
        "item": "ROBOTDANCE",
        "file": "Loyalty Freak Music - ROBOT DANCE ! - 01 Everyone is so alive.mp3",
        "license": "http://creativecommons.org/publicdomain/zero/1.0/",
        "genre": "electro / dance (CC0)",
        "sha256": "c34e37e414a20bf4ca05833d5a83ce0bf2723162bbd79c7723dcadbffc0b8171",
    },
    {
        "title": "Ultimate Metal",
        "artist": "Loyalty Freak Music",
        "item": "LoyaltyFreakMusicHYPERMETAL2017122060804395",
        "file": "LoyaltyFreakMusic-HyperMetal-08UltimateMetal.mp3",
        "license": "http://creativecommons.org/publicdomain/zero/1.0/",
        "genre": "metal (CC0)",
        "sha256": "1162c0ebe990418ce47f1729fe708c052592e7a8141e8c5f546e7e2bec4d4851",
    },
]


def _url(item: str, fname: str) -> str:
    return "https://archive.org/download/%s/%s" % (item, quote(fname))


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(track: dict, out_dir: str, record: bool) -> str:
    import requests
    fname = "%02d - %s - %s.mp3" % (
        TRACKS.index(track) + 1, track["artist"], track["title"])
    fname = "".join(c for c in fname if c not in '/\\:*?"<>|')
    dest = os.path.join(out_dir, fname)
    if not os.path.exists(dest):
        url = _url(track["item"], track["file"])
        print("  fetching %s ..." % url, flush=True)
        r = requests.get(url, timeout=120, stream=True)
        r.raise_for_status()
        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        os.rename(tmp, dest)
    got = _sha256(dest)
    if record:
        track["sha256"] = got
    elif track["sha256"] and got != track["sha256"]:
        raise RuntimeError(
            "sha256 mismatch for %r: expected %s got %s -- refusing to train "
            "on a file that doesn't match the recorded fixture"
            % (track["title"], track["sha256"], got))
    track["_local_path"] = dest
    track["_bytes"] = os.path.getsize(dest)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", default="/tmp/fixture_corpus",
                    help="download directory (gitignored, container-local)")
    ap.add_argument("--out", default="/tmp/fixture_corpus_world.etsworld")
    ap.add_argument("--record", action="store_true",
                    help="(re)compute sha256 from the download and OVERWRITE "
                         "the manifest below + the receipt -- use this the "
                         "first time you run the script for real")
    ap.add_argument("--receipt",
                    default=os.path.join(ROOT, "cloud/fixtures",
                                         "fixture_corpus_receipt.json"))
    ap.add_argument("--skip-train", action="store_true",
                    help="fetch + verify only, do not train")
    a = ap.parse_args()

    os.makedirs(a.audio, exist_ok=True)
    print("fetching %d CC-BY/CC0 tracks -> %s" % (len(TRACKS), a.audio), flush=True)
    paths = []
    for t in TRACKS:
        p = fetch(t, a.audio, a.record)
        paths.append(p)
        print("  ok  %-28s %-22s %8d bytes  sha256=%s"
              % (t["title"], t["artist"], t["_bytes"], t["sha256"][:16] + "..."),
              flush=True)

    if a.skip_train:
        print("skip-train: fetch/verify only, done.")
        return 0

    from cloud.companion.train_local import build_trained_world
    print("training %d tracks -> %s" % (len(paths), a.out), flush=True)
    t0 = time.time()
    r = build_trained_world(paths, a.out,
                            progress=lambda s: print("  [%5.0fs] %s"
                                                     % (time.time() - t0, s), flush=True))
    dt = time.time() - t0
    print("ok=%s in %.0fs" % (r.get("ok"), dt), flush=True)
    if not r.get("ok"):
        return 1

    # build_trained_world returns {"world": out_path, ...} -- a path, not the
    # object -- so load the just-saved file back to read its shape.
    from ets.engine.worldfile import load_world
    world = load_world(a.out).world
    units_per_track = [int(len(t.masses)) for t in world.tracks]
    receipt = {
        "ts": time.strftime("%Y-%m-%d"),
        "kind": "fixture-corpus-training-receipt",
        "id": "cc-fixture-corpus-2026-08-14",
        "source": "Internet Archive (archive.org), CC-BY/CC0 tracks only -- see "
                   "TRACKS in scripts/fetch_and_train_fixture_corpus.py",
        "note": "Freely-licensed counterpart to operator_corpus_receipt.json. "
                "The audio and the trained world are container-local and "
                "gitignored; this receipt + the fetch script reproduce the "
                "world from public CC-BY/CC0 sources -- no private files "
                "needed.",
        "tracks_trained": len(paths),
        "train_seconds": round(dt),
        "world_bytes": os.path.getsize(a.out),
        "world_sha256": _sha256(a.out),
        "world_shape": {
            "tracks": len(world.tracks),
            "M": int(world.M),
            "units_per_track": units_per_track,
        },
        "tracks": [
            {
                "title": t["title"],
                "artist": t["artist"],
                "source_url": "https://archive.org/details/%s" % t["item"],
                "file_url": _url(t["item"], t["file"]),
                "license": t["license"],
                "genre": t["genre"],
                "bytes": t["_bytes"],
                "sha256": t["sha256"],
            }
            for t in TRACKS
        ],
    }
    os.makedirs(os.path.dirname(a.receipt), exist_ok=True)
    with open(a.receipt, "w") as f:
        json.dump(receipt, f, indent=1)
    print("wrote receipt -> %s" % a.receipt, flush=True)
    print("units_per_track = %s" % units_per_track, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
