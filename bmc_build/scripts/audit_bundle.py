"""Phase 1 software audit of the bring-up bundle (no SDK, no hardware)

Checks that the actuator map is BMC's circular 28 x 28 layout and that every bundle file
matches the driver's configs/sight copy, then reports each flat's range, largest neighbor
step and how many values each phase's soft maximum would clip. Writes a JSON report.
Exit status: 0 if every check passed, 1 otherwise.
"""

import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

import bringup
import numpy as np
from bmc_dm import ActuatorMap, DMConfig

SIGHT_SIDE: Final = 28
SIGHT_ACTUATORS: Final = 648
SIGHT_EDGE_ACTUATORS: Final = 80
DRIVER_BUNDLE: Final = bringup.BUILD_DIR / "driver" / "configs" / "sight"
# Soft maximum of each phase group in the test plan: bring-up, flat ramp, Sight
PHASE_MAXIMUMS: Final = (0.4, 0.6, 0.8)


@dataclass(frozen=True)
class FlatStats:
    """A flat's values on the actuators, in command units"""

    minimum: float
    maximum: float
    max_neighbor_step: float
    clipped: tuple[int, ...]  # Values above each of PHASE_MAXIMUMS

    def row(self, name: str) -> str:
        """Return the stats as one table row"""
        clipped = " / ".join(map(str, self.clipped))
        return (
            f"{name:8} {self.minimum:6.3f} {self.maximum:6.3f} "
            f"{self.max_neighbor_step:6.3f}  {clipped}"
        )


def check_map(actuator_map: ActuatorMap) -> list[str]:
    """Return problems with the actuator map, empty if it is Sight's layout"""
    problems = []
    if not np.array_equal(actuator_map.indices, ActuatorMap.circular(SIGHT_SIDE).indices):
        problems.append(f"actuator map is not ActuatorMap.circular({SIGHT_SIDE})")
    if actuator_map.num_actuators != SIGHT_ACTUATORS:
        problems.append(f"{actuator_map.num_actuators} actuators, expected {SIGHT_ACTUATORS}")
    if actuator_map.edge_actuators.size != SIGHT_EDGE_ACTUATORS:
        problems.append(f"{actuator_map.edge_actuators.size} edge actuators")
    return problems


def check_copies(bundle: Path) -> tuple[dict[str, str], list[str]]:
    """Return each bundle file's SHA-256 and the files that differ from the driver's copy"""
    hashes, problems = {}, []
    for path in sorted(bundle.iterdir()):
        if path.suffix not in (".npy", ".txt"):
            continue
        hashes[path.name] = bringup.sha256(path)
        original = DRIVER_BUNDLE / path.name
        if not original.is_file() or bringup.sha256(original) != hashes[path.name]:
            problems.append(f"{path.name} differs from {original}")
    return hashes, problems


def flat_stats(config: DMConfig) -> dict[str, FlatStats]:
    """Return each flat's statistics on the actuators"""
    stats = {}
    for name, flat in config.flats.items():
        vector = config.actuator_map.to_vector(flat)
        stats[name] = FlatStats(
            minimum=float(vector.min()),
            maximum=float(vector.max()),
            max_neighbor_step=bringup.max_neighbor_step(config.actuator_map, vector),
            clipped=tuple(int(np.count_nonzero(vector > limit)) for limit in PHASE_MAXIMUMS),
        )
    return stats


def main() -> int:
    """Run the audit and print a table"""
    config = DMConfig.load(bringup.BUNDLE)
    problems = check_map(config.actuator_map)
    hashes, copy_problems = check_copies(bringup.BUNDLE.parent)
    problems += copy_problems
    stats = flat_stats(config)
    problems += [f"flat {name} goes below 0" for name, row in stats.items() if row.minimum < 0]
    limits = " / ".join(map(str, PHASE_MAXIMUMS))
    print(f"{'flat':8} {'min':>6} {'max':>6} {'step':>6}  values above {limits}")
    for name, row in stats.items():
        print(row.row(name))
    for problem in problems:
        print(f"audit_bundle: PROBLEM: {problem}")
    report = {
        "utc": bringup.utc_stamp(),
        "sha256": hashes,
        "phase_maximums": PHASE_MAXIMUMS,
        "flats": {name: asdict(row) for name, row in stats.items()},
        "problems": problems,
    }
    path = bringup.write_report("audit_bundle", report)
    print(f"audit_bundle: {'FAILED' if problems else 'passed'}; report {path}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
