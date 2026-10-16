=========================================
Software Build: GPU Stack, Python and RTC
=========================================

:Prerequisite: :doc:`rt_build` complete and verified
:Next: run :ref:`section-sw-verify`, then the instrument is ready

.. contents::
   :depth: 1
   :local:

----

.. _section-packages:

1. System Packages
==================

Install only what the instrument needs. The GPUs are used for computation, not
display; GUIs are not run locally. Work through the sections in order, because
each one links against the layer below it.

The toolchain installed here is what the NVIDIA and EDT runfile installers
compile kernel modules with, and what MAGMA and MILK are built with. Installing
it before any driver work avoids a failed install several steps later. DKMS is
included so kernel modules rebuild automatically on kernel update.

.. code-block:: bash

   sudo apt update
   sudo apt install -y \
       build-essential \
       make gcc \
       dkms \
       cmake \
       git \
       pkg-config \
       wget curl \
       net-tools \
       libopenblas-dev

.. note::
   ``build-essential``, ``make`` and ``gcc`` are required by the NVIDIA runfile
   installer in :ref:`section-nvidia`, which compiles kernel modules against
   the running kernel. ``libopenblas-dev`` is the BLAS library MAGMA is
   configured against in :ref:`section-magma`.

.. caution::
   Kernel headers matching the **real-time** kernel must already be installed
   (:ref:`section-rt-kernel`). Confirm with
   ``dpkg -l | grep linux-headers-$(uname -r)`` before continuing.

----

.. _section-nvidia:

2. NVIDIA Driver
================

Driver 595.91.07 is installed from the vendor runfile, which is the only
practical path on a ``PREEMPT_RT`` kernel. NVIDIA does not support real-time
kernels and the installer refuses to run on one unless explicitly overridden.
Because Secure Boot is enabled (:ref:`section-bios`), the kernel module must be
signed and the key enrolled through MOK, which requires physical console access
at a GPU for one reboot. The open MIT/GPL module flavour is required for
Blackwell cards; the proprietary flavour loads but will not drive them.

.. caution::
   Perform this installation over SSH or from the motherboard console with
   nothing connected to the GPU display outputs. NVIDIA cards initialize
   differently with a display attached, which interferes with driver
   installation on a headless compute node.

Download and Install
--------------------

#. Confirm the GPUs are visible:

   .. code-block:: bash

      lspci | grep -i vga

#. Download and prepare the runfile:

   .. code-block:: bash

      cd /data/soft
      wget https://us.download.nvidia.com/XFree86/Linux-x86_64/595.91.07/NVIDIA-Linux-x86_64-595.91.07.run
      chmod +x NVIDIA-Linux-x86_64-595.91.07.run

#. Optionally attempt a normal install first, in case a later release has
   removed the restriction:

   .. code-block:: bash

      sudo bash NVIDIA-Linux-x86_64-595.91.07.run

   This is expected to abort with an error about ``PREEMPT_RT`` kernels.

#. Install with the real-time check overridden:

   .. code-block:: bash

      sudo IGNORE_PREEMPT_RT_PRESENCE=1 bash NVIDIA-Linux-x86_64-595.91.07.run

.. note::
   One source note records this variable as ``IGNORE_PREEMPT_RT_PRESENTS``.
   The correct spelling is ``IGNORE_PREEMPT_RT_PRESENCE``. NVIDIA's refusal is
   a statement about support, not a technical block.

Installer Prompts
-----------------

.. list-table::
   :header-rows: 1
   :widths: 40 20 40

   * - Prompt
     - Answer
     - Rationale
   * - Multiple kernel module types
     - **MIT/GPL**
     - Required for Blackwell. The proprietary module is not valid for this GPU
       generation.
   * - Disable nouveau drivers
     - ``y``
     - The open-source driver conflicts with the NVIDIA module
   * - Update initramfs
     - ``y``
     - Required so the module is available at boot
   * - Sign kernel module
     - ``y``
     - Required under Secure Boot
   * - Generate a new key pair
     - ``y``
     -
   * - Delete private signing key
     - ``n``
     - The key is needed to re-sign after kernel updates
   * - Signed module failed to load
     - Install signed kernel module
     - Expected; the key is not yet enrolled
   * - Register with DKMS
     - ``y``
     - Rebuilds the module automatically on kernel update
   * - More than one tool available
     - ``update-initramfs``
     - The standard Ubuntu initial-ramdisk tool
   * - Rebuild initramfs
     - ``y``
     -
   * - Update X configuration file
     - ``n``
     - The GPUs are used for computation, not display

