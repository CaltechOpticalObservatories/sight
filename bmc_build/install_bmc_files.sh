#!/bin/bash
# Install BMC's files for one mirror into the SDK, only after audit_profile.py passes on them
#   sudo ./install_bmc_files.sh [SERIAL]        (default 30CW009#052)
# Reads bmc_files/SERIAL.dm and the map and calibration files it names, audits them as the
# operator, then copies them into /opt/Boston Micromachines/{Profiles,Map,Calibration}.
# Never overwrites a different file. See README.rst, section 5.
set -euo pipefail

readonly PREFIX="/opt/Boston Micromachines"

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly files=$here/bmc_files
readonly serial=${1:-30CW009#052}
readonly profile=$files/$serial.dm

die() { echo "install_bmc_files: $*" >&2; exit 1; }
run() { echo "+ $*"; "$@"; }

install_file() {
    local source=$1 target="$PREFIX/$2/$(basename "$1")"
    [[ -f $source ]] || die "no $source"
    if [[ -e $target ]]; then
        cmp -s "$source" "$target" || die "$target exists and differs from $source"
        echo "already installed: $target"
    else
        run install -m 0644 -o root -g root "$source" "$target"
    fi
    sha256sum "$target"
}

((EUID == 0)) || die "run with sudo"
operator=${SUDO_USER:?run through sudo}
[[ -d $PREFIX/Profiles ]] || die "the SDK is not installed; run install_bmc_sdk.sh first"
[[ -f $profile ]] || die "no $profile; copy BMC's files into $files first"

# Audit as the operator, so nothing runs Python as root
sudo -u "$operator" "$here/run.sh" audit_profile.py "$profile" --maps "$files" \
    --calibrations "$files" || die "the audit failed; nothing was installed"
report=$(find "$here/logs" -name "audit_profile_${serial}_*.json" | sort | tail -n 1)
read -r map calibration < <("$here/venv/bin/python" -I -c \
    'import json, sys; e = json.load(open(sys.argv[1]))["entries"]; print(e.get("map", ""), e.get("calibration", ""))' \
    "$report")

install_file "$profile" Profiles
install_file "$files/$map" Map
if [[ -n $calibration ]]; then
    install_file "$files/$calibration" Calibration
fi
echo "done"
