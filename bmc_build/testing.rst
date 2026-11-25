=========================================
BMC Kilo-DM: Testing on the SIGHT RTC
=========================================

How the deformable mirror is tested on ``sight-rtc`` (``hesperus``): safety rules, how a
session runs, the test phases and their status, the communication test, and what to do
when something goes wrong. Building the host side (SDK, PCIe module, BMC's files,
Python driver) is in ``README.rst`` in this folder. The full test plan is
``~/sight-dev/plans/bmc_dm_test_plan.md`` on the workstation.

Records (session logs, run output, findings) are kept on the workstation, not here; see
`Records`_.

At a glance
===========

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Item
     - Value
   * - Mirror
     - BMC kilo-DM ``30CW009#052``, 28 x 28 grid, 648 actuators
   * - Interface
     - BMC PCIe card at ``c1:00.0`` (``1a8f:2000``), fiber to the driver box, device
       ``/dev/bmc_mdrv0``
   * - High voltage
     - The driver box's power switch (no software HV switch on PCIe)
   * - Work folder
     - ``~hespy/software/bmc_build``
   * - Python driver
     - ``bmc_dm`` in ``venv/``; exact version in ``venv/DRIVER_VERSION``
   * - Bring-up bundle
     - ``bundle/bringup.toml``: soft limits 0.0 to 0.4, no default flat; steps may raise
       the maximum, never above Sight's 0.8
   * - Operator account
     - ``hespy``, in group ``bmc-dm``
   * - Test status
     - ``~/sight-dev/plans/bmc_dm_test_status.md`` on the workstation

Scripts and tools
=================

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - File
     - Use
   * - ``run.sh SCRIPT.py [ARGS]``
     - Runs ``scripts/SCRIPT.py`` with ``venv/`` and the SDK (``/opt`` once installed,
       otherwise the build in ``sdk/``); prints and saves the output to
       ``logs/SCRIPT_<utc>.out``, with the kernel, driver, SDK path and tmux state in the
       first line
   * - ``tools/check.sh``
     - Every software check, no SDK or hardware needed
   * - ``scripts/sdk_probe.py``
     - Imports ``bmc`` and prints its path and version (expects 4.1.3). Opens no DM
   * - ``scripts/rehearse.py [--dwell-s S]``
     - Every hardware phase's actions on the SDK's dummy driver, with the plan's
       amplitudes and caps. JSON report
   * - ``scripts/fault_drill.py``
     - Holds a flat on the dummy driver and interrupts it with Ctrl-C, SIGTERM, SIGHUP
       and an exception; checks the bias came back and the mirror was zeroed and
       disconnected. JSON report
   * - ``scripts/audit_bundle.py``
     - The bundle's map is BMC's circular 28 x 28 layout, its files match the driver's,
       and each flat's range, largest neighbor step and values above 0.4, 0.6 and 0.8
   * - ``scripts/audit_profile.py PROFILE.dm``
     - Decodes and checks a BMC profile (see ``README.rst``, section 5)
   * - ``scripts/card_status.py``
     - **Read-only** card and driver box status through ``bmc_ltest -i`` (below)
   * - ``scripts/bringup.py``
     - Shared safety layer, not run directly (below)

``scripts/bringup.py`` is how every script that drives the mirror opens it:

* **Dummy by default.** Without ``--hardware`` it opens ``DUMMY000648`` from
  ``dummy/Profiles``, with its own log and last-command file, so a rehearsal never
  reaches the real profile. ``--hardware`` is refused outside tmux.
* **Always ends at zero.** On every exit (normal, error, Ctrl-C, SIGTERM, SIGHUP) it
  sends ``zero()`` and then ``disconnect()``, with signals held off meanwhile.
* **Refuses instead of clipping.** ``send()`` prints the peak, the number of actuators
  moved and the largest neighbor step, and refuses a command whose peak passes the
  step's cap or that has a value outside the soft limits.
* **Checked limits.** A step may raise the soft maximum, never above 0.8, and SDK folders
  named in the bundle must exist.
* ``flash_edge`` and ``simulate_turbulence`` send through the driver directly, so the
  driver's clip warning is their only guard.

Safety rules
============

1.  **No actuator writes before the actuator phases.** ``card_status.py`` only reads.
    ``connect()`` writes configuration but no actuator value; ``disconnect()`` (the
    SDK's ``close_dm``) writes 0 to every actuator.
2.  **Use** ``bmc_ltest`` **only through** ``card_status.py``. It runs ``-i`` alone; the
    tool's other options poke actuators (``-p``), set or zero them all (``-z``,
    ``-Z``), write registers (``-R``, ``-B``) or start sequences and dither (``-S``,
    ``-W``, ``-j``).
