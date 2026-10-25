#!/usr/bin/env python3
"""Stub CLI that leaves a long-lived grandchild, then silently reads stdin.

The grandchild inherits stdout and stderr, as multiprocessing workers and the
resource_tracker do; killing only this process would leave the harness waiting
on pipes the grandchild still holds open.
"""

import os
import subprocess
import sys

# The test owns this path so it can kill the sleeper even if the harness raises.
PID_FILE_ENV = "CLI_CONTRACT_PID_FILE"

SMOKE_SIZE = 2
LARGE_RUN_THRESHOLD: int | None = None

SLEEPER = "import time; time.sleep(30)  # cli_contract_grandchild"


def main() -> None:
    grandchild = subprocess.Popen([sys.executable, "-c", SLEEPER])
    with open(os.environ.get(PID_FILE_ENV, "gc.pid"), "w") as handle:
        handle.write(str(grandchild.pid))
    sys.stdin.readline()


if __name__ == "__main__":
    main()
