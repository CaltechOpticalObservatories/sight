"""Tests for the read-only card status against a stub bmc_ltest"""

import json
from pathlib import Path

import bringup
import card_status
import pytest
from fake_sdk import ltest_output, write_ltest

FIBER_UP = 0b11000  # channel and lane up, SFP present, light received
HV_ON = 0b1


def test_parse_decodes_the_status_bits() -> None:
    """Register values decode into named bits"""
    text = ltest_output(fiber=FIBER_UP, hv=HV_ON)
    fields = card_status.parse(text)
    assert not card_status.problems(text, fields)
    assert fields["hw_rev"] == "v2000_6.0"
    assert fields["fiber.lane_up"] is True
    assert fields["fiber.loss_of_light"] is False
    assert fields["hv.hv_on"] is True


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        (ltest_output(hw_rev="v1234_1.0"), "not BMC's design"),
        (ltest_output() + "ERR:   BMCreadKiloStatus gave 'read failed'\n", "ERR:"),
        (ltest_output().replace("1 boards", "2 boards"), "2 boards"),
        (ltest_output().replace("  fiber:    0x00000004\n", ""), "no fiber line"),
    ],
)
def test_bad_readings_are_flagged(text: str, problem: str) -> None:
    """Errors, a foreign card, extra boards and missing lines are all problems"""
    found = card_status.problems(text, card_status.parse(text))
    assert any(problem in line for line in found), found


def test_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Box off, repeated reads, box on compared with box off; the stub only accepts -b 0 -i"""
    monkeypatch.setattr(card_status, "LTEST", tmp_path / "missing")
    assert card_status.main(["--label", "boxoff"]) == 1
    monkeypatch.setattr(card_status, "LTEST", write_ltest(tmp_path, ltest_output()))
    assert card_status.main(["--compare", "boxoff"]) == 1
    assert card_status.main(["--label", "boxoff", "--cycles", "3"]) == 0
    write_ltest(tmp_path, ltest_output(fiber=FIBER_UP, hv=HV_ON))
    assert card_status.main(["--label", "boxon", "--compare", "boxoff"]) == 0
    (report,) = bringup.LOGS_DIR.glob("card_boxon_*.json")
    assert "hv.hv_on: False -> True" in json.loads(report.read_text(encoding="utf-8"))["changes"]
