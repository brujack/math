"""Snyk probe: deliberate command injection; never merged."""

import subprocess
import sys

subprocess.run(sys.argv[1], shell=True, check=False)