.. warning::
   Answering ``y`` to deleting the private signing key will require generating
   and enrolling a new key after every kernel update. Answer ``n``.

Record the signing key locations reported by the installer:

.. code-block:: text

   Private key: /usr/share/nvidia/nvidia-modsign-key-<ID>.key
   Public key:  /usr/share/nvidia/nvidia-modsign-crt-<ID>.der

.. note::
   The certificate ID is generated per installation. Read it from the installer
   output rather than copying a value from this document. The reference build
   kept ``nvidia-modsign-crt-9A20B563.der``. Two NVIDIA installer keys are
   enrolled, one left over from an earlier install (:ref:`section-sw-pending`).

.. _section-mok:

MOK Enrollment **[reboot]**
---------------------------

#. Enroll the public key:

   .. code-block:: bash

      sudo mokutil --import /usr/share/nvidia/nvidia-modsign-crt-<ID>.der

   Set a temporary password when prompted.

#. Attach a monitor to a GPU output for the enrollment screen.
#. Reboot:

   .. code-block:: bash

      sudo reboot

#. At the blue MOK screen: press any key, select **Enroll MOK**, then
   **Continue**, then **Yes**, enter the temporary password, and reboot.
#. Disconnect the display from the GPU.

.. warning::
   The temporary password is needed at the next boot and cannot be recovered.
   Write it down before rebooting.

.. note::
   This is the one point in the build where a display must be connected to a
   GPU. The MOK enrollment interface runs in firmware before the OS starts and
   is not reachable over SSH. If the screen is missed, the system boots normally
   and the module will not load; re-import and reboot again.

Verify
------

.. code-block:: bash

   mokutil --list-enrolled | grep nvidia
   lsmod | grep nvidia
   lsmod | grep nouveau               # expect no output
   nvidia-smi
   nvidia-smi --query-gpu=compute_cap --format=csv
   nvidia-smi -q | grep -i architecture    # Blackwell

Reference build:

.. code-block:: text

   NVIDIA-SMI 595.91.07   Driver Version: 595.91.07   CUDA Version: 13.2
   NVIDIA GeForce RTX 5090   00000000:21:00.0

.. note::
   The CUDA version reported here is the maximum the driver supports, not an
   installed toolkit. It is the input to the version decision in
   :ref:`section-cuda`. The architecture name matters downstream: MAGMA is
   compiled with ``GPU_TARGET ?= Blackwell`` in :ref:`section-magma`.

.. tip::
   If ``nvidia-smi`` fails, read ``dmesg`` first. In the reference build the
   failure was an unsigned module that was not loaded at boot, and the kernel
   log named the cause directly.

Rollback
--------

.. code-block:: bash

   sudo /usr/bin/nvidia-uninstall
   sudo update-initramfs -u
   sudo reboot

----

.. _section-cuda:

3. CUDA Toolkit
===============

CUDA Toolkit 13.3.1 is installed from the vendor runfile with the bundled
driver explicitly deselected, so the signed driver from :ref:`section-nvidia`
is preserved. CUDA is the compute layer that MAGMA and MILK both build against,
so its paths must be correct and visible to the linker before either is
attempted. The section closes by building and running NVIDIA's sample programs,
which is the only reliable way to confirm the toolkit, driver and GPU work
together.

.. warning::
   During the installer, **deselect the NVIDIA driver component**. Leaving it
   selected overwrites the signed MIT/GPL driver with an unsigned proprietary
   build, which will not load under Secure Boot and is not valid for Blackwell
   cards.

Install
-------

.. code-block:: bash

   cd /data/soft
   wget https://developer.download.nvidia.com/compute/cuda/13.3.1/local_installers/cuda_13.3.1_610.43.02_linux.run
   chmod +x cuda_13.3.1_610.43.02_linux.run
   sudo sh cuda_13.3.1_610.43.02_linux.run

Accept the EULA, unselect **Driver**, and leave everything else at defaults.
Confirm the summary:

.. code-block:: text

   Driver:   Not Selected
   Toolkit:  Installed in /usr/local/cuda-13.3/

