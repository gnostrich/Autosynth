# REPORT — web fabrication-class remediation (2026-07-18)

Operator directive: remediate 3 data-captioned decorative surfaces (fabrication
class; the tape is a REPEAT of the prior sine-art scar) per REAL-OR-ABSENT, and
add a standing caption guard. Prereg: `cloud/PREREG-webfab-remediation.md`.
Rollback tag: `pre-webfab-remediation-2026-07-18` @ `b054411`.

## Fix 1 — Output Tape (the repeat sine-art scar): REMOVED, honest-empty
`buildWave()` (the `Math.sin` cosmetic fill of `#wav`) deleted entirely; `#wav`
replaced by static honest-empty `#wavEmpty` "waveform not wired". Caption
`settled render · playhead from telemetry` → `playhead from telemetry ·
waveform not wired`. Playhead/clock stay (real: `applyTelemetry →
updateTape(d.t)`). No replacement art.

## Fix 2 — Lane Console: all four lanes WIRED real; inert sliders removed
Verified by running the bridge on `demo.etsworld`: the engine's per-bar Layer-0
statistics `r.phi` (`ets/writer/phi.py`) are real and live. The four lanes now
read intrinsically-bounded [0,1] reductions of produced state, transmitted on
the telemetry frame (`d.lanes`), same read-only pattern as `roles`/`nowplaying`:
region → occupancy concentration of `phi.region`; continuity →
`phi.cont / n_placements`; novelty → `phi.novelty` (already [0,1]); density →
filled-slot fraction. The inert `<input type=range>` affordance is gone (the
web's only engine input is the field). Caption `display · tolerances & weights`
→ `display · live arrangement statistics (read-only)`. The `62/74/33/55`
literals deleted; an absent value reads "—".

## Fix 3 — "drift" meter: real LOOP wired; SLIDE honestly disarmed (wall)
The proxy `(max−min of roles)*1.4` deleted. Replaced by the engine's real
gauge-drift split, read via the existing meter modules (no engine edit):
- **LOOP[g]** — `ets.meters.gauge_loop.loop_g` over a bounded window
  (deque maxlen=16, I-8) of committed `r.O`. Real, live, nonzero (≈±0.001–0.004,
  moves with steering; ~1.7 ms/bar). The incorruptible holonomy quantity.
- **SLIDE[g]** — reads the per-bar gauge FRAME. **WALL (surfaced, not
  patched):** on any v0 world the writer holds the frame at identity every bar
  (`stream.py` "v0: frozen identity frame"; verified frame.transpose/phase set
  = {0.0} all bars) → slide is structurally zero. The bridge computes slide
  honestly and auto-arms only if the frame ever moves; on the shipped world it
  disarms → "—", labeled `gauge[g] · slide`. SLIDE and LOOP shown as a
  read-only pair, never collapsed into one "drift" number.

**Divergence disclosure (one sentence):** the directive's preferred path was
"transmit real SLIDE and LOOP"; LOOP is fully wired and live, while SLIDE reads
honest-disarm because the shipped v0 world's gauge frame never slides — a real
engine construction wall, surfaced not patched.

## Standing guard (both proven to bite)
`cloud/tests/test_web_fab_guard.py` — caption→data-source map over index.html,
WEB-FIELD-INV style. WEB-FAB-1: scar-phrase ban + allowlist-registration of
every data-claim caption + hardcoded-value ban (bites on "settled render", on
an unregistered data caption, and on a `LANES val:62` literal). WEB-FAB-2: no
`Math.sin/cos/tan/random` may feed a data-surface writer (bites on
`Math.sin`→`#wav` and on art→`setMeter`; allows layout trig on the caption-less
`#ambient` canvas). 11/11 green.

## Invariants
- I-5/I-14: loop/slide/φ are read-only reductions; audio byte-identical
  (`test_stream_decode` green); settlement stays one `set_region` call site.
- I-8: loop/frame windows `deque(maxlen=16)` — bounded by material, not time.
- Core zero-diff: `ets/` and `architecture-v6/ets/` untouched (all engine
  quantities READ via the bridge). app.py NOT edited (SSE frame already
  `json.dumps(p.telemetry)` — new keys flow automatically; no new endpoint).

## Ledger
Incident note logged at source (`LEDGER_DATA.json`, rendered by
`scripts/build_ledger.py` → `LEDGER.md`): fabrication-repeat, three surfaces,
remediation + standing guard.

## Final pytest tail
```
156 passed in 48.37s
```
(145 baseline + 11 WEB-FAB.)
