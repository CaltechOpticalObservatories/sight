"""Tests for the read-only card status against a stub bmc_ltest"""

from pathlib import Path

import bringup
import card_status
import pytest
from fake_sdk import ltest_output, write_ltest

FIBER_UP = 0b11000  # channel and lane up, SFP present, light received
HV_ON = 0b1


def _use_stub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, output: str) -> Path:
    """Point card_status at a stub bmc_ltest that prints output"""
    stub = write_ltest(tmp_path, output)
    monkeypatch.setattr(card_status, "LTEST", stub)
    monkeypatch.setattr(card_status, "read_kernel_log", lambda _since: "")
    return stub


def test_parse_decodes_every_register_bit() -> None:
    """The fiber, HV and kilo registers decode into named bits"""
    status = card_status.parse(ltest_output(fiber=FIBER_UP, hv=HV_ON, kilo=0b100))
    assert not status.problems()
    assert status.fields["boards"] == 1
    assert status.fields["hw_rev"] == "v2000_6.0"
    assert status.fields["fiber.lane_up"] is True
    assert status.fields["fiber.loss_of_light"] is False
    assert status.fields["fiber.sfp_absent"] is False
    assert status.fields["hv.hv_on"] is True
    assert status.fields["kilo.fifo_half_full"] is True


@pytest.mark.parametrize(
    ("output", "problem"),
    [
        (ltest_output(hw_rev="v1234_1.0"), "not BMC's design"),
        (ltest_output() + "ERR:   BMCreadKiloStatus gave 'read failed'\n", "ERR:"),
        (ltest_output().replace("1 boards", "2 boards"), "2 boards"),
        (ltest_output().replace("  fiber:    0x00000004\n", ""), "no fiber line"),
        ("  HW  rev: '--no driver--'\n", "--no driver--"),
    ],
)
def test_bad_readings_are_flagged(output: str, problem: str) -> None:
    """Errors, a foreign card, extra boards and missing lines are all problems"""
    problems = card_status.parse(output).problems()
    assert any(problem in text for text in problems), problems


def test_changes_lists_only_differing_fields() -> None:
    """Powering the driver box on shows up as changed bits"""
    off = card_status.parse(ltest_output()).fields
    on = card_status.parse(ltest_output(fiber=FIBER_UP, hv=HV_ON)).fields
    differences = card_status.changes(off, on)
    assert "hv.hv_on: False -> True" in differences
    assert "fiber.loss_of_light: True -> False" in differences
    assert not card_status.changes(off, off)


def test_missing_ltest_is_an_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Before the SDK is installed the script fails cleanly"""
    monkeypatch.setattr(card_status, "LTEST", tmp_path / "missing")
    assert card_status.main(["--label", "boxoff"]) == 1


def test_main_reports_and_compares(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A box-off report, then a box-on reading compared with it"""
    _use_stub(monkeypatch, tmp_path, ltest_output())
    assert card_status.main(["--label", "boxoff"]) == 0
    _use_stub(monkeypatch, tmp_path, ltest_output(fiber=FIBER_UP, hv=HV_ON))
    assert card_status.main(["--label", "boxon", "--compare", "boxoff"]) == 0
    reports = sorted(bringup.LOGS_DIR.glob("card_boxon_*.json"))
    assert len(reports) == 1
    assert "hv.hv_on: False -> True" in reports[0].read_text(encoding="utf-8")


def test_compare_without_baseline_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Comparing with a label that has no report is an error, not a silent pass"""
    _use_stub(monkeypatch, tmp_path, ltest_output())
    assert card_status.main(["--compare", "boxoff"]) == 1


def test_cycles_pass_on_a_steady_card(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Repeated identical readings and a clean kernel log pass"""
    _use_stub(monkeypatch, tmp_path, ltest_output())
    assert card_status.main(["--cycles", "5"]) == 0


def test_kernel_warning_fails_the_cycles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A kernel WARNING during the cycles is a problem"""
    _use_stub(monkeypatch, tmp_path, ltest_output())
    monkeypatch.setattr(
        card_status, "read_kernel_log", lambda _since: "WARNING: CPU: 3 at bmc_mdrv_ioctl\n"
    )
    assert card_status.main(["--cycles", "2"]) == 1


def test_only_the_info_option_is_ever_passed(tmp_path: Path) -> None:
    """The stub exits 99 on any other arguments, so a passing read proves -b 0 -i"""
    stub = write_ltest(tmp_path, ltest_output())
    assert not card_status.read_status(stub).problems()
    assert card_status.LTEST_ARGS == ("-b", "0", "-i")
