"""Phase 1 audit of a BMC profile (.dm) before it is used to open the real mirror

Decodes the profile (every byte XOR-ed with 0x83, newlines raw) and checks what the SDK
does not: an 11-character serial, a USB or PCIe type, 648 actuators, vlim at most maxv
(otherwise DAC counts overflow and wrap), the map and calibration files present (a missing
map makes open_dm fail with the DM already open), and for PCIe an HVA type whose fiber and
Camera Link settings agree (the SDK only warns, then writes them to the card).

usage: audit_profile.py PROFILE.dm [--maps FOLDER] [--calibrations FOLDER]
"""

import argparse
import hashlib
import math
import sys
from pathlib import Path
from typing import Final

import bringup

SDK_ROOT: Final = Path("/opt/Boston Micromachines")
SIGHT_ACTUATORS: Final = "648"
SERIAL_LENGTH: Final = 11
DRIVER_TYPES: Final = {"0": "USB", "1": "PCIe", "2": "dummy"}
# HVATYPES in BMC_PCIeApi.h; kilo drivers take their data over fiber in kilo mode
HVA_TYPES: Final = {
    "0": "Camera Link",
    "1": "S-driver",
    "2": "KILO1024",
    "3": "KILO2K",
    "4": "KILO4K",
}
KILO_TYPES: Final = frozenset({"2", "3", "4"})
# Every key the SDK's read_profile() understands (BMCCore/bmcdmprofile.cpp)
KNOWN_KEYS: Final = frozenset(
    [
        "type",
        "size",
        "maxv",
        "hva",
        "use_fiber",
        "use_CL",
        "burst_mode",
        "fiber_mode",
        "vlim",
        "map",
        "calibration",
        "inactive",
        "driver_sn",
    ]
)


def decode(path: Path) -> dict[str, str]:
    """Return the profile's key=value lines, decoded as the SDK does"""
    entries = {}
    for raw in path.read_bytes().split(b"\n"):
        # The SDK drops a trailing carriage return before unscrambling
        line = bytes(byte ^ bringup.PROFILE_KEY for byte in raw.removesuffix(b"\r")).decode()
        if line:
            key, _, value = line.partition("=")
            entries[key] = value
    return entries


def _number(entries: dict[str, str], key: str) -> float:
    """Return a numeric value, NaN if it is missing or not a number"""
    try:
        return float(entries.get(key, "nan"))
    except ValueError:
        return math.nan


def audit(path: Path, maps: Path, calibrations: Path) -> tuple[dict[str, str], list[str]]:
    """Decode a profile and return its entries and every problem found"""
    entries = decode(path)
    maxv, vlim = _number(entries, "maxv"), _number(entries, "vlim")
    fiber, camera_link, kilo_mode = (
        entries.get(key) == "1" for key in ("use_fiber", "use_CL", "fiber_mode")
    )
    pcie, hva, calibration = (
        entries.get("type") == "1",
        entries.get("hva"),
        entries.get("calibration"),
    )
    kilo_ok = hva not in KILO_TYPES or (fiber and kilo_mode)
    checks = (
        (len(path.stem) == SERIAL_LENGTH, f"file name {path.stem!r} is not an 11-character serial"),
        (
            entries.get("type") in ("0", "1"),
            f"type {entries.get('type')!r} is not USB (0) or PCIe (1)",
        ),
        (
            entries.get("size") == SIGHT_ACTUATORS,
            f"size {entries.get('size')!r} is not {SIGHT_ACTUATORS}",
        ),
        (0 < vlim <= maxv, f"vlim {vlim} must be above 0 and at most maxv {maxv} (nan: missing)"),
        (
            (maps / entries.get("map", "")).is_file(),
            f"map file {entries.get('map')!r} is missing from {maps}",
        ),
        (
            not calibration or (calibrations / calibration).is_file(),
            f"no calibration {calibration!r}",
        ),
        (
            not pcie or hva in HVA_TYPES,
            f"hva {hva!r} is not one of BMC's types {sorted(HVA_TYPES)}",
        ),
        (not pcie or fiber != camera_link, "exactly one of use_fiber and use_CL must be 1"),
        (not pcie or kilo_ok, "a kilo driver needs use_fiber=1 and fiber_mode=1"),
        (not pcie or hva != "1" or not kilo_mode, "an S-driver must not set fiber_mode=1"),
        (not pcie or hva != "0" or camera_link, "a Camera Link driver needs use_CL=1"),
    )
    unknown = [f"unknown key {key!r}" for key in entries if key not in KNOWN_KEYS]
    return entries, unknown + [message for passed, message in checks if not passed]


def main(argv: list[str] | None = None) -> int:
    """Audit one profile and print its entries and problems"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--maps", type=Path, default=SDK_ROOT / "Map")
    parser.add_argument("--calibrations", type=Path, default=SDK_ROOT / "Calibration")
    args = parser.parse_args(argv)
    if not args.profile.is_file():
        print(f"audit_profile: no profile at {args.profile}; copy BMC's files there first")
        return 1
    entries, problems = audit(args.profile, args.maps, args.calibrations)
    for key, value in entries.items():
        print(f"  {key} = {value}")
    driver, hva = DRIVER_TYPES.get(entries.get("type", "")), HVA_TYPES.get(entries.get("hva", ""))
    print(f"audit_profile: driver {driver}, HVA type {hva}", flush=True)
    report = {
        "profile": str(args.profile.resolve()),
        "sha256": hashlib.sha256(args.profile.read_bytes()).hexdigest(),
        "entries": entries,
    }
    return bringup.finish(f"audit_profile_{args.profile.stem}", report, problems)


if __name__ == "__main__":
    sys.exit(main())
