"""Warm the detector in a controlled way, then disconnect (before any power-off).

Runs prepare_shutdown(blocking=True) while a telemetry thread logs the temperatures,
then prints "safe to power off" only if the CCD is at or above the safe shutdown
temperature. Exit status: 0 only when it is safe to power off.
"""
from __future__ import annotations

import argparse
import sys

import bringup
from nuvu import NuvuCamera


def main(argv: list[str] | None = None,
         factory: bringup.CameraFactory = bringup.default_factory) -> int:
    """Warm up and report whether power-off is safe."""
    parser = argparse.ArgumentParser(description=__doc__)
    bringup.add_connection_args(parser)
    parser.add_argument("--period-s", type=float, default=5.0)
    args = parser.parse_args(argv)
    path = bringup.logs_dir() / f"warmup_{bringup.utc_stamp()}.csv"

    def warm(camera: NuvuCamera) -> int:
        safe = camera.get_safe_shutdown_temperature()
        with bringup.Telemetry(camera, path, args.period_s):
            warmed = camera.prepare_shutdown(blocking=True)
        ccd = camera.get_temperature("ccd")
        print(f"prepare_shutdown ok: {warmed}; CCD {ccd} C; safe shutdown {safe} C; "
              f"log {path}")
        if warmed and ccd is not None and safe is not None and ccd >= safe:
            print("safe to power off")
            return 0
        print("NOT safe to power off: keep the camera powered and investigate")
        return 1

    return bringup.run_in_session("warm_and_close", args, factory, warm)


if __name__ == "__main__":
    sys.exit(main())
