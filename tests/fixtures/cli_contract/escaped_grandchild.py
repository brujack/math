#!/usr/bin/env python3
"""Stub CLI whose grandchild leaves the process group and holds stdout open.

A group kill cannot reach the grandchild, so the pipes never reach end of file
and the harness's drain after the kill must give up instead of waiting.
"""

import os
import subprocess
import sys
import tempfile

# The test owns this file so it can kill the sleeper even if the harness raises.
# The name comes from the parent (test) pid and a fixed tag, not from the
# environment, so no outside input reaches open().
PID_FILE_TAG = "escaped"

SMOKE_SIZE = 2
LARGE_RUN_THRESHOLD: int | None = None

SLEEPER = "import os, time; os.setsid(); time.sleep(30)  # cli_contract_escaped"


def _pid_file_path() -> str:
    name = f"cli_contract_{os.getppid()}_{PID_FILE_TAG}.pid"
    return os.path.join(tempfile.gettempdir(), name)


def main() -> None:
    print("partial output", flush=True)
    grandchild = subprocess.Popen([sys.executable, "-c", SLEEPER])
    with open(_pid_file_path(), "w") as handle:
        handle.write(str(grandchild.pid))
    sys.stdin.readline()


if __name__ == "__main__":
    main()
