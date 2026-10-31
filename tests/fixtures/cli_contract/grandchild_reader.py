"""Stub CLI that leaves a long-lived grandchild, then silently reads stdin.

The grandchild inherits stdout and stderr, as multiprocessing workers and the
resource_tracker do; killing only this process would leave the harness waiting
on pipes the grandchild still holds open.
"""

import os
import subprocess
import sys
import tempfile

# The test owns this file so it can kill the sleeper even if the harness raises.
# The name comes from the parent (test) pid and a fixed tag, not from the
# environment, so no outside input reaches open().
PID_FILE_TAG = "reader"

SMOKE_SIZE = 2
LARGE_RUN_THRESHOLD: int | None = None

SLEEPER = "import time; time.sleep(30)  # cli_contract_grandchild"


def _pid_file_path() -> str:
    name = f"cli_contract_{os.getppid()}_{PID_FILE_TAG}.pid"
    return os.path.join(tempfile.gettempdir(), name)


def main() -> None:
    grandchild = subprocess.Popen([sys.executable, "-c", SLEEPER])
    with open(_pid_file_path(), "w") as handle:
        handle.write(str(grandchild.pid))
    sys.stdin.readline()


if __name__ == "__main__":
    main()
