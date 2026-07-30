"""WS-2 (backend half) — the wavemap carries NO telemetry, and the heatmap layer
cannot touch audio (PREREG-waveform-scrub).

WS-2 in the directive: "heatmap derives from placement telemetry only; frozen
telemetry -> frozen heatmap; deleting heatmap leaves audio byte-identical." The
backend's half of that is two claims, both gated here:

  A. NO SECOND FEED. ``/api/wavemap`` serves only the frozen world's material map
     (envelope + stored spans + stored q). The achieved-heatmap feed stays the
     EXISTING ``/api/telemetry`` ``nowplaying``/``nowplaying_unit`` reduction — this
     endpoint must not carry, mirror or duplicate any live/placement quantity. Gated
     as: the served key sets are exactly the frozen contract's, and no telemetry
     token appears anywhere in the payload. And since the map is a property of the
     FROZEN world, it is BYTE-STABLE: repeated calls, calls interleaved with bar
     production, and a fresh player that loads the sidecar all serialize identically.

  B. NO AUDIO PATH. The wavemap is a pure read. The produced tape is byte-identical
     whether the wavemap was NEVER computed, computed BEFORE playing, computed
     BETWEEN bars, or computed and then DELETED (sidecar removed). Four arms, one
     hash — if any differed, the "read-only overlay" claim would be false.

The interleaved arm also carries the WS-7 sense at the bridge level (a read cannot
perturb the tape); the route-level WS-7/WS-8 gates live in
test_wavemap_not_a_playhead.py.
"""
from __future__ import annotations

import json

from cloud.tests.test_wavemap_fixture import probe

_PROBE = r'''
import hashlib, json, os
from cloud.companion.engine_bridge import StreamPlayer

SIDE = WORLD + ".wavemap.json"
N_BARS = 2

def fresh():
    return StreamPlayer(WORLD, seed=0, is_trained=True)

def hash_bars(p, n=N_BARS, call_wavemap_after=None):
    """Produce n bars, hashing the PCM. If call_wavemap_after is set, the wavemap is
    requested BETWEEN bars (a read-only call in the middle of the stream)."""
    h = hashlib.sha256()
    wm = None
    for i in range(n):
        pcm, _roles = p.produce_one_bar()
        h.update(pcm)
        if call_wavemap_after is not None and i == call_wavemap_after:
            wm = p.wavemap()
    return h.hexdigest(), wm

def drop():
    for f in (SIDE, SIDE + ".tmp"):
        if os.path.exists(f):
            os.remove(f)

# --- ARM 1: the wavemap was NEVER computed (no sidecar, no call) --------------
drop()
h_never, _ = hash_bars(fresh())
sidecar_after_never = os.path.exists(SIDE)

# --- ARM 2: computed BEFORE playing (writes the sidecar) ---------------------
p2 = fresh()
wm2 = p2.wavemap()
h_before, _ = hash_bars(p2)
sidecar_after_compute = os.path.exists(SIDE)

# --- ARM 3: a FRESH player that loads the sidecar, wavemap read BETWEEN bars --
p3 = fresh()
h_mid, wm3 = hash_bars(p3, call_wavemap_after=0)

# --- ARM 4: sidecar DELETED again, fresh player, no wavemap call --------------
drop()
h_after_delete, _ = hash_bars(fresh())

# recompute once more from scratch (no sidecar) to prove the COMPUTED map equals
# the SIDECAR-loaded one byte for byte (a stale/differing cache would show here).
p5 = fresh()
wm5 = p5.wavemap()

emit({"h_never": h_never, "h_before": h_before, "h_mid": h_mid,
      "h_after_delete": h_after_delete,
      "sidecar_after_never": sidecar_after_never,
      "sidecar_after_compute": sidecar_after_compute,
      "s2": json.dumps(wm2), "s3": json.dumps(wm3), "s5": json.dumps(wm5),
      "top_keys": sorted(wm2.keys()),
      "track_keys": sorted(set(k for t in wm2["tracks"].values() for k in t))})
'''


def _d():
    if not hasattr(_d, "_v"):
        _d._v = probe(_PROBE)
    return _d._v


def test_audio_is_byte_identical_with_without_and_after_the_wavemap():
    """B: four arms, one hash. The material map has no audio path."""
    d = _d()
    hs = {k: d[k] for k in ("h_never", "h_before", "h_mid", "h_after_delete")}
    assert len(set(hs.values())) == 1, (
        "producing the tape is NOT byte-identical across the wavemap arms — the "
        f"read-only map has an audio path: {hs}")


def test_the_sidecar_is_created_only_by_a_wavemap_request():
    d = _d()
    assert d["sidecar_after_never"] is False, \
        "a player that was never asked for a wavemap must not write the sidecar"
    assert d["sidecar_after_compute"] is True, \
        "a wavemap request must persist its sidecar (compute once per world)"


def test_frozen_world_gives_a_byte_stable_wavemap():
    """A: frozen world -> frozen map. Computed fresh, loaded from the sidecar, and
    computed again after the sidecar was deleted — all identical serializations."""
    d = _d()
    assert d["s2"] == d["s3"], \
        "the sidecar-loaded wavemap differs from the freshly computed one"
    assert d["s2"] == d["s5"], \
        "recomputing the wavemap after deleting the sidecar gives a different map"


def test_wavemap_serves_no_telemetry():
    """A: exactly the frozen contract's keys, and not one live/placement quantity.
    The achieved heatmap must keep reading /api/telemetry's nowplaying_unit."""
    d = _d()
    assert d["top_keys"] == ["M", "ok", "q_source", "sr", "tracks"], d["top_keys"]
    assert d["track_keys"] == ["duration_s", "name", "peaks", "slices"], d["track_keys"]
    blob = json.loads(d["s2"])
    text = json.dumps({k: v for k, v in blob.items() if k != "q_source"})
    for token in ("nowplaying", "roles", "glow", "heat", "playing", "warmed",
                  "bar", "telemetry", "lanes", "region"):
        assert token not in text, (
            f"the wavemap payload mentions '{token}' — it must carry NO telemetry / "
            "no second decision channel, only the frozen world's material map")
