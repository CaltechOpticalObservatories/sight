=========================================
Nuvu HNü 128: SDK Build on the SIGHT RTC
=========================================

:Prerequisite: :doc:`software_build` through :ref:`section-edt` complete and verified
:Camera: Nuvu HNü 128, SN06283454, CCD60 128x128 EMCCD, on EDT unit 0, Camera Link
         channel 0
:SDK: Nuvu SDK 4.12.0, Ubuntu 22.04 build (``NuPixel``), installed by hand
:Reference build: 2026-11-03, ``hesperus``, kernel ``7.0.0-38-realtime``
:Testing: ``nuvu_build/testing.rst`` (test procedures, phases and status)

The Nuvu HNü 128 is read out through the EDT VisionLink F1 that
:ref:`section-edt` installs. Nuvu's SDK (``libnuvu``) drives it through an EDT
plugin, and the Python driver (the ``nuvu`` package) wraps the SDK. Nuvu's
installer supports only Ubuntu 20.04 and 22.04, and its EDT step would replace
the patched EDT driver, so every step here is done by hand. Follow the sections
in order.

.. contents::
   :depth: 1
   :local:

----

1. Build Layers and Files
=========================

Each layer depends on the one below it::

     Python driver   |  nuvu package in ~/nuvu_build/venv (imports libnuvu before numpy)
     Nuvu SDK        |  /opt/NuvuCameras: libnuvu 4.12.0, EDT plugin nc_grab_edt 3.2.0
     EDT driver      |  EDT PDV 6.2.1, kernel module patched for PREEMPT_RT
     Kernel          |  7.0.0-38-realtime, held

This folder (``nuvu_build/`` in the sight repository) is deployed to
``~hespy/nuvu_build`` on the RTC:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - File
     - Use
   * - ``edt_pci_pdv-6.2.1-preempt-rt.patch``
     - EDT kernel module patch for the real-time kernel (section 2)
   * - ``install_nuvu_sdk.sh``, ``uninstall_nuvu_sdk.sh``
     - Install the SDK into ``/opt/NuvuCameras``, and remove it again (section 3)
   * - ``run.sh``, ``scripts/``
     - Launcher and bring-up scripts used by the tests (``testing.rst``)
   * - ``tools/``
     - EDT-level test programs: C sources and the stress script (section 5)
   * - ``tests/``
     - Rehearsal tests for the scripts against a fake SDK, run on the workstation
   * - ``testing.rst``
     - Test procedures: safety rules, sessions, phases, known issues
   * - ``NuPixel.rst``
     - Running Nuvu's NuPixel GUI over ``ssh -X``

Not in the repository: the SDK tarball (vendor file), ``venv/``, the compiled
tools, and the ``logs/`` and ``frames/`` the scripts create.

.. warning::
   Light combined with EM gain can permanently damage the detector, and the
   warranty does not cover it. Nothing in this build powers the camera; read
   the safety rules in ``testing.rst`` before the first power-on.

----

.. _section-nuvu-edt-patch:

2. EDT Driver Patch for PREEMPT_RT
==================================

EDT PDV 6.2.1's kernel module calls ``preempt_disable()`` and then takes a
``spinlock_t``, which is a sleeping lock on a ``PREEMPT_RT`` kernel. The result
is ``BUG: scheduling while atomic`` whenever the lock is contended, then host
lockups; Nuvu's SDK triggers it on its first camera scan. The patch skips the
redundant ``preempt_disable``/``preempt_enable`` pair on ``PREEMPT_RT`` only. It
is applied to the DKMS source, so later kernels build with it.

.. warning::
   Without this patch the host can lock up hard under Camera Link use. Apply it
   before installing the SDK.

Run with the camera off and nothing using the board:

.. code-block:: bash

   fuser -v /dev/pdv0_*                                  # must print nothing

   # Keep a pristine copy of the DKMS source (once)
   sudo tar -C /usr/src -czf /root/edt_pci_pdv-6.2.1-orig.tar.gz edt_pci_pdv-6.2.1

   cd ~/nuvu_build
   sudo patch -d /usr/src/edt_pci_pdv-6.2.1 -p1 --dry-run < edt_pci_pdv-6.2.1-preempt-rt.patch
   sudo patch -d /usr/src/edt_pci_pdv-6.2.1 -p1 < edt_pci_pdv-6.2.1-preempt-rt.patch

   # Rebuild for every kernel that has the module (DKMS signs it with the MOK key)
   for k in $(dkms status edt_pci_pdv/6.2.1 | awk -F', ' '{print $2}'); do
       sudo dkms build edt_pci_pdv/6.2.1 -k "$k" --force &&
           sudo dkms install edt_pci_pdv/6.2.1 -k "$k" --force
   done

   sudo modprobe -r edt_pci_pdv && sudo modprobe edt_pci_pdv

Verify
------

.. code-block:: bash

   cat /sys/module/edt_pci_pdv/srcversion                # 38A1C0CA3BF007F52131B1A
   modinfo -F signer edt_pci_pdv                         # the MOK signing key
   ls -l /dev/pdv0_*                                     # three devices
   journalctl -k -n 20 --no-pager | grep -i edt          # no BUG or WARNING

The original module reports srcversion ``EFC020F5DC5329B8E5F7606``.

.. caution::
   Reinstalling or upgrading EDT PDV replaces ``/usr/src/edt_pci_pdv-6.2.1``
   and drops the patch. Reapply it, or check that the new release fixes the
   issue.

.. note::
   With any channel open the driver logs ``DevInt at channel 2`` hundreds of
   times per second. It is log noise, not an error. EDT's ``libpdv`` 6.2.1 also
   has an ``edt_set_event_func`` bug (callbacks never fire, close hangs); the
   Nuvu 4.12.0 plugin does not use that call.

Rollback
--------

.. code-block:: bash

   sudo rm -rf /usr/src/edt_pci_pdv-6.2.1
   sudo tar -C /usr/src -xzf /root/edt_pci_pdv-6.2.1-orig.tar.gz
   # then the dkms loop and the modprobe above; srcversion returns to EFC020F5DC5329B8E5F7606

----

.. _section-nuvu-sdk:

3. Nuvu SDK 4.12.0
==================

Use the Ubuntu 22.04 build, ``NuvuSW_NuPixel_4.12.0_ubuntu-22.04_x86_64.tar.gz``
(from Nuvu; sha256 ``aa00dbc1b40e6f99552064fcd1bce946d80a340a8baa4be40cc8ead5c9a8ccaf``).
Its EDT plugin, ``nc_grab_edt.so`` 3.2.0, is built for EDT PDV 6.2.1. SDK
4.2.1 ships a plugin built for EDT 5.5 that cannot load against 6.2.1.

.. caution::
   Do not run Nuvu's ``installNuvuCameras.sh`` or ``nc-install-edt.bash``. The
   first stops at an unsupported-OS prompt on Ubuntu 26.04; the second
   reinstalls EDT with the unpatched driver, which locks up this kernel.

``install_nuvu_sdk.sh`` does the installer's steps by hand:

#. checks the sha256 of ``libnuvu``, the EDT plugin, its ``nc_16cl.cfg`` and
   ``/opt/EDTpdv/libpdv.so.6.2.1`` against the reviewed files, that
   ``edt_pci_pdv`` is loaded and that ``libpdv.so.6`` is in the ``ld.so`` cache;
#. creates the ``nuvu-cameras`` group and adds the operator;
#. copies ``NuvuCameras`` to ``/opt/NuvuCameras`` and the EDT plugin into its
   ``Plugins/``, owned ``root:nuvu-cameras``;
#. writes ``/etc/ld.so.conf.d/nuvu.conf`` and runs ``ldconfig``.

It refuses to overwrite an existing install.

Install
-------

.. code-block:: bash

   mkdir -p /data/soft/nuvu && cd /data/soft/nuvu
   # copy the tarball here, then check it
   sha256sum NuvuSW_NuPixel_4.12.0_ubuntu-22.04_x86_64.tar.gz
   tar -xzf NuvuSW_NuPixel_4.12.0_ubuntu-22.04_x86_64.tar.gz --no-same-owner

   sudo ~/nuvu_build/install_nuvu_sdk.sh \
       --installer /data/soft/nuvu/NuvuSW_NuPixel_4.12.0_ubuntu-22.04_x86_64/NuvuInstaller

