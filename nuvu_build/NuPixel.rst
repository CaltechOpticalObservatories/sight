==================
NuPixel on the RTC
==================

How to run Nuvu's NuPixel GUI on ``sight-rtc`` (``hesperus``, Ubuntu 26.04, headless) over SSH
X forwarding, for the Nuvu HNü 128 (SN06283454).

What is installed
=================

- **NuPixel:** ``/opt/NuvuCameras/bin/nuPixel_legacy`` (SDK 4.12.0, Ubuntu 22.04 build). It
  ships its own Qt 6 in ``/opt/NuvuCameras/Qt``.
- **Camera:** EDT VisionLink F1 frame grabber, unit 0, channel 0.
- **User guide:** ``Documentation/nuPixel Legacy User Guide.pdf`` inside the SDK tarball
  (``NuvuSW_NuPixel_4.12.0_ubuntu-22.04_x86_64.tar.gz``).

One-time setup
==============

1. **User:** run as ``hespy``, or any user in the ``nuvu-cameras`` group
   (``sudo usermod -aG nuvu-cameras USER``, then log in again).

2. **X client libraries:** the RTC has no desktop. Install the packages NuPixel and its Qt
   ``xcb`` plugin need, as listed in ``README.rst`` (section 6, NuPixel). Check that
   nothing is missing (no output means ready):

   .. code-block:: bash

      ldd /opt/NuvuCameras/bin/nuPixel_legacy /opt/NuvuCameras/bin/platforms/libqxcb.so | grep "not found"

3. **Save folders** (optional; Nuvu's installer normally creates them):

   .. code-block:: bash

      mkdir -p ~/Documents/"NuPixel Images" ~/Documents/"NuPixel Camera Settings" \
        ~/Documents/"NuPixel Processing Context"

SSH X forwarding (``X11Forwarding yes``) and ``xauth`` are already set up on the RTC.

Run
===

.. code-block:: bash

   ssh -X hespy@sight-rtc
   /opt/NuvuCameras/bin/nuPixel_legacy

If the window does not open or shows OpenGL errors, try these in order:

.. code-block:: bash

   QT_XCB_GL_INTEGRATION=none /opt/NuvuCameras/bin/nuPixel_legacy

Then reconnect with ``ssh -Y`` (trusted forwarding) instead of ``ssh -X``.

Over a slow link the live view will lag; that is X forwarding, not the camera.

Camera power
============

The camera is on outlet 5 ("Nuvu") of the WTI PDU at 192.168.1.11. Switch it with the
``wti_nps`` driver in ``~/test/pdu/src`` as shown in ``~/nuvu_build/testing.rst`` ("Camera power (PDU
outlet 5)"). Light outlets 1, 2, 4, 9 and 14 must be off whenever the camera is powered. Wait about
15 s after power-on before connecting, and at least 5 minutes after any power-off before
powering on again.

Safety rules (read before connecting)
=====================================

1. **One program at a time.** Close NuPixel before running any ``~/nuvu_build`` script, and
   do not start NuPixel while a script is connected.
2. **Light plus EM gain can destroy the detector.** Keep EM gain at 1 with the cap on.
   Never open the shutter with light around. Stay below EM gain 1000 even later (Nuvu).
3. **Connecting starts cooling.** The camera cools from power-on, and every connection sets
   the target to -60 °C (about 13 °C/min). Keep each powered session under about 4
   minutes, and read the CCD temperature before power-off.
4. **Never let the detector warm up on its own from below -60 °C.** If it ever gets that
   cold, close NuPixel and run ``~/nuvu_build/run.sh warm_and_close.py`` before powering off
   (NuPixel's own warm-up has not been tried on this system). An emergency power-off is
   allowed; then keep it off at least 5 minutes.
5. **Electronics heat fast** (FPGA about +10 °C in 70 s on the first sessions), another
   reason for short sessions.
6. **Do not run Nuvu's "Gains Offsets Temp" example or ``nc-install-edt.bash``.** The first
   sets EM gain to about 2500; the second reinstalls an EDT driver that locks up this
   real-time kernel.

Troubleshooting
===============

- **"Could not load the Qt platform plugin xcb":** an X library is missing; rerun the
  ``ldd`` check above.
- **"cannot open display":** the SSH session has no X forwarding; reconnect with ``-X`` or
  ``-Y`` and check that ``echo $DISPLAY`` is not empty.
- **No camera found:** the camera is off, still booting (wait 15 s), or another program has
  it open.
- **Garbled channel 1:** channel 1 is an unused input and shows serial noise; the camera
  is on channel 0.
- **SDK logs:** ``~/.nuvu/Logs/nc_driver/`` for the user running NuPixel.
