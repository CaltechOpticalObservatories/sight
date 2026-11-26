=========================================================
Fast Steering Mirrors: Galil Controller Build on the RTC
=========================================================

:Status: **Outline.** Sections marked **TBD** wait for hardware details; the install
         steps will be automated with a TOML config and install scripts, as in
         ``bmc_build``
:Prerequisite: :doc:`software_build` through :ref:`section-python` complete
:Hardware: Galil DMC-30000 series motion controller (setup notes are for a
           DMC-30012-BOX; model **TBD**) driving two fast steering mirrors, tip and tilt
           each, through a split 100-pin cable (mirror models **TBD**)
:Interface: Ethernet from the RTC to the controller (interface and IP **TBD**)
:SDK: Galil gclib and ``gcapsd`` from Galil's apt repository
:Driver: ``galilfsm`` (``github.com/COO-Utilities/galilfsm``, ``DMC30000``) and the
         two-mirror library in this folder
:Reference build: **TBD** (not built yet)
:Testing: :doc:`fsm_testing` (``fsm_build/testing.rst``)

The two FSMs steer the beam by analog voltage: each axis of each mirror is driven by one
Galil analog output. One controller drives both mirrors through a 100-pin cable split into
one leg per mirror. The ``galilfsm`` driver exposes the controller's analog outputs and
knows nothing about mirrors; the library here maps mirror axes to outputs and enforces
each mirror's limits. Follow the sections in order.

.. contents::
   :depth: 1
   :local:

----

1. Build Layers and Files
=========================

Each layer depends on the one below it::

     Mirror library   |  fsm_build library: two mirrors, axis map, limits (config TOML)
     Galil driver     |  galilfsm DMC30000 in ~/software/fsm_build/venv
     gclib            |  Galil's libgclib and gcapsd, Python gclib
     Network          |  RTC interface to the controller (TBD)
     Controller       |  Galil DMC-30000 series, analog outputs to the split cable

This folder (``fsm_build/`` in the sight repository) will be deployed to
``~hespy/software/fsm_build`` on the RTC. Planned files:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - File
     - Use
   * - ``install_gclib.sh``, ``uninstall_gclib.sh``
     - Install Galil's apt repository, gclib and ``gcapsd``; and remove them (sections 5
       and 8)
   * - ``config/fsm.toml``
     - Controller address; for each mirror the Galil output on each axis, polarity,
       center voltage and voltage limits (section 6)
   * - Mirror library (name **TBD**)
     - Two-mirror control on top of ``galilfsm`` (section 6)
   * - ``run.sh``, ``scripts/``
     - Launcher and bring-up scripts used by the tests (``testing.rst``)
   * - ``tools/check.sh``
     - Every software check, no hardware needed
   * - ``tests/``
     - Tests against a fake gclib
   * - ``pyproject.toml``
     - pytest, mypy and ruff settings
   * - ``testing.rst``
     - Test procedures: safety rules, phases, known issues

Not in the repository: ``venv/``, the driver clone and the ``logs/`` the scripts create.

.. warning::
   **TBD:** each mirror's safe input range and slew limits. Until they are known, nothing
   in this build drives an output beyond 0 V.

----

.. _section-fsm-controller:

2. Controller Hardware and Power
================================

From the DMC-30012 bring-up (``galil_dmc30012_setup.md``, DMC-30000 user manual
``man_3x01x.pdf``: power p.181, J5 pinout p.174):

* Input range 20 to 80 VDC; the controller alone draws about 5 W. A 24 V supply on its
  27 V range was used; the 36 V range limits current to 2.2 A.
* Power connector (2-pin Molex): pin 1 GND, pin 2 +VS. Set and check the voltage before
  connecting.
* Green PWR LED: powered. Red and green blinking together: supply current limit too low.
* Never plug or unplug power or signal connectors while powered.

**TBD:** the controller model and part options on the SIGHT bench, its power supply, and
where it is mounted.

----

.. _section-fsm-wiring:

3. Split Cable and Wiring
=========================