.. caution::
   The installer warns that a driver of version 610.00 or later is required,
   while the installed driver is 595.91.07. The reference build functions with
   this combination, but it is an unresolved version mismatch
   (:ref:`section-sw-pending`).

.. note::
   The installer also prints an incomplete-installation warning about the
   missing driver. This is expected and correct here. The installer log is at
   ``/var/log/cuda-installer.log``.

.. _section-cuda-paths:

Paths
-----

Add to ``~/.bashrc_rtc``:

.. code-block:: bash

   export PATH="/usr/local/cuda-13.3/bin:$PATH"

Register the library path with the dynamic linker:

.. code-block:: bash

   echo "/usr/local/cuda-13.3/lib64" | sudo tee /etc/ld.so.conf.d/cuda-13-3.conf
   cat /etc/ld.so.conf.d/cuda-13-3.conf
   sudo ldconfig
   source ~/.bashrc_rtc
   nvcc --version

.. tip::
   A reboot accomplishes both ``ldconfig`` and the shell reload and removes any
   doubt about stale state. If anything behaves oddly after a path change,
   reboot before investigating further.

.. note::
   Path problems at this layer are the most common source of difficulty later
   in the build: linking against the wrong library, failing to link at all, or
   compiling against mismatched headers. Getting them right here prevents a
   class of failures in :ref:`section-magma` and :ref:`section-milk`.

Test with cuda-samples
----------------------

.. code-block:: bash

   cd /data/repos
   git clone https://github.com/NVIDIA/cuda-samples.git
   cd cuda-samples
   git checkout tags/v13.3
   mkdir build && cd build
   cmake ..
   make -j$(nproc)

Then run several compute-oriented samples from ``../Samples``; they are
executables inside descriptively named directories.

.. note::
   The sample tag must match the installed CUDA version. CMake will report a
   number of components as not found; most relate to graphics and display and
   are irrelevant here. If CUDA itself is not found, the paths above are wrong.
   Warnings during ``make`` are expected and numerous; errors are not.

Rollback
--------

.. code-block:: bash

   sudo /usr/local/cuda-13.3/bin/cuda-uninstaller
   sudo rm /etc/ld.so.conf.d/cuda-13-3.conf
   sudo ldconfig

Remove the CUDA ``PATH`` line from ``~/.bashrc_rtc``.

----

.. _section-edt:

4. EDT Framegrabber
===================

The EDT PDV driver serves the VisionLink F1 Camera Link framegrabber, which is
the RTC's image input path. The vendor package declares a maximum supported
kernel version well below the real-time kernel in use, so its DKMS build
refuses to run until that restriction is overridden. As with the NVIDIA module,
the resulting kernel module must be signed and enrolled through MOK. The
section ends with a loopback test against a simulated camera, which confirms
the card and driver without the real camera present.

Install
-------

.. code-block:: bash

   cd /data/soft
   wget https://edt.com/wp-content/uploads/2025/09/edtpdv_6.2.1_amd64.deb
   sudo apt install ./edtpdv_6.2.1_amd64.deb

The DKMS build is expected to fail:

.. code-block:: text

   Warning: The dkms.conf for module edt_pci_pdv/6.2.1 includes a
   BUILD_EXCLUSIVE directive which does not match this kernel/arch/config.
   ERROR: DKMS build failed. Kernel module not installed.

.. note::
   This failure is expected. The package itself installed correctly; only the
   kernel module build was blocked.

.. _section-edt-dkms:

DKMS Kernel Restriction
-----------------------

#. Confirm the cause:

   .. code-block:: bash

      cat /usr/src/edt_pci_pdv-6.2.1/dkms.conf     # BUILD_EXCLUSIVE_KERNEL_MAX="6.12"
      uname -r                                     # 7.0.0-30-realtime

#. Override the restriction:

   .. code-block:: bash

      sudo tee /etc/dkms/edt_pci_pdv-6.2.1.conf <<'EOF'
      BUILD_EXCLUSIVE_KERNEL_MAX=""
      EOF

#. Build and install against the running kernel:

   .. code-block:: bash

      cd /opt/EDTpdv
      sudo dkms build -m edt_pci_pdv -v 6.2.1 -k "$(uname -r)"
      sudo dkms install -m edt_pci_pdv -v 6.2.1 -k "$(uname -r)"

.. caution::
   Overriding ``BUILD_EXCLUSIVE_KERNEL_MAX`` builds the module against a kernel
   the vendor has not qualified. It works in the reference build, but it is an
   unsupported configuration and must be re-verified after every kernel update.

