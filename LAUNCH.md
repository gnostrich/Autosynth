# LAUNCH — ETS two-process desktop rig (engine + panel)

Spec §12: TWO processes, native desktop, OSC over localhost. The ENGINE owns
the frozen world, the streaming writer, and the audio; the PANEL is a pure
control surface + display. Killing the panel never touches the engine (the
two-process law); any OSC/MIDI hardware can replace the panel entirely.

## 0. Prerequisites

```bash
pip install -e ".[panel]"        # PySide6-Essentials, python-osc, sounddevice
```

- `sounddevice` is needed for LIVE AUDIO only; the engine imports it lazily
  and runs headless-gracefully without it (loudly reported, writer/OSC/meters
  identical). Offline render and CI never need it.
- Verify the audio device first (PART B):
  `python tools/audio_check.py` — enumerates devices and plays a test tone
  (deliverable of the audio-check feature; graceful no-device message).

## 1. Artifacts

```bash
# frozen corpus world (once per world-freeze; ~30 s):
python scripts/build_worldfile.py --out /home/user/Geodesic-Mixing/corpus.etsworld
```

- σ_φ calibration: the engine loads the REGISTERED instrument automatically
  (`ets.calibration.load_sigma_phi`, artifact `ets/calibration/sigma_phi.json`)
  and REFUSES a stale one (world-hash guard). Precedence:
  `--sigma-phi file.json` > world-file-embedded > registered artifact.
  With NO calibration at all the engine runs untilted-only and any lean halts
  with `WorldNotCalibrated` (scales are never invented).

## 2. Launch order

```bash
# terminal 1 — ENGINE first (it must own the control port before the panel
# says hello):
python -m ets.engine --world /home/user/Geodesic-Mixing/corpus.etsworld \
    --latency-profile desktop            # add --seed N for a reproducible tape

# terminal 2 — PANEL:
python -m ets.panel                      # defaults: engine at 127.0.0.1:9000
```

Engine startup sequence (all in its stdout log):
1. `sigma_phi: ...` — which calibration source was resolved; disarmed lanes.
2. `bank: N units in memory` — source materialization (all tracks preloaded
   BEFORE the clock starts; a run may seed any unit and loading inside the
   deadline would starve the writer). NOTE the memory cost: full-corpus band
   audio is ~0.8 GB per 5-min track at float64 — budget the desktop
   accordingly or freeze a smaller world for live sets. Corpus banks are
   stored float32 (declared capacity decision; ~8.5 GB for the 20-track
   corpus; render arithmetic stays float64).
3. warmup bars + `latency derivation (...): {"L_bars": ..., "formula":
   "L = ceil(max(T_prod)/T_bar) + 1"}` — L from BUFFER MATH measured on THIS
   host (pre-registered procedure; PREREG "Latency profile table").
4. `DECLARED CONTROL LATENCY: L=k bars (...) + device 46.4ms` — lanes bind at
   the write frontier, so a knob move lands k bars later. Plugin-latency
   semantics, surfaced, never hidden (also sent to the panel in /ets/welcome).
5. If no audio device: `LIVE AUDIO UNAVAILABLE (...) — running HEADLESS live
   loop` (this build box; PART B desktops get real output).

## 3. OSC handshake confirmation

On panel start you must see, in this order:

- panel stdout: `HELLO -> 127.0.0.1:9000 (meters_port=<P>)`
- engine log:   `HELLO from panel 127.0.0.1 (meters_port=<P>)`
- engine log:   `WELCOME -> 127.0.0.1:<P>  (K=<anchors>, L=<bars>, bar=<s>s,
                world <hash8>, disarmed=...)`
- panel window: status row flips to
  `engine: connected  K=<anchors>  L=<bars> bars  world <hash8>` and the
  REGION strips grow to K.

If the handshake does not complete: engine not started first, port collision
(`--port` / `--engine-port`), or a firewall on localhost UDP.

## 4. PART B verification checklist (desktop with audio)

1. LANES ECHO — move any lane on the panel; the engine log prints
   `LANES region=[...] density=... T_s=...` for every move, and the change is
   AUDIBLE exactly L bars later (the declared latency).
2. METERS UPDATE PER BAR — the clock display advances each bar
   (`CLOCK bar N`); NOVELTY saturation moves; DRIFT jacks read +0.000
   (identity frame, honest) and are labeled `[deprecated: conflated]`;
   SLIDE/LOOP jack pairs read `—` until the Stage-0 meter feed lands (they
   are displays of another instrument's shadow values — never fabricated).
3. COMMA READS `inf` — the TOLERANCES box shows COMMA = `inf` untouched
   (shipped behavior unchanged); turning either knob logs
   `TOLERANCES leash=... comma=...` in the engine with the note
   `(declared; consumed by nothing — Stage-1 authority pending)`.
4. PANEL-KILL LEAVES ENGINE PLAYING — kill the panel process; audio
   continues, engine log keeps committing bars. Restart the panel; the
   handshake re-establishes and displays resume. (The two-process law.)
5. MIDI CC LEARN — arm a lane (API: `panel.arm_cc_learn(...)`), send a CC,
   the binding drives the lane and emits over the same /ets/lanes channel.
6. UNDERRUN = HALT — if the desktop cannot produce a bar inside L·T_bar the
   engine HALTS with `WALL: audio underrun ...`. That is the designed
   behavior (connector Real-time typing): report the host, do not expect a
   degraded-quality fallback; none exists.

## 5. Offline render (deterministic, H-8)

```bash
python -m ets.engine --world corpus.etsworld --render out.flac --seconds 30 \
    --knob-script knobs.json --seed 0
```

`knobs.json`: `{"events": [{"bar": 4, "lane": "density", "value": 1.5}, ...]}`
(lanes = the six of spec §8; `region` takes a list). The `.receipt.json`
sidecar records the full determinism tuple (world sha256, LAMBDA, knob
trajectory sha256, seed, audio sha256): same tuple ⇒ bit-identical audio
(CI: tests/harness/test_h8_determinism.py).

## 6. Declared limitations (honest state, with unblocking conditions)

- DENSITY and GAUGE-STIFFNESS lanes are DISARMED under the current registered
  σ_φ artifact: the instrument (measured on the MAP-settling untilted writer)
  found ZERO untilted fluctuation for their observables ⇒ identifiable=false
  ⇒ λ is UNDEFINED there. The lanes are present (spec §8 exhaustiveness),
  transmit u, and apply NO tilt; the panel status row and engine log say so.
  UNBLOCKING: this engine's writer SAMPLES at T_s>0 (Laplace looseness around
  the settled optimum + seeded fiber draws), under which φ_density fluctuates
  — a registered RE-RUN of the σ_φ instrument against the sampling writer can
  legitimately calibrate DENSITY. (GAUGE additionally needs a live gauge
  block in the writer — a v0 wall: the frame is frozen at identity, so
  φ_gauge ≡ 0 and even a calibrated scale would tilt nothing.)
- EOC gate currently emits 0 in live mode (no live phrase detector runs in
  the engine yet; the offline phrase meter exists in ets.meters). Owned by
  the meters lineage; the jack, wire, and display are in place.
- SLIDE/LOOP jacks display `—` until the Stage-0 meters feature emits them.
- The engine clock message reports the WRITE FRONTIER bar (where control
  binds), not the playhead bar; they differ by exactly L.
