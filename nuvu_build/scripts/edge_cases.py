"""Driver edge cases with the detector warm, EM gain 1 and the shutter closed (test plan Phase 4).

Runs every case in turn and records ok and details for each; frames are checked against the
phase 4 cap (a breach makes the camera dark and stops the script). The report goes to logs/.
Exit status: 0 if every case passed.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from typing import Final

import bringup
import numpy as np
from nuvu import NuvuCamera
from nuvu.nuvu_camera import DEFAULT_READOUT_MODE, TIMEOUT_MARGIN_MS

CAPS: Final = bringup.PHASE_CAPS[4]
NC_ERROR_GRAB_TIMEOUT: Final = 214
EXPOSURE_MS: Final = 1000.0
FORCED_TIMEOUT_MS: Final = 50
# Ten 1 s frames: a 10 s read without 10 s of warm dark signal
POLLED_FRAMES: Final = 10
POLL_PERIOD_S: Final = 0.5
MIN_POLLS: Final = 15
MAX_POLL_LATENCY_S: Final = 1.0
INTERRUPT_AFTER_S: Final = 1.5
SECOND_PROCESS_TIMEOUT_S: Final = 45
PREPARE_SHUTDOWN_MAX_S: Final = 30.0
OTHER_READOUT_MODE: Final = 2

Result = dict[str, object]

SECOND_PROCESS_CODE: Final = """
import sys
from nuvu import NuvuCamera
camera = NuvuCamera(log=False)
camera.connect(int(sys.argv[1]), int(sys.argv[2]))
print("connected:", camera.connected, "status:", camera.status, camera.status_string)
if camera.connected:
    camera.disconnect()
