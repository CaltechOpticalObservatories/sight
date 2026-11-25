"""Phase 0 rehearsal: the hardware phases' actions on the SDK's dummy driver

Prints the SDK module's path and version, then runs straight through the test plan's steps
with its amplitudes and caps: connect, wrong serial, first motion, refusals, flat ramp,
flash_edge, turbulence and persistence. Stops at the first failure; exit status 1.
"""

import sys
import time
from typing import Final

import bmc  # pylint: disable=import-error  # BMC's SDK, on PYTHONPATH through run.sh
import bringup
import numpy as np
from bmc_dm import ActuatorMap, BmcDmController, DMError, MirrorState, actuators, zernike_basis

SDK_VERSION: Final = "4.1.3"
SIGHT_SIDE: Final = 28
MISSING_SERIAL: Final = "NOPROFILE00"
# Nearest the center of the 28 x 28 grid (13.5, 13.5), the lowest index of the four
CENTER_ACTUATOR: Final = 309
FIRST_MOTION: Final = (0.05, 0.1, 0.2, 0.3)
FIRST_MOTION_CAP: Final = 0.3
FLAT: Final = "inst"
FLAT_STEPS: Final = (0.25, 0.5, 0.75, 1.0)
FLAT_MAXIMUM: Final = 0.6
FLAT_CAP: Final = 0.56
TURBULENCE_NOLLS: Final = (2, 3, 4)
TURBULENCE_RATE_HZ: Final = 5.0
TURBULENCE_DURATION_S: Final = 1.0
# Allowed lateness of the whole turbulence run, for scheduling jitter
TURBULENCE_SLACK_S: Final = 0.2


class CheckFailed(Exception):
    """Raised when a rehearsal step sees the wrong result"""


def expect(condition: bool, message: str) -> None:
    """Raise CheckFailed with message unless condition holds"""
    if not condition:
        raise CheckFailed(message)


def holds(dm: BmcDmController, surface: np.ndarray) -> bool:
    """Return True if the last command is exactly surface on the actuators"""
    return bool(np.array_equal(dm.get_vector(), dm.actuator_map.to_vector(surface)))


def first_motion() -> None:
    """Phase 2 and 3: connect, poke the center actuator, refuse commands over the limits"""
    with bringup.session(hardware=False) as dm:
        expect(
            np.array_equal(dm.actuator_map.indices, ActuatorMap.circular(SIGHT_SIDE).indices),
            "the bundle's actuator map is not BMC's circular 28 x 28 layout",
        )
        report = dm.status_report()
        expect(report.mirror_state is MirrorState.ZEROED, f"on connect: {report.summary()}")
        pattern = actuators(dm.actuator_map, CENTER_ACTUATOR)
        for amplitude in FIRST_MOTION:
            label = f"actuator {CENTER_ACTUATOR} at {amplitude}"
            bringup.send(dm, amplitude * pattern, cap=FIRST_MOTION_CAP, label=label)
            dm.zero()
        for amplitude in (FIRST_MOTION_CAP + 0.05, dm.config.soft_limits[1] + 0.1):
            try:
                bringup.send(dm, amplitude * pattern, cap=FIRST_MOTION_CAP, label=f"{amplitude}")
            except bringup.RefusedStep as error:
                print(f"rehearse: refused as expected: {error}", flush=True)
            else:
                raise CheckFailed(f"{amplitude} was sent")
    dm = BmcDmController(bringup.load_config(hardware=False))
    try:
        dm.connect(MISSING_SERIAL)
    except DMError as error:
        print(f"rehearse: wrong serial refused as expected: {error}", flush=True)
    else:
        dm.disconnect()
        raise CheckFailed(f"{MISSING_SERIAL} connected")


def flats_and_routines() -> None:
    """Phase 5a, 6 and 7: flat ramp, flash_edge, turbulence, then persistence"""
    with bringup.session(hardware=False, maximum=FLAT_MAXIMUM, zero_on_exit=False) as dm:
        flat = dm.config.flats[FLAT]
        for fraction in FLAT_STEPS:
            bringup.send(dm, fraction * flat, cap=FLAT_CAP, label=f"{fraction} x {FLAT}")
        dm.flash_edge(-0.1, pause_s=0.0, iterations=3, bias=flat)
        expect(holds(dm, flat), "flash_edge did not restore the flat")
        # Build the Zernike basis first, so the timing covers only the sends and holds
        zernike_basis(dm.actuator_map, max(TURBULENCE_NOLLS))
        start = time.monotonic()
        applied = dm.simulate_turbulence(
            list(TURBULENCE_NOLLS), 0.001, TURBULENCE_RATE_HZ, TURBULENCE_DURATION_S, bias=flat
        )
        elapsed = time.monotonic() - start
        expect(holds(dm, flat), "simulate_turbulence did not restore the flat")
        expect(len(applied) == round(TURBULENCE_RATE_HZ * TURBULENCE_DURATION_S), "steps lost")
        expect(elapsed <= TURBULENCE_DURATION_S + TURBULENCE_SLACK_S, f"took {elapsed:.2f} s")
    with bringup.session(hardware=False, maximum=FLAT_MAXIMUM) as dm:
        report = dm.status_report()
        expect(report.mirror_state is MirrorState.ZEROED, f"on reconnect: {report.summary()}")
        expect(holds(dm, flat), "the saved command is not the flat")
        dm.restore()
        expect(dm.status_report().mirror_state is MirrorState.HOLDING, "restore() sent nothing")


def main() -> int:
    """Check the SDK, run the rehearsal and report"""
    version = bmc.BmcDm().version_string()
    print(f"rehearse: SDK {version!r} from {bmc.__file__}", flush=True)
    problems = [] if SDK_VERSION in version else [f"SDK version is not {SDK_VERSION}"]
    try:
        first_motion()
        flats_and_routines()
    except (CheckFailed, bringup.RefusedStep, DMError, ValueError) as error:
        problems.append(f"{type(error).__name__}: {error}")
    return bringup.finish("rehearse", {"sdk": version, "sdk_module": bmc.__file__}, problems)


if __name__ == "__main__":
    sys.exit(main())
