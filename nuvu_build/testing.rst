======================================
Nuvu HNü 128: Testing on the SIGHT RTC
======================================

Everything needed to run, test and maintain the Nuvu HNü 128 EMCCD on ``sight-rtc``
(``hesperus``). Read the safety rules before powering the camera. The camera can be damaged
permanently in ways the warranty does not cover, and the software does not prevent all of
them.

How the camera is tested on ``sight-rtc``: safety rules, how a session runs, the test
phases and their status, and what to do when something goes wrong. Building the host
side (EDT patch, Nuvu SDK, Python driver, tools) is in ``README.rst`` in this folder.

Records (session logs, run output, findings) are kept on the workstation, not here; see
`Records`_.

At a glance
===========

.. list-table::
   :header-rows: 1

   * - Item
     - Value
   * - Camera
     - Nuvu HNü 128, SN06283454, CCD60 128x128 EMCCD, air cooled
   * - Camera power
     - WTI NPS-16 PDU at 192.168.1.11, **outlet 5**
   * - Frame grabber
     - EDT VisionLink F1 (PCIe 81:00.0), devices ``/dev/pdv0_0``, ``pdv0_1``, ``pdv0_2`` (Camera Link channels 0 to 2)
   * - Camera Link channel
     - **0** (found 2026-11-03). Channel 1 is an unused floating input
   * - Host
     - Ubuntu 26.04, kernel ``7.0.0-38-realtime`` (PREEMPT_RT), held
   * - EDT software
     - EDT PDV 6.2.1 in ``/opt/EDTpdv``; kernel module ``edt_pci_pdv`` **patched** for PREEMPT_RT (srcversion ``38A1C0CA3BF007F52131B1A``)
   * - Nuvu SDK
     - 4.12.0, Ubuntu 22.04 build, installed in ``/opt/NuvuCameras``
   * - Python driver
     - ``nuvu`` package from the nuvu repo, installed in ``venv/``; exact version in ``venv/DRIVER_VERSION``
   * - Operator account
     - ``hespy``, in group ``nuvu-cameras``
   * - Readout mode
     - 1 (EM, 10 MHz), selected by ``connect()``
   * - Safe shutdown temperature
     - -60 °C (calibrated EM gain works from -80 to -30 °C)
   * - Test status
     - ``~/sight-dev/plans/nuvu_test_status.md`` on the workstation


Scripts and tools
=================

.. list-table::
   :header-rows: 1

   * - File
     - Use
   * - ``run.sh SCRIPT.py [ARGS]``
     - Runs ``scripts/SCRIPT.py`` with ``venv/``, prints and saves the output to ``logs/SCRIPT_<utc>.out`` with the kernel and driver version in the first line
   * - ``scripts/status.py [--unit U] [--channel C]``
     - Read-only report: cameras found, identity, readout modes, every getter and range. No setters besides readout mode 1, which ``connect()`` selects. JSON to ``logs/``
   * - ``scripts/connect_cycle.py [--cycles 3] [--pause-s 2]``
     - Connect and disconnect repeatedly, nothing in between; checks the serial number each time
   * - ``scripts/telemetry_log.py [--duration-s 600] [--period-s 30]``
     - Logs all temperatures and the target to CSV. Sends no commands
   * - ``scripts/dark_frames.py``
     - Phase 3: mode 1, EM gain 1, shutter closed; 10 frames at 1, 10, 100, 1000 ms, then 1000 continuous frames read in order. Checks gain 2 refused warm, timeouts, bias, read noise, frame rate against nominal, idle after abort. Frames to ``frames/``, JSON report to ``logs/``; a frame over the phase cap makes the camera dark and stops
   * - ``scripts/edge_cases.py``
     - Phase 4: EM gain 1001 refused, mode change during acquisition refused, forced read timeout then ``use_auto_timeout()``, temperature polls during 10 s of reads, second process refused, Ctrl-C during reads then reconnect, ``disconnect()`` during acquisition, ``prepare_shutdown()`` while warm. Four connects; JSON report to ``logs/``
   * - ``scripts/safe_dark.py``
     - EM gain to minimum, shutter closed, acquisition aborted, temperatures printed
   * - ``scripts/warm_and_close.py [--period-s 5]``
     - Controlled warm-up (``prepare_shutdown``) with temperature logging; prints "safe to power off" only when the CCD is at or above the safe shutdown temperature
   * - ``NuPixel.rst``
     - How to run Nuvu's NuPixel GUI over ``ssh -X``: packages, launch, safety
   * - ``scripts/bringup.py``
     - Shared safety layer, not run directly (below)
   * - ``tools/serial_noise CHANNEL SECONDS``
     - Built from ``tools/serial_noise.c`` (see ``README.rst``). Counts the bytes a Camera Link serial line delivers. With the camera off, a floating line shows noise
   * - ``tools/stress_events.sh [ITERATIONS]``
     - Stresses the EDT driver on all three channels and checks the kernel log for BUG/WARNING. Camera may stay off
   * - ``tools/edt_event_fix``
     - Built from ``tools/edt_event_fix.c``; used by ``stress_events.sh``
   * - ``tools/cameras_enumeration``
     - Nuvu's "Cameras Enumeration" example, built from ``/opt/NuvuCameras/CameraExamples`` (4.12.0): lists cameras, opens and closes the first one found. No setters

