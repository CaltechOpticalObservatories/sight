==============================
Physical Build: Hardware Setup
==============================

:Next: :doc:`rt_build`

.. contents::
   :depth: 1
   :local:

----

1. Overview
===========

The SIGHT RTC is a GPU compute server built on an ASUS Pro WS TRX50-SAGE WIFI
workstation board, carrying an NVIDIA GeForce RTX 5090 and an EDT VisionLink F1
Camera Link framegrabber. None of the hardware
is modified; "build" here means installing standard components into the base
chassis and confirming the machine posts cleanly. Slot assignment and cooling
are settled at this stage because they are disruptive to change once the
software stack is built. Values below were read from the machine with
``dmidecode``, ``lspci`` and ``nvidia-smi``; the remaining open items are
listed in :ref:`section-pb-pending`.

.. warning::
   Wear a grounded ESD wrist strap, or ground yourself against the chassis
   before handling any component. GPUs, framegrabbers and memory are all
   damaged by static discharge, and the damage is frequently latent rather than
   immediate.

.. warning::
   Disconnect mains power and confirm the PSU switch is off before opening the
   chassis. Standby rails remain energized on many server boards even when the
   system appears off.

----

.. _section-pb-bom:

2. Bill of Materials
====================

.. list-table::
   :header-rows: 1
   :widths: 22 43 35

   * - Component
     - Part
     - Purpose
   * - GPU
     - 1 x NVIDIA GeForce RTX 5090, Blackwell, 32 GB (second card planned)
     - Control-loop computation. See :ref:`section-pb-pending`
   * - Framegrabber
     - EDT VisionLink F1, Camera Link, PCIe x1 Gen2
     - Frame input from the Nuvu camera
   * - Motherboard
     - ASUS Pro WS TRX50-SAGE WIFI, rev 1.xx
     - Chassis mainboard
   * - CPU
     - AMD Ryzen Threadripper 9970X, 32 cores / 64 threads, single NUMA node
     - Housekeeping, build and control loop
   * - Memory
     - 4 x 48 GB DDR5-6400, SK Hynix ``HMCGY4MHBRB490N`` (192 GB)
     - Must accommodate the ``/milk/shm`` tmpfs
   * - Storage
     - KIOXIA CD8-R ``KCD8XRUG3T84``, 3.84 TB NVMe
     - OS and ``/data``
   * - PSU
     - [TBD]
     - Must supply a 575 W GPU plus system load, with headroom for a second

.. caution::
   An RTX 5090 can draw 575 W under load, and a second card is planned
   (:ref:`section-pb-pending`). Confirm PSU capacity and the number of
   available PCIe power connectors before assembly rather than after.

----

.. _section-pb-assembly:

3. Assembly
===========

Work on an ESD-safe bench with the unit unplugged.

Mainboard and Memory
--------------------

#. Unpack and inventory all components against :ref:`section-pb-bom`. Record
   serial numbers in :ref:`section-pb-inventory`.
#. Install the CPU, cooler and memory on the motherboard per the board manual.
#. Mount the motherboard in the chassis and connect front-panel, power and fan
   headers.

PCIe Cards
----------

#. Install the RTX 5090 in a primary x16 slot. Record the slot assignment in
   :ref:`section-pb-inventory`.
#. Install the EDT VisionLink F1 framegrabber.
#. Connect PCIe power to the GPU, using separate cable runs where the PSU
   provides them.

.. note::
   The VisionLink F1 is a PCIe x1 Gen2 card: ``lspci`` reports a maximum link
   of x1 at 5.0 GT/s, so the x1 link ``pciload`` reports is its design, not a
   slot fault.

Cabling
-------

#. Connect storage and network cabling. Record the cable map in
   :ref:`section-pb-inventory`.
#. Connect the BMC or management port if the platform provides one.
#. Attach a monitor to the **motherboard** video output, not to a GPU.
#. Close the chassis and connect mains power.

.. tip::
   Cable the management interface first. Several steps in :doc:`software_build`
   require a reboot with no display attached to the GPUs, and out-of-band
   access makes those steps far less tedious.

.. caution::
   Do not connect a display to either GPU during OS install or driver
   installation. NVIDIA cards initialize differently with a display attached,
   which interferes with driver installation on a headless compute node. A
   display is reconnected to a GPU later, for MOK enrollment only
   (:ref:`section-mok`).

----

4. First Power-On
=================

Before moving on to :doc:`rt_build`, power on, enter firmware setup and
confirm:

* All installed memory is detected and matches :ref:`section-pb-bom`.
* The GPU is detected.
* The framegrabber is present.
* All fans are spinning and thermals at idle are within vendor limits.

