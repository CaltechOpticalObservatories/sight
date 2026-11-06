#!/bin/bash
# Run one bring-up script with the venv (SDK 4.12.0: no EDT shim, no preload)
# usage: run.sh SCRIPT.py [ARGS...]   (output is also saved to logs/SCRIPT_<utc>.out)
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
script=${1:?usage: run.sh SCRIPT.py [ARGS...]}
shift
mkdir -p "$here/logs"
out="$here/logs/${script%.py}_$(date -u +%Y%m%dT%H%M%SZ).out"
echo "run.sh: $script $* ($(uname -r), driver $(cat "$here/venv/DRIVER_VERSION" 2>/dev/null))" | tee "$out"
set +e
"$here/venv/bin/python" -B -u "$here/scripts/$script" "$@" 2>&1 | tee -a "$out"
status=${PIPESTATUS[0]}
echo "run.sh: exit $status" | tee -a "$out"
exit "$status"