**TBD:** the 100-pin cable, which device it plugs into, and how it is split into one leg
per mirror. This section will hold:

* a wiring diagram from the controller through the split to both mirrors;
* the pinout:

  .. list-table::
     :header-rows: 1
     :widths: 15 20 25 20 20

     * - Pin
       - Signal
       - Leg / connector
       - Mirror
       - Axis
     * - TBD
       - TBD
       - TBD
       - TBD
       - TBD

* grounds and shields, and which side each is tied on;
* how the split was made and labelled;
* a continuity and isolation check with a meter, mirrors and controller off.

Known so far: the DMC-30000's analog outputs AO1 and AO2 are ±10 V, 16-bit. AO1 is the
axis A motor command line and works as a general output only after the axis is set up
(``MO A``, ``MT 1``, ``BR 0``, ``BA A``); AO2 is always a general output. **TBD:** how four
mirror axes map onto the controller's outputs.

----

.. _section-fsm-network:

4. Network
==========

The controller does not request an address, so ``gclib.ip_requests()`` returns nothing;
that is expected. The bring-up controller was at ``169.254.16.180`` (MAC
``00:50:4c:40:93:18``). Galil MACs start with ``00:50:4c``.

Planned steps (interface and addresses **TBD**):

#. Give the RTC interface a fixed address and the link-local range with ``nmcli``.
#. Find the controller (``arp-scan`` on the interface, or ``IA?`` over serial).
#. Give it a fixed address: ``IA <a>,<b>,<c>,<d>``, then ``BN`` to burn it.
#. ``ping`` it from the RTC.

----

.. _section-fsm-gclib:

5. Galil gclib
==============

``install_gclib.sh`` (planned) will add Galil's apt repository, install ``gclib`` and
``gcapsd``, and check ``libgclib.so.2`` and the ``gcapsd`` service. The Python ``gclib``
package comes from Galil's index into the build's venv (section 6). Manual steps today:

.. code-block:: bash

   wget https://www.galil.com/sw/pub/apt/all/galil-release_1_all.deb
   sudo apt install ./galil-release_1_all.deb && rm galil-release_1_all.deb
   sudo apt update && sudo apt install gclib gcapsd

**TBD:** confirm both packages on Ubuntu 26.04 and the RT kernel.

----

.. _section-fsm-library:

6. Python Driver and Mirror Library
===================================

The scripts run from their own environment in ``~/software/fsm_build/venv``. It holds:

* the ``galilfsm`` driver at a pinned commit (``DMC30000``: connect, analog outputs, read
  back the voltage actually output);
* the Python ``gclib`` package from Galil's index;
* the mirror library from this folder.

The mirror library (design **TBD**) reads ``config/fsm.toml`` and offers one object per
mirror (tip, tilt, center) sharing one controller connection. It checks every command
against that mirror's limits before it reaches the driver, and returns both mirrors to
their center on every exit.

**TBD:** whether the library lives here or in ``galilfsm``; the config format.

----

.. _section-fsm-verify:

7. Verification
===============

Run with the mirrors unpowered.

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Check
     - Expected
   * - ``ldconfig -p | grep gclib``
     - ``libgclib.so.2``
   * - ``systemctl status gcapsd``
     - active
   * - ``ping <controller>``
     - Replies (address **TBD**)
   * - ``tools/check.sh``
     - ``check.sh: all passed``
   * - Status script (**TBD**)
     - Controller model, firmware, both analog outputs at 0 V

----

.. _section-fsm-uninstall:

8. Uninstall
============

``uninstall_gclib.sh`` (planned): remove ``gclib``, ``gcapsd`` and Galil's apt
repository. The venv and this folder are removed by hand.

----

.. _section-fsm-maintenance:

9. Maintenance
==============

* **gclib updates** come from Galil's apt repository; rerun the verification after one.
* **Controller firmware** (**TBD**): version, and how it is updated.
* **Driver and library updates** happen between test rounds only (section 6); the round
  then restarts from Phase 0.
