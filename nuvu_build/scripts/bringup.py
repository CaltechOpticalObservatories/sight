"""Shared helpers for the Nuvu HNu 128 bring-up scripts (run them through ../run.sh).

session() is the only way the scripts open the camera. On every exit, including errors
and Ctrl-C, it brings EM gain to its minimum (if it is settable and not already there),
aborts a running acquisition and disconnects. guarded_gain() and check_frame() refuse
rather than clip.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Final, Self

# nuvu first: libnuvu must be loaded before numpy loads libstdc++
from nuvu import NC_AUTO_CHANNEL, NC_AUTO_UNIT, NuvuCamera, VersionType
from nuvu.errors import error_name

import numpy as np

ROOT: Final = Path(__file__).resolve().parent.parent
COMPONENTS: Final = ("ccd", "controller", "power_supply", "fpga", "heatsink")
SATURATED: Final = 65535
MAX_GAIN_RATIO: Final = 2.5

CameraFactory = Callable[[Path], NuvuCamera]


class ConnectFailed(RuntimeError):
    """The SDK could not open the camera."""


class Refused(RuntimeError):
    """A requested setting is outside the phase caps; nothing was sent to the camera."""


class FrameOverCap(RuntimeError):
    """A frame broke the phase's signal cap; the camera was already made dark."""


@dataclass(frozen=True)
class PhaseCaps:
    """Limits for one test phase: highest calibrated EM gain and peak ADU above bias."""

    em_gain: int
    adu_above_bias: float


# From the test plan's phase table; the dark phases use 500 ADU to catch light leaks
PHASE_CAPS: Final = {
    2: PhaseCaps(em_gain=1, adu_above_bias=500.0),
    3: PhaseCaps(em_gain=1, adu_above_bias=500.0),
    4: PhaseCaps(em_gain=1, adu_above_bias=500.0),
    5: PhaseCaps(em_gain=1, adu_above_bias=500.0),
    6: PhaseCaps(em_gain=1, adu_above_bias=500.0),
    7: PhaseCaps(em_gain=100, adu_above_bias=500.0),
    8: PhaseCaps(em_gain=1, adu_above_bias=8800.0),
    9: PhaseCaps(em_gain=100, adu_above_bias=2000.0),
}


@dataclass(frozen=True)
class FrameStats:
    """Summary of one saved frame."""

    path: Path
    minimum: int
    median: float
    maximum: int
    std: float
    peak_above_bias: float


def utc_stamp() -> str:
    """Return the current UTC time as a compact sortable string."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def logs_dir() -> Path:
    """Return the logs directory, creating it if needed."""
    path = ROOT / "logs"
    path.mkdir(exist_ok=True)
    return path


def frames_dir() -> Path:
    """Return the frames directory, creating it if needed."""
    path = ROOT / "frames"
    path.mkdir(exist_ok=True)
    return path


def default_factory(logfile: Path) -> NuvuCamera:
    """Create the real driver, logging to the console and to logfile."""
    return NuvuCamera(log=True, logfile=str(logfile))


def add_connection_args(parser: argparse.ArgumentParser) -> None:
    """Add --unit and --channel (auto-detect by default)."""
    parser.add_argument("--unit", type=int, default=NC_AUTO_UNIT,
                        help="SDK unit (board type plus index); auto-detect by default")
    parser.add_argument("--channel", type=int, default=NC_AUTO_CHANNEL,
                        help="channel on the board; auto-detect by default")


def identity(camera: NuvuCamera) -> dict[str, object]:
    """Return the camera's identity and versions."""
    versions = {v.name.lower(): camera.get_version(v) for v in VersionType}
    return {"serial": camera.serial_number, "model": camera.model,
            "detector": camera.get_detector_type(), "unit": camera.unit,
            "channel": camera.channel, "versions": versions}


def temperatures(camera: NuvuCamera) -> dict[str, float | None]:
    """Return the five component temperatures and the target, in C."""
    values: dict[str, float | None] = {c: camera.get_temperature(c) for c in COMPONENTS}
    values["target"] = camera.get_target_temperature(camera_request=True)
    return values


def em_gain_minimum(camera: NuvuCamera) -> int | None:
    """Return the minimum calibrated EM gain, or None if it can't be set now."""
    if not camera.is_em_gain_available():
        return None
    gain_range = camera.get_em_gain_range()
    return None if gain_range is None else gain_range[0]


def _gain_to_minimum(camera: NuvuCamera) -> None:
    minimum = em_gain_minimum(camera)
    if minimum is not None and camera.get_em_gain(camera_request=True) != minimum:
        camera.set_em_gain(minimum)