3.  **The driver box is the bench operator's.** Power it on and off in BMC's order;
    connect or remove cables only with everything off. Never pull the fiber or the
    mirror cable to stop something.
4.  **Scripts that hold a shape run inside tmux** (``tmux new -s bmc``), so a dropped
    SSH session cannot kill them. SIGTERM and SIGHUP still clean up; ``kill -9`` and a
    PC crash do not, and the box then holds the last shape until it is powered off.
5.  **One process uses the card at a time.**
6.  **Audit BMC's profile before installing it** (``install_bmc_files.sh`` does). A
    missing map makes ``open_dm`` fail with the DM already open.
7.  **No driver changes in the middle of a test round.** Log the finding, finish or stop
    the round, change the driver, restart from Phase 0.

How a session runs
==================

Two roles:

* **Remote operator** (over ``ssh sight-rtc`` as ``hespy``): writes and runs the scripts
  and reads the output. Never uses sudo.
* **Bench operator** (the user): owns the driver box power, the light path and its
  camera, runs every sudo step, and says **go** before every hardware step.

For each hardware step:

1. The remote operator posts the step: script, what it writes (if anything), the box
   state needed, and the expected result.
2. The bench operator checks the bench and says go.
3. One script runs; it ends with the card and mirror in a known state.
4. Both report; go or stop is decided before the next step.

Any stop condition, unexpected error or doubt ends the session: driver box off. Resume
only once the cause is understood.

Test phases
===========

.. list-table::
   :header-rows: 1
   :widths: 22 48 30

   * - Phase
     - What
     - Status
   * - 0. Software gate
     - ``check.sh``, SDK build, ``sdk_probe.py``, ``rehearse.py``, ``fault_drill.py``
       on the dummy driver
     - **Passed** 2026-11-03 on the SDK build in ``sdk/``, and 2026-11-25 on the
       ``/opt`` install
   * - 1. Audit
     - ``audit_bundle.py``; BMC's profile (``audit_profile.py``); bench and camera
     - Bundle **passed** 2026-11-03; profile not received; bench open
   * - 1b. Communication
     - The communication test below: card alone, then driver box on, nothing written
     - Step A done 2026-11-25 (module bound, ``/dev/bmc_mdrv0`` in ``bmc-dm``, kernel
       log clean) except BMC's files; steps B and C not started
   * - 2. to 9.
     - Connect, first motion, map and orientation, flats, dynamic routines,
       persistence, recovery, drift (test plan)
     - Not started; scripts not written

Stop a phase on: a kernel BUG or WARNING, any ``bmc_ltest`` error, a hardware revision
that is not ``v2000``, a fiber link that does not follow the driver box's power, or any
change on the camera when the box powers on.

Communication test (no actuator writes)
=======================================

Proves that the RTC, the card, the fiber link and the driver box talk to each other
without writing any actuator value. Run each step as ``hespy`` on ``sight-rtc``, check
its expected result, then go on.

A. Host setup (bench operator, driver box off)
----------------------------------------------

#. Install the SDK and module (``README.rst``, section 4), then log in again:

   .. code-block:: bash

      cd ~/software/bmc_build && sudo ./install_bmc_sdk.sh

   Expected: ``done.`` with ``/dev/bmc_mdrv0`` listed as ``crw-rw---- root bmc-dm``.

#. Copy BMC's files into ``~/software/bmc_build/bmc_files/`` and install them:

   .. code-block:: bash

      cd ~/software/bmc_build && sudo ./install_bmc_files.sh

   Expected: ``audit_profile: passed``, then the installed files and their sha256.

#. Phase 0 on the ``/opt`` SDK (dummy driver, the card is not used):

   .. code-block:: bash

      cd ~/software/bmc_build && ./run.sh sdk_probe.py && ./run.sh rehearse.py && ./run.sh fault_drill.py

   Expected: the SDK path ``/opt/Boston Micromachines/lib/python3``, version
   ``4.1.3``, ``rehearse: all passed`` and ``fault_drill: all passed``.

B. Card only (driver box off)
-----------------------------

#. Record the box-off baseline:

   .. code-block:: bash

      cd ~/software/bmc_build && ./run.sh card_status.py --label boxoff

   Expected: one board, hardware revision ``v2000_...``, ``card_status: passed``.