.. note::
   The reference deployment site is Palomar, where ambient temperatures can be
   low at startup. ``nvidia-smi`` reports *T.Limit* as headroom below the
   GPU's slowdown point: 61 C of headroom at a 29 C idle, with slowdown at
   T.Limit -2 C and shutdown at T.Limit -5 C. Cold-start behaviour should be
   characterized before winter operation; record the test in
   :ref:`section-rec-cold-start`.

After the OS is installed (:doc:`rt_build`), confirm from Linux:

.. code-block:: bash

   free -h                            # installed memory
   lscpu | grep -E '^Core|^Socket|^Thread'
   lspci | grep -i vga                # RTX 5090
   lspci | grep -i edt                # framegrabber
   lsblk

----

.. _section-pb-inventory:

5. Hardware Inventory
=====================

Values later pages depend on. Update on every rebuild.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Item
     - Value
   * - Hostname
     - ``hesperus``
   * - Motherboard
     - ASUS Pro WS TRX50-SAGE WIFI, rev 1.xx
   * - Firmware
     - American Megatrends 1317 (2026-02-03)
   * - CPU
     - AMD Ryzen Threadripper 9970X, 32 cores / 64 threads
   * - Memory
     - 4 x 48 GB DDR5-6400 SK Hynix ``HMCGY4MHBRB490N`` (183 GiB usable)
   * - Storage
     - KIOXIA ``KCD8XRUG3T84``, 3.84 TB NVMe
   * - GPU
     - 1 x NVIDIA GeForce RTX 5090, 32607 MiB, Blackwell architecture
   * - GPU bus ID
     - ``0000:21:00.0``, link x16 PCIe Gen5 (32 GT/s max)
   * - GPU power cap
     - 575 W, T.Limit headroom 61 C at idle
   * - Framegrabber
     - EDT VisionLink F1
   * - Framegrabber s/n
     - ``VLF101431``
   * - Framegrabber p/n
     - ``019-14836-30``, rev 30
   * - Framegrabber FPGA
     - ``5CGTFD5C5``, clock 100 MHz, opt F1/FH/SDR
   * - Framegrabber bus ID
     - ``0000:81:00.0``
   * - Framegrabber link
     - PCIe x1, 5.0 GT/s (card maximum)
   * - PCIe slot map
     - [TBD] (firmware does not report physical slot labels)
   * - NUMA topology
     - Single node: all CPUs, the GPU and the framegrabber on node 0

----

6. Troubleshooting
==================

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Symptom
     - Resolution
   * - System does not post
     - Reseat memory and the GPU one at a time. Confirm PCIe power is connected
       to the GPU.
   * - A GPU is missing from ``lspci``
     - Reseat the card and confirm the slot is an x16 electrical slot. Check
       *Above 4G decoding* is enabled (:ref:`section-bios`).
   * - Framegrabber absent from ``lspci``
     - Reseat the card. If still absent, try a different slot before suspecting
       the card.
   * - Framegrabber negotiates a narrow PCIe link
     - x1 at 5.0 GT/s is the card's maximum. Anything narrower or slower points
       at the slot: compare ``LnkCap`` and ``LnkSta`` in ``lspci -vvv``.
   * - GPU link reports 2.5 GT/s
     - Expected at idle: the link drops to Gen1 to save power and trains up
       under load. Check ``LnkSta`` while a CUDA sample runs.
   * - GPU thermal throttling at idle
     - Check fan operation and airflow obstruction before suspecting the cards.

----

.. _section-pb-pending:

7. Pending Tasks
================

* [ ] **PB-1: Bill of materials.** Motherboard, CPU, RAM and storage recorded
  2026-10-15. PSU model and wattage still need reading off the label.
* [ ] **PB-2: Cable map and slot assignments.** NUMA topology recorded
  (single node). Match bus IDs ``21:00.0`` and ``81:00.0`` to the board's slot
  labels and record the cable map.
* [x] **PB-3: GPU count.** Resolved 2026-10-15: one RTX 5090 is installed for
  preliminary testing. A second is planned but waits on chassis space; revisit
  PSU capacity and slot assignment when it is fitted.
* [x] **PB-4: Framegrabber link width.** Resolved 2026-10-15: x1 at 5.0 GT/s
  is the card's maximum link capability.
* [ ] **PB-5: Environmental limits.** Characterize cold-start GPU behaviour at
  Palomar before winter operation (:ref:`section-rec-cold-start`).
* [x] **PB-6: Framegrabber provenance.** The card was transferred from a
  discontinued machine. Checked 2026-10-15: FPGA ``5cgtfd5c5`` rev 30 on a
  Micron ``N25Q064A13ESE40G`` FPROM, and every file in
  ``/opt/EDTpdv/camera_config`` ships with ``edtpdv`` 6.2.1. No site config
  was carried over: the framegrabber will capture from the Nuvu camera, whose
  config is still to be written (SW-8).
