"""Phase 0 rehearsal: the hardware phases' actions on the SDK's dummy driver

Each check opens its own session, as the hardware scripts will, with the same pattern
amplitudes and caps as the test plan. Writes a JSON report to logs/.
Exit status: 0 if every check passed, 1 otherwise.
"""

import argparse
import sys
import time
from collections.abc import Callable
from typing import Final

import bringup
import numpy as np
from bmc_dm import (
    ActuatorMap,
    BmcDmController,
    DMError,
    MirrorState,
    actuators,
    columns,
    grid,
    letter_f,
    rows,
    zernike_basis,
)

CONNECT_CYCLES: Final = 3
SIGHT_ACTUATORS: Final = 648
MISSING_SERIAL: Final = "NOPROFILE00"
FIRST_MOTION: Final = (0.05, 0.1, 0.2, 0.3)
FIRST_MOTION_CAP: Final = 0.3
MAP_AMPLITUDE: Final = 0.2
GRID_AMPLITUDE: Final = 0.1
GRID_SPACING: Final = 4
FLAT: Final = "inst"
FLAT_STEPS: Final = (0.25, 0.5, 0.75, 1.0)
FLAT_MAXIMUM: Final = 0.6
FLAT_CAP: Final = 0.56
FLASH_AMPLITUDE: Final = -0.1
FLASH_ITERATIONS: Final = 3
TURBULENCE_NOLLS: Final = (2, 3, 4)
TURBULENCE_AMPLITUDE: Final = 0.001
TURBULENCE_RATE_HZ: Final = 5.0
TURBULENCE_DURATION_S: Final = 1.0
# Allowed lateness of the whole turbulence run, for scheduling jitter
TURBULENCE_SLACK_S: Final = 0.2

type Check = Callable[[float], str]


class CheckFailed(Exception):
    """Raised when a rehearsal check sees the wrong result"""


def _expect(condition: bool, message: str) -> None:
    """Raise CheckFailed with message unless condition holds"""
    if not condition:
        raise CheckFailed(message)


def center_actuator(actuator_map: ActuatorMap) -> int:
    """Return the actuator nearest the grid center (the lowest index on a tie)"""
    row, column = np.nonzero(actuator_map.mask)
    center = (actuator_map.side - 1) / 2
    distance = np.hypot(row - center, column - center)
    candidates = actuator_map.indices[row, column][distance == distance.min()]
    return int(candidates.min())


def _holds(dm: BmcDmController, surface: np.ndarray) -> bool:
    """Return True if the last command is exactly surface on the actuators"""
    return bool(np.array_equal(dm.get_vector(), dm.actuator_map.to_vector(surface)))


def connect_cycle(dwell_s: float) -> str:
    """Phase 2: connect, read, disconnect, several times"""
    for cycle in range(CONNECT_CYCLES):
        with bringup.session(hardware=False) as dm:
            report = dm.status_report()
            _expect(
                dm.actuator_map.num_actuators == SIGHT_ACTUATORS,
                f"cycle {cycle}: {dm.actuator_map.num_actuators} actuators",
            )
            _expect(
                report.mirror_state is MirrorState.ZEROED and not dm.get_vector().any(),
                f"cycle {cycle}: {report.summary()}",
            )
            bringup.dwell(dwell_s)
    return f"{CONNECT_CYCLES} cycles, each zeroed on connect"


def wrong_serial(_dwell_s: float) -> str:
    """Phase 2: a serial without a profile gives a readable DMError"""
    dm = BmcDmController(bringup.load_config(hardware=False))
    try:
        dm.connect(MISSING_SERIAL)
    except DMError as error:
        return f"refused: {error}"
    dm.disconnect()
    raise CheckFailed(f"{MISSING_SERIAL} connected")


def first_motion(dwell_s: float) -> str:
    """Phase 3: poke the center actuator at rising amplitudes, zeroing in between"""
    with bringup.session(hardware=False) as dm:
        index = center_actuator(dm.actuator_map)
        for amplitude in FIRST_MOTION:
            surface = amplitude * actuators(dm.actuator_map, index)
            command_plan = bringup.send(
                dm, surface, cap=FIRST_MOTION_CAP, label=f"actuator {index} at {amplitude}"
            )
            _expect(command_plan.moved == 1, f"{command_plan.moved} actuators moved")
            bringup.dwell(dwell_s)
            dm.zero()
        _expect(not dm.get_vector().any(), "not zero at the end")
    return f"actuator {index} at {FIRST_MOTION}"


def over_cap_refused(_dwell_s: float) -> str:
    """Phase 3 guard: a peak over the cap, or over the soft maximum, is never sent"""
    with bringup.session(hardware=False) as dm:
        pattern = actuators(dm.actuator_map, center_actuator(dm.actuator_map))
        maximum = dm.config.soft_limits[1]
        refused = []
        for amplitude, cap in ((FIRST_MOTION_CAP + 0.05, FIRST_MOTION_CAP), (maximum + 0.1, 1.0)):
            try:
                bringup.send(dm, amplitude * pattern, cap=cap, label=f"{amplitude} (must refuse)")
            except bringup.RefusedStep as error:
                refused.append(str(error))
                continue
            raise CheckFailed(f"{amplitude} with cap {cap} was sent")
        _expect(dm.status_report().last_command_at is None, "a command reached the SDK")
    return "; ".join(refused)


