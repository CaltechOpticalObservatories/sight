"""Make the bring-up scripts importable, install the fake SDK, keep output out of logs/

The repository holds only the bundle's TOML (the map and flats come from the driver at
deploy), so every test gets its own bundle: that TOML, BMC's circular map and uniform
flats.
"""

import shutil
import sys
import tomllib
import types
from pathlib import Path
from typing import Final

import numpy as np
import pytest
from bmc_dm import ACTUATOR_MAP_FILE, ActuatorMap

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import bringup  # pylint: disable=wrong-import-position
from fake_sdk import NO_ERR, FakeBmcDm  # pylint: disable=wrong-import-position

SIGHT_SIDE: Final = 28
# Inside the bundle's 0.4 soft maximum
FLAT_LEVEL: Final = 0.3


@pytest.fixture(autouse=True)
def fixture_fake_sdk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Install the fake bmc module and write the dummy profile and logs under tmp_path"""
    monkeypatch.setitem(sys.modules, "bmc", types.SimpleNamespace(BmcDm=FakeBmcDm, NO_ERR=NO_ERR))
    monkeypatch.setattr(FakeBmcDm, "instances", [])
    monkeypatch.setattr(bringup, "DUMMY_DIR", tmp_path / "dummy")
    monkeypatch.setattr(bringup, "LOGS_DIR", tmp_path / "logs")


@pytest.fixture(autouse=True)
def fixture_bundle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Build the bring-up bundle under tmp_path and point bringup at it"""
    source = bringup.BUNDLE
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    shutil.copy(source, bundle / source.name)
    actuator_map = ActuatorMap.circular(SIGHT_SIDE)
    np.savetxt(bundle / ACTUATOR_MAP_FILE, actuator_map.indices, fmt="%d")
    flat = actuator_map.to_surface(np.full(actuator_map.num_actuators, FLAT_LEVEL))
    for file in tomllib.loads(source.read_text(encoding="utf-8"))["flats"].values():
        np.save(bundle / file, flat)
    monkeypatch.setattr(bringup, "BUNDLE", bundle / source.name)
    return bundle
