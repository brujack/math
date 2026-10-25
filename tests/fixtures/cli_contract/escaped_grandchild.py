#!/usr/bin/env python3
"""Stub CLI whose grandchild leaves the process group and holds stdout open.

A group kill cannot reach the grandchild, so the pipes never reach end of file
and the harness's drain after the kill must give up instead of waiting.
"""

import os
import subprocess
import sys

# The test owns this path so it can kill the sleeper even if the harness raises.
PID_FILE_ENV = "CLI_CONTRACT_PID_FILE"

SMOKE_SIZE = 2
LARGE_RUN_THRESHOLD: int | None = None

SLEEPER = "import os, time; os.setsid(); time.sleep(30)  # cli_contract_escaped"


def main() -> None:
    print("partial output", flush=True)
    grandchild = subprocess.Popen([sys.executable, "-c", SLEEPER])
    with open(os.environ.get(PID_FILE_ENV, "esc.pid"), "w") as handle:
        handle.write(str(grandchild.pid))
    sys.stdin.readline()


if __name__ == "__main__":
    main()
