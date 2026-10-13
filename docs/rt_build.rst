====================================
RT Build: Firmware, OS and RT Kernel
====================================

:Prerequisite: :doc:`physical_build` complete
:Next: :doc:`software_build`

.. contents::
   :depth: 1
   :local:

----

1. Scope
========

The OS is **Real-time Ubuntu 26.04 LTS**: Ubuntu with Canonical's
``PREEMPT_RT`` kernel (:ref:`section-rt-kernel`). ``PREEMPT_RT`` makes the
kernel fully preemptible, converts spinlocks to sleeping rt-mutexes with
priority inheritance, and runs IRQ handlers as schedulable threads. This page
takes the machine from bare hardware to a tuned RT platform with the directory
layout the software stack depends on.

Design rules for this page:

#. **The RT kernel is the foundation, not an optimization.** Every tuning step
   assumes ``PREEMPT_RT`` is running.
#. **No desktop environment.** Ubuntu **Server**, no GNOME, no display manager.
   The machine is operated over SSH.
#. **Secure Boot stays enabled.** This commits the build to signing and
   enrolling kernel modules in :doc:`software_build`.

----

2. Installation Media
=====================

All drives are erased before starting; this is a full rebuild.

* **OS:** Ubuntu **Server** 26.04 LTS (``.iso``, not Desktop)
* **Source:** official Ubuntu download
* **Format:** bootable USB (``dd`` / Rufus / balenaEtcher), 8 GB or larger

.. caution::
   Confirm the edition is Server, not Desktop. This is easy to get wrong at
   download time and expensive to discover later.

Also have on hand:

* A second machine for downloading installers and for SSH access.
* Monitor, keyboard, and a video cable that reaches both the motherboard video
  output and a GPU output. Both are needed, at different stages.
* Network access with sufficient bandwidth for multi-gigabyte downloads.

----

.. _section-bios:

3. Firmware: BIOS and Secure Boot
=================================

Do this before installing the OS. Starting from optimized defaults removes any
configuration inherited from prior use or factory testing, which matters
because firmware settings materially affect real-time determinism. Secure Boot
is left enabled, which is the decision that drives the module-signing work in
:doc:`software_build`. Real-time firmware tuning is deferred to
:ref:`section-shielding`, where it can be measured.

.. caution::
   Loading optimized defaults discards any existing firmware configuration,
   including boot order and storage controller mode. Record anything you need
   to preserve before proceeding.

BIOS Settings
-------------

#. Power on and enter firmware setup.
#. **Save & Exit ‣ Load Optimized Defaults: Yes**, then **Save & Exit**.
#. Re-enter setup and confirm the settings below.
#. Set the USB drive as the first boot device, then **Save & Exit**.
#. Record the firmware version and every non-default setting in
   :ref:`section-verify`.

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Setting
     - Value
     - Rationale
   * - Boot mode
     - UEFI
     - Required for Secure Boot and MOK enrollment
   * - Secure Boot
     - Enabled
     - See the note below
   * - Above 4G decoding
     - Enabled
     - Required for multiple large-BAR GPUs
   * - Hyper-Threading / SMT
     - [TBD]
     - Commonly disabled on RT systems for determinism
   * - C-states
     - [TBD]
     - Deep C-states add wake latency
   * - Turbo / SpeedStep
     - [TBD]
     - Frequency transitions add jitter
   * - Virtualization / IOMMU
     - [TBD]
     - Affects device isolation and latency
   * - Resizable BAR
     - [TBD]
     - Evaluate against GPU workload

.. note::
   **Secure Boot remains enabled.** One source note suggested disabling it, but
   the reference build enrolls MOK signing keys for both the NVIDIA and EDT
   kernel modules, which is only meaningful with Secure Boot active. The MOK
   path is followed throughout. Disabling Secure Boot is a valid alternative
   that removes the signing steps in :ref:`section-nvidia` and
   :ref:`section-edt`, but it is not the path taken here.

.. note::
   The real-time firmware settings above are left open deliberately. Changing
   power-management settings without a latency measurement to compare against
   is guesswork; see :ref:`section-rt-pending`.

----

.. _section-os-install:

4. OS Installation (Ubuntu Server 26.04)
========================================

Installer options are left at their defaults. The goal at this stage is a
current, working machine that later layers can build on.

.. caution::
   The installer will partition and erase the target disk. Confirm the correct
   target before proceeding.

Installation Parameters
-----------------------

* **Language / Keyboard:** English
* **Networking:** Ethernet connected, no proxy
* **Mirror:** default
* **Server profile:** minimized install
* **OpenSSH:** **install it.** Without ``sshd`` a headless build stops here.
* **Featured / Popular Snaps:** select **none**. ``snapd`` timers are a jitter
  source.

Credentials
-----------

* **Server name:** ``hesperus``
* **User:** ``hespy`` (gets ``sudo``)
* **Password:** set during installation, **not documented here**

First Boot
----------

Confirm the installed release before going any further:

.. code-block:: bash

   lsb_release -d                     # Ubuntu 26.04 LTS

.. caution::
   If this does not report 26.04, stop and reinstall from correct media. Every
   version pairing in this document assumes 26.04.

.. code-block:: bash

   sudo apt update
   sudo apt full-upgrade

Record the Python version present in the base system. It determines the
development package and symlink used in :ref:`section-milk`:

.. code-block:: bash

   python3 --version                  # reference build: 3.14.4

----

.. _section-identity:

5. Identity: Hostname, Users, Groups
====================================

Hostname
--------

.. code-block:: bash

   sudo hostnamectl set-hostname hesperus

Map the loopback alias in ``/etc/hosts``:

.. code-block:: text

   127.0.1.1   hesperus

User and Groups
---------------

``hespy``, created at install, is the operator account. It owns the software
staging tree and runs the instrument software.

.. code-block:: bash

   id hespy

SSH Access
----------

Confirm SSH from the second machine before relying on remote-only access:

.. code-block:: bash

   ssh hespy@hesperus

.. tip::
   Verify SSH now. Several steps in :doc:`software_build` require the machine
   to run with no display attached to the GPUs, and SSH is the only practical
   way to work in that state.

----

.. _section-filesystem:

6. Filesystem Layout
====================

This section creates the directory structure every later page depends on.
Software is staged and built under ``/data`` rather than in a home directory so
the build is reproducible by any operator and survives account changes.
Group-writable ownership allows builds to run without root, which limits the
blast radius of a mistaken command. These paths appear in configuration files
throughout the stack, so changing them later is disruptive.

Directories
-----------

.. code-block:: bash

   sudo mkdir /data
   sudo chown root:hespy /data
   sudo chmod g+w /data
   mkdir /data/soft
   mkdir /data/repos

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Path
     - Purpose
   * - ``/data/soft``
     - All downloaded installers, archives and source trees
   * - ``/data/repos``
     - Git clones for test suites and samples
   * - ``/usr/local/<pkg>-<version>``
     - Versioned install prefixes, with an unversioned symlink alongside
   * - ``/etc/ld.so.conf.d/<pkg>.conf``
     - One dynamic-linker file per package, followed by ``ldconfig``

.. note::
   Root ownership with a group-writable bit lets ``hespy`` create and build
   software without ``sudo``, while keeping the directory itself under
   administrative control.

Shell Environment
-----------------

All RTC-specific environment additions go in one dedicated file, sourced from
``~/.bashrc``:

.. code-block:: bash

   touch ~/.bashrc_rtc

Add to ``~/.bashrc``:

.. code-block:: bash

   if [ -f ~/.bashrc_rtc ]; then
       . ~/.bashrc_rtc
   fi

.. note::
   Every ``PATH``, library path and environment variable added in
   :doc:`software_build` goes into ``~/.bashrc_rtc``. Keeping them in one file
   makes the environment reviewable at a glance and portable to another machine
   or account.

----

.. _section-rt-kernel:

7. Real-time Kernel
===================

From 26.04, ``PREEMPT_RT`` is fully upstream and the real-time kernel is in the
main Ubuntu archive. No Ubuntu Pro subscription is needed; earlier releases
required one. This is part of why the OS layer was pushed to a current release
rather than held back.

Install **[reboot]**
--------------------

.. code-block:: bash

   sudo apt update
   sudo apt install ubuntu-realtime
   sudo apt upgrade
   sudo reboot

If the machine comes back on the generic kernel, pick the ``-realtime`` entry
under *Advanced options for Ubuntu* in the GRUB menu.

Verify
------

.. code-block:: bash

   uname -a                           # contains PREEMPT_RT and -realtime
   cat /sys/kernel/realtime           # 1
   lsb_release -d                     # Ubuntu 26.04 LTS, unchanged

Reference build:

.. code-block:: text

   Linux hesperus 7.0.0-30-realtime #30.1-Ubuntu SMP PREEMPT_RT
     Fri Aug 7 13:54:26 UTC 2026 x86_64 GNU/Linux

.. note::
   Two things must be present: the ``-realtime`` suffix on the kernel version
   and the ``PREEMPT_RT`` string. A kernel that is merely ``PREEMPT`` is not the
   real-time kernel.

Kernel Headers
--------------

.. code-block:: bash

   sudo apt install linux-headers-$(uname -r)

.. caution::
   Install these **after** booting the real-time kernel. ``$(uname -r)`` now
   resolves to the RT kernel, and the NVIDIA and EDT modules in
   :doc:`software_build` will fail to build against mismatched headers.

As-built Result
---------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Component
     - Value
   * - OS
     - Ubuntu 26.04 LTS (server)
   * - Kernel
     - ``7.0.0-30-realtime``, ``PREEMPT_RT``
   * - Firmware
     - [TBD], Secure Boot enabled
   * - Operator account
     - ``hespy``
   * - Python (system)
     - 3.14.4

----

.. _section-shielding:

8. CPU Shielding
================

Cores carrying the control loop are shielded from the scheduler, RCU callbacks
and the timer tick, and hardware IRQs are directed away from them. None of this
is recorded in the source notes for ``hesperus``, so this section is a scaffold
rather than a procedure. It is retained in the outline because an RTC without
CPU shielding and a measured latency figure has not been shown to meet its
real-time requirement. See :ref:`section-rt-pending`.

GRUB Kernel Parameters **[reboot]**
-----------------------------------

Edit ``/etc/default/grub`` and set the shielded core range. The parameter set
below is the conventional starting point; the specific core ranges for this
machine are **[TBD]**:

.. code-block:: text

   GRUB_CMDLINE_LINUX_DEFAULT="quiet clocksource=tsc tsc=reliable nmi_watchdog=0 nosoftlockup isolcpus=domain,[TBD] rcu_nocbs=[TBD] nohz_full=[TBD] irqaffinity=[TBD] kthread_cpus=[TBD]"

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Parameter
     - Purpose
   * - ``clocksource=tsc tsc=reliable``
     - Use the TSC; avoids HPET/ACPI read latency spikes
   * - ``nmi_watchdog=0``
     - Remove periodic NMI perf interrupts
   * - ``nosoftlockup``
     - Suppress soft-lockup warnings from long RT bursts
   * - ``isolcpus=domain,<set>``
     - Remove the shielded cores from all scheduling domains
   * - ``rcu_nocbs=<set>``
     - Offload RCU callbacks from the isolated cores
   * - ``nohz_full=<set>``
     - Stop the tick when one task is runnable
   * - ``irqaffinity=<housekeeping>``
     - Direct hardware IRQs to housekeeping cores
   * - ``kthread_cpus=<housekeeping>``
     - Restrict kernel threads to housekeeping cores

.. warning::
   The ``irqaffinity`` and ``isolcpus`` ranges **must not overlap**.

.. code-block:: bash

   sudo update-grub
   sudo reboot

   # After boot
   cat /proc/cmdline
   cat /sys/devices/system/cpu/isolated
   cat /sys/devices/system/cpu/nohz_full

Disable irqbalance
------------------

``irqbalance`` redistributes interrupts at runtime and silently undoes
``irqaffinity``:

.. code-block:: bash

   sudo systemctl disable --now irqbalance

Confine systemd Services
------------------------

Keep every systemd service, present and future, off the shielded cores. Edit
``/etc/systemd/system.conf``:

.. code-block:: ini

   [Manager]
   CPUAffinity=[TBD housekeeping range]

.. code-block:: bash

   sudo systemctl daemon-reexec

Check C-states
--------------

.. code-block:: bash

   for cpu in /sys/devices/system/cpu/cpu*/cpuidle/state*; do
       echo -n "$cpu: "; cat "$cpu"/name
       echo -n "  Exit latency: ";     cat "$cpu"/latency
       echo -n "  Disabled [1=yes]: "; cat "$cpu"/disable
   done

.. note::
   An isolated core whose periodic task finishes early idles for the rest of the
   cycle, and the idle subsystem drops it into a deep C-state with a long exit
   latency. That exit latency is the jitter. Disable C-states below C1 and set
   the power profile to *Maximum Performance* in :ref:`section-bios`.

----

9. Service Stripping
====================

Disable unneeded daemons, timers and update machinery. ``|| true`` keeps the
block safe when a unit is absent. This is not recorded in the source notes for
``hesperus``; the list below is a conventional starting point to be confirmed
against this machine's actual service set.

.. code-block:: bash

   for svc in \
       irqbalance.service \
       cups.service cups-browsed.service \
       ModemManager.service \
       avahi-daemon.service avahi-daemon.socket \
       bluetooth.service \
       apt-daily.timer apt-daily-upgrade.timer \
       unattended-upgrades.service \
       fwupd-refresh.timer \
       man-db.timer \
       motd-news.timer \
       update-notifier-download.timer \
       update-notifier-motd.timer \
       plocate-updatedb.timer \
       apport.service
   do
       sudo systemctl disable --now "$svc" 2>/dev/null || true
   done

   # Audit what is left
   systemctl list-units --type=service --state=running
   systemctl list-timers --all

Keep enabled: ``ssh``, ``systemd-networkd``, ``systemd-resolved`` and the time
sync service.

.. warning::
   With ``unattended-upgrades`` disabled, **security patching is manual**.
   Schedule a maintenance window (:ref:`section-rt-pending`).

.. caution::
   Do not disable ``dkms``-related units. The NVIDIA and EDT modules in
   :doc:`software_build` rely on DKMS to rebuild after a kernel update.

----

.. _section-rt-privileges:

10. RT Tooling and Scheduling Privileges
========================================

.. code-block:: bash

   sudo apt install -y util-linux rt-tests stress-ng

``rt-tests`` provides ``cyclictest`` for :ref:`section-verify`.

Allow ``hespy`` to request real-time priority. Create
``/etc/security/limits.d/99-rt.conf``:

.. code-block:: text

   hespy    -    rtprio    95
   hespy    -    memlock   unlimited
   hespy    -    nice      -20

Log out and back in to apply. Alternatively grant the capability on ``chrt``:

.. code-block:: bash

   sudo setcap 'cap_sys_nice=eip' "$(command -v chrt)"

----

.. _section-verify:

11. Verification
================

Reboot, then record the results as the as-built baseline. Do not start
:doc:`software_build` until the rows below pass.

.. list-table::
   :header-rows: 1
   :widths: 25 50 25

   * - Check
     - Command
     - Expected
   * - Hostname
     - ``hostnamectl``
     - ``hesperus``
   * - OS release
     - ``lsb_release -d``
     - Ubuntu 26.04 LTS
   * - RT kernel
     - ``uname -a``
     - contains ``PREEMPT_RT`` and ``-realtime``
   * - RT flag
     - ``cat /sys/kernel/realtime``
     - ``1``
   * - Kernel headers
     - ``dpkg -l | grep linux-headers-$(uname -r)``
     - installed
   * - Secure Boot
     - ``mokutil --sb-state``
     - enabled
   * - No desktop
     - ``systemctl get-default``
     - ``multi-user.target``
   * - SSH reachable
     - ``ssh hespy@hesperus`` from a second machine
     - login succeeds
   * - ``/data`` ownership
     - ``ls -ld /data``
     - ``drwxrwxr-x root hespy``
   * - Group write
     - ``touch /data/testfile`` as ``hespy``
     - succeeds without ``sudo``
   * - Subdirectories
     - ``ls /data``
     - ``soft`` and ``repos``
   * - Environment hook
     - ``grep bashrc_rtc ~/.bashrc``
     - conditional source block present
   * - Python
     - ``python3 --version``
     - ``3.14.4``
   * - Kernel cmdline
     - ``cat /proc/cmdline``
     - matches :ref:`section-shielding` **[TBD]**
   * - Isolated cores
     - ``cat /sys/devices/system/cpu/isolated``
     - **[TBD]**
   * - irqbalance off
     - ``systemctl is-enabled irqbalance``
     - ``disabled`` / not-found
   * - Clocksource
     - ``cat /sys/devices/system/clocksource/clocksource0/current_clocksource``
     - ``tsc``

Latency Baseline
----------------

.. code-block:: bash

   # 30 min, RT prio 80, one thread per shielded core
   sudo cyclictest -m -S -p80 -i200 -h400 -D30m -a <shielded> > cyclictest_baseline.txt

   # Repeat while stressing the housekeeping cores
   stress-ng --cpu 8 --taskset <housekeeping> --timeout 30m &
   sudo cyclictest -m -S -p80 -i200 -h400 -D30m -a <shielded> > cyclictest_loaded.txt

A large gap between loaded and idle max latency means something is still
running on the isolated cores; recheck ``irqaffinity`` first.