.. note::
   The override is placed in ``/etc/dkms/`` rather than by editing the vendor's
   ``dkms.conf`` directly, so a package update does not silently discard it and
   the modification stays visible.

MOK Enrollment **[reboot]**
---------------------------

.. code-block:: bash

   sudo mokutil --import /var/lib/shim-signed/mok/MOK.der
   sudo reboot

Complete enrollment at the blue MOK screen as in :ref:`section-mok`, with a
display attached to a GPU.

.. note::
   This is the shim-signed DKMS key, separate from the NVIDIA installer's key.
   Both must be enrolled.

Library Path and Verification
-----------------------------

.. code-block:: bash

   echo /opt/EDTpdv | sudo tee /etc/ld.so.conf.d/edt-pdv.conf
   sudo ldconfig

   cd /opt/EDTpdv
   ./pciload

Reference build:

.. code-block:: text

   Library version 6.2.1 (64 bit)
   pdv driver version 6.2.1 (64 bit)
   pdv unit 0 (VisionLink F1):
     ID 0x9d, 5cgtfd5c5 PCIe FPGA
     s/n VLF101431, p/n 019-14836-30, rev 30, clock 100 Mhz
     PCIe negotiated link width x1, 5.0 Gbps

Test against a simulated camera:

.. code-block:: bash

   ./initcam -c 2 -f camera_config/generic24cl.cfg
   ./take -u 0 -c 2

.. tip::
   Run the simulated camera test before connecting camera hardware, so any
   failure is unambiguously on the RTC side.

Rollback
--------

.. code-block:: bash

   sudo dkms remove -m edt_pci_pdv -v 6.2.1 --all
   sudo apt remove edtpdv
   sudo rm /etc/dkms/edt_pci_pdv-6.2.1.conf
   sudo rm /etc/ld.so.conf.d/edt-pdv.conf
   sudo ldconfig

----

.. _section-magma:

5. MAGMA
========

MAGMA provides the dense and sparse linear algebra routines the RTC uses, and
manages the division of work and data movement between CPU and GPU. It is built
from source rather than packaged because it must be compiled against this
machine's specific CUDA version, BLAS library and GPU architecture. Version
2.10.0 is used because it is contemporaneous with CUDA 13 and includes Blackwell
support. MILK links against MAGMA at compile time, so this section must complete
before :ref:`section-milk`.

Build
-----

.. code-block:: bash

   cd /data/soft
   wget https://icl.utk.edu/projectsfiles/magma/downloads/magma-2.10.0.tar.gz
   tar -xzf magma-2.10.0.tar.gz
   cd magma-2.10.0
   sudo apt install gfortran
   cp make.inc-examples/make.inc.openblas make.inc

Edit ``make.inc``:

.. list-table::
   :header-rows: 1
   :widths: 10 30 60

   * - Line
     - Setting
     - Value
   * - 19
     - ``OPENBLASDIR ?=``
     - ``/usr/lib/x86_64-linux-gnu/openblas-pthread``
   * - 52
     - ``GPU_TARGET ?=``
     - ``Blackwell``
   * - 83
     - ``LIBDIR +=``
     - ``-L$(OPENBLASDIR)``

.. warning::
   ``GPU_TARGET`` must match the architecture reported by ``nvidia-smi -q``
   in :ref:`section-nvidia`. A mismatch produces a library that compiles
   cleanly but fails at runtime on these cards.

.. note::
   Line numbers are from the 2.10.0 example file. Confirm by setting name
   rather than by line number if the version differs.

.. code-block:: bash

   make -j 64 lib
   make -j 64 test
   make -j 64 sparse-lib
   make -j 64 sparse-test
   sudo make install prefix=/usr/local/magma-2.10.0

.. _section-magma-pkgconfig:

pkg-config Correction
---------------------

MAGMA 2.10.0 emits a malformed ``Cflags`` line. Edit
``/usr/local/magma-2.10.0/lib/pkgconfig/magma.pc`` so that it reads:

.. code-block:: text

   Cflags: -I${includedir} -DNDEBUG -DADD_ -fopenmp -I/usr/local/cuda/include

.. caution::
   This is a known defect in the MAGMA release, not a local misconfiguration.
   MILK locates MAGMA through pkg-config and will fail to configure if this
   file is left uncorrected.

