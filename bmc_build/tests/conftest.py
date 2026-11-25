"""Make the bring-up scripts importable, install the fake SDK, keep output out of logs/

The repository holds only the bundle's TOML (the map and flats come from the driver at
deploy), so every test gets its own bundle: that TOML, BMC's circular map and uniform
flats.
"""

import shutil
import sys
import tomllib
from pathlib import Path
from typing import Final
from unittest.mock import MagicMock

import numpy as np
import pytest
from bmc_dm import ACTUATOR_MAP_FILE, ActuatorMap

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import bringup  # pylint: disable=wrong-import-position
from fake_sdk import fake_bmc  # pylint: disable=wrong-import-position

SIGHT_SIDE: Final = 28
# Inside the bundle's 0.4 soft maximum
FLAT_LEVEL: Final = 0.3


@pytest.fixture(name="sdk", autouse=True)
def fixture_sdk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MagicMock:
    """Install the fake bmc module, keep dummy files and logs in tmp_path, return the device"""
    bmc = fake_bmc()
    monkeypatch.setitem(sys.modules, "bmc", bmc)
    monkeypatch.setattr(bringup, "DUMMY_DIR", tmp_path / "dummy")
    monkeypatch.setattr(bringup, "LOGS_DIR", tmp_path / "logs")
    device: MagicMock = bmc.BmcDm.return_value
    return device


@pytest.fixture(autouse=True)
def fixture_bundle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Build the bring-up bundle under tmp_path and point bringup at it"""
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    shutil.copy(bringup.BUNDLE, bundle)
    actuator_map = ActuatorMap.circular(SIGHT_SIDE)
    np.savetxt(bundle / ACTUATOR_MAP_FILE, actuator_map.indices, fmt="%d")
    flat = actuator_map.to_surface(np.full(actuator_map.num_actuators, FLAT_LEVEL))
    for file in tomllib.loads(bringup.BUNDLE.read_text(encoding="utf-8"))["flats"].values():
        np.save(bundle / file, flat)
    monkeypatch.setattr(bringup, "BUNDLE", bundle / bringup.BUNDLE.name)
