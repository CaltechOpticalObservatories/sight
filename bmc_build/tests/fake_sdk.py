"""Stand-ins for BMC's software: the bmc Python module and the bmc_ltest program"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

NO_ERR = 0
SIGHT_ACTUATORS = 648


def fake_bmc() -> SimpleNamespace:
    """Return a bmc module whose BmcDm is one mock device: every call succeeds and is recorded"""
    device = MagicMock()
    for call in ("set_profiles_path", "set_maps_path", "open_dm", "send_data", "close_dm"):
        getattr(device, call).return_value = NO_ERR
    device.num_actuators.return_value = SIGHT_ACTUATORS
    device.get_actuator_data.return_value = [0.0] * SIGHT_ACTUATORS
    return SimpleNamespace(BmcDm=MagicMock(return_value=device), NO_ERR=NO_ERR)


def ltest_output(*, fiber: int = 0b100, hv: int = 0, hw_rev: str = "v2000_6.0") -> str:
    """Return bmc_ltest -i output in its real format; the default fiber is loss of light only"""
    return (
        "DoInfo: we detect 1 boards\n"
        "  lib rev: 'v2.03'\n"
        "  drv rev: 'v2.03'\n"
        f"  HW  rev: '{hw_rev}'\n"
        "  HVA:      2 'KILO1024'\n"
        "  orien:    0 'normal'\n"
        f"  fiber:    0x{fiber:08X}\n"
        f"  HVAcc:    0x{hv:08X}\n"
        "  Kilo:     0x00000000\n"
        "  seqRate:  0.000000\n"
    )


def write_ltest(folder: Path, output: str) -> Path:
    """Write a stub bmc_ltest that prints output for -b 0 -i and fails on anything else"""
    (folder / "output.txt").write_text(output, encoding="utf-8")
    stub = folder / "bmc_ltest"
    stub.write_text(
        f'#!/bin/sh\n[ "$*" = "-b 0 -i" ] || exit 99\ncat "{folder / "output.txt"}"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub
