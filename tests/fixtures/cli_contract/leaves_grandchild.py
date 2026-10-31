"""Stub CLI that exits 0 but leaves a long-lived, silent grandchild behind."""

import os
import subprocess
import sys
import tempfile

# The test owns this file so it can kill the sleeper even if the harness raises.
# The name comes from the parent (test) pid and a fixed tag, not from the
# environment, so no outside input reaches open().
PID_FILE_TAG = "leftover"

SMOKE_SIZE = 2
LARGE_RUN_THRESHOLD: int | None = None

SLEEPER = "import time; time.sleep(30)  # cli_contract_leftover"


def _pid_file_path() -> str:
    name = f"cli_contract_{os.getppid()}_{PID_FILE_TAG}.pid"
    return os.path.join(tempfile.gettempdir(), name)


def main() -> None:
    grandchild = subprocess.Popen(
        [sys.executable, "-c", SLEEPER],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with open(_pid_file_path(), "w") as handle:
        handle.write(str(grandchild.pid))


if __name__ == "__main__":
    main()
