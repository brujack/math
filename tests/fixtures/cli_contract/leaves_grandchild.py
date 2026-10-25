#!/usr/bin/env python3
"""Stub CLI that exits 0 but leaves a long-lived, silent grandchild behind."""

import subprocess
import sys

SMOKE_SIZE = 2
LARGE_RUN_THRESHOLD: int | None = None

SLEEPER = "import time; time.sleep(300)  # cli_contract_leftover"


def main() -> None:
    grandchild = subprocess.Popen(
        [sys.executable, "-c", SLEEPER],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with open("gc.pid", "w") as handle:
        handle.write(str(grandchild.pid))


if __name__ == "__main__":
    main()