#. 100 more read-only reads, then the kernel log:

   .. code-block:: bash

      ./run.sh card_status.py --label cycles --cycles 100

   Expected: ``card_status: passed`` (every read identical, no kernel BUG or
   WARNING).

C. Driver box on, nothing sent
------------------------------

#. Bench: camera reference frame with the box off.
#. Bench: power the driver box on in BMC's order, no script running. Camera frame:
   unchanged from the reference.
#. Read and compare with the baseline:

   .. code-block:: bash

      ./run.sh card_status.py --label boxon --compare boxoff

   Expected: the fiber bits change (light received, channel and lane up) and
   ``hv.hv_on`` becomes true; ``card_status: passed``.

#. Bench: power the box off. Then:

   .. code-block:: bash

      ./run.sh card_status.py --label boxoff --compare boxoff

   Expected: ``no change`` against the earlier baseline.

#. Repeat C2 to C4 once.

D. SDK connect with the box off (not yet written)
-------------------------------------------------

``connect()`` then ``disconnect()`` through the driver with the box **off**, so the
configuration writes and the zeros from ``close_dm`` reach only the card. The same with
the box on is the first actuator write and waits for Phase 2.

Reading ``card_status``
=======================

``card_status.py`` decodes the three status registers into named bits (from BMC's
``bmc_mdlib.h``) and saves them with the raw output in ``logs/card_<label>_<utc>.json``:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Field
     - Meaning
   * - ``fiber.sfp_absent``
     - No fiber transceiver in the card (false when it is fitted)
   * - ``fiber.loss_of_light``
     - No light on the fiber, as with the driver box off
   * - ``fiber.channel_up``, ``fiber.lane_up``
     - The fiber link's startup handshake with the driver box succeeded
   * - ``fiber.soft_error``, ``fiber.hard_error``, ``fiber.sfp_tx_fault``
     - Bit errors, clock loss or a transmitter fault
   * - ``hv.hv_on``
     - The driver box reports high voltage on
   * - ``hv.data_dropped``, ``hv.dacs_busy``
     - Brief transfer states
   * - ``hv.error_since_power_on``
     - Any driver box error since it was powered on
   * - ``kilo.dac_overflow``, ``kilo.bad_address``, ``kilo.fifo_half_full``
     - Kilo driver data errors

``--compare LABEL`` lists every field that differs from the newest ``LABEL`` report;
``--cycles N`` repeats the read N times and checks the kernel log afterwards. The
expected values with the box on are BMC's to confirm (open question).

If something goes wrong
=======================

1. **Driver box off.** It holds the high voltage and the last shape.
2. **Script unresponsive or SSH lost:** ``tmux attach -t bmc``, Ctrl-C, kill it if
   needed. A killed script leaves the box holding its last shape until the box is
   powered off.
3. **Kernel BUG or host hang:** stop all mirror work; check ``journalctl -k -b -1`` after
   the reboot.
4. **To take the SDK out entirely:** ``sudo ./uninstall_bmc_sdk.sh`` (``README.rst``,
   section 6).

Records
=======

Kept on the workstation, under ``~/sight-dev/``:

.. code-block:: bash

   rsync -a sight-rtc:software/bmc_build/logs/ ~/sight-dev/daily_log/rtc/bmc/logs/

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Path
     - What
   * - ``daily_log/<date>.md``
     - Running log of each day
   * - ``daily_log/rtc/bmc/logs/``
     - Output copied from ``logs/`` here
   * - ``plans/bmc_dm_test_plan.md``
     - Full test plan behind the phase table
   * - ``plans/bmc_dm_test_status.md``
     - Current status, findings for the driver rework, open items

Known issues and watch items
============================

* **Map loading cannot be rehearsed.** The dummy driver loads no map, so a bad or
  missing map only shows on the real card; the profile audit is the guard.
* **Flats near the ceiling:** ``quick`` and ``mean600`` peak at 0.798 and 0.799 against
  Sight's 0.8; ``mean700`` peaks at 0.9 and is clipped; ``mean500`` (0.678) needs more
  than the 0.6 flat-ramp ceiling.
* **The SDK zeroes on close** and on Python exit, so a mirror keeps its shape only while
  a session stays connected; ``last_command.npy`` and ``restore()`` bring it back.
* **Driver findings for the next round** (not fixed, driver frozen): close the SDK
  object when ``open_dm`` fails after opening; ``connected`` stays false if the first
  readback fails; reject missing SDK folders in ``DMConfig``; optionally a checked
  ``zero()`` before ``close_dm``; a neighbor-step guard once BMC gives its limit.