``scripts/bringup.py`` is how every script opens the camera:

- On every exit (normal, error or Ctrl-C) it sets EM gain to minimum, aborts acquisition
  and disconnects.
- ``Telemetry`` logs all temperatures and the target to CSV from a thread, for scripts
  that want it.
- ``guarded_gain()`` refuses an EM gain above the phase cap, more than 2.5x the current
  gain, when calibrated gain is unavailable, or when the predicted peak would pass the
  phase's ADU cap.
- ``check_frame()`` saves the frame and, if the peak passes the phase's ADU cap or any pixel
  saturates, runs the safe-dark sequence and exits.

Phase caps (EM gain / ADU above bias): Phases 2 to 6: 1 / 500. Phase 7: 100 / 500.
Phase 8: 1 / 8,800. Phase 9: 100 / 2,000.

Safety rules
============

1.  **Light plus EM gain is the one way to destroy the detector.** Over-illumination
    saturates the EM register and ages or damages it permanently, not covered by warranty
    (HNü manual 2.4). Start at EM gain 1, raise it slowly, stay below 1000. The driver
    refuses calibrated gain above 1000 (``em_gain_limit``) and raw gain unless
    ``allow_raw_em_gain`` is set; testing stays far lower through the per-phase caps in
    ``bringup.py``. Keep the lens cap on and the room dark unless a phase says otherwise.
2.  **Deliberate cooling only from Phase 5 on.** A cold detector can only be warmed in a
    controlled way through the SDK (``warm_and_close.py``); Phases 2 to 4 proved that path
    on 2026-11-03. Long cooled sessions also need the camera's cooling (fan and vents, or
    liquid) confirmed first, because the electronics keep heating (rule 4). If the warm-up
    path fails, the only exit is an emergency power-off.
3.  **Never let the detector warm up on its own from below -60 °C.** Power off only after
    ``warm_and_close.py`` prints "safe to power off". ``disconnect()`` alone does not warm it.
    An emergency power-off is allowed, followed by at least 5 minutes off.
4.  **The camera starts cooling as soon as it is powered**, toward its stored target
    (-44.99 °C), and **every ``ncCamOpen`` sets the target to -60 °C** (the camera's
    ``DefaultSetTempCCD``). Bring-up keeps each power-on short instead of managing the
    target: windows under about 4 minutes, at least 5 minutes off between them, CCD read
    before every power-off and well above -60 °C. Measured: CCD about 12 °C/min in the
    first minute, about 4 °C/min after 4 minutes (-22.4 °C at 4.5 min); electronics do not
    settle (FPGA +18 °C in 4 minutes, still rising; heatsink +2 °C).
    ``prepare_shutdown()`` while warm sets the target to -55 °C, so the camera keeps
    cooling if left powered.
5.  **Never run the vendor example "Gains Offsets Temp".** It sets EM gain to about 2500.
    "Simple Acquisition" opens the shutter. "Cameras Enumeration" is the only vendor
    example used.
6.  **Never run Nuvu's ``nc-install-edt.bash``.** It reinstalls EDT with the unpatched
    driver, which locks up this RT kernel.