def map_orientation(dwell_s: float) -> str:
    """Phase 4: single actuators, a row, a column and the F, then grids covering every actuator"""
    with bringup.session(hardware=False) as dm:
        actuator_map = dm.actuator_map
        middle = actuator_map.side // 2
        edge_actuator = int(actuator_map.edge_actuators[actuator_map.edge_actuators.size // 4])
        patterns = {
            "actuator 0": actuators(actuator_map, 0),
            f"edge actuator {edge_actuator}": actuators(actuator_map, edge_actuator),
            f"row {middle}": rows(actuator_map, middle),
            f"column {middle}": columns(actuator_map, middle),
            "letter F": letter_f(actuator_map),
        }
        for label, pattern in patterns.items():
            bringup.send(dm, MAP_AMPLITUDE * pattern, cap=MAP_AMPLITUDE, label=label)
            bringup.dwell(dwell_s)
            dm.zero()
        coverage = np.zeros(actuator_map.num_actuators)
        for row in range(GRID_SPACING):
            for column in range(GRID_SPACING):
                pattern = grid(actuator_map, row, column, GRID_SPACING)
                label = f"grid {row},{column}"
                bringup.send(dm, GRID_AMPLITUDE * pattern, cap=GRID_AMPLITUDE, label=label)
                coverage += actuator_map.to_vector(pattern)
                bringup.dwell(dwell_s)
                dm.zero()
        _expect(bool((coverage == 1).all()), "grids do not move every actuator exactly once")
    return f"{len(patterns)} patterns, {GRID_SPACING**2} grids covering all actuators once"


def flat_ramp(dwell_s: float) -> str:
    """Phase 5a: ramp the flat up in fractions under a raised soft maximum"""
    with bringup.session(hardware=False, maximum=FLAT_MAXIMUM) as dm:
        flat = dm.config.flats[FLAT]
        peaks = []
        for fraction in FLAT_STEPS:
            label = f"{fraction} x {FLAT}"
            peaks.append(
                round(bringup.send(dm, fraction * flat, cap=FLAT_CAP, label=label).peak, 3)
            )
            bringup.dwell(dwell_s)
        _expect(_holds(dm, flat), "the last step is not the flat")
    return f"peaks {peaks}"


def dynamic(_dwell_s: float) -> str:
    """Phase 6: flash_edge and simulate_turbulence restore the flat and keep the rate"""
    with bringup.session(hardware=False, maximum=FLAT_MAXIMUM) as dm:
        flat = dm.config.flats[FLAT]
        bringup.send(dm, flat, cap=FLAT_CAP, label=FLAT)
        dm.flash_edge(FLASH_AMPLITUDE, pause_s=0.0, iterations=FLASH_ITERATIONS, bias=flat)
        _expect(_holds(dm, flat), "flash_edge did not restore the flat")
        # Build the Zernike basis first, so the timing covers only the sends and holds
        zernike_basis(dm.actuator_map, max(TURBULENCE_NOLLS))
        start = time.monotonic()
        applied = dm.simulate_turbulence(
            list(TURBULENCE_NOLLS),
            TURBULENCE_AMPLITUDE,
            rate_hz=TURBULENCE_RATE_HZ,
            duration_s=TURBULENCE_DURATION_S,
            bias=flat,
        )
        elapsed = time.monotonic() - start
        _expect(_holds(dm, flat), "simulate_turbulence did not restore the flat")
        steps = round(TURBULENCE_RATE_HZ * TURBULENCE_DURATION_S)
        _expect(len(applied) == steps, f"{len(applied)} of {steps} wavefronts applied")
        _expect(
            elapsed <= TURBULENCE_DURATION_S + TURBULENCE_SLACK_S,
            f"turbulence took {elapsed:.2f} s for {TURBULENCE_DURATION_S} s",
        )
    return f"flash_edge x{FLASH_ITERATIONS}; {steps} wavefronts in {elapsed:.2f} s"


def persistence(_dwell_s: float) -> str:
    """Phase 7: the flat is saved, connect sends nothing, restore() puts it back"""
    with bringup.session(hardware=False, maximum=FLAT_MAXIMUM, zero_on_exit=False) as dm:
        flat = dm.config.flats[FLAT]
        bringup.send(dm, flat, cap=FLAT_CAP, label=FLAT)
    with bringup.session(hardware=False, maximum=FLAT_MAXIMUM) as dm:
        report = dm.status_report()
        _expect(report.mirror_state is MirrorState.ZEROED, f"on connect: {report.summary()}")
        _expect(_holds(dm, flat), "the saved command is not the flat")
        dm.restore()
        report = dm.status_report()
        _expect(report.mirror_state is MirrorState.HOLDING, f"after restore: {report.summary()}")
    return "flat saved, loaded without sending, restored"


# Persistence runs last and ends zeroed, so earlier checks start from zeros
CHECKS: Final[tuple[Check, ...]] = (
    connect_cycle,
    wrong_serial,
    first_motion,
    over_cap_refused,
    map_orientation,
    flat_ramp,
    dynamic,
    persistence,
)


def main(argv: list[str] | None = None) -> int:
    """Run every check and report the results"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dwell-s", type=float, default=0.0, help="hold time per step")
    args = parser.parse_args(argv)
    results: dict[str, dict[str, object]] = {}
    for check in CHECKS:
        print(f"== {check.__name__}", flush=True)
        try:
            results[check.__name__] = {"passed": True, "detail": check(args.dwell_s)}
        except (CheckFailed, bringup.RefusedStep, DMError, ValueError) as error:
            results[check.__name__] = {
                "passed": False,
                "detail": f"{type(error).__name__}: {error}",
            }
        print(f"-- {check.__name__}: {results[check.__name__]}", flush=True)
    passed = all(result["passed"] for result in results.values())
    path = bringup.write_report("rehearse", {"utc": bringup.utc_stamp(), "checks": results})
    print(f"rehearse: {'all passed' if passed else 'FAILED'}; report {path}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
