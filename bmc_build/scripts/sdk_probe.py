"""Phase 0 SDK check: import BMC's Python module and print its version, opening no DM

Exit status: 0 if the module loads and reports EXPECTED_VERSION, 1 otherwise.
"""

import importlib
import sys
from typing import Final

EXPECTED_VERSION: Final = "4.1.3"


def main() -> int:
    """Import bmc and report where it came from and its version"""
    try:
        # Imported by name so a missing SDK is reported rather than a traceback
        bmc = importlib.import_module("bmc")
    except ImportError as error:
        print(f"sdk_probe: cannot import bmc: {error}", flush=True)
        return 1
    # version_string() wraps the static BMCVersionString(), so it is safe without open_dm
    version = bmc.BmcDm().version_string()
    print(f"sdk_probe: bmc from {bmc.__file__}", flush=True)
    print(f"sdk_probe: version {version!r}, NO_ERR {bmc.NO_ERR}", flush=True)
    if EXPECTED_VERSION not in version:
        print(f"sdk_probe: expected version {EXPECTED_VERSION}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
