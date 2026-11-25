"""Read-only status of the BMC PCIe card and the driver box behind it

Runs BMC's bmc_ltest with -i, which only reads registers: board count, revisions, HVA mode,
orientation, fiber link, high-voltage and kilo status, sequence rate. Every other
bmc_ltest option can write registers (pokes, zeroing, sequences), so this script never
passes anything else. Decodes the status registers, checks the card, compares with an
earlier report and writes a JSON report.

usage: card_status.py [--label LABEL] [--compare LABEL] [--cycles N]
Exit status: 0 if every check passed, 1 otherwise.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import bringup

LTEST: Final = Path("/opt/Boston Micromachines/sys/bin/bmc_ltest")
# The only arguments ever passed: board 0, read-only info
LTEST_ARGS: Final = ("-b", "0", "-i")
LTEST_TIMEOUT_S: Final = 10.0
EXPECTED_BOARDS: Final = 1
# BMC's design ID, the top 16 bits of the hardware revision register
DESIGN_ID: Final = "v2000"

# Status register bits, least significant first (bmc_mdlib.h)
FIBER_BITS: Final = (
    "sfp_absent",  # SFP_nPRST: clear while the SFP module is present
    "sfp_tx_fault",
    "loss_of_light",
    "channel_up",
    "lane_up",
    "soft_error",
    "hard_error",
)
HV_BITS: Final = ("hv_on", "data_dropped", "dacs_busy", "error_since_power_on")
KILO_BITS: Final = ("dac_overflow", "bad_address", "fifo_half_full")

_FIELDS: Final = {
    "boards": re.compile(r"we detect (\d+) boards"),
    "lib_rev": re.compile(r"lib rev: '([^']*)'"),
    "driver_rev": re.compile(r"drv rev: '([^']*)'"),
    "hw_rev": re.compile(r"HW  rev: '([^']*)'"),
    "hva_mode": re.compile(r"HVA:\s+(.+)$"),
    "orientation": re.compile(r"orien:\s+(.+)$"),
    "fiber": re.compile(r"fiber:\s+(0x[0-9A-Fa-f]+)"),
    "hv": re.compile(r"HVAcc:\s+(0x[0-9A-Fa-f]+)"),
    "kilo": re.compile(r"Kilo:\s+(0x[0-9A-Fa-f]+)"),
    "sequence_rate": re.compile(r"seqRate:\s+(\S+)"),
}
_REGISTERS: Final = {"fiber": FIBER_BITS, "hv": HV_BITS, "kilo": KILO_BITS}
# bmc_ltest prefixes failures with "ERR: " and the library returns these instead of a version
_ERROR_MARKERS: Final = ("ERR:", "--no driver--", "--invalid driver--")

type Fields = dict[str, object]


class CardError(Exception):
    """Raised when bmc_ltest cannot be run"""


@dataclass(frozen=True)
class CardStatus:
    """One bmc_ltest -i reading, decoded"""

    text: str
    fields: Fields

    def problems(self) -> list[str]:
        """Return everything wrong with the reading, empty if the card looks right"""
        problems = [line.strip() for line in self.text.splitlines() if _is_error(line)]
        problems += [f"no {name} line" for name in _FIELDS if name not in self.fields]
        if self.fields.get("boards") not in (None, EXPECTED_BOARDS):
            problems.append(f"{self.fields['boards']} boards, expected {EXPECTED_BOARDS}")
        hw_rev = str(self.fields.get("hw_rev", ""))
        if "hw_rev" in self.fields and not hw_rev.startswith(DESIGN_ID):
            problems.append(f"hardware revision {hw_rev!r} is not BMC's design {DESIGN_ID}")
        return problems


def _is_error(line: str) -> bool:
    """Return True for a bmc_ltest error line"""
    return any(marker in line for marker in _ERROR_MARKERS)


def decode(register: str, value: int) -> Fields:
    """Return each named bit of a status register as a bool, keyed register.bit"""
    return {
        f"{register}.{name}": bool(value >> bit & 1)
        for bit, name in enumerate(_REGISTERS[register])
    }


def parse(text: str) -> CardStatus:
    """Parse bmc_ltest -i output into raw fields and decoded register bits"""
    fields: Fields = {}
    for line in text.splitlines():
        for name, pattern in _FIELDS.items():
            if match := pattern.search(line):
                fields[name] = match.group(1).strip()
    if "boards" in fields:
        fields["boards"] = int(str(fields["boards"]))
    for register in _REGISTERS:
        if register in fields:
            fields.update(decode(register, int(str(fields[register]), 16)))
    return CardStatus(text=text, fields=fields)


def read_status(executable: Path | None = None) -> CardStatus:
    """Run bmc_ltest -b 0 -i (LTEST unless given) and parse its output

    :raises CardError: if bmc_ltest is missing, hangs or exits with an error
    """
    executable = executable or LTEST
    if not executable.is_file():
        raise CardError(f"bmc_ltest is not installed at {executable}; run install_bmc_sdk.sh")
    try:
        result = subprocess.run(
            [str(executable), *LTEST_ARGS],
            capture_output=True,
            text=True,
            timeout=LTEST_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise CardError(f"bmc_ltest did not answer within {LTEST_TIMEOUT_S} s") from error
    if result.returncode != 0:
        raise CardError(f"bmc_ltest exited {result.returncode}: {result.stdout}{result.stderr}")
    return parse(result.stdout + result.stderr)


def changes(before: Fields, after: Fields) -> list[str]:
    """Return one line per field that differs between two readings"""
    names = sorted(before.keys() | after.keys())
    return [
        f"{name}: {before.get(name)} -> {after.get(name)}"
        for name in names
        if before.get(name) != after.get(name)
    ]


def latest_report(label: str) -> Fields:
    """Return the fields of the newest card report with label

    :raises CardError: if there is none
    """
    reports = sorted(bringup.LOGS_DIR.glob(f"card_{label}_*.json"))
    if not reports:
        raise CardError(f"no card_{label} report in {bringup.LOGS_DIR} to compare with")
    fields: Fields = json.loads(reports[-1].read_text(encoding="utf-8"))["fields"]
    return fields


def read_kernel_log(since: float) -> str:
    """Return the kernel log since a Unix time (the operator is in group adm)"""
    result = subprocess.run(
        ["journalctl", "-k", "--no-pager", "--since", f"@{since:.0f}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def kernel_problems(since: float, reader: Callable[[float], str] | None = None) -> list[str]:
    """Return kernel log lines since a Unix time that report a BUG, WARNING or call trace"""
    pattern = re.compile(r"\bBUG\b|\bWARNING\b|Call Trace|bmc_mdrv.*(fail|error)", re.IGNORECASE)
    log = (reader or read_kernel_log)(since)
    return [f"kernel: {line}" for line in log.splitlines() if pattern.search(line)]


def cycle(first: CardStatus, count: int, executable: Path | None = None) -> list[str]:
    """Read the card count more times; return problems, including any reading that changed"""
    problems = []
    for index in range(count):
        status = read_status(executable)
        problems += [f"cycle {index + 1}: {problem}" for problem in status.problems()]
        problems += [
            f"cycle {index + 1}: {change}" for change in changes(first.fields, status.fields)
        ]
        if problems:
            break
    return problems


def main(argv: list[str] | None = None) -> int:
    """Read the card once (or count times), check it, compare and report"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="status", help="report name, e.g. boxoff or boxon")
    parser.add_argument("--compare", metavar="LABEL", help="compare with the newest LABEL report")
    parser.add_argument("--cycles", type=int, default=0, help="extra read-only reads to repeat")
    args = parser.parse_args(argv)
    start = time.time()
    try:
        baseline = latest_report(args.compare) if args.compare else None
        status = read_status()
        print(status.text, end="", flush=True)
        problems = status.problems()
        if args.cycles:
            problems += cycle(status, args.cycles)
            problems += kernel_problems(start)
            print(f"card_status: {args.cycles} more reads, kernel log checked", flush=True)
    except CardError as error:
        print(f"card_status: {error}", flush=True)
        return 1
    differences = changes(baseline, status.fields) if baseline is not None else []
    if baseline is not None:
        print(f"card_status: compared with the newest {args.compare} report:", flush=True)
        print("\n".join(f"  {line}" for line in differences) or "  no change", flush=True)
    for problem in problems:
        print(f"card_status: PROBLEM: {problem}", flush=True)
    report = {
        "utc": bringup.utc_stamp(),
        "fields": status.fields,
        "compared_with": args.compare,
        "changes": differences,
        "cycles": args.cycles,
        "problems": problems,
        "output": status.text,
    }
    path = bringup.write_report(f"card_{args.label}", report)
    print(f"card_status: {'FAILED' if problems else 'passed'}; report {path}", flush=True)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
