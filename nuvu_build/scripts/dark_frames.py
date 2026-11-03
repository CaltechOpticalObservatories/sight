"""Dark frames with the detector warm, EM gain 1 and the shutter closed (test plan Phase 3).

Takes FRAMES_PER_EXPOSURE frames at each exposure, then CONTINUOUS_FRAMES frames in a
continuous acquisition read chronologically, and checks them against the phase 3 cap
(a breach makes the camera dark and stops the script). Frames go to frames/, the report
to logs/. Exit status: 0 if every check passed.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from typing import Final

import bringup
import numpy as np
from nuvu import NuvuCamera
from nuvu.nuvu_camera import TIMEOUT_MARGIN_MS

CAPS: Final = bringup.PHASE_CAPS[3]
READOUT_MODE: Final = 1  # EM amplifier, 10 MHz vertical and horizontal
EXPOSURES_MS: Final = (1.0, 10.0, 100.0, 1000.0)
FRAMES_PER_EXPOSURE: Final = 10
CONTINUOUS_FRAMES: Final = 1000
SHAPE: Final = (128, 128)
BIAS_SPREAD_ADU: Final = 5.0
# The first frame after start() carries charge from the idle period (top rows +12 ADU)
SETTLING_FRAMES: Final = 1
READ_NOISE_ADU: Final = (8.0, 14.0)  # certificate: about 10.5 ADU at 10 MHz
FRAMERATE_TOLERANCE: Final = 0.10


def read_noise(first: np.ndarray, second: np.ndarray) -> float:
    """Return the read noise in ADU from two frames: std of the difference over sqrt(2)."""
    return float(np.std(first.astype(np.float64) - second) / math.sqrt(2))


def read_frames(camera: NuvuCamera, count: int) -> list[np.ndarray]:
    """Read up to count frames of the running acquisition in order; stop at a failed read."""
    frames = []
    for _ in range(count):
        frame = camera.read_image(chronological=True)
        if frame is None:
            break
        frames.append(frame)
    return frames


def take_exposures(camera: NuvuCamera, report: dict[str, object]) -> float:
    """Take the frames at each exposure, record checks, and return the bias in ADU."""
    bias = None
    for exposure in EXPOSURES_MS:
        camera.set_exposure_time(exposure)
        times = (camera.get_exposure_time(), camera.get_waiting_time(),
                 camera.get_readout_time())
        camera.start(FRAMES_PER_EXPOSURE)
        frames = read_frames(camera, FRAMES_PER_EXPOSURE)
        if camera.is_acquiring() is not False:
            camera.abort()
        if bias is None and frames:
            bias = float(np.median(frames[0]))
        stats = [bringup.check_frame(camera, frame, CAPS, bias or 0.0,
                                     f"dark_{exposure:g}ms_{index:02d}")
                 for index, frame in enumerate(frames)]
        report[f"{exposure:g}ms"] = {
            "frames": len(frames),
            "timeout_ok": None not in times and camera.get_timeout() == (
                int(sum(times)) + TIMEOUT_MARGIN_MS),
            "shape_ok": all(f.shape == SHAPE and f.dtype == np.uint16 for f in frames),
            "medians": [s.median for s in stats],
            "peak_above_bias": max((s.peak_above_bias for s in stats), default=None),
            "read_noise_adu": read_noise(frames[0], frames[1]) if len(frames) > 1 else None,
        }
    return bias or 0.0


def take_continuous(camera: NuvuCamera, bias: float) -> dict[str, object]:
    """Read CONTINUOUS_FRAMES chronologically and compare the frame rate with nominal."""
    camera.set_exposure_time(EXPOSURES_MS[0])
    nominal = camera.get_framerate_nominal()
    camera.start(0)
    # Time from the first frame, so start-up latency does not count against the rate
    frames = read_frames(camera, 1)
    start = time.monotonic()
    frames += read_frames(camera, CONTINUOUS_FRAMES - len(frames))
    elapsed = time.monotonic() - start
    sdk_rate = camera.get_framerate()
    camera.abort()
    measured = (len(frames) - 1) / elapsed if len(frames) > 1 and elapsed > 0 else 0.0
    if frames:
        bringup.check_frame(camera, np.max(frames, axis=0), CAPS, bias, "dark_continuous_max")
    return {"frames": len(frames), "nominal_hz": nominal, "measured_hz": measured,
            "sdk_framerate_hz": sdk_rate, "acquiring_after_abort": camera.is_acquiring()}


def evaluate(report: dict[str, object]) -> dict[str, bool]:
    """Return the Phase 3 pass checks for a report."""
    exposures = [report[f"{e:g}ms"] for e in EXPOSURES_MS]
    first = exposures[0]
    continuous = report["continuous"]
    nominal = continuous["nominal_hz"] or 0.0
    noise = first["read_noise_adu"]
    return {
        "readout_mode_loaded": report["readout_mode_ok"] is True,
        "em_gain_is_1": report["em_gain"] == 1,
        "em_gain_2_refused_warm": not report["em_gain_2_accepted"],
        "all_frames_read": all(e["frames"] == FRAMES_PER_EXPOSURE for e in exposures)
        and continuous["frames"] == CONTINUOUS_FRAMES,
        "shape_uint16_128x128": all(e["shape_ok"] for e in exposures),
        "timeout_follows_exposure": all(e["timeout_ok"] for e in exposures),
        "bias_stable": float(np.ptp(first["medians"][SETTLING_FRAMES:])) <= BIAS_SPREAD_ADU,
        "read_noise_in_range": noise is not None
        and READ_NOISE_ADU[0] <= noise <= READ_NOISE_ADU[1],
        "framerate_within_10pct": nominal > 0
        and abs(continuous["measured_hz"] - nominal) <= FRAMERATE_TOLERANCE * nominal,
        "idle_after_abort": continuous["acquiring_after_abort"] is False,
    }


def run(camera: NuvuCamera) -> int:
    """Take the Phase 3 frames and write the report."""
    report: dict[str, object] = {"utc": bringup.utc_stamp(),
                                 "readout_mode_ok": camera.initialize(READOUT_MODE)}
    bringup.make_dark(camera)
    report["em_gain"] = camera.get_em_gain(camera_request=True)
    report["em_gain_2_accepted"] = camera.set_em_gain(2)
    if report["em_gain_2_accepted"]:
        camera.set_em_gain(1)
    report["temperatures_before"] = bringup.temperatures(camera)
    try:
        bias = take_exposures(camera, report)
        report["continuous"] = take_continuous(camera, bias)
    except bringup.FrameOverCap as error:
        print(f"stopped: {error}", flush=True)
        return 1
    report["temperatures_after"] = bringup.temperatures(camera)
    report["checks"] = evaluate(report)
    path = bringup.logs_dir() / f"dark_frames_{report['utc']}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str), f"\nreport: {path}", flush=True)
    return 0 if all(report["checks"].values()) else 1


def main(argv: list[str] | None = None,
         factory: bringup.CameraFactory = bringup.default_factory) -> int:
    """Run Phase 3."""
    parser = argparse.ArgumentParser(description=__doc__)
    bringup.add_connection_args(parser)
    args = parser.parse_args(argv)
    return bringup.run_in_session("dark_frames", args, factory, run)


if __name__ == "__main__":
    sys.exit(main())
