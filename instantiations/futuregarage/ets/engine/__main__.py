"""ENGINE process entry point (spec §12):

  live   :  python -m ets.engine --world corpus.etsworld --latency-profile desktop
  offline:  python -m ets.engine --world corpus.etsworld --render out.flac \
                --seconds 30 --knob-script knobs.json --seed 0

Live mode binds the closed OSC message space (control in on --port, meters out
to the panel announced by /ets/hello), derives its latency L from buffer math
at startup, and runs headless-gracefully where no audio device exists (this is
reported loudly; the writer/OSC/meter loop is identical). Offline mode renders
a scripted knob trajectory deterministically (H-8) and writes audio + a
receipt recording the (world hash, LAMBDA, knob trajectory, seed) tuple.
"""
from __future__ import annotations
import argparse
import logging
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m ets.engine",
        description="ETS engine — frozen world + streaming writer over OSC")
    ap.add_argument("--world", required=True, help="world file (.etsworld)")
    ap.add_argument("--latency-profile", default="desktop",
                    help="registered hardware profile (see ets.engine.latency)")
    ap.add_argument("--port", type=int, default=9000,
                    help="OSC control port (lanes/tolerances/hello)")
    ap.add_argument("--meters-host", default="127.0.0.1")
    ap.add_argument("--meters-port", type=int, default=9001,
                    help="initial meter target (replaced by /ets/hello)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--sigma-phi", default=None,
                    help="σ_φ calibration JSON (overrides world/registered)")
    ap.add_argument("--render", default=None, metavar="OUT",
                    help="offline render to OUT (flac) instead of live mode")
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--knob-script", default=None,
                    help="offline knob trajectory JSON (see engine.py)")
    ap.add_argument("--max-bars", type=int, default=None,
                    help="live mode: stop after N bars (demo/CI)")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, stream=sys.stdout,
        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    from ets.engine.engine import Engine, resolve_sigma
    from ets.engine.worldfile import load_world

    wf = load_world(args.world)
    sigma = resolve_sigma(wf, args.sigma_phi)
    eng = Engine(wf, profile=args.latency_profile, seed=args.seed, sigma=sigma)

    if args.render:
        res = eng.render_offline(args.seconds, knob_script=args.knob_script,
                                 out_path=args.render)
        print(f"[engine] offline render done: audio sha256 "
              f"{res.receipt['audio_sha256']}")
        return 0

    eng.run_live(control_port=args.port, meters_host=args.meters_host,
                 meters_port=args.meters_port, max_bars=args.max_bars)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
