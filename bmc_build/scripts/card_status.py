"""Read-only status of the BMC PCIe card and the driver box behind it

Runs BMC's bmc_ltest with -i only: that option only reads registers, while its others write
them (pokes, zeroing, sequences). Decodes the fiber, high-voltage and kilo status bits,
checks the card, optionally compares with the newest report of another label or repeats the
read, and writes logs/card_<label>_<utc>.json.

usage: card_status.py [--label LABEL] [--compare LABEL] [--cycles N]
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Final

import bringup

LTEST: Final = Path("/opt/Boston Micromachines/sys/bin/bmc_ltest")
# The only arguments ever passed: board 0, read-only info
LTEST_ARGS: Final = ("-b", "0", "-i")
LTEST_TIMEOUT_S: Final = 10.0
# BMC's design ID, the top 16 bits of the hardware revision register
DESIGN_ID: Final = "v2000"
# Status register bits, least significant first (bmc_mdlib.h); the SFP module is present
# while its bit is clear
REGISTERS: Final = {
    "fiber": ("sfp_absent", "sfp_tx_fault", "loss_of_light", "channel_up", "lane_up")
    + ("soft_error", "hard_error"),
    "hv": ("hv_on", "data_dropped", "dacs_busy", "error_since_power_on"),
    "kilo": ("dac_overflow", "bad_address", "fifo_half_full"),
}
# One line each in bmc_ltest -i output (DoInfo in bmc_ltest.c)
_LINES: Final = {
    "boards": r"we detect (\d+) boards",
    "lib_rev": r"lib rev: '([^']*)'",
    "driver_rev": r"drv rev: '([^']*)'",
    "hw_rev": r"HW  rev: '([^']*)'",
    "hva_mode": r"HVA:\s+(.+)$",
    "orientation": r"orien:\s+(.+)$",
    "fiber": r"fiber:\s+(0x[0-9A-Fa-f]+)",
    "hv": r"HVAcc:\s+(0x[0-9A-Fa-f]+)",
    "kilo": r"Kilo:\s+(0x[0-9A-Fa-f]+)",
    "sequence_rate": r"seqRate:\s+(\S+)",
}
# bmc_ltest prefixes failures with "ERR: "; the library prints these instead of a version
_ERROR_MARKERS: Final = ("ERR:", "--no driver--", "--invalid driver--")


def read() -> str:
    """Run bmc_ltest -b 0 -i and return its output"""
    return subprocess.run(
        [str(LTEST), *LTEST_ARGS],
        capture_output=True,
        text=True,
        timeout=LTEST_TIMEOUT_S,
        check=True,
    ).stdout


def parse(text: str) -> dict[str, object]:
    """Return each line's value, with the status registers decoded into register.bit flags"""
    fields: dict[str, object] = {
        name: match.group(1).strip()
        for name, pattern in _LINES.items()
        if (match := re.search(pattern, text, re.MULTILINE))
    }
    for register, bits in REGISTERS.items():
        if register in fields:
            value = int(str(fields[register]), 16)
            fields |= {
                f"{register}.{bit}": bool(value >> index & 1) for index, bit in enumerate(bits)
            }
    return fields


def problems(text: str, fields: dict[str, object]) -> list[str]:
    """Return error lines, missing lines, extra boards and a foreign design"""
    found = [line.strip() for line in text.splitlines() if any(m in line for m in _ERROR_MARKERS)]
    found += [f"no {name} line" for name in _LINES if name not in fields]
    if fields.get("boards", "1") != "1":
        found.append(f"{fields['boards']} boards, expected 1")
    if not str(fields.get("hw_rev", DESIGN_ID)).startswith(DESIGN_ID):
        found.append(f"hardware revision {fields['hw_rev']!r} is not BMC's design {DESIGN_ID}")
    return found


def changes(before: dict[str, object], after: dict[str, object]) -> list[str]:
    """Return one line per field that differs between two readings"""
    names = sorted(before.keys() | after.keys())
    return [
        f"{n}: {before.get(n)} -> {after.get(n)}" for n in names if before.get(n) != after.get(n)
    ]


def main(argv: list[str] | None = None) -> int:
    """Read the card (and again cycles times), check it, compare and report"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="status", help="report name, e.g. boxoff or boxon")
    parser.add_argument("--compare", metavar="LABEL", help="compare with the newest LABEL report")
    parser.add_argument("--cycles", type=int, default=0, help="extra reads that must match")
    args = parser.parse_args(argv)
    if not LTEST.is_file():
        print(f"card_status: bmc_ltest is not installed at {LTEST}", flush=True)
        return 1
    baselines = sorted(bringup.LOGS_DIR.glob(f"card_{args.compare}_*.json")) if args.compare else []
    if args.compare and not baselines:
        print(f"card_status: no card_{args.compare} report to compare with", flush=True)
        return 1
    text = read()
    print(text, end="", flush=True)
    fields = parse(text)
    found = problems(text, fields)
    differing = sum(read() != text for _ in range(args.cycles))
    if differing:
        found.append(f"{differing} of {args.cycles} repeated reads differ from the first")
    differences = []
    if baselines:
        baseline = json.loads(baselines[-1].read_text(encoding="utf-8"))["fields"]
        differences = changes(baseline, fields)
        print(f"card_status: compared with {baselines[-1].name}:", flush=True)
        print("\n".join(f"  {line}" for line in differences) or "  no change", flush=True)
    report = {"fields": fields, "changes": differences, "cycles": args.cycles, "output": text}
    return bringup.finish(f"card_{args.label}", report, found)


if __name__ == "__main__":
    sys.exit(main())