7.  **Change cables only with both the camera and the PC off** (manual 2.2). Here that
    means shutting down ``hesperus``. Never pull the Camera Link cable to stop something.
8.  **Environment:** 50 mm clear around the vents; ambient at most 30 °C (0 to 20 °C for
    full spec). The manual says the camera limits cooling to 5 °C/min; it measured faster
    in the first minute. Watch for condensation.
9.  Calibrated EM gain works only inside the calibrated temperature range (-80 to -30 °C);
    outside it the gain falls back to 1 and setting it fails. Never use raw EM gain.
10. A readout mode change resets EM gain, analog gain and offset, ROI, binning and crop
    mode. ``prepare_shutdown()`` stops acquisition, closes the shutter and sets EM gain to 1.

How a session runs
==================

Two roles:

- **Remote operator** (over ``ssh sight-rtc`` as ``hespy``): writes and runs the scripts,
  switches outlet 5 after the go, and reads the output. Never uses sudo.
- **Bench operator** (the user): owns the lens cap, light and cooling, runs every sudo
  step, and says **go** before every powered step.

For each powered step:

1. The remote operator posts the step: script, channel, readout mode, exposure, EM gain,
   target temperature, light state, expected result.
2. The bench operator checks the bench (cap, light, vents) and says go.
3. Light outlets read off, outlet 5 on, 15 s wait.
4. One script runs (long ones inside ``tmux``, so a dropped SSH session does not kill
   them). It always ends with EM gain at minimum, acquisition aborted, camera
   disconnected.
5. CCD temperature read, outlet 5 off and read back off.
6. Both report; go or stop is decided before the next step.

Any stop condition, unexpected error or doubt ends the session at a safe state (see
`If something goes wrong`_). Resume only once the cause is
understood. No driver changes in the middle of a test round: log the finding, finish or
stop the round, change the driver, restart from Phase 0.

Before a session
================

.. code-block:: bash

   uname -r                                   # 7.0.0-38-realtime
   ls /var/run/reboot-required 2>/dev/null    # nothing pending
   who                                        # nobody else logged in
   fuser -v /dev/pdv0_*                       # nothing has the board open
   cat /sys/module/edt_pci_pdv/srcversion     # 38A1C0CA3BF007F52131B1A (patched)
   journalctl -k -b --no-pager | grep -E "BUG|WARNING|edt_pci_pdv" | tail   # no BUGs
   cat ~/nuvu_build/venv/DRIVER_VERSION       # the driver under test
   ip -4 addr show enp100s0                   # 192.168.1.10/24 (for the PDU)
   pgrep -a nuPixel                           # NuPixel closed (one program at a time)

Then read outlet 5 (must be off) and the light outlets (see Camera power).

At the bench: ambient temperature, humidity and dew point noted; vents clear; cap on;
light off; abort procedure at hand.

Camera power (PDU outlet 5)
===========================

The PDU is reached over ``enp100s0``. Its address is set by hand and is **lost on every
reboot** (netplan does not cover this interface). Restore it with:

.. code-block:: bash

   sudo ip addr add 192.168.1.10/24 dev enp100s0

Switch the outlet with the ``wti_nps`` library in ``~/test/pdu/src``, using the shared RTC
Python. The library's defaults hold the login. Always read the state back after
switching:

.. code-block:: bash

   cd ~/test/pdu/src
   /opt/rtc_python/rtc_venv3.14.4/bin/python - <<'PY'
   from wti_nps import WtiNps
   pdu = WtiNps(log=False)
   pdu.connect("192.168.1.11")
   pdu.initialize()                                      # required before per-outlet calls
   print(pdu.get_outlet_name(5), pdu.outlet_status(5))   # read only: "Nuvu" False
   # pdu.outlet_on(5)    # only after the bench operator's go
   # pdu.outlet_off(5)   # only after warm_and_close.py (or as an emergency)
   print(pdu.get_outlets())
   pdu.disconnect()
   PY

After power-on, wait 15 s before talking to the camera. After an emergency power-off,
keep it off for at least 5 minutes.