Log in again so the ``nuvu-cameras`` group applies.

.. note::
   The reference build extracted the tarball in ``~/nuvu_build``, which is the
   script's default when ``--installer`` is not given. Either location works.

.. note::
   The SDK manual, changelog and C examples are in ``/opt/NuvuCameras``
   (``CameraExamples/``) and in the tarball (``Documentation/``).

Facts that matter
-----------------

* The EDT plugin takes ``libnuvu``'s own symbols from the global scope, so
  ``libnuvu`` must be loaded ``RTLD_GLOBAL``. Without it the plugin is skipped
  and no camera is found.
* ``libnuvu`` links its own ``libstdc++`` statically. If a system ``libstdc++``
  (numpy loads one) is in the process first, ``libnuvu`` can no longer format or
  parse numbers: SDK log headers lose their numbers and every camera reply
  fails its checksum (``NC_ERROR_COM_CSUM_SENT``). Load ``libnuvu`` first. The
  Python driver does both.
* The SDK opens the camera with no readout mode selected, and some camera
  queries then crash the process. Select a readout mode right after opening;
  the Python driver's ``connect()`` selects mode 1, as Nuvu's examples do.
* Every ``ncCamOpen`` sets the target temperature to the camera's default,
  -60 °C. The camera also cools from power-on.
* ``nc_16cl.cfg`` turns on framesync (``fv_once``); the VisionLink F1 supports
  it.
* With the camera off, a full scan returns "no camera" after about 10 s;
  channel 1 is an unused input whose serial line floats.

----

.. _section-nuvu-python:

4. Python Driver
================

The bring-up scripts run from their own environment in ``~/nuvu_build/venv``,
so the shared ``/opt/rtc_python`` environment (:ref:`section-python`) is not
changed. The driver comes from the nuvu repository
(``github.com/COO-Utilities/nuvu``); installing it also installs numpy and
``hardware_device_base`` (tag ``v1.0.1``) from GitHub.

On the workstation, ship a commit of the driver to the RTC:

.. code-block:: bash

   cd nuvu                                               # the nuvu repository
   git archive <commit> python | ssh sight-rtc 'mkdir -p /tmp/nuvu_src && tar -x -C /tmp/nuvu_src'

On the RTC:

.. code-block:: bash

   cd ~/nuvu_build
   python3 -m venv venv                                  # system Python 3.14
   venv/bin/pip install /tmp/nuvu_src/python
   echo "<branch> <commit> (<date>)" > venv/DRIVER_VERSION
   rm -rf /tmp/nuvu_src

To update the driver later, use the same commands with
``pip install --force-reinstall --no-deps``.

.. caution::
   In any program that uses the driver, import ``nuvu`` before numpy or anything
   else that loads ``libstdc++``. The driver refuses to load ``libnuvu`` late
   rather than fail silently.

Verify
------

.. code-block:: bash

   cat ~/nuvu_build/venv/DRIVER_VERSION
   ~/nuvu_build/venv/bin/python -c "
   import nuvu, numpy
   print(any('libnuvu.so' in line for line in open('/proc/self/maps')))"   # True

----

.. _section-nuvu-tools:

5. Deploy and Build the Tools
=============================

From the sight repository root on the workstation, with the nuvu repository
checked out next to it, run the rehearsal tests, then copy the folder to the
RTC. The exclusions keep the RTC-only items and the tests:

.. code-block:: bash

   cd nuvu_build
   PYTHONPATH=../../nuvu/python python3 -m pytest -q tests
   cd ..
   rsync -a --exclude tests/ --exclude venv/ --exclude logs/ --exclude frames/ \
       --exclude 'NuvuSW_*.tar.gz' nuvu_build/ sight-rtc:nuvu_build/

Build the tools on the RTC:

