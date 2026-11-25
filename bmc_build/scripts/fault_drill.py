"""Phase 0 fault drill: interrupt a held shape on the dummy driver and check the cleanup

Starts a child that holds the inst flat (or runs flash_edge or simulate_turbulence on
it), interrupts it with Ctrl-C, SIGTERM, SIGHUP or an exception, and checks that the
bias came back and the harness zeroed and disconnected. kill -9 cannot be drilled here:
it skips every cleanup, and the dummy driver shows nothing.
Exit status: 0 if every case passed, 1 otherwise.
"""

import argparse
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Final

import bringup
from bmc_dm import zernike_basis

READY: Final = "fault_drill: ready"
CLEANUP_LINES: Final = ("bringup: zeroed", "bringup: disconnected", "bias restored: True")
FLAT: Final = "inst"
FLAT_MAXIMUM: Final = 0.6
FLAT_CAP: Final = 0.56
FLASH_AMPLITUDE: Final = -0.1
FLASH_PAUSE_S: Final = 0.1
TURBULENCE_NOLLS: Final = (2, 3, 4)
TURBULENCE_AMPLITUDE: Final = 0.001
TURBULENCE_RATE_HZ: Final = 5.0
# Longer than any case needs, so only the interruption ends the child
CHILD_HOLD_S: Final = 60.0
# Lets flash_edge and turbulence get going before the signal
SETTLE_S: Final = 0.5
CHILD_TIMEOUT_S: Final = 30.0


@dataclass(frozen=True)
class Case:
    """One way of interrupting the child"""

    activity: str
    interruption: signal.Signals | None  # None: the child raises an exception itself
    # Python ends an uncaught Ctrl-C by re-raising SIGINT (-2); session() turns SIGTERM and
    # SIGHUP into SystemExit(128 + signal); simulate_turbulence handles Ctrl-C and returns
    expected_exit: int


CASES: Final = (
    Case("hold", signal.SIGINT, -signal.SIGINT),
    Case("hold", signal.SIGTERM, 128 + signal.SIGTERM),
    Case("hold", signal.SIGHUP, 128 + signal.SIGHUP),
    Case("flash", signal.SIGINT, -signal.SIGINT),
    Case("turbulence", signal.SIGINT, 0),
    Case("error", None, 1),
)


def child(activity: str) -> None:
    """Hold the flat, then run activity until interrupted"""
    with bringup.session(hardware=False, maximum=FLAT_MAXIMUM) as dm:
        flat = dm.config.flats[FLAT]
        bringup.send(dm, flat, cap=FLAT_CAP, label=FLAT)
        # Build the Zernike basis now, so the signal lands inside the routine's loop
        zernike_basis(dm.actuator_map, max(TURBULENCE_NOLLS))
        print(READY, flush=True)
        try:
            match activity:
                case "hold":
                    time.sleep(CHILD_HOLD_S)
                case "flash":
                    iterations = round(CHILD_HOLD_S / (2 * FLASH_PAUSE_S))
                    dm.flash_edge(FLASH_AMPLITUDE, FLASH_PAUSE_S, iterations, bias=flat)
                case "turbulence":
                    dm.simulate_turbulence(
                        list(TURBULENCE_NOLLS),
                        TURBULENCE_AMPLITUDE,
                        TURBULENCE_RATE_HZ,
                        CHILD_HOLD_S,
                        bias=flat,
                    )
                case "error":
                    raise RuntimeError("deliberate error")
        finally:
            restored = bool((dm.get_vector() == dm.actuator_map.to_vector(flat)).all())
            print(f"bias restored: {restored}", flush=True)


def run_case(case: Case) -> tuple[bool, str]:
    """Run one child, interrupt it, and check its exit status and cleanup lines"""
    command = [sys.executable, "-u", "-X", "faulthandler", __file__, "--child", case.activity]
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    ) as process:
        # Read one stream to the end: communicate() would skip output already buffered here
        watchdog = threading.Timer(CHILD_TIMEOUT_S, process.kill)
        watchdog.start()
        lines = []
        try:
            for line in process.stdout or ():
                lines.append(line.rstrip())
                if line.startswith(READY) and case.interruption is not None:
                    time.sleep(SETTLE_S)
                    process.send_signal(case.interruption)
        finally:
            watchdog.cancel()
    print("\n".join(f"    {line}" for line in lines), flush=True)
    missing = [line for line in CLEANUP_LINES if line not in lines]
    passed = not missing and process.returncode == case.expected_exit
    return passed, f"exit {process.returncode} (expected {case.expected_exit}), missing {missing}"


def main(argv: list[str] | None = None) -> int:
    """Run every case, or one child when called with --child"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", choices=sorted({case.activity for case in CASES}))
    args = parser.parse_args(argv)
    if args.child:
        child(args.child)
        return 0
    results: dict[str, dict[str, object]] = {}
    for case in CASES:
        name = f"{case.activity}, {case.interruption.name if case.interruption else 'exception'}"
        print(f"== {name}", flush=True)
        passed, detail = run_case(case)
        results[name] = {"passed": passed, "detail": detail}
        print(f"-- {name}: {'passed' if passed else 'FAILED'} ({detail})", flush=True)
    passed_all = all(result["passed"] for result in results.values())
    path = bringup.write_report("fault_drill", {"utc": bringup.utc_stamp(), "cases": results})
    print(f"fault_drill: {'all passed' if passed_all else 'FAILED'}; report {path}", flush=True)
    return 0 if passed_all else 1


if __name__ == "__main__":
    sys.exit(main())
