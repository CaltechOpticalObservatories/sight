=======================
Device Build Framework
=======================

Every device on the RTC (camera, deformable mirror, fast steering mirrors, and any added
later) is built and tested the same way, from one folder at the top of this repository:
``<device>_build/``. Two documents describe it, and both are part of this build note:
``README.rst`` (how to build it) and ``testing.rst`` (how to test it). This page is the
template for both and the rules they share.

.. contents::
   :depth: 1
   :local:

----

Folder Layout
=============

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Path
     - Contents
   * - ``README.rst``
     - Build guide, included in this document as ``<device>_build``
   * - ``testing.rst``
     - Test procedures, included as ``<device>_testing``
   * - ``install_<sdk>.sh``, ``uninstall_<sdk>.sh``
     - The ``sudo`` steps: checks, install, verification, and their undo
   * - ``run.sh``
     - Launcher for every script: the build's ``venv/``, output saved to
       ``logs/<script>_<utc>.out`` with the kernel and driver version in its first line
   * - ``scripts/``
     - ``bringup.py`` (the safety layer) and one script per test step
   * - ``tests/``
     - Tests for the scripts against a fake SDK: ``conftest.py``, ``fake_sdk.py``,
       ``test_*.py``
   * - ``tools/``
     - ``check.sh`` (every software check) and build helpers
   * - ``pyproject.toml``
     - pytest, mypy and ruff settings; the folder is not a package
   * - Config TOML (planned)
     - The device's settings, read by the scripts and the install steps

The folder is deployed to ``~hespy/software/<device>_build`` on the RTC with
``rsync -a --no-group``. Vendor files, ``venv/``, driver clones and the ``logs/`` the
scripts create stay out of the repository.

----

Build Guide: ``README.rst``
===========================

Title ``<Device>: <What> Build on the SIGHT RTC``, then this field list, in this order:

.. code-block:: rst

   :Status: Built / Outline, and what is still open
   :Prerequisite: the build note sections that must be complete first
   :Hardware: the device: model, serial, what it is attached to
   :Interface: how the RTC reaches it (card, bus, network)
   :SDK: vendor software, version, how it is installed
   :Driver: the Python driver, its repository and pinned commit
   :Reference build: date, host and kernel of the build this guide records
   :Testing: :doc:`<device>_testing` (<device>_build/testing.rst)

Then a short introduction, a local table of contents, and numbered sections separated by
``----``:

#. **Build Layers and Files:** the layer diagram (each layer depends on the one below it)
   and the table of files in the folder.
#. **Device steps,** one section per layer, bottom up; each ends with a *Verify*
   subsection where a check is possible, and *Facts that matter* where the vendor
   documentation is wrong or silent.
#. **Verification:** one table of checks and expected results for the finished build.
#. **Uninstall:** what the uninstall script removes and what it leaves.
#. **Maintenance:** kernel, SDK and driver updates.

----

Test Procedures: ``testing.rst``
================================

Title ``<Device>: Testing on the SIGHT RTC``, then these sections, in this order:

#. **At a glance:** the device, its interface, power, work folder, driver, status file.
#. **Scripts and tools:** a table of scripts, then what the safety layer guarantees.
#. **Safety rules:** numbered; what can damage the device and what the software does not
   prevent.
#. **How a session runs:** the two roles and the go / no-go loop.
#. **Test phases:** a table of phases with their status, then the stop conditions.
#. **Device procedures:** sessions, power, step-by-step tests (as many sections as the
   device needs).
#. **If something goes wrong:** the fastest safe stop first.
#. **Records:** where logs and notes are kept.
#. **Known issues and watch items.**

----

Shared Rules
============

* **Safety layer.** Every script that drives hardware opens it through
  ``scripts/bringup.py``, which runs against a fake or dummy device unless given
  ``--hardware``, refuses ``--hardware`` outside ``tmux``, returns the device to a safe
  state on every exit (error, Ctrl-C, SIGTERM, SIGHUP), and refuses a command outside
  the step's limits instead of clipping it.
* **Install scripts.** ``sudo`` scripts check before they change anything (running
  through ``sudo``, kernel, sha256 of the reviewed vendor files, hardware present, no
  earlier install), print every command they run, verify the result, and have an
  uninstall counterpart. They refuse to overwrite an existing install.
* **Roles.** The remote operator (``hespy`` over SSH, no ``sudo``) writes and runs the
  scripts; the bench operator owns power, light and every ``sudo`` step and says go
  before each hardware step.
* **Phases.** Phase 0 is the software gate (``tools/check.sh`` and a rehearsal against
  the fake device), Phase 1 the audit (wiring, files, bench), then hardware phases in
  order of risk.
* **Test rounds.** No driver change in the middle of a round: log the finding, finish or
  stop the round, change the driver, restart from Phase 0.
* **Records.** Logs are copied to ``~/sight-dev/daily_log/rtc/<device>/`` on the
  workstation; status and plans live in ``~/sight-dev/plans/``.
* **Unknowns.** Anything not yet confirmed is marked **TBD** in bold.

Known deviations: ``nuvu_build`` predates this framework. It deploys to
``~hespy/nuvu_build``, its tests run on the workstation, its logs go to
``~/sight-dev/daily_log/rtc/logs/``, and it has no ``tools/check.sh`` or ``pyproject.toml``
yet.
