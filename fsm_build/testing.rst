=================================================
Fast Steering Mirrors: Testing on the SIGHT RTC
=================================================

**Outline.** How the two fast steering mirrors and their Galil controller are tested on
``sight-rtc`` (``hesperus``): safety rules, how a session runs, the test phases and what
to do when something goes wrong. Building the host side (controller, split cable,
network, gclib, library) is in :doc:`fsm_build` (``README.rst`` in this folder). Sections marked **TBD**
wait for hardware details.

At a glance
===========

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Item
     - Value
   * - Controller
     - Galil DMC-30000 series (model **TBD**), address **TBD**
   * - Mirrors
     - Two FSMs, tip and tilt each (models and input ranges **TBD**)
   * - Wiring
     - One 100-pin cable split into one leg per mirror (``README.rst``, section 3)
   * - Work folder
     - ``~hespy/software/fsm_build``
   * - Config
     - ``config/fsm.toml``: axis map, polarity, centers, limits
   * - Operator account
     - ``hespy``
   * - Test status
     - **TBD** (a status file in ``~/sight-dev/plans/`` on the workstation)

Scripts and tools
=================

Planned, following ``bmc_build``:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - File
     - Use
   * - ``run.sh SCRIPT.py [ARGS]``
     - Runs a script with ``venv/``; saves the output to ``logs/SCRIPT_<utc>.out``
   * - ``tools/check.sh``
     - Every software check, no hardware needed
   * - ``scripts/bringup.py``
     - Shared safety layer (below)
   * - ``scripts/status.py``
     - **Read-only**: controller model, firmware and the voltage on each output
   * - ``scripts/rehearse.py``
     - The hardware phases' actions against a fake gclib
   * - Step scripts (**TBD**)
     - One per hardware phase

``scripts/bringup.py`` (planned) is how every script that drives the mirrors opens the
controller:

* **Fake by default.** Without ``--hardware`` it uses a fake gclib; ``--hardware`` is
  refused outside tmux.
* **Always ends at center.** On every exit (normal, error, Ctrl-C, SIGTERM, SIGHUP) both
  mirrors return to their center voltage, then the connection closes.
* **Refuses instead of clipping.** A command outside the step's cap or the mirror's
  limits is refused before it is sent.
* **Checked config.** Every axis maps to one output, no output to two axes.

Safety rules
============

Draft; **TBD** items wait for the mirrors' specifications.

1. **No output beyond 0 V until each mirror's input range is known** (**TBD**).
2. **Power order** for the controller and the mirror drivers (**TBD**); never plug or
   unplug the 100-pin cable or its legs with anything powered.
3. **Scripts that hold a position run inside tmux**, so a dropped SSH session cannot kill
   them.
4. **One process talks to the controller at a time.**
5. **Slew limits** between commands (**TBD**).
6. **No library changes in the middle of a test round.** Log the finding, finish or stop
   the round, change the library, restart from Phase 0.

How a session runs
==================

Two roles, as for the other builds:

* **Remote operator** (over ``ssh sight-rtc`` as ``hespy``): writes and runs the scripts
  and reads the output. Never uses sudo.
* **Bench operator** (the user): owns the controller and mirror power, the light path and
  its camera, runs every sudo step, and says **go** before every hardware step.

Test phases
===========

.. list-table::
   :header-rows: 1
   :widths: 25 50 25

   * - Phase
     - What
     - Status
   * - 0. Software gate
     - ``check.sh``, library tests and rehearsal against a fake gclib
     - Not started
   * - 1. Audit
     - Split cable: continuity and isolation with a meter, everything off; config matches
       the pinout
     - Not started
   * - 2. Connect, read only
     - ``status.py``: model, firmware, outputs at 0 V
     - Not started
   * - 3. Outputs, mirrors disconnected
     - Each output stepped and read back at the cable legs with a meter or scope
     - Not started
   * - 4. One axis at a time
     - Mirrors connected; small steps on each axis, watched on a camera
     - Not started
   * - 5. Full range
     - Each axis to its limits in steps; direction and scale recorded
     - Not started
   * - 6. Both mirrors
     - Both mirrors driven together; no crosstalk between legs
     - Not started
   * - 7. Recovery
     - ``kill -9`` while holding a position, then controller power loss: what the outputs
       do
     - Not started

Stop a phase on: any command error, an output that does not read back what was sent, a
mirror moving on the wrong axis or leg, or any change on a mirror that was not
commanded.

If something goes wrong
=======================

**TBD:** the fastest safe stop (mirror driver power or controller power), and what the
outputs hold after each.

Records
=======

Kept on the workstation, as for the other builds:

.. code-block:: bash

   rsync -a sight-rtc:software/fsm_build/logs/ ~/sight-dev/daily_log/rtc/fsm/logs/

Known issues and watch items
============================

* Controller model and number of analog outputs: the DMC-30012 has two (AO1, AO2), and
  two tip/tilt mirrors need four axes.
* The 100-pin cable: which device it connects to, and the split's pinout.
* Mirror models, input ranges, slew limits and power order.
* The RTC interface and the controller's address.
* ``galilfsm`` uses gclib 2.0's ``gclib.Controller``; confirm on the RTC.
