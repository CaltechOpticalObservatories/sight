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

The SIGHT RTC is a GPU compute server carrying two NVIDIA GeForce RTX 5090
cards and an EDT VisionLink F1 Camera Link framegrabber. None of the hardware
is modified; "build" here means installing standard components into the base
chassis and confirming the machine posts cleanly. Slot assignment and cooling
are settled at this stage because they are disruptive to change once the
software stack is built. Hardware detail in the source notes is thin, so
several values below are open (:ref:`section-pb-pending`).

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
     - 2 x NVIDIA GeForce RTX 5090, Blackwell, 32 GB
     - Control-loop computation. See :ref:`section-pb-pending`
   * - Framegrabber
     - EDT VisionLink F1, Camera Link, PCIe
     - Camera frame input
   * - Motherboard
     - [TBD] ASUS-based (``asus_wmi`` present in the reference build)
     - Chassis mainboard
   * - CPU
     - [TBD], 64 build threads available
     - Housekeeping and build
   * - Memory
     - [TBD]
     - Must accommodate the ``/milk/shm`` tmpfs
   * - Storage
     - [TBD]
     - OS and ``/data``
   * - PSU
     - [TBD]
     - Must supply two 575 W GPUs plus system load
   * - Chassis
     - [TBD]
     - Enclosure and cooling

.. caution::
   Two RTX 5090 cards can draw 575 W each under load. Confirm PSU capacity and
   the number of available PCIe power connectors before assembly rather than
   after.

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

#. Install the two RTX 5090 cards in the primary x16 slots. Record slot
   assignments and their NUMA node association in :ref:`section-pb-inventory`.
#. Install the EDT VisionLink F1 framegrabber.
#. Connect PCIe power to both GPUs, using separate cable runs where the PSU
   provides them.

.. note::
   In the reference build ``pciload`` reported the framegrabber negotiating a
   PCIe link width of x1 at 5.0 Gbps. Confirm whether this is expected for this
   card and slot before accepting it (:ref:`section-pb-pending`).

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
* Both GPUs are detected.
* The framegrabber is present.
* All fans are spinning and thermals at idle are within vendor limits.

.. note::
   The reference deployment site is Palomar, where ambient temperatures can be
   low at startup. Captured ``nvidia-smi`` output showed a GPU at 28 C against
   a temperature limit of 62 C. Cold-start behaviour should be characterized
   before winter operation (:ref:`section-pb-pending`).

After the OS is installed (:doc:`rt_build`), confirm from Linux:

.. code-block:: bash

   free -h                            # installed memory
   lscpu | grep -E '^Core|^Socket|^Thread'
   lspci | grep -i vga                # both RTX 5090 cards
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
   * - Base system
     - [TBD] ASUS-based motherboard
   * - CPU
     - [TBD], 64 build threads
   * - Memory
     - [TBD]
   * - Storage
     - [TBD]
   * - GPU
     - NVIDIA GeForce RTX 5090, 32607 MiB, Blackwell architecture
   * - GPU bus ID
     - ``00000000:21:00.0``
   * - GPU power cap
     - 575 W, temperature limit 62 C
   * - Framegrabber
     - EDT VisionLink F1
   * - Framegrabber s/n
     - ``VLF101431``
   * - Framegrabber p/n
     - ``019-14836-30``, rev 30
   * - Framegrabber FPGA
     - ``5CGTFD5C5``, clock 100 MHz, opt F1/FH/SDR
   * - Framegrabber link
     - PCIe x1, 5.0 Gbps
   * - PCIe slot map
     - [TBD]
   * - NUMA topology
     - [TBD]

----

6. Troubleshooting
==================

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Symptom
     - Resolution
   * - System does not post
     - Reseat memory and GPUs one at a time. Confirm PCIe power is connected to
       both cards.
   * - A GPU is missing from ``lspci``
     - Reseat the card and confirm the slot is an x16 electrical slot. Check
       *Above 4G decoding* is enabled (:ref:`section-bios`).
   * - Framegrabber absent from ``lspci``
     - Reseat the card. If still absent, try a different slot before suspecting
       the card.
   * - Framegrabber negotiates a narrow PCIe link
     - Confirm the slot's electrical width. The reference build reports x1; this
       is unresolved (:ref:`section-pb-pending`).
   * - GPU thermal throttling at idle
     - Check fan operation and airflow obstruction before suspecting the cards.

----

.. _section-pb-pending:

7. Pending Tasks
================

* [ ] **PB-1: Bill of materials.** Chassis, motherboard, CPU, RAM, storage and
  PSU are undocumented.
* [ ] **PB-2: Cable map and slot assignments.** Record PCIe slot numbers and
  NUMA topology.
* [ ] **PB-3: GPU count.** The source notes state two RTX 5090 cards, but all
  captured ``nvidia-smi`` output shows a single attached GPU. Confirm.
* [ ] **PB-4: Framegrabber link width.** Confirm whether PCIe x1 at 5.0 Gbps is
  expected for this card and slot.
* [ ] **PB-5: Environmental limits.** Characterize cold-start GPU behaviour at
  Palomar before winter operation.
* [ ] **PB-6: Framegrabber provenance.** The card was transferred from a
  discontinued machine. Confirm firmware revision and any site-specific camera
  configuration files carried over with it.
