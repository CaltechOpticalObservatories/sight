"""Tests for the bring-up safety layer against the fake bmc module (no SDK needed)"""

import os
import signal
from unittest.mock import MagicMock

import audit_profile
import bringup
import numpy as np
import pytest
from bmc_dm import BmcDmController, actuators

CAP = 0.3


def _poke(dm: BmcDmController, amplitude: float) -> np.ndarray:
    """Return amplitude on actuator 0 as a surface"""
    return amplitude * actuators(dm.actuator_map, 0)


def test_dummy_mode_never_uses_the_real_profile() -> None:
    """Dummy mode opens a type 2 profile under its own serial; hardware keeps the bundle's"""
    config = bringup.load_config(hardware=False)
    assert config.serial_number == bringup.DUMMY_SERIAL
    assert config.sdk_profiles_path is not None
    profile = config.sdk_profiles_path / f"{bringup.DUMMY_SERIAL}.dm"
    assert audit_profile.decode(profile)["type"] == "2"
    assert bringup.load_config(hardware=True).serial_number == "30CW009#052"


def test_unsafe_configs_are_refused(monkeypatch: pytest.MonkeyPatch, sdk: MagicMock) -> None:
    """A maximum above 0.8, a missing SDK folder, or hardware outside tmux"""
    with pytest.raises(bringup.RefusedStep, match="above Sight's"):
        bringup.load_config(hardware=False, maximum=bringup.SIGHT_MAXIMUM + 0.1)
    monkeypatch.delenv("TMUX", raising=False)
    with pytest.raises(bringup.RefusedStep, match="tmux"), bringup.session(hardware=True):
        pass
    sdk.open_dm.assert_not_called()
    with bringup.BUNDLE.open("a", encoding="utf-8") as toml:
        toml.write('\n[sdk]\nprofiles_path = "missing"\n')
    with pytest.raises(bringup.RefusedStep, match="does not exist"):
        bringup.load_config(hardware=True)


@pytest.mark.parametrize("amplitude", [CAP + 0.01, -0.1, 0.5, float("nan")])
def test_send_refuses_without_sending(amplitude: float, sdk: MagicMock) -> None:
    """Over the cap, outside the soft limits (0 to 0.4) or not finite: nothing is sent"""
    with bringup.session(hardware=False) as dm:
        with pytest.raises(bringup.RefusedStep):
            bringup.send(dm, _poke(dm, amplitude), cap=CAP, label="refused")
        sdk.send_data.assert_not_called()


@pytest.mark.parametrize(
    ("interruption", "raised"),
    [
        (None, RuntimeError),
        (signal.SIGINT, KeyboardInterrupt),
        (signal.SIGTERM, SystemExit),
        (signal.SIGHUP, SystemExit),
    ],
)
def test_every_exit_zeroes_and_disconnects(
    interruption: signal.Signals | None, raised: type[BaseException], sdk: MagicMock
) -> None:
    """An error, Ctrl-C, SIGTERM or SIGHUP all end with a zero command and one close"""
    handlers = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGHUP)}
    with pytest.raises(raised), bringup.session(hardware=False) as dm:
        bringup.send(dm, _poke(dm, 0.2), cap=CAP, label="poke")
        if interruption is None:
            raise RuntimeError("step failed")
        os.kill(os.getpid(), interruption)
    assert not any(sdk.send_data.call_args.args[0])
    assert sdk.close_dm.call_count == 1
    assert handlers == {number: signal.getsignal(number) for number in handlers}


def test_session_can_skip_the_zero(sdk: MagicMock) -> None:
    """zero_on_exit=False disconnects without sending, for persistence checks"""
    with bringup.session(hardware=False, zero_on_exit=False) as dm:
        bringup.send(dm, _poke(dm, 0.2), cap=CAP, label="poke")
    assert sdk.send_data.call_count == 1
    assert sdk.close_dm.call_count == 1
