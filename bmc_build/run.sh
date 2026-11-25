#!/bin/bash
# Run one bring-up script with the venv and the BMC SDK
# usage: run.sh SCRIPT.py [ARGS...]   (output is also saved to logs/SCRIPT_<utc>.out)
# Uses the SDK installed in /opt/Boston Micromachines if there is one, otherwise the
# build staged in sdk/python by tools/build_sdk.sh; the first line names which
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
script=${1:?usage: run.sh SCRIPT.py [ARGS...]}
shift
opt="/opt/Boston Micromachines"
if [[ -d $opt/lib/python3/bmc ]]; then
    sdk=$opt/lib/python3
else
    sdk=$here/sdk/python
    export LD_LIBRARY_PATH=$here/sdk/dm-sdk-4.1.3-ubuntu26/dm-sdk-4.1.3/lib/linux-g++/release${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
fi
export PYTHONPATH=$sdk
session=$([[ -n ${TMUX:-} ]] && echo "in tmux" || echo "not in tmux")
mkdir -p "$here/logs"
out="$here/logs/${script%.py}_$(date -u +%Y%m%dT%H%M%SZ).out"
echo "run.sh: $script $* ($(uname -r), driver $(cat "$here/venv/DRIVER_VERSION"), sdk $sdk, $session)" | tee "$out"
set +e
"$here/venv/bin/python" -B -u -X faulthandler "$here/scripts/$script" "$@" 2>&1 | tee -a "$out"
status=${PIPESTATUS[0]}
echo "run.sh: exit $status" | tee -a "$out"
exit "$status"