.. code-block:: bash

   cd ~/nuvu_build/tools
   gcc -O2 -Wall -I/opt/EDTpdv -o serial_noise serial_noise.c -L/opt/EDTpdv -lpdv -lpthread -ldl -lm
   gcc -O2 -Wall -I/opt/EDTpdv -o edt_event_fix edt_event_fix.c -L/opt/EDTpdv -lpdv -lpthread -ldl -lm
   E=/opt/NuvuCameras/CameraExamples
   gcc -O2 -Wall -I/opt/NuvuCameras/include -I"$E/Utility" -o cameras_enumeration \
       "$E/Cameras Enumeration/Cameras Enumeration.c" "$E/Utility/utility.c" \
       -L/opt/NuvuCameras/lib -lnuvu -lm

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Tool
     - Use
   * - ``serial_noise CHANNEL SECONDS``
     - Counts the bytes a Camera Link serial line delivers; a floating line
       shows noise
   * - ``cameras_enumeration``
     - Nuvu's "Cameras Enumeration" example: lists cameras, opens and closes
       the first one. Sends no setters
   * - ``stress_events.sh [ITERATIONS]``
     - Stresses the EDT driver on all three channels and checks the kernel log
       for BUG or WARNING; uses ``edt_event_fix``

----

6. NuPixel (optional)
=====================

Nuvu's GUI, ``/opt/NuvuCameras/bin/nuPixel_legacy``, needs X client libraries
that a headless install lacks:

.. code-block:: bash

   sudo apt install libfontconfig1 libxkbcommon-x11-0 libx11-xcb1 libxcb-cursor0 \
     libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render0 \
     libxcb-render-util0 libxcb-shape0 libxcb-shm0 libxcb-sync1 libxcb-xfixes0 libxcb-xkb1

Running it over ``ssh -X``, and its safety rules, are in ``NuPixel.rst``.

----

.. _section-nuvu-verify:

7. Verification
===============

Run with the camera off.

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Check
     - Expected
   * - ``uname -r``
     - ``7.0.0-38-realtime``
   * - ``cat /sys/module/edt_pci_pdv/srcversion``
     - ``38A1C0CA3BF007F52131B1A`` (patched)
   * - ``ldconfig -p | grep -E 'libnuvu|libpdv.so.6'``
     - both listed
   * - ``getent group nuvu-cameras``
     - includes ``hespy``
   * - ``sha256sum /opt/NuvuCameras/lib/libnuvu.so.4.12.0``
     - ``a8d24dc5...6242b8`` (as pinned in ``install_nuvu_sdk.sh``)
   * - ``~/nuvu_build/tools/serial_noise 0 5``, then channels 1 and 2
     - channels 0 and 2 silent; channel 1 noise
   * - ``~/nuvu_build/tools/cameras_enumeration``
     - "Found 0 camera(s)" in about 10 s, no hang
   * - ``./run.sh status.py --unit 0 --channel 0``
     - "no camera found", exit 1, no traceback
   * - ``head -2`` of the newest ``~/.nuvu/Logs/nc_driver/ncLogFile_*``
     - ``NUVU CAMERAS SDK 4.12.0 LOG`` and ``--- EPISODE 1 ---`` (missing
       numbers mean ``libnuvu`` was loaded after ``libstdc++``)
   * - ``journalctl -k -b | grep -E 'BUG|WARNING'``
     - nothing

The first powered steps are Phases 2 to 4 in ``testing.rst``.

----

8. Uninstall
============

.. code-block:: bash

   sudo ~/nuvu_build/uninstall_nuvu_sdk.sh    # refuses while a process has the SDK loaded
   rm -rf ~/nuvu_build/venv

This removes ``/opt/NuvuCameras``, ``/etc/ld.so.conf.d/nuvu.conf`` and the
``nuvu-cameras`` group. The EDT patch stays; roll it back as in
:ref:`section-nuvu-edt-patch`.

----

9. Maintenance
==============

* **Kernel updates.** Keep the real-time kernel held during camera testing.
  Before any reboot after a kernel or driver update, check that ``dkms status``
  shows both nvidia and ``edt_pci_pdv`` installed for the new kernel and that
  ``/boot/initrd.img-<version>`` exists, then rerun section 7.
* **EDT updates** drop the patch (section 2).
* **SDK updates.** A new SDK needs new pinned hashes in ``install_nuvu_sdk.sh``
  and a full rerun of the camera-off checks and the test phases.
* **Driver updates** happen between test rounds only (section 4); the round then
  restarts from Phase 0.
