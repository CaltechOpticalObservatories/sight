===========================================
BMC Kilo-DM: SDK Build on the SIGHT RTC
===========================================

:Prerequisite: :doc:`software_build` through :ref:`section-mok` complete (Secure Boot
               key enrolled); kernel ``7.0.0-38-realtime`` held
:Mirror: Boston Micromachines kilo-DM ``30CW009#052``, 648 actuators on a 28 x 28 grid
:Interface: BMC PCIe card at ``c1:00.0`` (``1a8f:2000``), fiber to the driver box
:SDK: DM-SDK 4.1.3 with the team's Ubuntu 26.04 patch, built from source
:Driver: ``bmc_dm`` (``github.com/COO-Utilities/bmc_dm``), ``main`` ``9546ba0``
:Reference build: 2026-11-03 SDK build on ``hesperus``; 2026-11-25 SDK and module
                  installed by hand with the steps ``install_bmc_sdk.sh`` automates,
                  Phase 0 passed on it. Section 5 waits for BMC's files
:Testing: ``bmc_build/testing.rst`` (test procedures, phases and status)

The deformable mirror is driven through BMC's DM-SDK, which talks to a PCIe card in the
RTC; the card sends actuator values over fiber to BMC's driver box, which holds the high
voltage. The Python driver (``bmc_dm``) wraps the SDK's Python module. BMC's installer
targets Ubuntu 18.04, so the SDK is built from source here and installed by a reviewed
script. Follow the sections in order.

.. contents::
   :depth: 1
   :local:

----

1. Build Layers and Files
=========================

Each layer depends on the one below it::

     Python driver   |  bmc_dm in ~/software/bmc_build/venv
     DM-SDK          |  /opt/Boston Micromachines: libBMC 4.1.3, Python module bmc, bmc_ltest
     PCIe module     |  bmc_mdrv, signed with the host MOK, autoloaded
     Kernel          |  7.0.0-38-realtime, held

This folder (``bmc_build/`` in the sight repository) is deployed to
``~hespy/software/bmc_build`` on the RTC:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - File
     - Use
   * - ``install_bmc_sdk.sh``, ``uninstall_bmc_sdk.sh``
     - Sign the PCIe module, install the SDK and module, restrict the card to a group;
       and remove it all again (sections 4 and 6)
   * - ``install_bmc_files.sh``
     - Install BMC's profile, map and calibration files after the profile audit passes
       (section 5)
   * - ``run.sh``, ``scripts/``
     - Launcher and bring-up scripts used by the tests (``testing.rst``)
   * - ``bundle/bringup.toml``
     - Bring-up config bundle: soft maximum 0.4, no default flat (section 2)
   * - ``tools/build_sdk.sh``, ``tools/check.sh``
     - Build the SDK without sudo (section 3); run every software check
   * - ``tests/``
     - Tests for the scripts against a fake SDK and a stub ``bmc_ltest``
   * - ``pyproject.toml``
     - pytest, mypy and ruff settings for ``scripts/`` and ``tests/``
   * - ``testing.rst``
     - Test procedures: safety rules, phases, the communication test, known issues

Not in the repository: the SDK tarball and its build (``sdk/``), the driver clone
(``driver/``), ``venv/``, BMC's mirror files (``bmc_files/``), the bundle's map and
flats (copied from the driver), and the ``dummy/`` and ``logs/`` the scripts create.

.. warning::
   Nothing in this build writes an actuator value. The SDK's ``close_dm`` (the driver's
   ``disconnect()``) writes zeros to every actuator, so it belongs to the actuator
   phases; read the safety rules in ``testing.rst`` before connecting to the mirror.

----

.. _section-bmc-deploy:

2. Deploy and Python Driver
===========================

From the sight repository root on the workstation, run the tests, then copy the folder
to the RTC. ``--no-group`` keeps the workstation's group ID, which is ``nuvu-cameras``
on the RTC, off the files:

.. code-block:: bash

   cd bmc_build
   PYTHONPATH=scripts:tests python3 -m pytest -q        # needs bmc_dm in the Python used
   cd ..
   rsync -a --no-group bmc_build/ sight-rtc:software/bmc_build/

The scripts run from their own environment in ``~/software/bmc_build/venv``, so the
shared ``/opt/rtc_python`` environment (:ref:`section-python`) is not changed. The
driver is cloned at the tested commit; its tests and its Sight bundle are used here.
On the RTC:

