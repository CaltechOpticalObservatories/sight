"""Rehearse every bring-up script against the fake SDK before it runs on hardware."""
import argparse
import csv
import json
from pathlib import Path

import bringup
import connect_cycle
import dark_frames
import edge_cases
import numpy as np
import pytest
import safe_dark
import status
import telemetry_log
import warm_and_close
from fake_sdk import SHUTTER_CLOSE, FakeSdk, make_factory
from nuvu import NC_AUTO_CHANNEL, NC_AUTO_UNIT

AUTO = ["--unit", str(NC_AUTO_UNIT), "--channel", str(NC_AUTO_CHANNEL)]


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    bringup.add_connection_args(parser)
    return parser.parse_args([])


def test_status_is_read_only(warm: FakeSdk, isolated_root: Path) -> None:
    """status.py sends no setters and ends disconnected with a JSON report."""
    assert status.main(AUTO, make_factory(warm)) == 0
    assert not warm.setters()
    assert warm.names()[-1] == "ncCamClose"
    report = json.loads(next((isolated_root / "logs").glob("status_*.json")).read_text())
    assert report["identity"]["serial"] == "SN06283454"
    assert report["safe_shutdown_c"] == -60.0
    assert len(report["readout_modes"]) == 2


def test_status_camera_off_fails_cleanly(warm: FakeSdk) -> None:
    """With the camera off, status.py finds nothing and never opens."""
    warm.cameras = 0
    assert status.main(AUTO, make_factory(warm)) == 1
    assert "ncCamOpen" not in warm.names()


def test_status_open_failure_is_clean(warm: FakeSdk) -> None:
    """A listed camera that fails to open gives exit 1, not a traceback."""
    warm.open_fails = True
    assert status.main(AUTO, make_factory(warm)) == 1
    assert not warm.setters()


def test_connect_cycle(warm: FakeSdk) -> None:
    """Three cycles open and close three times with nothing else changed."""
    assert connect_cycle.main([*AUTO, "--pause-s", "0"], make_factory(warm)) == 0
    assert warm.names().count("ncCamOpen") == 3
    assert warm.names().count("ncCamClose") == 3
    assert not warm.setters()


def test_telemetry_log(warm: FakeSdk, isolated_root: Path) -> None:
    """telemetry_log.py writes rows with every temperature and sends no setters."""
    argv = [*AUTO, "--duration-s", "0.25", "--period-s", "0.05"]
    assert telemetry_log.main(argv, make_factory(warm)) == 0
    path = next((isolated_root / "logs").glob("telemetry_*.csv"))
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(rows) >= 3
    assert set(rows[0]) == {"utc", *bringup.COMPONENTS, "target"}
    assert not warm.setters()


def test_over_cap_gain_is_refused(cold: FakeSdk) -> None:
    """A gain above the phase cap is refused and never sent."""
    with (bringup.session("t", _args(), make_factory(cold)) as camera,
          pytest.raises(bringup.Refused, match="phase cap")):
        bringup.guarded_gain(camera, 2, bringup.PHASE_CAPS[3], peak_above_bias=10.0)
    assert "ncCamSetCalibratedEmGain" not in cold.names()


def test_gain_step_and_predicted_peak(cold: FakeSdk) -> None:
    """Steps over 2.5x and predicted peaks over the cap are refused; a safe step is sent."""
    caps = bringup.PHASE_CAPS[7]
    cold.state["em_gain"] = 10
    with bringup.session("t", _args(), make_factory(cold)) as camera:
        with pytest.raises(bringup.Refused, match="more than"):
            bringup.guarded_gain(camera, 30, caps, peak_above_bias=10.0)
        with pytest.raises(bringup.Refused, match="predicted peak"):
            bringup.guarded_gain(camera, 20, caps, peak_above_bias=300.0)
        bringup.guarded_gain(camera, 20, caps, peak_above_bias=100.0)
        assert cold.state["em_gain"] == 20
    assert cold.state["em_gain"] == 1, "session must leave EM gain at minimum"


def test_gain_refused_when_warm(warm: FakeSdk) -> None:
    """Calibrated EM gain is refused while the detector is outside its range."""
    with (bringup.session("t", _args(), make_factory(warm)) as camera,
          pytest.raises(bringup.Refused, match="not available")):
        bringup.guarded_gain(camera, 1, bringup.PHASE_CAPS[7], peak_above_bias=0.0)


def test_bright_frame_runs_safe_dark(cold: FakeSdk, isolated_root: Path) -> None:
    """A saturated frame makes the camera dark at once, then raises."""
    cold.state["em_gain"] = 50
    cold.state["acquiring"] = 1
    frame = np.full((128, 128), 400, dtype=np.uint16)
    frame[64, 64] = bringup.SATURATED
    with bringup.session("t", _args(), make_factory(cold)) as camera:
        with pytest.raises(bringup.FrameOverCap, match="saturated=True"):
            bringup.check_frame(camera, frame, bringup.PHASE_CAPS[7], bias=400.0, name="bright")
        assert cold.state == cold.state | {"em_gain": 1, "shutter": SHUTTER_CLOSE, "acquiring": 0}
    assert list((isolated_root / "frames").glob("bright_*.npy"))


def test_session_is_safe_after_interrupt(cold: FakeSdk) -> None:
    """Ctrl-C inside a session still ends with gain at minimum, abort, close."""
    cold.state["em_gain"] = 10
    with (pytest.raises(KeyboardInterrupt),
          bringup.session("t", _args(), make_factory(cold)) as camera):
        camera.start()
        raise KeyboardInterrupt
    tail = cold.names()[-6:]
    assert "ncCamSetCalibratedEmGain" in tail
    assert tail.index("ncCamAbort") < tail.index("ncCamClose")
    assert cold.state["em_gain"] == 1 and cold.state["acquiring"] == 0


