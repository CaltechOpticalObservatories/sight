#!/bin/bash
# Undo install_nuvu_sdk.sh: remove /opt/NuvuCameras, the ld.so entry and the group
#   sudo ./uninstall_nuvu_sdk.sh
set -euo pipefail

readonly DEST=/opt/NuvuCameras
readonly GROUP=nuvu-cameras
readonly LDCONF=/etc/ld.so.conf.d/nuvu.conf

die() { echo "uninstall_nuvu_sdk: $*" >&2; exit 1; }
run() { echo "+ $*"; "$@"; }

((EUID == 0)) || die "run with sudo"
if grep -lq "$DEST/" /proc/[0-9]*/maps 2>/dev/null; then
    die "a process still has the SDK loaded: $(grep -l "$DEST/" /proc/[0-9]*/maps 2>/dev/null | cut -d/ -f3 | xargs)"
fi
run rm -rf "$DEST"
run rm -f "$LDCONF"
run ldconfig
if getent group "$GROUP" >/dev/null; then
    run groupdel "$GROUP"
fi
echo "done"
