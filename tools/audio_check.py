#!/usr/bin/env python3
"""ETS audio-device preflight (directive v1, PART B step 2 dependency).

Standalone: stdlib + numpy + sounddevice ONLY — no repo imports, no engine
(this must run before the engine exists), no web tech (spec I-13). It

  1. enumerates the host's audio output devices (sounddevice.query_devices),
  2. prints the default output device,
  3. renders a 1 s 440 Hz sine at -12 dBFS to the default output
     (override with --device INDEX-or-NAME-substring).

Exit codes:
  0  tone rendered successfully
  2  graceful diagnostic path: sounddevice/numpy not installed, PortAudio
     library missing, no output-capable device (headless box), device
     resolution or playback failure. Always a clear one-line-cause message on
     stderr, never a traceback.
"""
from __future__ import annotations

import argparse
import sys

TONE_HZ = 440.0
TONE_SECONDS = 1.0
TONE_DBFS = -12.0
FALLBACK_SR = 48000


def _fail(msg: str):
    print(f"audio_check: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _import_sounddevice():
    """Lazy import with actionable diagnostics for both failure species:
    missing Python package (ImportError) and missing PortAudio C library
    (sounddevice raises OSError at import time)."""
    try:
        import sounddevice as sd
        return sd
    except ImportError:
        _fail(
            "the 'sounddevice' package is not installed.\n"
            "  install it with:  pip install sounddevice\n"
            "  (it is part of the project's 'panel' extra: pip install 'ets[panel]')"
        )
    except OSError as e:
        _fail(
            f"sounddevice could not load the PortAudio library ({e}).\n"
            "  on Debian/Ubuntu:  sudo apt-get install libportaudio2\n"
            "  on macOS (Homebrew):  brew install portaudio"
        )


def _import_numpy():
    try:
        import numpy as np
        return np
    except ImportError:
        _fail("numpy is not installed. Install it with:  pip install numpy")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="audio_check",
        description="Enumerate audio output devices and render a 1 s 440 Hz "
                    "test tone at -12 dBFS.")
    ap.add_argument("--device", default=None, metavar="DEV",
                    help="output device index or name substring "
                         "(default: system default output)")
    args = ap.parse_args(argv)

    sd = _import_sounddevice()
    np = _import_numpy()

    try:
        devices = sd.query_devices()
    except sd.PortAudioError as e:
        _fail(f"PortAudio could not enumerate devices ({e}). "
              "Is an audio backend (ALSA/PulseAudio/PipeWire/JACK) running?")

    outputs = [(i, d) for i, d in enumerate(devices)
               if int(d.get("max_output_channels", 0)) > 0]
    print(f"{len(devices)} audio device(s), {len(outputs)} output-capable:")
    for i, d in outputs:
        print(f"  [{i}] {d['name']}  ({d['max_output_channels']} out @ "
              f"{d['default_samplerate']:.0f} Hz)")

    if not outputs:
        _fail("no output-capable audio device found (headless box?). "
              "The sounding path runs on the desktop.")

    try:
        default_out = int(sd.default.device[1])
    except (TypeError, ValueError, IndexError):
        default_out = -1
    if 0 <= default_out < len(devices):
        print(f"default output: [{default_out}] {devices[default_out]['name']}")
    else:
        print("default output: (none set)")

    # Resolve the target: --device (index or name substring) else default output.
    if args.device is not None:
        dev = args.device
        device = int(dev) if dev.lstrip("+-").isdigit() else dev
    elif default_out >= 0:
        device = default_out
    else:
        _fail("no default output device; pass --device to pick one explicitly.")

    try:
        info = sd.query_devices(device, kind="output")
    except (ValueError, sd.PortAudioError) as e:
        _fail(f"could not resolve output device {args.device!r}: {e}")

    sr = int(info["default_samplerate"]) or FALLBACK_SR
    amp = 10.0 ** (TONE_DBFS / 20.0)                       # -12 dBFS ~ 0.251
    t = np.arange(int(round(TONE_SECONDS * sr)), dtype=np.float64) / sr
    tone = (amp * np.sin(2.0 * np.pi * TONE_HZ * t)).astype(np.float32)

    print(f"playing {TONE_SECONDS:g} s {TONE_HZ:g} Hz sine at {TONE_DBFS:g} dBFS "
          f"on [{info.get('index', device)}] {info['name']} @ {sr} Hz ...")
    try:
        sd.play(tone, samplerate=sr, device=device, blocking=True)
    except (sd.PortAudioError, OSError) as e:
        _fail(f"playback failed on device {info['name']!r}: {e}")

    print("ok: tone rendered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
