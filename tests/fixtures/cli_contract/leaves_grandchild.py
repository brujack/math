#!/usr/bin/env python3
"""Stub CLI that exits 0 but leaves a long-lived, silent grandchild behind."""

import os
import subprocess
import sys

# The test owns this path so it can kill the sleeper even if the harness raises.
PID_FILE_ENV = "CLI_CONTRACT_PID_FILE"

SMOKE_SIZE = 2
LARGE_RUN_THRESHOLD: int | None = None

SLEEPER = "import time; time.sleep(30)  # cli_contract_leftover"


def main() -> None:
    grandchild = subprocess.Popen(
        [sys.executable, "-c", SLEEPER],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with open(os.environ.get(PID_FILE_ENV, "gc.pid"), "w") as handle:
        handle.write(str(grandchild.pid))


if __name__ == "__main__":
    main()
