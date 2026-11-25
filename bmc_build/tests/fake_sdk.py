"""Stand-ins for BMC's software: the bmc Python module and the bmc_ltest program"""

from pathlib import Path
from typing import ClassVar, Final

NO_ERR: Final = 0
SIGHT_ACTUATORS: Final = 648


class FakeBmcDm:
    """Record SDK calls the way bmc.BmcDm would receive them"""

    instances: ClassVar[list["FakeBmcDm"]] = []

    def __init__(self) -> None:
        """Start with nothing sent and the DM closed"""
        self.sent: list[list[float]] = []
        self.serial: str | None = None
        self.profiles_path: str | None = None
        self.close_count = 0
        FakeBmcDm.instances.append(self)

    def set_profiles_path(self, path: str) -> int:
        """Record the profiles folder"""
        self.profiles_path = path
        return NO_ERR

    def set_maps_path(self, _path: str) -> int:
        """Accept a maps folder"""
        return NO_ERR

    def open_dm(self, serial: str) -> int:
        """Record the serial"""
        self.serial = serial
        return NO_ERR

    def num_actuators(self) -> int:
        """Return Sight's actuator count"""
        return SIGHT_ACTUATORS

    def send_data(self, data: list[float]) -> int:
        """Record a command"""
        self.sent.append(list(data))
        return NO_ERR

    def get_actuator_data(self) -> list[float]:
        """Return zeros, as the SDK does right after open"""
        return [0.0] * SIGHT_ACTUATORS

    def close_dm(self) -> int:
        """Count the close"""
        self.close_count += 1
        return NO_ERR

    def error_string(self, status: int) -> str:
        """Name the status code"""
        return f"fake error {status}"


def ltest_output(
    *, fiber: int = 0x00000004, hv: int = 0, kilo: int = 0, hw_rev: str = "v2000_6.0"
) -> str:
    """Return bmc_ltest -i output in its real format (DoInfo in bmc_ltest.c)

    The default fiber value has only loss of light set, as with the driver box off.
    """
    return (
        "DoInfo: we detect 1 boards\n"
        "  lib rev: 'v2.03'\n"
        "  drv rev: 'v2.03'\n"
        f"  HW  rev: '{hw_rev}'\n"
        "  HVA:      2 'KILO1024'\n"
        "  orien:    0 'normal'\n"
        f"  fiber:    0x{fiber:08X}\n"
        f"  HVAcc:    0x{hv:08X}\n"
        f"  Kilo:     0x{kilo:08X}\n"
        "  seqRate:  0.000000\n"
    )


def write_ltest(folder: Path, output: str) -> Path:
    """Write a stub bmc_ltest that prints output for -b 0 -i and fails for anything else"""
    stub = folder / "bmc_ltest"
    (folder / "output.txt").write_text(output, encoding="utf-8")
    stub.write_text(
        "#!/bin/sh\n"
        '[ "$*" = "-b 0 -i" ] || { echo "unexpected arguments: $*"; exit 99; }\n'
        f'cat "{folder / "output.txt"}"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub
