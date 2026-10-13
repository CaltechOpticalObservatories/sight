==============================
SIGHT RTC: GPU Real-time Build
==============================

:Authors: [TBD]
:Date: 2026-10-13
:Hostname: ``hesperus``
:User: ``hespy``
:OS: Real-time Ubuntu 26.04 LTS (``PREEMPT_RT`` kernel)
:Supersedes: ``sight_install_log.txt``, ``sight_rtc_build_note.rst``

A GPU-accelerated real-time controller for SIGHT at Caltech. Camera frames
arrive over an EDT Camera Link framegrabber, are processed on NVIDIA Blackwell
GPUs through CUDA and MAGMA, and move between processing stages through MILK
shared memory backed by RAM. Follow the three parts in order:

#. **Physical build:** hardware assembly and inspection.
#. **RT build:** BIOS and Secure Boot, OS install, identity, filesystem layout,
   RT kernel and CPU shielding.
#. **Software build:** GPU driver, CUDA, framegrabber, MAGMA, Python, MILK and
   the RTC application.

Build Layers
============

Each layer depends on the layer below it and is verified before the next is
started::

     software_build  |  RTC application
                     |  MILK / CACAO + shared memory
                     |  MAGMA   |  Python venv  |  EDT framegrabber
                     |  CUDA toolkit
                     |  NVIDIA driver
     ----------------+--------------------------------------------
     rt_build        |  Filesystem layout
                     |  Real-time kernel + CPU shielding
                     |  Ubuntu 26.04 LTS Server
                     |  BIOS / firmware
     ----------------+--------------------------------------------
     physical_build  |  Hardware

Design Rules
============

These rules govern every page that follows. The versions pinned in this
document will age out; the strategy for choosing them will not.

#. **Build in layers, and verify each layer before moving up.** Every page ends
   in a verification table for a reason. A fault introduced at the driver layer
   surfaces as an inscrutable compile error four layers later, and the cost of
   diagnosis rises sharply with distance from the cause.

#. **Keep component release dates clustered.** The best predictor of
   compatibility across this stack is how close the components are in release
   date. MAGMA 2.10.0 (February 2026) is paired with CUDA 13.x because MAGMA
   added CUDA 13 and Blackwell support in that window. Components separated by a
   year or more are suspect until proven otherwise.

#. **Build oldest-at-the-base, newer going up.** Choose the base layers
   conservatively and let the upper layers be more current: a stable driver,
   then a newer CUDA, then a newer shared-memory framework. Lower layers have
   more dependents, so churn there is more expensive.

#. **The OS is the deliberate exception.** The rule above would argue for the
   oldest workable OS, but this build pushes the OS as current as possible and
   rolls back only if something breaks. A current LTS release buys a longer
   support window and, on 26.04, a real-time kernel with no subscription.

#. **Install order is not arbitrary.** The NVIDIA driver precedes CUDA because
   the CUDA installer will otherwise overwrite a carefully built driver. MAGMA
   precedes MILK because MILK links against it at compile time. Kernel headers
   precede anything using DKMS.

#. **One toolchain.** Build and run within a single consistent compiler and
   library set. Environments that ship their own compilers and shared libraries
   can compile against one set of sources and execute against another, and the
   resulting failures appear far from their cause.

.. caution::
   Do not use Conda for the Python environment on this machine. It installs its
   own compilers and shared libraries, and :ref:`section-milk` compiles native
   extensions against whatever interpreter is on the ``PATH``.

.. note::
   Installing to non-standard locations is supported by every component here,
   but each one must then be told where things are. Historically this stack has
   failed by linking against the wrong library, failing to link at all, or
   compiling against headers that do not match the runtime. The ``.bashrc_rtc``
   and ``ld.so.conf.d`` conventions in :ref:`section-filesystem` exist to make
   these paths explicit and auditable.

.. note::
   Vendor documentation across this stack is extensive but often unclear or
   scattered. Cross-referencing vendor docs, project READMEs and community
   sources is expected. Record what actually worked, not what the documentation
   claimed.

Conventions
===========

* ``$`` prompts are omitted. Unless a block says otherwise, run as ``hespy``
  with ``sudo`` where shown.
* Steps marked **[reboot]** require a restart before continuing.
* Software is staged in ``/data/soft`` and built there, never from a home
  directory or ``/tmp``.
* Installed prefixes are versioned (``/usr/local/<pkg>-<version>``) with an
  unversioned symlink alongside, so a rollback is a symlink change.
* Four admonition types are used: **warning** for injury or hardware damage,
  **caution** for data loss or hard-to-reverse steps, **note** for rationale,
  and **tip** for optional time-savers.

.. toctree::
   :maxdepth: 1

   physical_build
   rt_build
   software_build