Symlink and Library Path
------------------------

.. code-block:: bash

   sudo ln -sfn /usr/local/magma-2.10.0 /usr/local/magma
   echo "/usr/local/magma/lib" | sudo tee /etc/ld.so.conf.d/magma.conf > /dev/null
   sudo ldconfig

.. note::
   Downstream configuration refers to ``/usr/local/magma``. Rolling back to a
   different MAGMA build is then a single symlink change rather than an edit
   across several files.

Verify
------

.. code-block:: bash

   ls /usr/local/magma-2.10.0/lib        # libmagma.so, libmagma_sparse.so
   ldconfig -p | grep magma
   pkg-config --cflags magma

   cd /data/soft/magma-2.10.0/testing
   ./run_test.py > tests.txt
   ./run_summarize.py tests.txt

----

.. _section-python:

6. Python Environment
=====================

An isolated Python environment is built on the system Python 3.14.4 rather than
a separate distribution. It lives at a fixed path outside any user's home
directory so it is available to services and to any operator. A plain virtual
environment is used deliberately instead of Conda, because Conda supplies its
own compilers and libraries and mixing those with the system toolchain causes
difficult-to-diagnose failures. MILK builds Python bindings against this
environment, so it must exist and be active before that build runs.

.. code-block:: bash

   python3 --version                       # 3.14.4
   sudo mkdir /opt/rtc_python
   sudo chown hespy:hespy /opt/rtc_python
   python3 -m venv /opt/rtc_python/rtc_venv3.14.4

Add to ``~/.bashrc_rtc``:

.. code-block:: bash

   source /opt/rtc_python/rtc_venv3.14.4/bin/activate

.. code-block:: bash

   source ~/.bashrc_rtc
   python -m pip install --upgrade pip
   python -m pip install numpy scipy matplotlib astropy setuptools pybind11
   python -m pip freeze > /data/soft/rtc_python_packages.txt

.. caution::
   Do not substitute Conda or another environment manager here.
   :ref:`section-milk` compiles native extensions against this environment.

.. note::
   ``pybind11`` is required by the MILK build, which locates it through
   ``python -m pybind11 --cmakedir``. ``setuptools`` is required for building
   native extensions. Encoding the Python version in the directory name means a
   future upgrade creates a parallel environment rather than overwriting a
   working one.

----

.. _section-milk:

7. MILK and CACAO
=================

MILK provides the shared-memory framework and image-stream infrastructure the
RTC is built on, and CACAO is the adaptive-optics control layer that runs on top
of it. Both are compiled from source with CUDA and MAGMA support enabled, which
is why every preceding layer had to be verified first. The build has two known
upstream defects that must be worked around: a missing ``CMakeLists.txt`` in the
CACAO licenses directory, and a ``python3-config`` symlink the system does not
create.

Dependencies
------------

.. code-block:: bash

   sudo apt install pkg-config liblapacke-dev libgsl-dev libfftw3-dev \
       libncurses-dev libreadline-dev bison flex libcfitsio-dev libhwloc-dev
   sudo apt install python3.14-dev
   sudo ln -s /usr/bin/python3.14-config /usr/bin/python3-config

.. note::
   The build expects a generic ``python3-config``, which Ubuntu does not provide
   for this version. Without the symlink the build fails while probing for
   Python.

Source and Environment
----------------------

.. code-block:: bash

   cd /data/soft
   git clone https://github.com/milk-org/milk.git
   cd milk
   ./fetch_cacao_dev.sh

Add to ``~/.bashrc_rtc``:

.. code-block:: bash

   export MILK_ROOT=/data/soft/milk
   export MILK_INSTALLDIR=/usr/local/milk
   export MILK_SHM_DIR=/milk/shm

.. code-block:: bash

   source ~/.bashrc_rtc
   export PKG_CONFIG_PATH=/usr/local/magma/lib/pkgconfig${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}

.. note::
   One source note places the MILK variables in ``~/.bashrc``. They are placed
   in ``~/.bashrc_rtc`` here for consistency with :ref:`section-filesystem`
   (:ref:`section-sw-pending`). ``MILK_SHM_DIR`` points at the tmpfs created in
   :ref:`section-shm`; the variable is set now because the build reads it.

Build
-----