The same PDU powers light sources and lasers (outlets 1, 2, 4, 9 and 14: laser controller,
laser safety, FSM laser, Pockels cell, visible light source). Check they are off before
any dark phase.

Running a step
==============

.. code-block:: bash

   tmux new -s nuvu                 # or: tmux attach -t nuvu
   cd ~/nuvu_build
   ./run.sh status.py --unit 0 --channel 0

Always pass ``--unit 0 --channel 0``; auto-detect scans every channel, including the noisy
channel 1 (see `Known issues and watch items`_). A connect takes about 17 s
(about 10 s to open, 6.7 s for the camera to load readout mode 1).

Test phases
===========

.. list-table::
   :header-rows: 1

   * - Phase
     - What
     - Limits
     - Status
   * - 0. Host and software gate
     - Kernel fixed, patched EDT module loaded, SDK installed, driver imports and loads libnuvu, rehearsal tests pass (on the workstation)
     - Camera off
     - **Passed on 4.12.0** (2026-11-03, again with driver ``9f9ae01``)
   * - 0b. Plugin path, camera off
     - ``tools/serial_noise`` per channel; ``tools/cameras_enumeration`` and ``status.py`` must finish without a hang or crash; direct connect per channel fails cleanly
     - Camera off
     - **Passed on 4.12.0** (2026-11-03): connects fail in 0.1 to 6.6 s, enumeration returns in about 10 s; rerun with ``9f9ae01``: SDK logs clean
   * - 1. Audit
     - Host, harness, PDU and bench checks
     - Camera off
     - **Passed 2026-11-03** (user)
   * - 2. Power and enumerate
     - Power on, wait 15 s; ``serial_noise``; enumeration; ``status.py``; ``connect_cycle.py`` (3x); ``telemetry_log.py`` 4 min at 10 s (short windows). Record channel, modes, ranges, safe shutdown temperature, and whether it cools by itself
     - Only the SDK's open-time commands and readout mode 1; cap on
     - **Passed 2026-11-03** (``58fcf61``): channel 0; ``status.py`` and 3 connect cycles clean; 4 min telemetry at 10 s instead of 10 min (short windows): CCD to -22.4 °C, FPGA +18 °C and still rising; safe shutdown -60 °C. Earlier attempts found the load-order and readout-mode bugs
   * - 3. Dark frames, warm
     - ``dark_frames.py``: EM 10 MHz mode; exposures 1, 10, 100, 1000 ms; 1000 continuous frames, then abort. Frames lost = measured ``get_framerate()`` below ``get_framerate_nominal()`` (the SDK's dropped-image count is always 0)
     - Gain 1; cap on
     - **Passed 2026-11-03** (rerun 22:12): all 10 checks; read noise 10.2 ADU; 524.5 Hz measured vs 524.2 nominal, no frames lost; bias check skips the first frame after start
   * - 4. Driver edge cases
     - ``edge_cases.py``: mode change while acquiring, disconnect while acquiring, forced timeout then ``use_auto_timeout()``, reads with parallel telemetry, Ctrl-C and reconnect, second process refused, ``set_em_gain(1001)`` refused, ``prepare_shutdown`` while warm
     - Gain 1; cap on
     - **Passed 2026-11-03** (22:10): all 8 cases; second process refused with ``NC_ERROR_CAMERA_FOUND``; ``prepare_shutdown()`` warm returns at once and sets the target to -55 °C
   * - 5. Mild cooling
     - Set -20 °C right after connect (the SDK sets -60 °C on open), hold 15 min with telemetry and bias tracking, ``warm_and_close.py``
     - Target ≥ -20 °C
     - **Blocked:** camera cooling not confirmed (Phases 2 to 4 passed); script not written yet
   * - 6. Operating temperature
     - Target -60 °C (air-cooled limit), darks, then a full ``warm_and_close.py``
     - Target ≥ -60 °C; gain 1
     - Not started
   * - 7. EM gain, dark
     - At -60 °C, gain 1, 2, 5, 10, 20, 50, 100
     - Gain ≤ 100; ADU 500; cap on
     - Not started
   * - 8. First light
     - Faint source through ND to about 25% full well; orientation, linearity, 2x2 binning
     - Gain 1; ADU 8,800
     - Not started
   * - 9. Light with EM gain
     - Needs Nuvu's answer on safe EM output; scene ≤ 50 ADU at gain 1, then up to 100
     - Gain ≤ 100; ADU 2,000
     - Not started
   * - 10. Recovery drill
     - Cold and acquiring: ``kill -9``; new session runs ``status.py``, ``safe_dark.py``, ``warm_and_close.py``
     - Gain 1; cap on
     - Not started
   * - 11. Soak
     - 1 h continuous at -60 °C with telemetry
     - As Phase 7 or 9
     - Not started

Stop a phase on: a crash or symbol error, any ``NC_ERROR_EDT_*`` or checksum error, a
hang, implausible temperatures, a heatsink or electronics temperature that keeps
climbing in a long phase, any cap hit, or any kernel BUG.

Expected values (certificate, EM output, 10 MHz): k-gain 14.68 e⁻/ADU; read noise at gain
1 about 154 e⁻ (about 10.5 ADU rms); full well at gain 1 about 259.6 ke⁻ (about 17,700 ADU
above bias); dark current 0.012 e⁻/px/s at operating temperature. Read noise in ADU should
stay about constant as EM gain rises. Measured warm (Phase 3): read noise 10.0 to 10.5
ADU; bias 3548 to 3616 ADU at analog gain 1, offset 5800; 524.5 Hz in mode 1 at 1 ms.

If something goes wrong
=======================

1. **Light first:** block the beam or put the cap on.
2. ``./run.sh safe_dark.py``
3. **Overheating or condensation:** power the camera off now (PDU outlet 5) and keep it
   off at least 5 minutes. Any other thermal doubt: ``./run.sh warm_and_close.py``.
4. **Script unresponsive or SSH lost:** ``tmux attach -t nuvu``, Ctrl-C, kill it if needed.
   Then a fresh ``safe_dark.py``, then ``warm_and_close.py``.
5. **Host hang or kernel BUG:** stop all camera work; check ``journalctl -k -b -1`` after the
   reboot and that the patched EDT module is loaded.

After a session
===============

.. code-block:: bash

   ./run.sh safe_dark.py
   ./run.sh warm_and_close.py        # if the CCD was cooled: wait for "safe to power off"

Then camera off at the PDU, cap on. Copy the output to the workstation and clear it here:

.. code-block:: bash

   # on the workstation
   rsync -a sight-rtc:nuvu_build/logs/ ~/sight-dev/daily_log/rtc/logs/
   rsync -a sight-rtc:nuvu_build/frames/ ~/sight-dev/daily_log/rtc/frames/   # if any were saved
   # on the RTC, once the copy is checked
   rm -rf ~/nuvu_build/logs ~/nuvu_build/frames

Host build and maintenance
==========================

The EDT driver patch, the Nuvu SDK install, the Python driver environment, the tools,
the camera-off verification and kernel or driver updates are in ``README.rst`` in this
folder. Change the driver between test rounds only, then restart the round at Phase 0.

Known issues and watch items
============================

- **Channel 1 serial noise.** With the camera off, ``pdv0_1`` delivers about 11 kB/s of
  garbage; channels 0 and 2 are silent. SDK 4.12.0 handles it (connect fails in 6.6 s,
  enumeration returns in about 10 s; 4.2.1 hung). libpdv may print "Got ACK; command
  succeeded." when a noise byte happens to be an ACK; that is not a camera.
- **Python sessions failed every camera reply** (``NC_ERROR_COM_CSUM_SENT``, 54) while the
  vendor C example worked. Cause: libnuvu carries a static libstdc++ whose unique symbols
  bind to the system libstdc++ when numpy has loaded it first; libnuvu then formats and
  parses no numbers (SDK log headers read ``NUVU CAMERAS SDK  LOG`` / ``--- EPISODE``, the
  scan reports "HNu VOID" serial "0.0.0"). Fixed in driver ``9f9ae01`` (installed):
  ``import nuvu`` loads libnuvu first, and the driver refuses to load it after libstdc++.
  Scripts must import nuvu before numpy. A garbled SDK log header means this bug is
  back. The camera's ``ERROR`` reply to ``vb 1`` on every open is normal.
- **SDK segfault before a readout mode is selected:** after ``ncCamOpen`` no readout mode
  is set (``NC_ERROR_CAM_NO_READOUT_MODE``), and ``get_trigger_mode(camera_request=True)``
  then crashes the process inside ``nc::CamContext::setTriggerModeCamera``. Nuvu's examples
  always call ``ncCamSetReadoutMode(cam, 1)`` right after open; since driver ``58fcf61``,
  ``connect()`` does the same.
- **Channel 2 is not a camera channel for the SDK:** ``ncCamOpen`` on it returns
  ``NC_ERROR_CAMERA_FOUND`` in milliseconds without opening it, and the scan skips it.
- **``edt_pci_pdv: DevInt at channel 2`` kernel messages** (hundreds per second) appear
  whenever the EDT plugin or a probe has a channel open, whatever channel it is. Log noise
  from the EDT driver, no errors; filter it out when reading ``journalctl -k``.
- **Bias differs between sessions:** 3548 ADU at 21:59 and 3616 ADU at 22:12 on
  2026-11-03, at different CCD and electronics temperatures. Track it against temperature
  in Phases 5 and 6.
- **The first frame after ``start()``** carries charge from the idle period (top rows
  about 12 ADU high, median a few ADU high); ``dark_frames.py`` skips it in the bias check.
- **A second process is refused** with ``NC_ERROR_CAMERA_FOUND``, not a "busy" error.
- **Ctrl-C lands when the current read returns** (up to one frame period plus readout).
- **EDT stress test:** one hang in 150 runs (10 s watchdog) on a channel 1+2 pair, no
  kernel errors. Rerun ``tools/stress_events.sh`` before relying on the board under load.
- **PDU address on ``enp100s0``** is not persistent (see Camera power).
- **Warm-up success is not proof of warmth.** On Nuvu's virtual camera,
  ``prepare_shutdown(blocking=True)`` returned success at once with the CCD still below the
  safe temperature. Always compare the CCD temperature with
  ``get_safe_shutdown_temperature()`` (as ``warm_and_close.py`` does); a ``None`` safe
  temperature means "not safe".
- **No warm-up progress from the driver.** Which return value of the SDK's progress
  callback interrupts the warm-up is undocumented; the telemetry thread logs the
  temperatures instead.
- **Dropped images are not counted** by SDK 4.12.0 (``get_nbr_dropped_images()`` is always
  0). Compare ``get_framerate()`` (measured) with ``get_framerate_nominal()``.
- **Driver behaviour to rely on** (branch ``elijahab/testing-final``): ``is_acquiring()`` is
  ``None`` when unknown and ``disconnect()`` then aborts; ``set_timeout()`` is a manual
  override until ``use_auto_timeout()``; ``get_safe_shutdown_temperature()`` is ``None`` when
  the camera reports no value.

Records
=======

Kept on the workstation, under ``~/sight-dev/``:

.. list-table::
   :header-rows: 1

   * - Path
     - What
   * - ``daily_log/<date>.md``
     - Running log of each day: what was done, results, decisions, open items
   * - ``daily_log/rtc/session_notes.md``
     - Bring-up notes kept on this host until 2026-11-03
   * - ``daily_log/rtc/logs/``, ``daily_log/rtc/frames/``
     - Output copied from ``logs/`` and ``frames/`` here (``logs/sdk_4.2.1/`` = before the SDK switch)
   * - ``daily_log/rtc/phase*_<date>/``, ``daily_log/rtc/archive_<date>/``
     - Per-phase outputs, and the end-of-day archive of ``logs/``, ``frames/`` and the SDK logs
   * - ``plans/nuvu_test_plan.md``
     - Full test plan behind the phase table
   * - ``plans/nuvu_test_status.md``
     - Current phase status and next steps
   * - ``edt_pdv_6.2.1_preempt_rt.md``
     - Both EDT bugs, evidence, patch and tests
   * - ``rt_kernel_dkms_initramfs_panic.md``
     - The realtime-kernel boot failure and its fix
   * - ``nuvu/`` (repo, branch ``elijahab/testing-final``)
     - The Python driver installed in ``venv/``
   * - ``sight/nuvu_build/`` (sight repository)
     - Master copy of this folder
