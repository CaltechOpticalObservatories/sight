#!/bin/bash
# Contend the EDT driver lock: register, re-register and close events on all three
# channels in parallel, then report hangs and kernel BUGs. Camera may stay off.
# usage: stress_events.sh [ITERATIONS]   (needs the edt_event_fix probe next to it, or PROBE)
set -uo pipefail

readonly ITERATIONS=${1:-50}
readonly PROBE=${PROBE:-$(dirname "$(realpath "$0")")/edt_event_fix}
since=$(date '+%F %T')

run_channel() {
    local channel=$1 hung=0
    for _ in $(seq "$ITERATIONS"); do
        "$PROBE" "$channel" 1 1 3 1 > /dev/null || hung=$((hung + 1))
    done
    echo "channel $channel: $ITERATIONS runs, $hung hung"
}

[[ -z $(fuser /dev/pdv0_* 2>/dev/null) ]] || { echo "board in use, not starting"; exit 1; }
for channel in 0 1 2; do
    run_channel "$channel" &
done
wait
echo "kernel log since $since:"
journalctl -k --since "$since" --no-pager -o cat | grep -E "BUG|WARNING|edt_pci_pdv|lockup" \
    || echo "  no BUG, WARNING or EDT messages"