.. code-block:: bash

   # Upstream defect: CMake descends into LICENSES and finds no CMakeLists.txt
   touch /data/soft/milk/plugins/cacao-src/LICENSES/CMakeLists.txt

   MILK_CMAKE_OPT="-DUSE_MAGMA=ON -DUSE_CUDA=ON \
   -Dpybind11_DIR=$(python -m pybind11 --cmakedir) \
   -DPYBIND11_FINDPYTHON=ON" ./compile.sh

   cd _build
   sudo make install
   sudo ln -s /usr/local/milk-1.03.00 /usr/local/milk
   sudo ln -s /usr/local/milk /usr/local/cacao

.. caution::
   Confirm the Python virtual environment is active before building. The build
   links Python bindings against whatever interpreter is on the ``PATH``, and a
   build against the system interpreter will not work under the venv at runtime.

.. warning::
   ``USE_MAGMA=ON`` and ``USE_CUDA=ON`` are what tie this build to
   :ref:`section-cuda` and :ref:`section-magma`. If either fails to configure,
   stop and resolve it here rather than building without GPU support.

.. note::
   Confirm the installed version directory name before creating the symlink; it
   reflects the MILK release cloned above and may differ from the reference
   build. Both workarounds on this page are upstream issues; re-check whether
   they are still needed after any MILK update.

----

.. _section-shm:

8. Shared Memory
================

MILK exchanges image streams between processes through shared memory, backed
here by a RAM-based tmpfs rather than disk. Keeping the streams in RAM is what
allows data to move between RTC stages without storage latency entering the
control loop. The mount is added to ``/etc/fstab`` so it is established
automatically at every boot.

.. code-block:: bash

   echo "tmpfs /milk/shm tmpfs rw,nosuid,nodev" | sudo tee -a /etc/fstab
   sudo mkdir -p /milk/shm
   sudo systemctl daemon-reload
   sudo mount /milk/shm

   df -h /milk/shm
   mount | grep milk

.. caution::
   Editing ``/etc/fstab`` incorrectly can prevent the system from booting.
   Verify the mount with ``sudo mount`` before rebooting. Contents of a tmpfs
   are lost on reboot; nothing requiring persistence belongs in ``/milk/shm``.

.. note::
   No size limit or ownership is specified in the source notes, so the mount
   takes the tmpfs default of half of physical RAM (91.9 GB on ``hesperus``)
   and is ``root:root`` with mode ``1777``, so any account can create streams.
   Confirm whether the RTC processes require a specific size or ownership
   (:ref:`section-sw-pending`). ``nosuid`` and ``nodev`` are standard hardening
   options and carry no performance cost.

----

.. _section-rtc-app:

9. RTC Application
==================

This section covers the SIGHT RTC application itself: acquisition, build,
configuration, services and interfaces. The source notes do not reach this
layer, so the section is a scaffold rather than a procedure. It is retained so
the structure is complete and the gap is visible rather than implicit. This is
the largest outstanding item in the build (:ref:`section-sw-pending`).

#. Acquire the RTC source. Record repository, branch and commit hash or tag.
#. Build the application.
#. Install to a versioned prefix with an unversioned symlink.
#. Install configuration files and document each significant parameter.
#. Define services, their startup order and their dependencies.
#. Configure interfaces: camera input, telemetry output, engineering and
   control GUI, and connections to upstream and downstream instrument systems.
#. Configure logging and log rotation.
#. Confirm the operator account can write to ``/milk/shm``.

----

.. _section-sw-verify:

10. Final Reboot and Verification
=================================

.. code-block:: bash

   sudo reboot

