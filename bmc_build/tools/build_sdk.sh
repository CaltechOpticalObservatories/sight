#!/bin/bash
# Build the patched DM-SDK in sdk/ (no sudo) and stage its Python module in sdk/python/bmc,
# where run.sh finds it until the SDK is installed in /opt
#   tools/build_sdk.sh [--pcie]     --pcie also builds the PCIe card's kernel module
# Needs the apt packages build.sh lists. Installing (sudo ./install.sh) is a separate step
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
sdk=$here/sdk/dm-sdk-4.1.3-ubuntu26
release=$sdk/dm-sdk-4.1.3/lib/linux-g++/release
stage=$here/sdk/python/bmc
mkdir -p "$here/logs"
out="$here/logs/build_sdk_$(date -u +%Y%m%dT%H%M%SZ).out"

"$sdk/build.sh" "$@" 2>&1 | tee "$out"
mkdir -p "$stage"
cp -a "$release/python3/__init__.py" "$release/python3/bmc.py" "$release/python3/_bmc.so" "$stage/"
echo "build_sdk.sh: staged the bmc module in $stage" | tee -a "$out"
