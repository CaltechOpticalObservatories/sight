"""Shared safety layer for the BMC DM bring-up scripts

Every script opens the mirror through session(), which:

* runs on the SDK's dummy driver (serial DUMMY000648, its own profiles folder) unless
  the script is given --hardware, and then only inside tmux;
* turns SIGTERM and SIGHUP into SystemExit, so a stopped script or a dropped SSH session
  still cleans up (kill -9 cannot be caught);
* on every exit sends zero(), whose SDK status is checked (close_dm ignores the result of
  its own zeroing), then disconnect(), holding off Ctrl-C and both signals meanwhile.

send() refuses a command, instead of letting the driver clip it, if its peak passes the
step's cap or any value lies outside the soft limits.
"""

import argparse
import hashlib
import json
import os
import signal
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType
from typing import Final, NoReturn

import numpy as np
from bmc_dm import ActuatorMap, BmcDmController, DMConfig
from numpy.typing import ArrayLike, NDArray

BUILD_DIR: Final = Path(__file__).resolve().parents[1]
BUNDLE: Final = BUILD_DIR / "bundle" / "bringup.toml"
LOGS_DIR: Final = BUILD_DIR / "logs"
DUMMY_DIR: Final = BUILD_DIR / "dummy"
DUMMY_SERIAL: Final = "DUMMY000648"
# Highest soft maximum a script may set: the one in bmc_dm's configs/sight bundle
SIGHT_MAXIMUM: Final = 0.8

# Profile for the SDK's dummy driver (type=2); test use only, never put it in the SDK's
# Profiles folder
_DUMMY_PROFILE: Final = (
    "type=2",
    "hva=0",
    "size=648",
    "maxv=300",
    "vlim=150",
    "map=",
    "inactive=0",
)
# BMC profiles are text with every byte XOR-ed with this key
PROFILE_KEY: Final = 0x83

_EXIT_SIGNALS: Final = (signal.SIGTERM, signal.SIGHUP)
_CLEANUP_SIGNALS: Final = (signal.SIGINT, *_EXIT_SIGNALS)


class RefusedStep(Exception):
    """Raised when a planned command or session breaks a bring-up rule"""


