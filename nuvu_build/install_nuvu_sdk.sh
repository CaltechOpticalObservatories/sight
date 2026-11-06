#!/bin/bash
# Install Nuvu SDK 4.12.0 by hand on a host the vendor installer refuses (Ubuntu 26.04)
#   sudo ./install_nuvu_sdk.sh [--user NAME] [--installer DIR] [--with-status-log]
# Install the nuvu-cameras group (with the operator in it), /opt/NuvuCameras, an ld.so
# entry and the EDT plugin; touch no camera and no EDT board. See README.rst, section 3
# Undo with uninstall_nuvu_sdk.sh
set -euo pipefail

readonly DEST=/opt/NuvuCameras
readonly GROUP=nuvu-cameras
readonly LDCONF=/etc/ld.so.conf.d/nuvu.conf
readonly LIBPDV=/opt/EDTpdv/libpdv.so.6.2.1
readonly SDK_VERSION=4.12.0

# The reviewed files: Nuvu SDK 4.12.0 (Ubuntu 22.04 build) and EDT PDV 6.2.1
readonly SHA_LIBNUVU=a8d24dc568042c1cf58c7aa34be1731c6874873fd7fa55d8c03e34792d6242b8
readonly SHA_PLUGIN=c40ac61fe3fad90a8ed7a3f419107fd9d6f722e4a3db9dbbf3d52ff207053e92
readonly SHA_PLUGIN_CFG=55810d32dd8094516f039139ab27dd3bc27694ca86176bba65dab32d6ca13bc4
readonly SHA_LIBPDV=db3b45e759bf2585e3a920101ba67bfc11a46f625bdebee81cd8b41616625150

die() { echo "install_nuvu_sdk: $*" >&2; exit 1; }
run() { echo "+ $*"; "$@"; }

operator=${SUDO_USER:-}
installer=""
with_status_log=false
while (($# > 0)); do
    case $1 in
        --user) operator=${2:?--user needs a name}; shift 2 ;;
        --installer) installer=${2:?--installer needs a directory}; shift 2 ;;
        --with-status-log) with_status_log=true; shift ;;
        *) die "unknown option $1" ;;
    esac
done
[[ -n $operator ]] || die "no operator: run through sudo or pass --user NAME"
operator_home=$(getent passwd "$operator" | cut -d: -f6) || die "unknown user $operator"
installer=${installer:-$operator_home/nuvu_build/NuvuSW_NuPixel_${SDK_VERSION}_ubuntu-22.04_x86_64/NuvuInstaller}
readonly plugin_src=$installer/Dependencies/Third-party/EDTpdv/nc_grab_edt

check_sha() {
    echo "$1  $2" | sha256sum --check --quiet - || die "$2 differs from the reviewed file"
}

preflight() {
    ((EUID == 0)) || die "run with sudo"
    [[ -d $installer/NuvuCameras ]] || die "no NuvuCameras directory in $installer"
    [[ ! -e $DEST ]] || die "$DEST already exists; run uninstall_nuvu_sdk.sh first"
    [[ ! -e $LDCONF ]] || die "$LDCONF already exists"
    check_sha "$SHA_LIBNUVU" "$installer/NuvuCameras/lib/libnuvu.so.$SDK_VERSION"
    check_sha "$SHA_PLUGIN" "$plugin_src/nc_grab_edt.so"
    check_sha "$SHA_PLUGIN_CFG" "$plugin_src/nc_16cl.cfg"
    check_sha "$SHA_LIBPDV" "$LIBPDV"
    grep -q '^edt_pci_pdv ' /proc/modules || die "EDT driver edt_pci_pdv is not loaded"
    # The plugin finds libpdv by soname through the ld.so cache
    ldconfig -p | grep "libpdv.so.6 .*=> /opt/EDTpdv/" >/dev/null || die "libpdv.so.6 is not in the ld.so cache"
    if [[ -e /var/run/reboot-required ]]; then
        echo "note: a reboot is pending; check edt_pci_pdv is loaded after it"
    fi
    echo "preflight ok: operator $operator, installer $installer"
}

install_files() {
    run groupadd -f "$GROUP"
    run usermod -aG "$GROUP" "$operator"
    run cp -a "$installer/NuvuCameras" "$DEST"
    run cp -a "$plugin_src" "$DEST/Plugins/"
    if $with_status_log; then
        run ln -s ../Extras/StatusLogging/nc_status_log "$DEST/Plugins/nc_status_log"
    fi
    run chown -R "root:$GROUP" "$DEST"
    run chmod -R u=rwX,g=rwX,o=rX "$DEST"
    # Lock files created by any group member stay in the group
    run chmod g+s "$DEST/LockFiles"
    echo "+ echo $DEST/lib > $LDCONF"
    echo "$DEST/lib" >"$LDCONF"
    run ldconfig
}

verify() {
    ls -l "$DEST/lib" "$DEST/Plugins" "$DEST/Plugins/nc_grab_edt"
    ldconfig -p | grep libnuvu
    getent group "$GROUP"
    sha256sum "$DEST/lib/libnuvu.so.$SDK_VERSION" "$DEST/Plugins/nc_grab_edt/nc_grab_edt.so"
    echo
    echo "done. $operator must log in again (or run 'newgrp $GROUP') to get the group."
}

preflight
install_files
verify
