"""Phase 1 audit of a BMC profile (.dm) before it is used to open the real mirror

Decodes the profile (every byte XOR-ed with 0x83, newlines raw) and checks what the SDK
does not:

* size is 648 and type is USB (0) or PCIe (1), not the dummy driver (2);
* maxv and vlim are present and vlim <= maxv (otherwise DAC counts overflow 16 bits and
  wrap, so 1.0 no longer means vlim);
* the map file it names exists in the maps folder (a missing map makes open_dm fail with
  the DM already open, and on USB with high voltage on), and so does the calibration file;
* for PCIe, the HVA type is known and its fiber and Camera Link settings agree with it
  (the SDK only logs a warning, then writes them to the card);
* the file name is the 11-character serial, and no key is unknown to the SDK.

usage: audit_profile.py PROFILE.dm [--maps FOLDER] [--calibrations FOLDER]
Writes a JSON report. Exit status: 0 if every check passed, 1 otherwise.
"""

import argparse
import sys
from pathlib import Path
from typing import Final

import bringup

SDK_ROOT: Final = Path("/opt/Boston Micromachines")
SIGHT_ACTUATORS: Final = 648
SERIAL_LENGTH: Final = 11
DRIVER_TYPES: Final = {"0": "USB", "1": "PCIe", "2": "dummy"}
HARDWARE_TYPES: Final = frozenset({"0", "1"})
PCIE: Final = "1"
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
    {
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
    }
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


def _number(entries: dict[str, str], key: str) -> float | None:
    """Return a numeric value, or None if it is missing or not a number"""
    try:
        return float(entries[key])
    except (KeyError, ValueError):
        return None


def check_voltages(entries: dict[str, str]) -> list[str]:
    """Return problems with maxv and vlim"""
    maxv, vlim = _number(entries, "maxv"), _number(entries, "vlim")
    if maxv is None or vlim is None:
        return ["maxv or vlim is missing or not a number"]
    if not 0 < vlim <= maxv:
        return [f"vlim {vlim} must be above 0 and at most maxv {maxv}"]
    return []


def check_files(entries: dict[str, str], maps: Path, calibrations: Path) -> list[str]:
    """Return problems with the map and calibration files the profile names"""
    problems = []
    if not entries.get("map"):
        problems.append("no map file named; ask BMC whether this driver needs one")
    elif not (maps / entries["map"]).is_file():
        problems.append(f"map file {maps / entries['map']} is missing")
    calibration = entries.get("calibration")
    if calibration and not (calibrations / calibration).is_file():
        problems.append(f"calibration file {calibrations / calibration} is missing")
    return problems


def check_pcie(entries: dict[str, str]) -> list[str]:
    """Return problems with a PCIe profile's HVA type, fiber and Camera Link settings"""
    if entries.get("type") != PCIE:
        return []
    hva = entries.get("hva")
    if hva not in HVA_TYPES:
        return [f"hva {hva!r} is not one of BMC's types {sorted(HVA_TYPES)}"]
    fiber, camera_link = entries.get("use_fiber") == "1", entries.get("use_CL") == "1"
    kilo_mode = entries.get("fiber_mode") == "1"
    problems = []
    if fiber == camera_link:
        problems.append("exactly one of use_fiber and use_CL must be 1")
    if hva in KILO_TYPES and not (fiber and kilo_mode):
        problems.append(f"{HVA_TYPES[hva]} needs use_fiber=1 and fiber_mode=1")
    if hva == "1" and kilo_mode:
        problems.append("an S-driver must not set fiber_mode=1")
    if hva == "0" and not camera_link:
        problems.append("a Camera Link driver needs use_CL=1")
    return problems


def audit(path: Path, maps: Path, calibrations: Path) -> tuple[dict[str, str], list[str]]:
    """Decode a profile and return its entries and every problem found"""
    entries = decode(path)
    problems = [f"unknown key {key!r}" for key in entries if key not in KNOWN_KEYS]
    if len(path.stem) != SERIAL_LENGTH:
        problems.append(f"file name {path.stem!r} is not an {SERIAL_LENGTH}-character serial")
    if entries.get("type") not in HARDWARE_TYPES:
        problems.append(f"type {entries.get('type')!r} is not USB (0) or PCIe (1)")
    if entries.get("size") != str(SIGHT_ACTUATORS):
        problems.append(f"size {entries.get('size')!r} is not {SIGHT_ACTUATORS}")
    problems += check_voltages(entries)
    problems += check_pcie(entries)
    problems += check_files(entries, maps, calibrations)
    return entries, problems


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
    driver = DRIVER_TYPES.get(entries.get("type", ""), "unknown")
    hva = HVA_TYPES.get(entries.get("hva", ""), "unknown")
    print(f"audit_profile: driver {driver}, HVA type {hva}")
    for problem in problems:
        print(f"audit_profile: PROBLEM: {problem}")
    report = {
        "utc": bringup.utc_stamp(),
        "profile": str(args.profile.resolve()),
        "sha256": bringup.sha256(args.profile),
        "entries": entries,
        "problems": problems,
    }
    path = bringup.write_report(f"audit_profile_{args.profile.stem}", report)
    print(f"audit_profile: {'FAILED' if problems else 'passed'}; report {path}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
