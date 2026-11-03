"""Connect and disconnect repeatedly with no commands in between (test plan Phase 2).

Exit status: 0 if every cycle connected and reported the same serial number.
"""
from __future__ import annotations

import argparse
import sys
import time

import bringup


def main(argv: list[str] | None = None,
         factory: bringup.CameraFactory = bringup.default_factory) -> int:
    """Run the cycles."""
    parser = argparse.ArgumentParser(description=__doc__)
    bringup.add_connection_args(parser)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--pause-s", type=float, default=2.0)
    args = parser.parse_args(argv)

    serials = []
    for cycle in range(1, args.cycles + 1):
        try:
            with bringup.session("connect_cycle", args, factory) as camera:
                serials.append(camera.serial_number)
                print(f"cycle {cycle}: {camera.model} {camera.serial_number} "
                      f"unit {camera.unit} channel {camera.channel}", flush=True)
        except bringup.ConnectFailed as error:
            print(f"cycle {cycle}: {error}", flush=True)
            return 1
        time.sleep(args.pause_s)
    consistent = len(set(serials)) == 1
    print(f"{args.cycles} cycles, serials consistent: {consistent}")
    return 0 if consistent else 1


if __name__ == "__main__":
    sys.exit(main())