def make_dark(camera: NuvuCamera) -> None:
    """EM gain to minimum, shutter closed, acquisition aborted (safe_dark's actions)."""
    _gain_to_minimum(camera)
    camera.set_shutter_mode("close")
    if camera.is_acquiring():
        camera.abort()


def make_safe(camera: NuvuCamera) -> None:
    """End any session: EM gain to minimum, abort, disconnect. Sends nothing unneeded."""
    if not camera.is_connected():
        return
    _gain_to_minimum(camera)
    if camera.is_acquiring():
        camera.abort()
    camera.disconnect()


@contextlib.contextmanager
def session(script: str, args: argparse.Namespace,
            factory: CameraFactory = default_factory) -> Iterator[NuvuCamera]:
    """Connect, log the identity, yield the camera, and always make it safe at the end."""
    camera = factory(logs_dir() / f"{script}_{utc_stamp()}.log")
    camera.connect(args.unit, args.channel)
    if not camera.is_connected():
        raise ConnectFailed(f"connect failed: {error_name(camera.status)} ({camera.status})")
    try:
        camera.report_info(f"identity: {identity(camera)}")
        yield camera
    finally:
        make_safe(camera)


def run_in_session(script: str, args: argparse.Namespace, factory: CameraFactory,
                   body: Callable[[NuvuCamera], int]) -> int:
    """Run body in a session and return its exit status; a failed connection gives 1."""
    try:
        with session(script, args, factory) as camera:
            return body(camera)
    except ConnectFailed as error:
        print(error, flush=True)
        return 1


class Telemetry:
    """Log the five temperatures and the target to CSV from a background thread."""

    def __init__(self, camera: NuvuCamera, path: Path, period_s: float,
                 echo: bool = True) -> None:
        self.camera = camera
        self.path = path
        self.period_s = period_s
        self.echo = echo
        self.rows = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="telemetry", daemon=True)

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 traceback: TracebackType | None) -> None:
        self._stop.set()
        self._thread.join()

    def _run(self) -> None:
        fields = ["utc", *COMPONENTS, "target"]
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            while True:
                row = {"utc": datetime.now(UTC).isoformat(timespec="seconds"),
                       **temperatures(self.camera)}
                writer.writerow(row)
                handle.flush()
                self.rows += 1
                if self.echo:
                    print("telemetry", row, flush=True)
                if self._stop.wait(self.period_s):
                    return


def guarded_gain(camera: NuvuCamera, target: int, caps: PhaseCaps,
                 peak_above_bias: float) -> None:
    """Set the calibrated EM gain, or raise Refused without sending anything.

    :param peak_above_bias: the current frame's peak above bias, used to predict the
        peak at the new gain
    """
    reasons = []
    if target > caps.em_gain:
        reasons.append(f"gain {target} above the phase cap {caps.em_gain}")
    current = None
    if not camera.is_em_gain_available():
        reasons.append("calibrated EM gain is not available")
    else:
        current = camera.get_em_gain(camera_request=True)
        if current is None or current <= 0:
            reasons.append("current gain unreadable")
    if current:
        if target > MAX_GAIN_RATIO * current:
            reasons.append(f"step {current} -> {target} is more than {MAX_GAIN_RATIO}x")
        predicted = peak_above_bias * target / current
        if predicted > caps.adu_above_bias:
            reasons.append(f"predicted peak {predicted:.0f} ADU above the cap "
                           f"{caps.adu_above_bias:.0f}")
    if reasons:
        raise Refused("; ".join(reasons))
    if not camera.set_em_gain(target):
        raise Refused(f"SDK rejected gain {target}")


def check_frame(camera: NuvuCamera, frame: np.ndarray, caps: PhaseCaps, bias: float,
                name: str) -> FrameStats:
    """Save a frame and its stats; on a cap breach make the camera dark and raise."""
    path = frames_dir() / f"{name}_{utc_stamp()}.npy"
    np.save(path, frame)
    stats = FrameStats(path=path, minimum=int(frame.min()), median=float(np.median(frame)),
                       maximum=int(frame.max()), std=float(frame.std()),
                       peak_above_bias=float(frame.max()) - bias)
    camera.report_info(f"frame {stats}")
    saturated = bool((frame >= SATURATED).any())
    if saturated or stats.peak_above_bias > caps.adu_above_bias:
        make_dark(camera)
        raise FrameOverCap(f"{path.name}: peak {stats.peak_above_bias:.0f} ADU above bias "
                           f"(cap {caps.adu_above_bias:.0f}), saturated={saturated}")
    return stats