@dataclass(frozen=True)
class CommandPlan:
    """What a command will do, checked before it is sent"""

    peak: float
    moved: int  # Actuators away from 0
    max_neighbor_step: float

    def summary(self) -> str:
        """Return the plan as one line"""
        return (
            f"peak {self.peak:.3f}, {self.moved} actuators moved, "
            f"largest neighbor step {self.max_neighbor_step:.3f}"
        )


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the --hardware switch every script shares"""
    parser.add_argument(
        "--hardware",
        action="store_true",
        help="drive the real mirror (default: the SDK's dummy driver)",
    )


def load_config(*, hardware: bool, maximum: float | None = None) -> DMConfig:
    """Load the bring-up bundle, set up for the dummy driver unless hardware

    :param maximum: soft maximum for this step instead of the bundle's
    :raises RefusedStep: if maximum passes SIGHT_MAXIMUM or an SDK folder is missing
    """
    config = DMConfig.load(BUNDLE)
    if maximum is not None:
        if maximum > SIGHT_MAXIMUM:
            raise RefusedStep(f"Soft maximum {maximum} is above Sight's {SIGHT_MAXIMUM}")
        config = replace(config, soft_limits=(config.soft_limits[0], maximum))
    if not hardware:
        config = _dummy_config(config)
    for folder in (config.sdk_profiles_path, config.sdk_maps_path):
        # The SDK silently falls back to its default folders when a path does not exist
        if folder is not None and not folder.is_dir():
            raise RefusedStep(f"SDK folder {folder} does not exist")
    return config


def _dummy_config(config: DMConfig) -> DMConfig:
    """Point config at the dummy profile, with its own log and last command files"""
    profiles = DUMMY_DIR / "Profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    scrambled = (bytes(byte ^ PROFILE_KEY for byte in line.encode()) for line in _DUMMY_PROFILE)
    (profiles / f"{DUMMY_SERIAL}.dm").write_bytes(b"\n".join(scrambled) + b"\n")
    return replace(
        config,
        serial_number=DUMMY_SERIAL,
        sdk_profiles_path=profiles,
        sdk_maps_path=None,
        logfile=str(LOGS_DIR / "bmc_dm_dummy"),
        last_command_path=DUMMY_DIR / "last_command.npy",
    )


@contextmanager
def session(
    *, hardware: bool, maximum: float | None = None, zero_on_exit: bool = True
) -> Iterator[BmcDmController]:
    """Connect, yield the controller, then always zero and disconnect

    :param maximum: soft maximum for this step instead of the bundle's
    :param zero_on_exit: False only for persistence checks; disconnect still runs
    :raises RefusedStep: for hardware outside tmux, or a config load_config refuses
    """
    if hardware and "TMUX" not in os.environ:
        raise RefusedStep(
            "Run hardware steps inside tmux, so a dropped SSH session cannot kill them"
        )
    config = load_config(hardware=hardware, maximum=maximum)
    mode = "HARDWARE" if hardware else "dummy"
    print(f"bringup: {mode} {config.serial_number}, soft limits {config.soft_limits}", flush=True)
    previous = {number: signal.signal(number, _exit_on_signal) for number in _EXIT_SIGNALS}
    dm = BmcDmController(config)
    try:
        dm.connect()
        yield dm
    finally:
        try:
            _close(dm, zero=zero_on_exit)
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)


def _exit_on_signal(number: int, _frame: FrameType | None) -> NoReturn:
    """Turn a stop signal into SystemExit so cleanup runs"""
    print(f"bringup: {signal.Signals(number).name} received, cleaning up", flush=True)
    raise SystemExit(128 + number)


def _close(dm: BmcDmController, *, zero: bool) -> None:
    """Zero (unless told not to) and disconnect, with Ctrl-C and stop signals held off"""
    if not dm.connected:
        return
    # Signals that arrive now stay pending and are raised once cleanup is done
    blocked = signal.pthread_sigmask(signal.SIG_BLOCK, _CLEANUP_SIGNALS)
    try:
        if zero:
            dm.zero()
            print("bringup: zeroed", flush=True)
    finally:
        try:
            dm.disconnect()
            print("bringup: disconnected", flush=True)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, blocked)


def max_neighbor_step(actuator_map: ActuatorMap, vector: NDArray[np.float64]) -> float:
    """Return the largest difference between actuators that are grid neighbors"""
    surface, mask = actuator_map.to_surface(vector), actuator_map.mask
    down = np.abs(np.diff(surface, axis=0))[mask[1:] & mask[:-1]]
    across = np.abs(np.diff(surface, axis=1))[mask[:, 1:] & mask[:, :-1]]
    return float(np.max(np.concatenate((down, across)), initial=0.0))


def plan(dm: BmcDmController, surface: ArrayLike, cap: float) -> CommandPlan:
    """Check a surface against the step's cap and the soft limits without sending it

    :raises RefusedStep: if a value is not finite, would be clipped, or passes cap
    """
    vector = dm.actuator_map.to_vector(surface)
    if not np.isfinite(vector).all():
        raise RefusedStep("Command has NaN or infinite values")
    minimum, maximum = dm.config.soft_limits
    if vector.min() < minimum or vector.max() > maximum:
        raise RefusedStep(
            f"Command spans {vector.min():.3f} to {vector.max():.3f}, outside the soft "
            f"limits {minimum} to {maximum}; the driver would clip it"
        )
    peak = float(vector.max())
    if peak > cap:
        raise RefusedStep(f"Command peak {peak:.3f} is above the step's cap {cap}")
    return CommandPlan(
        peak=peak,
        moved=int(np.count_nonzero(vector)),
        max_neighbor_step=max_neighbor_step(dm.actuator_map, vector),
    )


def send(dm: BmcDmController, surface: ArrayLike, *, cap: float, label: str) -> CommandPlan:
    """Plan a surface, print the plan, send it and print the status

    :raises RefusedStep: as plan() does, before anything is sent
    """
    command_plan = plan(dm, surface, cap)
    print(f"bringup: send {label}: {command_plan.summary()} (cap {cap})", flush=True)
    dm.set_surface(surface)
    print(f"bringup: {dm.status_report().summary()}", flush=True)
    return command_plan


def dwell(seconds: float) -> None:
    """Hold the current shape for seconds"""
    print(f"bringup: dwell {seconds} s", flush=True)
    time.sleep(seconds)


def sha256(path: Path) -> str:
    """Return a file's SHA-256 in hex"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_stamp() -> str:
    """Return the current UTC time for file names"""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def write_report(name: str, report: Mapping[str, object]) -> Path:
    """Write a JSON report to logs/ and return its path"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = LOGS_DIR / f"{name}_{utc_stamp()}.json"
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return path
