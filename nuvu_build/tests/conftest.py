"""Make the bring-up scripts importable and keep test output out of logs/ and frames/."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import bringup  # pylint: disable=wrong-import-position
from fake_sdk import FakeSdk  # pylint: disable=wrong-import-position


@pytest.fixture(autouse=True)
def isolated_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write logs and frames under a temporary root."""
    monkeypatch.setattr(bringup, "ROOT", tmp_path)
    return tmp_path


@pytest.fixture(name="warm")
def fixture_warm() -> FakeSdk:
    """Powered camera, warm detector (calibrated EM gain unavailable)."""
    return FakeSdk(cold=False)


@pytest.fixture(name="cold")
def fixture_cold() -> FakeSdk:
    """Powered camera at -60 C (calibrated EM gain available)."""
    return FakeSdk(cold=True)
