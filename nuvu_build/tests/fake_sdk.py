# The fake methods mirror the C signatures and take ctypes refs, so they stay untyped
# mypy: disable-error-code="no-untyped-def, no-untyped-call"
"""Extended copy of the driver's FakeLib for rehearsing the bring-up scripts.

Covers every SDK call the scripts make, records them in order, and models the state
that matters for safety: cold or warm detector, EM gain, shutter, acquisition, and a
camera that is powered off.
"""
from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Any

import numpy as np

from nuvu import NuvuCamera

NC_SUCCESS = 0
NC_GENERIC_ERROR = 1
NC_ERROR_CAM_NO_FEATURE = 107
NC_ERROR_GRAB_TIMEOUT = 214
CALIBRATED_EM_GAIN_FEATURE = 12
SHUTTER_CLOSE = 2
FRAME_SHAPE = (128, 128)
BIAS_ADU = 5800
READ_NOISE_ADU = 10.5
# connect() selects readout mode 1, which also sets the read timeout
CONNECT_SETTERS = ("ncCamSetReadoutMode", "ncCamSetTimeout")


def _set(ref: Any, value: Any) -> None:
    ref._obj.value = value  # pylint: disable=protected-access


class FakeSdk:
    """Stand-in for libnuvu: records calls and fills output arguments."""

    # pylint: disable=invalid-name, missing-function-docstring, unused-argument
    # pylint: disable=too-many-arguments, too-many-positional-arguments, too-many-public-methods

    def __init__(self, cameras: int = 1, cold: bool = False) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.cameras = cameras
        self.open_fails = False
        self.state: dict[str, Any] = {
            "cold": cold, "em_gain": 1, "acquiring": 0, "shutter": 3,
            "temps": [-60.0 if cold else 22.0, 31.0, 33.0, 41.0, 24.0],
            "target": -60.0 if cold else 20.0, "safe": -60.0, "warms_to": 20.0,
            "exposure": 0.0, "timeout": 1001, "frames_left": 0, "spot_adu": 0,
        }
        self._rng = np.random.default_rng(0)
        self._frame = np.zeros(FRAME_SHAPE, dtype=np.uint16)

    def __getattr__(self, name: str) -> Any:
        method = getattr(type(self), "_" + name, None)
        if method is None:
            raise AttributeError(name)

        def call(*args: Any) -> int:
            self.calls.append((name, args))
            return int(method(self, *args))
        return call

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def setters(self) -> list[str]:
        """SDK calls that change the camera, besides those every connect() makes."""
        changing = ("Set", "Start", "Abort", "PrepareShutdown")
        return [n for n in self.names()
                if any(word in n for word in changing) and n not in CONNECT_SETTERS]

    # connection and identity
    def _ncCamOpen(self, unit, channel, nbuf, cam_ref):
        if self.cameras == 0 or self.open_fails:
            return NC_GENERIC_ERROR
        _set(cam_ref, 0x1234)
        return NC_SUCCESS

    def _ncCamClose(self, cam):
        return NC_SUCCESS

    def _ncCamGetSerialNumber(self, cam, buf):
        buf.value = b"SN06283454"
        return NC_SUCCESS

    def _ncCamGetModel(self, cam, buf, size):
        buf.value = b"HNu128"
        return NC_SUCCESS

    def _ncCamGetDetectorType(self, cam, ref):
        _set(ref, 0)
        return NC_SUCCESS

    def _ncCamGetVersion(self, cam, kind, buf, size):
        buf.value = f"v{kind}".encode()
        return NC_SUCCESS

    # readout and timing
    def _ncCamGetNbrReadoutModes(self, cam, ref):
        _set(ref, 2)
        return NC_SUCCESS

    def _fill_mode(self, number, ampli, ampli_str, vert, horiz):
        _set(ampli, 1 if number == 1 else 2)
        ampli_str.value = b"EM" if number == 1 else b"Conventional"
        _set(vert, 2000000)
        _set(horiz, 10000000 if number == 1 else 1000000)

    def _ncCamGetReadoutMode(self, cam, number, ampli, ampli_str, vert, horiz):
        self._fill_mode(number, ampli, ampli_str, vert, horiz)
        return NC_SUCCESS

    def _ncCamSetReadoutMode(self, cam, mode):
        return NC_GENERIC_ERROR if self.state["acquiring"] else NC_SUCCESS

    def _ncCamSetTimeout(self, cam, timeout):
        self.state["timeout"] = timeout
        return NC_SUCCESS

    def _ncCamGetCurrentReadoutMode(self, cam, mode, ampli, ampli_str, vert, horiz):
        _set(mode, 1)
        self._fill_mode(1, ampli, ampli_str, vert, horiz)
        return NC_SUCCESS

    def _ncCamGetSize(self, cam, width, height):
        _set(width, 128)
        _set(height, 128)
        return NC_SUCCESS

    def _ncCamGetBinningMode(self, cam, bin_x, bin_y):
        _set(bin_x, 1)
        _set(bin_y, 1)
        return NC_SUCCESS

    def _ncCamGetReadoutTime(self, cam, ref):
        _set(ref, 1.7)
        return NC_SUCCESS

    def _ncCamGetFramerate(self, cam, ref):
        _set(ref, 580.0)
        return NC_SUCCESS

    def _ncCamSetExposureTime(self, cam, value):
        self.state["exposure"] = value
        return NC_SUCCESS

    def _ncCamGetExposureTime(self, cam, request, ref):
        _set(ref, self.state["exposure"])
        return NC_SUCCESS

    def _ncCamGetWaitingTime(self, cam, request, ref):
        _set(ref, 0.0)
        return NC_SUCCESS

    def _ncCamGetTimeout(self, cam, ref):
        _set(ref, self.state["timeout"])
        return NC_SUCCESS

    def _ncCamGetFramerateNominal(self, cam, request, ref):
        _set(ref, 1000.0 / max(self.state["exposure"], 1.7))
        return NC_SUCCESS

    def _ncCamGetTriggerMode(self, cam, request, mode, nbr):
        _set(mode, 0)
        _set(nbr, 1)
        return NC_SUCCESS

    def _ncCamGetShutterMode(self, cam, request, ref):
        _set(ref, self.state["shutter"])
        return NC_SUCCESS

    def _ncCamSetShutterMode(self, cam, mode):
        self.state["shutter"] = mode
        return NC_SUCCESS

    # acquisition
    def _ncCamStart(self, cam, nbr):
        self.state.update(acquiring=1, frames_left=nbr or -1)
        return NC_SUCCESS

    def _ncCamReadChronological(self, cam, image_ref, skipped_ref):
        if not self.state["acquiring"] or self.state["frames_left"] == 0:
            return NC_GENERIC_ERROR
        if self.state["timeout"] < self.state["exposure"]:
            return NC_ERROR_GRAB_TIMEOUT
        self.state["frames_left"] -= 1
        if self.state["frames_left"] == 0:
            self.state["acquiring"] = 0
        noise = self._rng.normal(BIAS_ADU, READ_NOISE_ADU, FRAME_SHAPE)
        self._frame[:] = np.clip(np.rint(noise), 0, 65535)
        # a light leak or hot spot in the middle of the frame
        self._frame[64, 64] += self.state["spot_adu"]
        # point the caller's image pointer at the frame buffer
        ctypes.pointer(image_ref._obj)[0] = self._frame.ctypes.data_as(  # pylint: disable=W0212
            ctypes.POINTER(ctypes.c_uint16))
        return NC_SUCCESS

    def _ncCamFlushReadQueues(self, cam):
        return NC_SUCCESS

    def _ncCamAbort(self, cam):
        self.state["acquiring"] = 0
        return NC_SUCCESS

    def _ncCamIsAcquiring(self, cam, ref):
        _set(ref, self.state["acquiring"])
        return NC_SUCCESS

    # gains
    def _ncCamParamAvailable(self, cam, feature, setting):
        if feature == CALIBRATED_EM_GAIN_FEATURE and self.state["cold"]:
            return NC_SUCCESS
        return NC_ERROR_CAM_NO_FEATURE

    def _ncCamGetCalibratedEmGain(self, cam, request, ref):
        _set(ref, self.state["em_gain"])
        return NC_SUCCESS

    def _ncCamSetCalibratedEmGain(self, cam, gain):
        if not self.state["cold"]:
            return NC_ERROR_CAM_NO_FEATURE
        self.state["em_gain"] = gain
        return NC_SUCCESS

    def _ncCamGetCalibratedEmGainRange(self, cam, low, high):
        _set(low, 1)
        _set(high, 5000)
        return NC_SUCCESS

    def _ncCamGetCalibratedEmGainTempRange(self, cam, low, high):
        _set(low, -85.0)
        _set(high, -30.0)
        return NC_SUCCESS

    def _ncCamGetAnalogGain(self, cam, request, ref):
        _set(ref, 1)
        return NC_SUCCESS

    def _ncCamGetAnalogGainRange(self, cam, low, high):
        _set(low, 1)
        _set(high, 4)
        return NC_SUCCESS

    def _ncCamGetAnalogOffset(self, cam, request, ref):
        _set(ref, 0)
        return NC_SUCCESS

    def _ncCamGetAnalogOffsetRange(self, cam, low, high):
        _set(low, -255)
        _set(high, 255)
        return NC_SUCCESS

    # temperatures
    def _ncCamGetComponentTemp(self, cam, component, ref):
        _set(ref, self.state["temps"][component])
        return NC_SUCCESS

    def _ncCamGetTargetDetectorTemp(self, cam, request, ref):
        _set(ref, self.state["target"])
        return NC_SUCCESS

    def _ncCamGetTargetDetectorTempRange(self, cam, low, high):
        _set(low, -85.0)
        _set(high, 20.0)
        return NC_SUCCESS

    def _ncCamGetSafeShutdownTemperature(self, cam, temp, flag):
        _set(temp, self.state["safe"])
        _set(flag, 0)
        return NC_SUCCESS

    def _ncCamPrepareShutdown(self, cam, blocking, callback):
        self.state.update(acquiring=0, shutter=SHUTTER_CLOSE, em_gain=1, cold=False,
                          target=20.0)
        self.state["temps"][0] = self.state["warms_to"]
        return NC_SUCCESS

    # enumeration
    def _ncControllerListOpen(self, ref):
        _set(ref, 0x99)
        return NC_SUCCESS

    def _ncControllerListGetSize(self, ctrl, ref):
        _set(ref, self.cameras)
        return NC_SUCCESS

    def _ncControllerListGetSerial(self, ctrl, i, buf, size):
        buf.value = b"SN06283454"
        return NC_SUCCESS

    def _ncControllerListGetModel(self, ctrl, i, buf, size):
        buf.value = b"HNu128"
        return NC_SUCCESS

    def _ncControllerListGetPortUnit(self, ctrl, i, ref):
        _set(ref, 0)
        return NC_SUCCESS

    def _ncControllerListGetPortChannel(self, ctrl, i, ref):
        _set(ref, 0)
        return NC_SUCCESS

    def _ncControllerListGetPortInterface(self, ctrl, i, buf, size):
        buf.value = b"EDT"
        return NC_SUCCESS

    def _ncControllerListGetDetectorSize(self, ctrl, i, width, height):
        _set(width, 128)
        _set(height, 128)
        return NC_SUCCESS

    def _ncControllerListFree(self, ctrl):
        return NC_SUCCESS


def make_factory(fake: FakeSdk) -> Any:
    """Return a camera factory whose cameras all use the given fake SDK."""

    def factory(_logfile: Path) -> NuvuCamera:
        camera = NuvuCamera(log=False)
        camera._lib = fake  # pylint: disable=protected-access
        return camera
    return factory