.. list-table::
   :header-rows: 1
   :widths: 25 50 25

   * - Check
     - Command
     - Expected
   * - Driver responds
     - ``nvidia-smi``
     - 595.91.07, all GPUs listed
   * - Modules loaded
     - ``lsmod | grep nvidia``
     - ``nvidia``, ``nvidia_uvm``, ``nvidia_modeset``, ``nvidia_drm``
   * - nouveau absent
     - ``lsmod | grep nouveau``
     - no output
   * - MOK keys enrolled
     - ``mokutil --list-enrolled``
     - NVIDIA installer key and shim DKMS key
   * - DKMS modules
     - ``dkms status``
     - nvidia and ``edt_pci_pdv/6.2.1`` built for the running kernel
   * - CUDA compiler
     - ``nvcc --version``
     - release 13.3
   * - CUDA linkage
     - ``ldconfig -p | grep cudart``
     - library listed
   * - CUDA samples
     - run a compute sample
     - reports PASS on the GPU
   * - Framegrabber
     - ``cd /opt/EDTpdv && ./pciload``
     - unit 0 VisionLink F1 reported
   * - Simulated capture
     - ``./take -u 0 -c 2``
     - frames captured, no error
   * - MAGMA linkage
     - ``ldconfig -p | grep magma``
     - libraries listed
   * - MAGMA pkg-config
     - ``pkg-config --cflags magma``
     - returns flags, no error
   * - Python
     - ``python --version``
     - ``3.14.4`` from ``rtc_venv3.14.4``
   * - Python packages
     - ``python -c "import numpy, scipy, astropy"``
     - no error
   * - MILK installed
     - ``ls -l /usr/local/milk``
     - symlink resolves to the version directory
   * - CACAO symlink
     - ``ls -l /usr/local/cacao``
     - resolves to ``/usr/local/milk``
   * - MILK environment
     - ``env | grep MILK``
     - all three variables present
   * - Shared memory
     - ``df -h /milk/shm``
     - tmpfs mounted automatically
   * - RTC services
     - ``systemctl status``
     - **[TBD]** all services active
   * - End-to-end
     - **[TBD]**
     - frames reach the RTC, loop runs at target rate

Re-run the latency baseline (:ref:`section-verify`) with the instrument
software running.

.. warning::
   A build that passes every check above but has no measured latency figure has
   not been shown to be a real-time system.

As-built Software Versions
--------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 25 45

   * - Component
     - Version
     - Install path
   * - NVIDIA driver
     - 595.91.07
     - MIT/GPL, DKMS, signed
   * - CUDA toolkit
     - 13.3.1
     - ``/usr/local/cuda-13.3/``
   * - CUDA reported by driver
     - 13.2
     -
   * - EDT PDV
     - 6.2.1
     - ``/opt/EDTpdv``
   * - MAGMA
     - 2.10.0
     - ``/usr/local/magma-2.10.0``
   * - OpenBLAS
     - archive package
     - ``/usr/lib/x86_64-linux-gnu/openblas-pthread``
   * - Python
     - 3.14.4
     - ``/opt/rtc_python/rtc_venv3.14.4``
   * - MILK
     - 1.03.00
     - ``/usr/local/milk-1.03.00``
   * - CACAO
     - via MILK plugin
     - ``/usr/local/cacao``
   * - RTC application
     - [TBD]
     -

----

11. Troubleshooting
===================

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Symptom
     - Resolution
   * - NVIDIA installer aborts on ``PREEMPT_RT``
     - Run with ``IGNORE_PREEMPT_RT_PRESENCE=1``. Note the spelling;
       ``PRESENTS`` has no effect.
   * - ``nvidia-smi`` reports no devices
     - Read ``dmesg`` first. Check ``lsmod | grep nvidia`` and
       ``lsmod | grep nouveau``. If the module loads but reports the card as
       unsupported, the proprietary flavour was installed instead of MIT/GPL;
       reinstall (:ref:`section-nvidia`).
   * - Kernel module blocked by Secure Boot
     - ``mokutil --list-enrolled`` and ``mokutil --sb-state``. Re-import and
       complete enrollment at the blue screen (:ref:`section-mok`). Each module
       family has its own key; both must be enrolled.
   * - nouveau still loaded
     - Confirm the blacklist file in ``/etc/modprobe.d/`` and that initramfs was
       rebuilt. Re-run the installer answering ``y`` to both.
   * - ``nvcc`` not found
     - Confirm ``/usr/local/cuda-13.3/bin`` is on ``PATH`` via
       ``~/.bashrc_rtc``, and that ``~/.bashrc`` sources that file. Open a new
       login shell.
   * - cuda-samples cmake cannot find CUDA
     - Check ``which nvcc``, ``ldconfig -p | grep cudart`` and
       ``/etc/ld.so.conf.d/cuda-13-3.conf`` (:ref:`section-cuda-paths`). Other
       "not found" components are usually graphics-related and benign.
   * - CUDA and driver version mismatch warning
     - The reference build pairs CUDA 13.3.1 with driver 595.91.07, outside
       NVIDIA's stated support. If GPU code fails at runtime, install a newer
       driver or roll CUDA back (:ref:`section-sw-pending`).
   * - EDT DKMS build fails
     - ``BUILD_EXCLUSIVE`` mismatch. Apply the override in ``/etc/dkms/`` and
       build with explicit ``-k "$(uname -r)"`` (:ref:`section-edt-dkms`).
       Recheck after any kernel update.
   * - ``pciload`` does not report the framegrabber
     - Confirm the card is in ``lspci`` and ``lsmod | grep edt`` shows the
       module. If the card is absent, reseat it.
   * - MAGMA build cannot find OpenBLAS
     - Confirm ``libopenblas-dev`` is installed and ``OPENBLASDIR`` in
       ``make.inc`` matches the installed path. Clean and rebuild.
   * - ``pkg-config --cflags magma`` errors
     - Malformed ``Cflags`` line in the generated ``magma.pc``
       (:ref:`section-magma-pkgconfig`).
   * - MILK build fails in the CACAO LICENSES directory
     - Create the empty ``CMakeLists.txt`` and rebuild (:ref:`section-milk`).
   * - ``python3-config`` not found
     - Create the symlink from ``python3.14-config`` and confirm
       ``python3.14-dev`` is installed.
   * - MILK cannot locate MAGMA
     - Check ``echo $PKG_CONFIG_PATH`` and ``pkg-config --cflags magma``. If
       pkg-config itself errors, fix :ref:`section-magma-pkgconfig` first.
   * - ``/milk/shm`` missing after reboot
     - Confirm the ``fstab`` entry and the mount point exist, then
       ``sudo systemctl daemon-reload`` and ``sudo mount /milk/shm``.
   * - Compiles cleanly but fails at runtime with missing symbols
     - Toolchain mixing. Check ``which gcc``, ``which python``, ``ldd`` against
       the failing library and ``$LD_LIBRARY_PATH``. Rebuild with the correct
       environment active.