.. code-block:: bash

   cd ~/software/bmc_build
   git clone -q https://github.com/COO-Utilities/bmc_dm.git driver
   git -C driver checkout -q --detach 9546ba00f81e5a034918a848d5d5823e2a4ad3a2
   python3 -m venv venv                                  # system Python 3.14
   venv/bin/pip install -q "./driver[zernike,dev]"
   echo "bmc_dm main 9546ba0 ($(date -u +%F))" > venv/DRIVER_VERSION
   cp driver/configs/sight/actuator_map.txt driver/configs/sight/*.npy bundle/

Installing the driver also installs numpy, poppy (Zernikes) and ``hardware_device_base``
(tag ``v1.0.1``) from GitHub. To change the driver between test rounds, check out the
new commit in ``driver/``, reinstall with ``pip install --force-reinstall --no-deps
./driver``, update ``DRIVER_VERSION`` and restart testing from Phase 0.

Verify
------

.. code-block:: bash

   cd ~/software/bmc_build && tools/check.sh             # check.sh: all passed

``check.sh`` runs the driver's tests, mypy, pylint and ruff in ``driver/``, then the
same for ``scripts/`` and ``tests/``, plus ``bash -n`` (and ``shellcheck`` when
installed) on the shell scripts. It needs no SDK and no hardware.

----

.. _section-bmc-sdk-build:

3. DM-SDK 4.1.3 Build
=====================

Use the team's patched source, ``dm-sdk-4.1.3-ubuntu26.tar.gz`` (sha256
``a8bdb9980844286ae093fe6cf77139d3c30d779dfa83aec8b67ec48bac9c5a49``). It builds with
GCC 15, Qt 5.15, OpenCV 4.10, log4cxx 1.5 and SWIG 4.4 on Ubuntu 26.04.

.. caution::
   Build from a path without spaces. The SDK's ``swig.prf`` does not quote paths, so
   in a folder like ``DM-SDK 4.1.3 Source`` the SWIG step fails and the Python module
   is never built.

Install the build packages:

.. code-block:: bash

   sudo apt install qtbase5-dev qt5-qmake liblog4cxx-dev libopencv-dev libusb-1.0-0-dev \
     swig libboost-dev libtbb12

Copy the tarball to ``~/software/bmc_build/sdk/``, then, as ``hespy``:

.. code-block:: bash

   cd ~/software/bmc_build/sdk
   sha256sum dm-sdk-4.1.3-ubuntu26.tar.gz
   tar -xzf dm-sdk-4.1.3-ubuntu26.tar.gz
   cd .. && tools/build_sdk.sh --pcie

``build_sdk.sh`` runs the SDK's ``build.sh`` (libraries, programs, Python module and,
with ``--pcie``, the ``bmc_mdrv`` kernel module and ``bmc_ltest``), logs to
``logs/build_sdk_<utc>.out`` and stages the Python module in ``sdk/python/bmc``.
``run.sh`` uses that staged module until the SDK is installed in ``/opt``.

The reference build finished with exit 0; its only warnings are unchecked ``scanf``
results in BMC's example programs and the kernel toolchain-version notes.

Facts that matter
-----------------

* **The kernel module is simple:** no interrupt handler, no DMA, no spinlocks; only
  mutexes, so it is safe on ``PREEMPT_RT``. Loading it maps the card's registers and
  writes nothing. It serves register reads and writes through ``ioctl``.
* **Opening the DM writes configuration, closing writes zeros.** ``open_dm`` reads the
  hardware revision (BMC's design ID is ``0x2000``), then writes the HVA mode (actuator
  count, fiber settings and driver type, from the profile), the actuator map and the
  orientation. ``close_dm``, and the SDK object's destructor, write 0 to every
  actuator. Neither sends a shape.
* **High voltage is the driver box's.** The PCIe interface has no software HV switch;
  the box's HV status can be read (``testing.rst``, ``card_status.py``).
* **No readback.** The SDK returns its own copy of the last command; BMC mirrors have
  no position sensing.
* **Any SDK call on a closed DM crashes Python** (segmentation fault). The driver checks
  the connection before every call.
* **Missing SDK folders fall back silently** to ``/opt/Boston Micromachines``; the
  bring-up scripts refuse a missing folder instead.
* **The dummy driver** (profile ``type=2``) accepts every command and loads no map, so
  map problems can only be found by auditing the profile.

----

.. _section-bmc-install:

4. SDK and PCIe Module Install
==============================

``install_bmc_sdk.sh`` installs the SDK built in section 3. It:

#. checks that it runs through ``sudo``, the kernel is ``7.0.0-38-realtime`` and the
   module's ``vermagic`` matches, ``/opt/Boston Micromachines`` does not exist yet, the
   BMC card (``1a8f:2000``) is present, the SDK's ``install.sh`` and the module match
   the reviewed files (sha256), and the host MOK is enrolled;
#. signs ``bmc_mdrv.ko`` with the host MOK (:ref:`section-mok`), as DKMS does for the EDT
   module, and checks the signer;
#. runs the SDK's ``install.sh --pcie``: libraries, programs, headers, the Python module,
   BMC's generic profiles and maps into ``/opt/Boston Micromachines``, an ``ld.so``
   entry, udev rules, the module into ``/lib/modules/7.0.0-38-realtime/extra`` with
   autoload, and ``modprobe``;
#. replaces BMC's udev rule, which lets every local user write the card's actuator
   registers, with group ``bmc-dm`` and mode 0660, and adds the operator to the group
   (``--keep-bmc-permissions`` skips this);
#. checks that the module is loaded and bound to the card, ``/dev/bmc_mdrv0`` exists,
   and the kernel log has no BUG, WARNING, signature or lockdown lines.

Run it with the driver box off:

.. code-block:: bash

   cd ~/software/bmc_build && sudo ./install_bmc_sdk.sh

Log in again so the ``bmc-dm`` group applies. ``run.sh`` then uses the SDK in
``/opt`` by itself; rerun Phase 0 (``testing.rst``) on it.

.. note::
   The reference install (2026-11-25) ran these steps by hand: ``kmodsign``, the SDK's
   ``install.sh --pcie`` and the ``bmc-dm`` udev rule. The script's checks were run
   against the resulting system: signer, module checksum, ``vermagic``, card and MOK.

.. caution::
   Running the SDK's ``install.sh`` again puts BMC's open udev rule back. A new kernel
   needs the module rebuilt and signed again (section 3, then this section).

----

.. _section-bmc-files:

5. BMC's Mirror Files
=====================

BMC supplies a profile for each mirror (``<serial>.dm``, text with every byte XOR-ed
with ``0x83``), the actuator map it names, and sometimes a calibration table. The SDK
has no 648-actuator map of its own. Copy BMC's files into
``~/software/bmc_build/bmc_files/`` (no sudo), then:

.. code-block:: bash

   cd ~/software/bmc_build && sudo ./install_bmc_files.sh

``install_bmc_files.sh`` runs ``audit_profile.py`` as the operator and installs nothing
unless it passes. The audit checks: a PCIe or USB type, 648 actuators, ``vlim`` at most
``maxv`` (otherwise DAC counts overflow and wrap), a known HVA type with matching fiber
and Camera Link settings (a kilo driver needs ``use_fiber=1`` and ``fiber_mode=1``), the
map and calibration files present, an 11-character serial and no unknown keys. The
script then copies the profile, map and calibration file into ``Profiles``, ``Map`` and
``Calibration`` under ``/opt/Boston Micromachines`` and never overwrites a different
file.

----

.. _section-bmc-uninstall:

6. Uninstall
============

.. code-block:: bash

   cd ~/software/bmc_build && sudo ./uninstall_bmc_sdk.sh

It refuses while any process has the card open or the SDK loaded, then unloads the
module and removes ``/opt/Boston Micromachines``, the ``ld.so`` entry, the udev rules,
the autoload entry, the installed module and the ``bmc-dm`` group. BMC's original files
stay in ``bmc_files/``.

----

.. _section-bmc-verify:

7. Verification
===============

Run with the driver box off.

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Check
     - Expected
   * - ``uname -r``
     - ``7.0.0-38-realtime``
   * - ``lspci -k -d 1a8f:2000``
     - The card, ``Kernel driver in use: bmc_mdrv``
   * - ``ls -l /dev/bmc_mdrv0``
     - ``crw-rw---- root bmc-dm``
   * - ``modinfo -F signer bmc_mdrv``
     - ``hesperus Secure Boot Module Signature key``
   * - ``cat ~/software/bmc_build/venv/DRIVER_VERSION``
     - The driver commit under test
   * - ``tools/check.sh``
     - ``check.sh: all passed``
   * - ``./run.sh sdk_probe.py``
     - ``bmc`` from ``/opt/Boston Micromachines/lib/python3``, version ``4.1.3``
   * - ``./run.sh rehearse.py`` and ``./run.sh fault_drill.py``
     - ``all passed`` (dummy driver; the card is not used)
   * - ``./run.sh card_status.py --label boxoff``
     - One board, hardware revision ``v2000_...``, no problems (``testing.rst``)
