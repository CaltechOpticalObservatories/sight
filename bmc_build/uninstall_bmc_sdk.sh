#!/bin/bash
# Undo install_bmc_sdk.sh: unload bmc_mdrv, remove the SDK, its system files and the group
#   sudo ./uninstall_bmc_sdk.sh
# Unloading writes nothing to the card. Removing /opt also removes BMC's mirror files there;
# the originals stay in bmc_files/.
set -euo pipefail

readonly PREFIX="/opt/Boston Micromachines"
readonly GROUP=bmc-dm

die() { echo "uninstall_bmc_sdk: $*" >&2; exit 1; }
run() { echo "+ $*"; "$@"; }

((EUID == 0)) || die "run with sudo"
if compgen -G "/dev/bmc_mdrv*" >/dev/null && fuser /dev/bmc_mdrv* >/dev/null 2>&1; then
    die "a process has the card open: $(fuser /dev/bmc_mdrv* 2>&1 | xargs)"
fi
if grep -lq "$PREFIX/" /proc/[0-9]*/maps 2>/dev/null; then
    die "a process still has the SDK loaded: $(grep -l "$PREFIX/" /proc/[0-9]*/maps 2>/dev/null | cut -d/ -f3 | xargs)"
fi
if lsmod | grep -q '^bmc_mdrv '; then
    run modprobe -r bmc_mdrv
fi
run rm -rf "$PREFIX"
run rm -f /etc/ld.so.conf.d/bmc-dmsdk.conf
run ldconfig
run rm -f /etc/udev/rules.d/60-bmc-usb.rules /etc/udev/rules.d/60-bmc-PCIe.rules
run udevadm control --reload-rules
run rm -f /etc/modules-load.d/bmc_mdrv.conf
run rm -f "/lib/modules/$(uname -r)/extra/bmc_mdrv.ko"
run depmod -a
if getent group "$GROUP" >/dev/null; then
    run groupdel "$GROUP"
fi
echo "done"