----

.. _section-sw-pending:

12. Pending Tasks
=================

* [ ] **SW-1: RTC application layer.** The application is the SIGHT Palomar
  instrument software. As of 2026-10-15 it has no configuration or service
  definitions yet, and its interfaces will be defined later. Largest open item
  in the build. ``/data/repos/pyMilk`` is present but not yet covered by this
  page.
* [ ] **SW-2: CUDA and driver pairing.** CUDA 13.3.1 requests driver 610.00 or
  later; 595.91.07 is installed. ``deviceQuery`` and ``vectorAdd`` pass on this
  pairing (2026-10-15), but it remains outside NVIDIA's stated support.
  Decision: move to the most recent NVIDIA driver, then update
  :ref:`section-nvidia` and re-run :ref:`section-sw-verify`.
* [x] **SW-3: NVIDIA modsign certificate ID.** Resolved 2026-10-15: the key on
  disk is ``9A20B563``. A second, stale NVIDIA installer key is still enrolled;
  remove it with ``mokutil --delete`` at the next console session
  (:ref:`section-rec-mok`).
* [x] **SW-4: MILK environment variable location.** Resolved 2026-10-15: the
  MILK variables are defined only in ``~/.bashrc_rtc``.
* [ ] **SW-5: Shared memory sizing.** The tmpfs default (91.9 GB,
  ``root:root`` ``1777``) stands: no size cap is needed for now. Ownership is
  undetermined.
* [ ] **SW-6: Upstream workarounds.** Re-check the CACAO ``CMakeLists.txt`` and
  ``python3-config`` fixes after any MILK or Ubuntu update.
* [x] **SW-7: Update procedure.** Policy: no routine updates. The stack runs on
  a working, stable configuration until a change is forced; then update one
  layer at a time and re-run the verification for that layer and every layer
  above it.
* [ ] **SW-8: Nuvu camera configuration.** The framegrabber will capture from
  the Nuvu camera. Write its EDT camera config and replace the simulated camera
  test in :ref:`section-edt` with a real capture.

----

13. References
==============

* `NVIDIA Linux driver downloads <https://www.nvidia.com/en-us/drivers/>`_
* `CUDA Toolkit downloads <https://developer.nvidia.com/cuda-downloads>`_
* `cuda-samples <https://github.com/NVIDIA/cuda-samples>`_
* `MAGMA <https://icl.utk.edu/magma/>`_
* `MILK <https://github.com/milk-org/milk>`_
* `CACAO <https://github.com/cacao-org/cacao>`_
* `EDT PDV software <https://edt.com/>`_
