"""Make the camera dark and idle: EM gain to minimum, shutter closed, acquisition aborted.

Run at the end of every phase and as step 2 of the abort procedure. It does not warm the
detector; use warm_and_close.py for that. Exit status: 0 if the camera was reached.
"""
from __future__ import annotations

import argparse
import sys

import bringup
from nuvu import NuvuCamera


def make_dark_and_report(camera: NuvuCamera) -> int:
    """Make the camera dark, then print its state."""
    bringup.make_dark(camera)
    print("temperatures:", bringup.temperatures(camera))
    print("safe shutdown temperature:", camera.get_safe_shutdown_temperature())
    print("shutter:", camera.get_shutter_mode(camera_request=True),
          "acquiring:", camera.is_acquiring())
    return 0


def main(argv: list[str] | None = None,
         factory: bringup.CameraFactory = bringup.default_factory) -> int:
    """Make the camera safe and report temperatures."""
    parser = argparse.ArgumentParser(description=__doc__)
    bringup.add_connection_args(parser)
    args = parser.parse_args(argv)
    return bringup.run_in_session("safe_dark", args, factory, make_dark_and_report)


if __name__ == "__main__":
    sys.exit(main())
