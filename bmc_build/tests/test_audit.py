"""Tests for the Phase 1 audits: profile decoding and checks, and the bundle audit"""

from pathlib import Path

import audit_bundle
import audit_profile
import bringup
import numpy as np
import pytest
from bmc_dm import ActuatorMap, DMConfig

GOOD_PROFILE = (
    "type=1",
    "hva=2",
    "use_fiber=1",
    "use_CL=0",
    "fiber_mode=1",
    "size=648",
    "maxv=200",
    "vlim=150",
    "map=SIGHT648.map",
    "inactive=0",
)


def _write_profile(folder: Path, lines: tuple[str, ...], serial: str = "30CW009#052") -> Path:
    """Write a scrambled profile with a CRLF on its first line, as BMC's editors may"""
    encoded = [bytes(byte ^ bringup.PROFILE_KEY for byte in line.encode()) for line in lines]
    encoded[0] += b"\r"
    path = folder / f"{serial}.dm"
    path.write_bytes(b"\n".join(encoded) + b"\n")
    return path


@pytest.fixture(name="maps")
def fixture_maps(tmp_path: Path) -> Path:
    """Return a maps folder holding the map GOOD_PROFILE names"""
    folder = tmp_path / "Map"
    folder.mkdir()
    (folder / "SIGHT648.map").write_text("0\n")
    return folder


def _problems(path: Path, maps: Path) -> list[str]:
    """Audit path against maps and return its problems"""
    return audit_profile.audit(path, maps, maps.parent / "Calibration")[1]


def test_good_profile_decodes_and_passes(tmp_path: Path, maps: Path) -> None:
    """A PCIe profile for 648 actuators with its map passes, CRLF and all"""
    entries, problems = audit_profile.audit(
        _write_profile(tmp_path, GOOD_PROFILE), maps, tmp_path / "Calibration"
    )
    assert entries["type"] == "1"
    assert entries["vlim"] == "150"
    assert not problems


@pytest.mark.parametrize(
    ("replaced", "replacement", "problem"),
    [
        ("type=1", "type=2", "not USB"),
        ("size=648", "size=952", "is not 648"),
        ("vlim=150", "vlim=250", "at most maxv"),
        ("maxv=200", "maxv=", "missing or not a number"),
        ("map=SIGHT648.map", "map=OTHER.map", "is missing"),
        ("map=SIGHT648.map", "map=", "no map file"),
        ("inactive=0", "inactiv=0", "unknown key"),
        ("hva=2", "hva=7", "not one of BMC's types"),
        ("fiber_mode=1", "fiber_mode=0", "needs use_fiber=1 and fiber_mode=1"),
        ("use_CL=0", "use_CL=1", "exactly one of use_fiber and use_CL"),
    ],
)
def test_bad_profile_is_flagged(
    tmp_path: Path, maps: Path, replaced: str, replacement: str, problem: str
) -> None:
    """Each kind of bad profile gives its own problem"""
    lines = tuple(replacement if line == replaced else line for line in GOOD_PROFILE)
    problems = _problems(_write_profile(tmp_path, lines), maps)
    assert any(problem in text for text in problems), problems


def test_short_file_name_is_flagged(tmp_path: Path, maps: Path) -> None:
    """The SDK only accepts 11-character serials"""
    problems = _problems(_write_profile(tmp_path, GOOD_PROFILE, serial="30CW009"), maps)
    assert any("11-character" in text for text in problems)


def test_dummy_profile_is_not_hardware() -> None:
    """The harness's own dummy profile is rejected as a hardware profile"""
    config = bringup.load_config(hardware=False)
    assert config.sdk_profiles_path is not None
    path = config.sdk_profiles_path / f"{bringup.DUMMY_SERIAL}.dm"
    entries, problems = audit_profile.audit(path, path.parent, path.parent)
    assert entries["type"] == "2"
    assert any("not USB" in text for text in problems)


def test_sight_map_passes() -> None:
    """The bundle's actuator map is BMC's circular 28 x 28 layout"""
    assert not audit_bundle.check_map(DMConfig.load(bringup.BUNDLE).actuator_map)


def test_wrong_map_is_flagged() -> None:
    """A 34 x 34 kilo-DM map is not Sight's"""
    assert audit_bundle.check_map(ActuatorMap.circular(34))


def test_flat_stats_count_clipped_values() -> None:
    """Values above each phase maximum are counted on the actuators only"""
    actuator_map = ActuatorMap.circular(audit_bundle.SIGHT_SIDE)
    vector = np.full(actuator_map.num_actuators, 0.5)
    vector[0] = 0.9
    config = DMConfig(
        "test", actuator_map, (0.0, 0.8), flats={"flat": actuator_map.to_surface(vector)}
    )
    stats = audit_bundle.flat_stats(config)["flat"]
    assert stats.clipped == (actuator_map.num_actuators, 1, 1)
    assert stats.maximum == pytest.approx(0.9)
    assert stats.max_neighbor_step == pytest.approx(0.4)


def test_missing_profile_fails_cleanly(tmp_path: Path) -> None:
    """A profile that is not there yet is an error message, not a traceback"""
    assert audit_profile.main([str(tmp_path / "30CW009#052.dm")]) == 1
