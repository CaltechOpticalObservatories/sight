"""Log temperatures and the target to CSV with no commands sent (test plan Phase 2).

Answers whether the camera starts cooling by itself after power-on or ncCamOpen.
Exit status: 0 when the run completes.
"""
from __future__ import annotations

import argparse
import sys
import time

import bringup
from nuvu import NuvuCamera


def main(argv: list[str] | None = None,
         factory: bringup.CameraFactory = bringup.default_factory) -> int:
    """Log for the requested duration."""
    parser = argparse.ArgumentParser(description=__doc__)
    bringup.add_connection_args(parser)
    parser.add_argument("--duration-s", type=float, default=600.0)
    parser.add_argument("--period-s", type=float, default=30.0)
    args = parser.parse_args(argv)
    path = bringup.logs_dir() / f"telemetry_{bringup.utc_stamp()}.csv"

    def log(camera: NuvuCamera) -> int:
        with bringup.Telemetry(camera, path, args.period_s) as telemetry:
            time.sleep(args.duration_s)
        print(f"{telemetry.rows} samples in {path}")
        return 0

    return bringup.run_in_session("telemetry_log", args, factory, log)


if __name__ == "__main__":
    sys.exit(main())
