=====================
Commissioning Records
=====================

:Prerequisite: :doc:`software_build` verified

.. contents::
   :depth: 1
   :local:

Fill these in as the open commissioning tasks are completed. Each table is
linked from the pending task it closes; record the date and operator for every
entry.

----

.. _section-rec-latency:

1. Latency Measurements
=======================

Closes RT-1 and RT-2. Requirement: timing jitter within 1% of the loop period.
Run in this order, using the commands in :ref:`section-verify`.

.. list-table::
   :header-rows: 1
   :widths: 22 12 18 12 12 12 12

   * - Run
     - Date
     - Shielded CPUs
     - Duration
     - Max (us)
     - Avg (us)
     - Pass
   * - Idle, unshielded
     -
     - none
     -
     -
     -
     -
   * - Idle, shielded
     -
     -
     -
     -
     -
     -
   * - Loaded, shielded
     -
     -
     -
     -
     -
     -
   * - With RTC running
     -
     -
     -
     -
     -
     -

----

.. _section-rec-firmware:

2. Firmware RT Settings
=======================

Closes RT-3. Change one setting at a time and re-run the loaded, shielded
measurement after each.

.. list-table::
   :header-rows: 1
   :widths: 30 14 18 18 20

   * - Change
     - Date
     - Max before (us)
     - Max after (us)
     - Kept
   * - SMT off
     -
     -
     -
     -
   * - C-states below C1 off
     -
     -
     -
     -
   * - Core Performance Boost off
     -
     -
     -
     -
   * - Governor ``performance``
     -
     -
     -
     -

----

.. _section-rec-services:

3. Service Stripping
====================

Closes RT-5. Apply the loop in :ref:`section-services`, then record the audit.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Item
     - Value
   * - Date
     -
   * - Units disabled
     -
   * - Units deliberately kept
     -
   * - Running service count after
     -

----

.. _section-rec-storage:

4. Data Volume
==============

Closes RT-7. A dedicated ``/data`` logical volume carved from ``ubuntu-vg``.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Item
     - Value
   * - Date
     -
   * - Logical volume
     -
   * - Size
     -
   * - Filesystem
     -
   * - Mount options
     -
   * - Contents migrated from root volume
     -

----

.. _section-rec-mok:

5. Stale MOK Key Removal
========================

Follows SW-3. Remove the stale NVIDIA installer key with ``mokutil --delete``;
completing it needs a display on the GPU, as in :ref:`section-mok`.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Item
     - Value
   * - Date
     -
   * - Key removed (serial or subject)
     -
   * - Keys enrolled after removal
     -
   * - ``nvidia-smi`` after reboot
     -

----

.. _section-rec-cold-start:

6. Cold-start Test at Palomar
=============================

Closes PB-5. Start from a cold soak and log until temperatures settle.

.. list-table::
   :header-rows: 1
   :widths: 14 14 16 16 40

   * - Date
     - Ambient (C)
     - GPU at power-on (C)
     - Time to steady state
     - Behaviour and notes
   * -
     -
     -
     -
     -
   * -
     -
     -
     -
     -