def test_safe_dark(cold: FakeSdk) -> None:
    """safe_dark.py brings gain to minimum, closes the shutter and stops acquiring."""
    cold.state.update(em_gain=20, acquiring=1)
    assert safe_dark.main(AUTO, make_factory(cold)) == 0
    assert cold.state["em_gain"] == 1
    assert cold.state["shutter"] == SHUTTER_CLOSE
    assert cold.state["acquiring"] == 0


def test_warm_and_close(cold: FakeSdk, capsys: pytest.CaptureFixture[str]) -> None:
    """warm_and_close.py says safe only when the CCD ends at or above the safe temperature."""
    assert warm_and_close.main([*AUTO, "--period-s", "0.05"], make_factory(cold)) == 0
    assert "safe to power off" in capsys.readouterr().out

    stuck = FakeSdk(cold=True)
    stuck.state["warms_to"] = -70.0
    assert warm_and_close.main([*AUTO, "--period-s", "0.05"], make_factory(stuck)) == 1
    assert "NOT safe" in capsys.readouterr().out


def test_camera_off_everywhere(warm: FakeSdk) -> None:
    """Every script fails cleanly (exit 1, no traceback) when the camera can't be opened."""
    warm.open_fails = True
    factory = make_factory(warm)
    assert connect_cycle.main([*AUTO, "--pause-s", "0"], factory) == 1
    assert telemetry_log.main([*AUTO, "--duration-s", "0"], factory) == 1
    assert safe_dark.main(AUTO, factory) == 1
    assert warm_and_close.main(AUTO, factory) == 1
    assert dark_frames.main(AUTO, factory) == 1
    assert edge_cases.main(AUTO, factory) == 1


def _fake_clock(monkeypatch: pytest.MonkeyPatch, rate_hz: float) -> None:
    """Make the continuous run appear to read its frames at rate_hz."""
    ticks = iter([0.0, (dark_frames.CONTINUOUS_FRAMES - 1) / rate_hz])
    monkeypatch.setattr(dark_frames.time, "monotonic", lambda: next(ticks))


def test_dark_frames(warm: FakeSdk, isolated_root: Path,
                     monkeypatch: pytest.MonkeyPatch) -> None:
    """dark_frames.py passes every check on clean frames and ends dark and idle."""
    _fake_clock(monkeypatch, rate_hz=580.0)
    assert dark_frames.main(AUTO, make_factory(warm)) == 0
    report = json.loads(next((isolated_root / "logs").glob("dark_frames_*.json")).read_text())
    assert all(report["checks"].values())
    assert report["continuous"]["frames"] == dark_frames.CONTINUOUS_FRAMES
    frames = list((isolated_root / "frames").glob("dark_*.npy"))
    assert len(frames) == len(dark_frames.EXPOSURES_MS) * dark_frames.FRAMES_PER_EXPOSURE + 1
    assert warm.state["shutter"] == SHUTTER_CLOSE and warm.state["acquiring"] == 0
    assert warm.names()[-1] == "ncCamClose"


def test_dark_frames_slow_reads_fail(warm: FakeSdk, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reading well below the nominal frame rate fails the frame rate check."""
    _fake_clock(monkeypatch, rate_hz=400.0)
    assert dark_frames.main(AUTO, make_factory(warm)) == 1


def test_dark_frames_light_leak_stops(warm: FakeSdk) -> None:
    """A spot above the phase cap stops the run with the camera dark and closed."""
    warm.state["spot_adu"] = 1000
    assert dark_frames.main(AUTO, make_factory(warm)) == 1
    assert "ncCamSetExposureTime" in warm.names()
    assert warm.names().count("ncCamStart") == 1
    assert warm.state["shutter"] == SHUTTER_CLOSE and warm.state["acquiring"] == 0
    assert warm.names()[-1] == "ncCamClose"


def _refused_second_process(_unit: int, _channel: int) -> tuple[int, str]:
    return 1, "connected: False status: 232 NC_ERROR_ALREADY_OPENED"


def test_edge_cases(warm: FakeSdk, isolated_root: Path,
                    monkeypatch: pytest.MonkeyPatch) -> None:
    """edge_cases.py passes every case on the fake and ends dark, idle and closed."""
    monkeypatch.setattr(edge_cases, "run_second_process", _refused_second_process)
    monkeypatch.setattr(edge_cases, "INTERRUPT_AFTER_S", 0.2)
    monkeypatch.setattr(edge_cases, "POLL_PERIOD_S", 0.0)
    monkeypatch.setattr(edge_cases, "MIN_POLLS", 1)
    assert edge_cases.main(AUTO, make_factory(warm)) == 0
    report = json.loads(next((isolated_root / "logs").glob("edge_cases_*.json")).read_text())
    assert all(case["ok"] for case in report.values())
    assert warm.names().count("ncCamOpen") == 4
    assert warm.state["acquiring"] == 0 and warm.names()[-1] == "ncCamClose"


def test_edge_cases_second_process_taking_over_fails(
        warm: FakeSdk, monkeypatch: pytest.MonkeyPatch) -> None:
    """A second process that connects fails the run."""
    monkeypatch.setattr(edge_cases, "run_second_process", lambda _u, _c: (2, "connected: True"))
    monkeypatch.setattr(edge_cases, "INTERRUPT_AFTER_S", 0.2)
    monkeypatch.setattr(edge_cases, "POLL_PERIOD_S", 0.0)
    monkeypatch.setattr(edge_cases, "MIN_POLLS", 1)
    assert edge_cases.main(AUTO, make_factory(warm)) == 1
