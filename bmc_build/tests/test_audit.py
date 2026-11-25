"""Tests for the profile audit: decoding and every check"""

from pathlib import Path

import audit_profile
import bringup
import pytest

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


def _audit(folder: Path, lines: tuple[str, ...], serial: str = "30CW009#052") -> list[str]:
    """Write a profile (CRLF on its first line, as BMC's editors may) and return its problems"""
    (folder / "SIGHT648.map").write_text("0\n", encoding="utf-8")
    encoded = [bringup.scramble(line) for line in lines]
    encoded[0] += b"\r"
    path = folder / f"{serial}.dm"
    path.write_bytes(b"\n".join(encoded) + b"\n")
    return audit_profile.audit(path, folder, folder)[1]


def test_good_profile_passes(tmp_path: Path) -> None:
    """A PCIe kilo profile for 648 actuators with its map passes"""
    assert not _audit(tmp_path, GOOD_PROFILE)


@pytest.mark.parametrize(
    ("replaced", "replacement", "problem"),
    [
        ("type=1", "type=2", "not USB"),
        ("size=648", "size=952", "is not 648"),
        ("vlim=150", "vlim=250", "at most maxv"),
        ("maxv=200", "maxv=", "nan: missing"),
        ("map=SIGHT648.map", "map=OTHER.map", "is missing"),
        ("map=SIGHT648.map", "map=", "is missing"),
        ("inactive=0", "inactiv=0", "unknown key"),
        ("hva=2", "hva=7", "not one of BMC's types"),
        ("fiber_mode=1", "fiber_mode=0", "needs use_fiber=1 and fiber_mode=1"),
        ("use_CL=0", "use_CL=1", "exactly one of use_fiber and use_CL"),
    ],
)
def test_bad_profile_is_flagged(
    tmp_path: Path, replaced: str, replacement: str, problem: str
) -> None:
    """Each kind of bad profile gives its own problem"""
    problems = _audit(
        tmp_path, tuple(replacement if line == replaced else line for line in GOOD_PROFILE)
    )
    assert any(problem in text for text in problems), problems


def test_bad_serial_and_missing_profile(tmp_path: Path) -> None:
    """The SDK only accepts 11-character serials; a missing profile is a message, not a traceback"""
    assert any("11-character" in text for text in _audit(tmp_path, GOOD_PROFILE, serial="30CW009"))
    assert audit_profile.main([str(tmp_path / "30CW009#052.dm")]) == 1
