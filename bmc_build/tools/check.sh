#!/bin/bash
# Run every software check: the driver's own suite (fake SDK) and the harness's tests
# and linters. Needs no SDK and no hardware. Output also goes to logs/check_<utc>.out
set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export PATH=$here/venv/bin:$PATH
mkdir -p "$here/logs"
exec > >(tee "$here/logs/check_$(date -u +%Y%m%dT%H%M%SZ).out") 2>&1
echo "check.sh: driver $(cat "$here/venv/DRIVER_VERSION")"

failed=()
step() {
    echo "== $*"
    "$@" || failed+=("$*")
}

cd "$here/driver"
step pytest -q -p no:cacheprovider
step mypy --cache-dir=/dev/null bmc_dm.py test_bmc_dm.py
step pylint --no-docstring-rgx='^$' bmc_dm.py test_bmc_dm.py
step ruff check --no-cache .
step ruff format --no-cache --check .

cd "$here"
# The driver clone gives mypy the typed bmc_dm source (the installed copy has no py.typed)
export PYTHONPATH=$here/scripts:$here/tests MYPYPATH=$here/scripts:$here/tests:$here/driver
step pytest -q
step mypy --cache-dir=/dev/null scripts tests
step pylint --no-docstring-rgx='^$' scripts/*.py tests/*.py
step ruff check --no-cache scripts tests
step ruff format --no-cache --check scripts tests
shell_scripts=("$here"/*.sh "$here"/tools/*.sh)
for script in "${shell_scripts[@]}"; do
    step bash -n "$script"
done
if command -v shellcheck >/dev/null; then
    step shellcheck "${shell_scripts[@]}"
else
    echo "== shellcheck not installed; skipped"
fi

if ((${#failed[@]})); then
    printf 'check.sh: FAILED: %s\n' "${failed[@]}"
    exit 1
fi
echo "check.sh: all passed"
