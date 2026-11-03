"""Read-only camera report: enumeration, identity, readout modes, every getter and range.

Sends no setters besides the readout mode 1 that connect() selects. Lists the cameras
the SDK sees, connects, queries (camera_request=True where the SDK supports it),
disconnects, and writes the report as JSON to logs/.
Exit status: 0 on success, 1 if no camera was found or the connection failed.
"""
from __future__ import annotations

import argparse
import json
import sys

import bringup
from nuvu import NuvuCamera


def collect(camera: NuvuCamera) -> dict[str, object]:
    """Query every read-only value the driver offers."""
    em_available = camera.is_em_gain_available()
    return {
        "identity": bringup.identity(camera),
        "readout_modes": camera.get_readout_modes(),
        "readout_mode": camera.get_readout_mode(),
        "size": camera.get_size(),
        "binning": camera.get_binning(),
        "readout_time_ms": camera.get_readout_time(),
        "framerate_hz": camera.get_framerate(),
        "exposure_ms": camera.get_exposure_time(camera_request=True),
        "waiting_ms": camera.get_waiting_time(camera_request=True),
        "timeout_ms": camera.get_timeout(),
        "trigger_mode": camera.get_trigger_mode(camera_request=True),
        "shutter_mode": camera.get_shutter_mode(camera_request=True),
        "acquiring": camera.is_acquiring(),
        "em_gain_available": em_available,
        "em_gain": camera.get_em_gain(camera_request=True) if em_available else None,
        "em_gain_range": camera.get_em_gain_range(),
        "em_gain_temp_range_c": camera.get_calibrated_em_gain_temp_range(),
        "analog_gain": camera.get_analog_gain(camera_request=True),
        "analog_gain_range": camera.get_analog_gain_range(),
        "analog_offset": camera.get_analog_offset(camera_request=True),
        "analog_offset_range": camera.get_analog_offset_range(),
        "temperatures_c": bringup.temperatures(camera),
        "target_range_c": camera.get_target_temperature_range(),
        "safe_shutdown_c": camera.get_safe_shutdown_temperature(),
    }


def main(argv: list[str] | None = None,
         factory: bringup.CameraFactory = bringup.default_factory) -> int:
    """Run the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    bringup.add_connection_args(parser)
    args = parser.parse_args(argv)

    report: dict[str, object] = {"utc": bringup.utc_stamp()}
    lister = factory(bringup.logs_dir() / f"status_list_{bringup.utc_stamp()}.log")
    report["cameras"] = lister.list_cameras()
    print("cameras:", report["cameras"], flush=True)
    if not report["cameras"]:
        print("no camera found", flush=True)
        return 1

    def query(camera: NuvuCamera) -> int:
        report.update(collect(camera))
        return 0

    status = bringup.run_in_session("status", args, factory, query)
    if status != 0:
        return status
    path = bringup.logs_dir() / f"status_{report['utc']}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"report: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