sys.exit(2 if camera.connected else 1)
"""


def checked_frame(camera: NuvuCamera, frame: np.ndarray, name: str) -> None:
    """Check a frame against the phase cap, using its own median as the bias."""
    bringup.check_frame(camera, frame, CAPS, float(np.median(frame)), name)


def em_gain_limit(camera: NuvuCamera) -> Result:
    """set_em_gain above the driver limit is refused and the gain stays at 1."""
    accepted = camera.set_em_gain(camera.em_gain_limit + 1)
    gain = camera.get_em_gain(camera_request=True)
    return {"ok": not accepted and gain == 1, "accepted": accepted, "gain_after": gain}


def mode_change_while_acquiring(camera: NuvuCamera) -> Result:
    """set_readout_mode fails cleanly during a continuous acquisition."""
    camera.set_exposure_time(EXPOSURE_MS)
    camera.start(0)
    changed = camera.set_readout_mode(OTHER_READOUT_MODE)
    code = camera.status
    still_acquiring = camera.is_acquiring()
    camera.abort()
    camera.flush()
    if changed:
        camera.set_readout_mode(DEFAULT_READOUT_MODE)
    mode = camera.get_readout_mode()
    return {"ok": not changed and still_acquiring is True, "changed": changed,
            "error": code, "acquiring_during": still_acquiring, "mode_after": mode}


def forced_timeout(camera: NuvuCamera) -> Result:
    """A read timeout shorter than the exposure gives None and NC_ERROR_GRAB_TIMEOUT."""
    camera.set_exposure_time(EXPOSURE_MS)
    camera.set_timeout(FORCED_TIMEOUT_MS)
    camera.start(1)
    start = time.monotonic()
    frame = camera.read_image(chronological=True)
    elapsed = time.monotonic() - start
    code = camera.status
    if camera.is_acquiring() is not False:
        camera.abort()
    camera.flush()
    restored = camera.use_auto_timeout()
    times = (camera.get_exposure_time(), camera.get_waiting_time(), camera.get_readout_time())
    expected = None if None in times else int(sum(times)) + TIMEOUT_MARGIN_MS
    timeout = camera.get_timeout()
    return {"ok": frame is None and code == NC_ERROR_GRAB_TIMEOUT and restored
            and timeout == expected, "frame_returned": frame is not None, "error": code,
            "read_s": elapsed, "timeout_after_auto_ms": timeout, "expected_ms": expected}


def polls_during_reads(camera: NuvuCamera) -> Result:
    """Temperature polls keep answering while another thread blocks in image reads."""
    camera.set_exposure_time(EXPOSURE_MS)
    frames: list[np.ndarray] = []

    def reader() -> None:
        for _ in range(POLLED_FRAMES):
            frame = camera.read_image(chronological=True)
            if frame is None:
                return
            frames.append(frame)

    camera.start(POLLED_FRAMES)
    thread = threading.Thread(target=reader, name="reader")
    thread.start()
    latencies, failures = [], 0
    while thread.is_alive():
        start = time.monotonic()
        failures += camera.get_temperature("ccd") is None
        latencies.append(time.monotonic() - start)
        thread.join(POLL_PERIOD_S)
    if camera.is_acquiring() is not False:
        camera.abort()
    for index, frame in enumerate(frames):
        checked_frame(camera, frame, f"edge_polled_{index:02d}")
    worst = max(latencies, default=None)
    return {"ok": len(frames) == POLLED_FRAMES and len(latencies) >= MIN_POLLS
            and failures == 0 and worst is not None and worst < MAX_POLL_LATENCY_S,
            "frames": len(frames), "polls": len(latencies), "failed_polls": failures,
            "worst_poll_s": worst}


def run_second_process(unit: int, channel: int) -> tuple[int, str]:
    """Try to connect from another process; return its exit code and output."""
    done = subprocess.run([sys.executable, "-c", SECOND_PROCESS_CODE, str(unit), str(channel)],
                          capture_output=True, text=True, timeout=SECOND_PROCESS_TIMEOUT_S,
                          check=False)
    return done.returncode, (done.stdout + done.stderr).strip()


def second_process(camera: NuvuCamera, args: argparse.Namespace) -> Result:
    """A second process is refused while this one holds the camera, which keeps working."""
    code, output = run_second_process(args.unit, args.channel)
    camera.start(1)
    frame = camera.read_image(chronological=True)
    if frame is not None:
        checked_frame(camera, frame, "edge_after_second_process")
    ccd = camera.get_temperature("ccd")
    return {"ok": code == 1 and frame is not None and ccd is not None,
            "second_exit": code, "second_output": output[-500:],
            "first_still_reads": frame is not None, "first_ccd": ccd}


def interrupt_during_read(args: argparse.Namespace, factory: bringup.CameraFactory) -> Result:
    """Ctrl-C during blocking reads ends the session safely."""
    timer = threading.Timer(INTERRUPT_AFTER_S, os.kill, (os.getpid(), signal.SIGINT))
    start = time.monotonic()
    interrupted_after = None
    try:
        with bringup.session("edge_cases", args, factory) as camera:
            camera.set_exposure_time(EXPOSURE_MS)
            camera.start(0)
            start = time.monotonic()
            timer.start()
            while camera.read_image(chronological=True) is not None:
                pass
    except KeyboardInterrupt:
        interrupted_after = time.monotonic() - start
    finally:
        timer.cancel()
    return {"ok": interrupted_after is not None, "interrupted_after_s": interrupted_after}


def reconnect_and_disconnect_while_acquiring(camera: NuvuCamera) -> Result:
    """After the interrupt the camera reconnects idle; disconnect() then stops a live run."""
    idle_on_reconnect = camera.is_acquiring()
    camera.set_exposure_time(EXPOSURE_MS)
    camera.start(0)
    frame = camera.read_image(chronological=True)
    if frame is not None:
        checked_frame(camera, frame, "edge_before_disconnect")
    camera.disconnect()
    return {"ok": idle_on_reconnect is False and frame is not None
            and not camera.is_connected(), "acquiring_on_reconnect": idle_on_reconnect,
            "read_before_disconnect": frame is not None}


def prepare_shutdown_warm(camera: NuvuCamera) -> Result:
    """The camera reconnects idle after a disconnect mid-acquisition; warm, prepare_shutdown
    returns at once."""
    idle_on_reconnect = camera.is_acquiring()
    before = bringup.temperatures(camera)
    start = time.monotonic()
    done = camera.prepare_shutdown(blocking=True)
    elapsed = time.monotonic() - start
    return {"ok": idle_on_reconnect is False and done and elapsed < PREPARE_SHUTDOWN_MAX_S,
            "acquiring_on_reconnect": idle_on_reconnect, "prepare_shutdown_s": elapsed,
            "temperatures_before": before, "temperatures_after": bringup.temperatures(camera),
            "em_gain_after": camera.get_em_gain(camera_request=True),
            "shutter_after": camera.get_shutter_mode(camera_request=True)}


def run_cases(args: argparse.Namespace, factory: bringup.CameraFactory) -> dict[str, Result]:
    """Run every case, connecting four times."""
    results: dict[str, Result] = {}
    with bringup.session("edge_cases", args, factory) as camera:
        bringup.make_dark(camera)
        results["em_gain_limit"] = em_gain_limit(camera)
        results["mode_change_while_acquiring"] = mode_change_while_acquiring(camera)
        results["forced_timeout"] = forced_timeout(camera)
        results["polls_during_reads"] = polls_during_reads(camera)
        results["second_process"] = second_process(camera, args)
    results["interrupt_during_read"] = interrupt_during_read(args, factory)
    with bringup.session("edge_cases", args, factory) as camera:
        results["disconnect_while_acquiring"] = reconnect_and_disconnect_while_acquiring(camera)
    with bringup.session("edge_cases", args, factory) as camera:
        results["prepare_shutdown_warm"] = prepare_shutdown_warm(camera)
    return results


def main(argv: list[str] | None = None,
         factory: bringup.CameraFactory = bringup.default_factory) -> int:
    """Run Phase 4 and write the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    bringup.add_connection_args(parser)
    args = parser.parse_args(argv)
    try:
        results = run_cases(args, factory)
    except bringup.ConnectFailed as error:
        print(error, flush=True)
        return 1
    except bringup.FrameOverCap as error:
        print(f"stopped: {error}", flush=True)
        return 1
    path = bringup.logs_dir() / f"edge_cases_{bringup.utc_stamp()}.json"
    path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(json.dumps(results, indent=2, default=str), f"\nreport: {path}", flush=True)
    return 0 if all(result["ok"] for result in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
