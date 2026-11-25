#!/bin/bash
# Install the BMC DM-SDK built in sdk/ and its PCIe kernel module on the RTC
#   sudo ./install_bmc_sdk.sh [--user NAME] [--keep-bmc-permissions]
# Checks the reviewed build, signs bmc_mdrv.ko with the host's Secure Boot key (MOK), runs
# BMC's install.sh --pcie (SDK in /opt, ld.so entry, udev rules, module load and autoload),
# then limits /dev/bmc_mdrv* to group bmc-dm. Loading the module writes nothing to the
# card. Undo with uninstall_bmc_sdk.sh. See README.rst, section 4.
set -euo pipefail

readonly PREFIX="/opt/Boston Micromachines"
readonly KERNEL=7.0.0-38-realtime
readonly PCI_ID=1a8f:2000
readonly GROUP=bmc-dm
readonly UDEV_RULE=/etc/udev/rules.d/60-bmc-PCIe.rules
readonly MOK_DIR=/var/lib/shim-signed/mok
readonly MOK_SIGNER="hesperus Secure Boot Module Signature key"

# The reviewed files: the patched DM-SDK 4.1.3 install.sh, and the module built from it
# (unsigned; a signature is appended after MODULE_SIZE bytes)
readonly SHA_INSTALL=ee93664b15f84fbb5574b0e575d94befff725e5883466fa8ec8b288776204bb3
readonly SHA_MODULE=adac2642a52f8dfdc0b6938a5de3891d9891d99ce683ef2346e41e0ee8458d5c
readonly MODULE_SIZE=425600

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly sdk=$here/sdk/dm-sdk-4.1.3-ubuntu26
readonly module=$sdk/dm-sdk-4.1.3/linux-mdrv-pcie/bin/bmc_mdrv.ko
start=$(date +%s)

die() { echo "install_bmc_sdk: $*" >&2; exit 1; }
run() { echo "+ $*"; "$@"; }

operator=${SUDO_USER:-}
keep_permissions=false
while (($# > 0)); do
    case $1 in
        --user) operator=${2:?--user needs a name}; shift 2 ;;
        --keep-bmc-permissions) keep_permissions=true; shift ;;
        *) die "unknown option $1" ;;
    esac
done

check_sha() {
    echo "$1  $2" | sha256sum --check --quiet - || die "$2 differs from the reviewed file"
}

preflight() {
    ((EUID == 0)) || die "run with sudo"
    [[ -n $operator ]] && getent passwd "$operator" >/dev/null \
        || die "no operator: run through sudo or pass --user NAME"
    [[ $(uname -r) == "$KERNEL" ]] || die "kernel is $(uname -r); the module was built for $KERNEL"
    [[ ! -e $PREFIX ]] || die "$PREFIX already exists; run uninstall_bmc_sdk.sh first"
    lspci -n -d "$PCI_ID" | grep -q . || die "no BMC PCIe card ($PCI_ID) found"
    check_sha "$SHA_INSTALL" "$sdk/install.sh"
    [[ -f $module ]] || die "no $module; run tools/build_sdk.sh --pcie first"
    [[ $(modinfo -F vermagic "$module") == "$KERNEL "* ]] || die "$module is not built for $KERNEL"
    # Compare only the module itself, so an earlier signature does not hide a different build
    [[ $(head -c "$MODULE_SIZE" "$module" | sha256sum | cut -d' ' -f1) == "$SHA_MODULE" ]] \
        || die "$module differs from the reviewed build"
    mokutil --test-key "$MOK_DIR/MOK.der" 2>&1 | grep -q "already enrolled" \
        || die "$MOK_DIR/MOK.der is not enrolled for Secure Boot"
    echo "preflight ok: operator $operator, kernel $KERNEL, card $PCI_ID, $(mokutil --sb-state)"
}

sign_module() {
    local signer
    signer=$(modinfo -F signer "$module")
    if [[ -z $signer ]]; then
        run kmodsign sha512 "$MOK_DIR/MOK.priv" "$MOK_DIR/MOK.der" "$module"
        run chown "$operator:" "$module"
        signer=$(modinfo -F signer "$module")
    fi
    [[ $signer == "$MOK_SIGNER" ]] || die "$module is signed by '$signer', not '$MOK_SIGNER'"
    echo "module signed by: $signer"
}

restrict_permissions() {
    run groupadd -f "$GROUP"
    run usermod -aG "$GROUP" "$operator"
    # BMC's rule gives every local user write access to the card's actuator registers
    echo "+ write $UDEV_RULE (group $GROUP, mode 0660)"
    echo "SUBSYSTEM==\"bmc_mdrv\", KERNEL==\"bmc_mdrv[0-9]\", GROUP=\"$GROUP\", MODE=\"0660\"" \
        >"$UDEV_RULE"
    run udevadm control --reload-rules
    run udevadm trigger --subsystem-match=bmc_mdrv
    run udevadm settle
}

verify() {
    lsmod | grep -q '^bmc_mdrv ' || die "bmc_mdrv is not loaded"
    lspci -k -d "$PCI_ID" | grep -q "Kernel driver in use: bmc_mdrv" \
        || die "bmc_mdrv did not bind to the card"
    ls -l /dev/bmc_mdrv*
    ls "$PREFIX/lib/python3/bmc" "$PREFIX/sys/bin/bmc_ltest"
    if journalctl -k --no-pager --since "@$start" | grep -iE "\bbug\b|\bwarning\b|signature|lockdown"; then
        die "the kernel log above needs checking before the card is used"
    fi
    echo
    echo "done. $operator must log in again to be in group $GROUP."
}

preflight
sign_module
run "$sdk/install.sh" --pcie
if $keep_permissions; then
    echo "keeping BMC's udev rule: /dev/bmc_mdrv* is writable by every local user"
else
    restrict_permissions
fi
verify
