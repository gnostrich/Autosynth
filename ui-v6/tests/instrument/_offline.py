"""Shared fast fixed-seed offline render for the neutrality tests (F3-D/F3-E).

A ~1.5s synthetic clip (embedded bank, fixed seed) with a small knob trajectory —
byte-reproducible, and cheap enough not to contend with the long render under
samples/.
"""
from __future__ import annotations

_KNOB = ('{"events": [{"bar": 1, "lane": "region", '
         '"value": [1.0, 0.0, -0.5, 0.0]}]}')


def render_clip(tmp_path, seed=11, seconds=1.5):
    """Returns (audio, provenance_segments, n_samples, sr)."""
    import numpy as np
    from ets.engine.worldfile import load_world
    from ets.engine.engine import Engine, resolve_sigma, bar_schedule
    from ets.render import render
    from tests.harness.worldtools import (write_synthetic_worldfile,
                                          embedded_bank_for)

    tmp_path.mkdir(parents=True, exist_ok=True)
    wp = tmp_path / "w.etsworld"
    write_synthetic_worldfile(str(wp), seed=0)
    wf = load_world(str(wp))
    eng = Engine(wf, seed=seed, sigma=resolve_sigma(wf))
    knob = tmp_path / "knob.json"
    knob.write_text(_KNOB)
    res = eng.render_offline(seconds, knob_script=str(knob))

    # provenance for the same render (for the tape/cue models): re-drive the
    # writer identically and render each bar (deterministic — same seed/world).
    world = wf.world
    from ets.engine.engine import apply_knob_events, load_knob_script
    from ets.panel.lanes import default_lane_vector
    w = eng.writer.__class__(world, seed=seed)
    events = load_knob_script(str(knob))
    u = default_lane_vector(world.M)
    bank = embedded_bank_for(world)
    segs = []
    n = 0
    n_bars = max(1, int(round(seconds / w.bar_seconds)))
    for b in range(n_bars):
        u = apply_knob_events(u, events, b)
        tilt = eng._tilt_for(u)
        r = w.write_bar(tilt=tilt)
        sched = bar_schedule(world, r.rows, w.s_phase)
        _audio, prov = render(sched, bank)
        s = prov.segments.copy()
        s["out_start"] += n
        s["out_end"] += n
        segs.append(s)
        n += prov.n_samples
    segments = np.concatenate(segs) if segs else prov.segments[:0]
    return res.audio, segments, int(n), int(world.sr)