.. warning::
   No latency budget or measured result exists for ``hesperus``. Until one is
   defined and recorded, this build has no evidence that it meets its real-time
   requirement. This is the highest-priority open item on this page
   (:ref:`section-rt-pending`).

----

12. Troubleshooting
===================

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Symptom
     - Resolution
   * - System boots into the generic kernel
     - Select the ``-realtime`` entry under *Advanced options for Ubuntu* in
       GRUB, then set it as the default. If absent, reinstall
       ``ubuntu-realtime`` and run ``update-grub``.
   * - USB drive absent from the boot menu
     - Confirm the drive was flashed as UEFI-bootable and boot mode is UEFI.
       Try a rear-panel USB port.
   * - ``lsb_release`` reports the wrong release
     - Wrong installer media. Reinstall; every version pairing assumes 26.04.
   * - Module build fails after a kernel update
     - Headers no longer match. Reinstall
       ``linux-headers-$(uname -r)`` and re-run the DKMS builds in
       :doc:`software_build`.
   * - Latency spikes under load
     - Check in order: (1) ``irqaffinity`` overlapping the shielded set;
       (2) ``irqbalance`` still running; (3) C-states enabled, visible as jitter
       on an *idle* isolated core; (4) SMT still on; (5) unpinned processes on
       the shielded cores.
   * - ``chrt``: "Operation not permitted"
     - ``limits.d`` rtprio grant or ``cap_sys_nice`` missing
       (:ref:`section-rt-privileges`); re-login after editing limits.
   * - Group membership not taking effect
     - Re-login, or ``newgrp`` for the current shell.
   * - Builds fail with permission errors under ``/data``
     - Confirm ``chown root:hespy`` and ``chmod g+w`` were applied
       (:ref:`section-filesystem`).

----

.. _section-rt-pending:

13. Pending Tasks
=================

* [ ] **RT-1: Latency budget and baseline.** No ``cyclictest`` result or jitter
  requirement exists. This is the primary open gate for the build.
* [ ] **RT-2: CPU shielding parameters.** ``isolcpus``, ``nohz_full``,
  ``rcu_nocbs``, ``irqaffinity``, ``kthread_cpus`` and hugepage settings are
  undetermined for this machine.
* [ ] **RT-3: Firmware RT settings.** SMT, C-states, turbo, IOMMU and
  Resizable BAR are left at optimized defaults pending measurement.
* [ ] **RT-4: Secure Boot posture.** Confirmed as enabled, contrary to one
  source note. Re-confirm at the next rebuild.
* [ ] **RT-5: Service stripping list.** The list on this page is conventional,
  not measured against this machine.
* [ ] **RT-6: Patching policy.** ``unattended-upgrades`` is disabled; define a
  manual maintenance window.
* [ ] **RT-7: Storage layout.** Partitioning scheme and filesystem sizing for
  ``/data`` are undocumented.
* [ ] **RT-8: Network configuration.** Addressing, time sync and any
  instrument-side links are undocumented.
* [ ] **RT-9: Backup and recovery.** Image the system disk once
  :doc:`software_build` verifies, and test the restore.

----

14. References
==============

Real-time Ubuntu
----------------

* `Real-time Ubuntu overview <https://ubuntu.com/real-time>`_
* `Real-time Ubuntu documentation <https://documentation.ubuntu.com/real-time/latest/>`_
* `How to enable Real-time Ubuntu <https://documentation.ubuntu.com/real-time/latest/how-to/enable-real-time-ubuntu/>`_
* `Switch from real-time to generic kernel <https://documentation.ubuntu.com/real-time/latest/how-to/switch-from-realtime-to-generic-kernel/>`_

Tuning
------

* `Configure CPUs for real-time processing <https://documentation.ubuntu.com/real-time/latest/how-to/cpu-boot-configs/>`_
* `Tune IRQ affinity <https://documentation.ubuntu.com/real-time/latest/how-to/tune-irq-affinity/>`_
* `Kernel boot parameters reference <https://documentation.ubuntu.com/real-time/latest/reference/kernel-boot-parameters/>`_
* `Modify kernel boot parameters <https://documentation.ubuntu.com/real-time/latest/how-to/modify-kernel-boot-parameters/>`_

Measurement
-----------

* `Measure maximum latency <https://documentation.ubuntu.com/real-time/latest/how-to/measure-maximum-latency/>`_
* `Tools for measuring real-time metrics <https://documentation.ubuntu.com/real-time/latest/reference/real-time-metrics-tools/>`_
