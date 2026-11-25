"""Tests for the bring-up safety layer against the fake bmc module (no SDK needed)"""

import os
import shutil
import signal
from pathlib import Path

import bringup
import numpy as np
import pytest
from bmc_dm import BmcDmController, actuators
from fake_sdk import FakeBmcDm

CAP = 0.3


def _sdk() -> FakeBmcDm:
    """Return the single fake DM the test opened"""
    assert len(FakeBmcDm.instances) == 1
    return FakeBmcDm.instances[0]


def _poke(dm: BmcDmController, amplitude: float) -> np.ndarray:
    """Return amplitude on actuator 0 as a surface"""
    return amplitude * actuators(dm.actuator_map, 0)


def test_dummy_config_uses_the_dummy_profile_only() -> None:
    """The default mode opens DUMMY000648 from its own folder, never the bundle's serial"""
    config = bringup.load_config(hardware=False)
    assert config.serial_number == bringup.DUMMY_SERIAL
    assert config.sdk_profiles_path == bringup.DUMMY_DIR / "Profiles"
    profile = (bringup.DUMMY_DIR / "Profiles" / f"{bringup.DUMMY_SERIAL}.dm").read_bytes()
    lines = bytes(byte ^ bringup.PROFILE_KEY if byte != ord("\n") else byte for byte in profile)
    assert lines.decode().splitlines()[0] == "type=2"


def test_hardware_config_keeps_the_bundle_serial() -> None:
    """Hardware mode uses the bundle as written"""
    assert bringup.load_config(hardware=True).serial_number == "30CW009#052"


def test_maximum_above_sight_is_refused() -> None:
    """No script can raise the soft maximum past Sight's 0.8"""
    with pytest.raises(bringup.RefusedStep):
        bringup.load_config(hardware=False, maximum=bringup.SIGHT_MAXIMUM + 0.1)


def test_missing_sdk_folder_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A profiles path that does not exist is refused instead of falling back to /opt"""
    bundle = tmp_path / "bundle_missing_sdk"
    shutil.copytree(bringup.BUNDLE.parent, bundle)
    toml = bundle / bringup.BUNDLE.name
    toml.write_text(toml.read_text() + '\n[sdk]\nprofiles_path = "missing"\n')
    monkeypatch.setattr(bringup, "BUNDLE", toml)
    with pytest.raises(bringup.RefusedStep, match="does not exist"):
        bringup.load_config(hardware=True)


def test_hardware_outside_tmux_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hardware sessions need tmux and are refused before the SDK is touched"""
    monkeypatch.delenv("TMUX", raising=False)
    with pytest.raises(bringup.RefusedStep, match="tmux"), bringup.session(hardware=True):
        pass
    assert not FakeBmcDm.instances


def test_plan_reports_peak_moved_and_neighbor_step() -> None:
    """A single poke from zero moves one actuator by its amplitude"""
    with bringup.session(hardware=False) as dm:
        command_plan = bringup.plan(dm, _poke(dm, 0.2), cap=CAP)
    assert command_plan == bringup.CommandPlan(peak=0.2, moved=1, max_neighbor_step=0.2)


@pytest.mark.parametrize("amplitude", [CAP + 0.01, -0.1, 0.5, float("nan")])
def test_send_refuses_without_sending(amplitude: float) -> None:
    """Over the cap, outside the soft limits (0 to 0.4) or not finite: nothing is sent"""
    with bringup.session(hardware=False) as dm:
        with pytest.raises(bringup.RefusedStep):
            bringup.send(dm, _poke(dm, amplitude), cap=CAP, label="refused")
        assert not _sdk().sent


def test_session_zeroes_and_disconnects_after_an_error() -> None:
    """An exception in the step still ends with a zero command and a close"""
    with pytest.raises(RuntimeError), bringup.session(hardware=False) as dm:
        bringup.send(dm, _poke(dm, 0.2), cap=CAP, label="poke")
        raise RuntimeError("step failed")
    assert not any(_sdk().sent[-1])
    assert _sdk().close_count == 1


def test_session_can_skip_the_zero() -> None:
    """zero_on_exit=False disconnects without sending, for persistence checks"""
    with bringup.session(hardware=False, zero_on_exit=False) as dm:
        bringup.send(dm, _poke(dm, 0.2), cap=CAP, label="poke")
    assert len(_sdk().sent) == 1
    assert _sdk().close_count == 1


@pytest.mark.parametrize("number", [signal.SIGTERM, signal.SIGHUP])
def test_stop_signal_runs_the_cleanup(number: signal.Signals) -> None:
    """SIGTERM and SIGHUP become SystemExit, the mirror is zeroed, handlers are restored"""
    before = signal.getsignal(number)
    with pytest.raises(SystemExit) as raised, bringup.session(hardware=False) as dm:
        bringup.send(dm, _poke(dm, 0.2), cap=CAP, label="poke")
        os.kill(os.getpid(), number)
    assert raised.value.code == 128 + number
    assert not any(_sdk().sent[-1])
    assert _sdk().close_count == 1
    assert signal.getsignal(number) == before
