"""Shared safety layer for the BMC DM bring-up scripts

session() opens the mirror on the SDK's dummy driver unless hardware=True (then only inside
tmux), turns SIGTERM and SIGHUP into SystemExit, and on every exit sends zero() and then
disconnect(): close_dm zeroes too, but does not report whether that worked. send()
refuses, rather than clips, a command outside the step's cap or the soft limits.
"""

import json
import os
import signal
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType
from typing import Final, NoReturn

import numpy as np
from bmc_dm import BmcDmController, DMConfig
from numpy.typing import ArrayLike

BUILD_DIR: Final = Path(__file__).resolve().parents[1]
BUNDLE: Final = BUILD_DIR / "bundle" / "bringup.toml"
LOGS_DIR: Final = BUILD_DIR / "logs"
DUMMY_DIR: Final = BUILD_DIR / "dummy"
DUMMY_SERIAL: Final = "DUMMY000648"
# Highest soft maximum a step may set: the one in bmc_dm's configs/sight bundle
SIGHT_MAXIMUM: Final = 0.8
# Profile for the SDK's dummy driver; test use only, never put it in the SDK's Profiles
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


class RefusedStep(Exception):
    """Raised when a command or session breaks a bring-up rule"""


def scramble(line: str) -> bytes:
    """Encode one profile line the way BMC stores it"""
    return bytes(byte ^ PROFILE_KEY for byte in line.encode())


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
        profiles = DUMMY_DIR / "Profiles"
        profiles.mkdir(parents=True, exist_ok=True)
        (profiles / f"{DUMMY_SERIAL}.dm").write_bytes(
            b"\n".join(map(scramble, _DUMMY_PROFILE)) + b"\n"
        )
        config = replace(
            config,
            serial_number=DUMMY_SERIAL,
            sdk_profiles_path=profiles,
            sdk_maps_path=None,
            logfile=str(LOGS_DIR / "bmc_dm_dummy"),
            last_command_path=DUMMY_DIR / "last_command.npy",
        )
    for folder in (config.sdk_profiles_path, config.sdk_maps_path):
        # The SDK silently falls back to its default folders when a path does not exist
        if folder is not None and not folder.is_dir():
            raise RefusedStep(f"SDK folder {folder} does not exist")
    return config


@contextmanager
def session(
    *, hardware: bool, maximum: float | None = None, zero_on_exit: bool = True
) -> Iterator[BmcDmController]:
    """Connect, yield the controller, then always zero (unless told not to) and disconnect

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
    """Zero and disconnect, with Ctrl-C and stop signals held until both are done"""
    if not dm.connected:
        return
    blocked = signal.pthread_sigmask(signal.SIG_BLOCK, (signal.SIGINT, *_EXIT_SIGNALS))
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


def send(dm: BmcDmController, surface: ArrayLike, *, cap: float, label: str) -> None:
    """Send a surface, then print the mirror's status

    :raises RefusedStep: before sending, if a value is not finite, below the soft minimum,
        or above the step's cap or the soft maximum
    """
    vector = dm.actuator_map.to_vector(surface)
    minimum, maximum = dm.config.soft_limits
    ceiling = min(cap, maximum)
    if not (np.isfinite(vector).all() and minimum <= vector.min() and vector.max() <= ceiling):
        raise RefusedStep(
            f"{label}: {vector.min():.3f} to {vector.max():.3f} is outside {minimum} to {ceiling}"
        )
    dm.set_surface(surface)
    print(f"bringup: sent {label}: {dm.status_report().summary()}", flush=True)


def finish(name: str, report: Mapping[str, object], problems: list[str]) -> int:
    """Print the problems, write logs/<name>_<utc>.json and return the exit status"""
    for problem in problems:
        print(f"{name}: PROBLEM: {problem}", flush=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = LOGS_DIR / f"{name}_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    content = {**report, "problems": problems}
    path.write_text(json.dumps(content, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"{name}: {'FAILED' if problems else 'passed'}; report {path}", flush=True)
    return 1 if problems else 0
