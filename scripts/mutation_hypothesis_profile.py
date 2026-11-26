#!/usr/bin/env python3
"""Name-keyed Hypothesis profile for the mutation gate (R9) and its preflight (R10).

`write <dir>` creates <dir>/sitecustomize.py. Hypothesis derandomizes from a digest
of the test function's source, so a mutant that edits a test body would draw
different examples than the base run. The generated file keys the digest on
`__qualname__` instead, and loads a derandomized profile.

`preflight <dir>` proves the profile is active: two `@given` functions sharing a
`__qualname__` but with different bodies must draw the same first 10 examples.
Exit 0 when they do; exit 1 with the R10 message otherwise.
"""

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile

SITECUSTOMIZE = """\
import hashlib

import hypothesis.core
from hypothesis import HealthCheck, settings


def _name_keyed_digest(f):
    return hashlib.sha384(f.__qualname__.encode()).digest()


hypothesis.core.function_digest = _name_keyed_digest
settings.register_profile("mutation-gate", derandomize=True, database=None, deadline=None, suppress_health_check=list(HealthCheck))
settings.load_profile("mutation-gate")
"""

# Two functions, same __qualname__, different bodies; compare their first 10 draws.
PREFLIGHT_SCRIPT = """\
import sys

from hypothesis import given, strategies as st

seen_a = []
seen_b = []


def first(x):
    seen_a.append(x)


def second(x):
    seen_b.append(x + 0)


first.__qualname__ = second.__qualname__ = "preflight_test"
given(st.integers())(first)()
given(st.integers())(second)()
sys.exit(0 if seen_a[:10] == seen_b[:10] and len(seen_a) >= 10 else 1)
"""

PREFLIGHT_TIMEOUT_SECONDS = 120


def write_sitecustomize(directory: pathlib.Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "sitecustomize.py").write_text(SITECUSTOMIZE)


def _preflight_env(directory: pathlib.Path) -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(directory) + os.pathsep + existing if existing else str(directory)
    )
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _profile_active(directory: pathlib.Path) -> bool:
    with tempfile.TemporaryDirectory() as scratch:
        script = pathlib.Path(scratch) / "preflight.py"
        script.write_text(PREFLIGHT_SCRIPT)
        try:
            result = subprocess.run(
                [sys.executable, str(script)],
                env=_preflight_env(directory),
                capture_output=True,
                check=False,
                stdin=subprocess.DEVNULL,
                timeout=PREFLIGHT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return False
    return result.returncode == 0


def _hypothesis_version() -> str:
    try:
        import hypothesis
    except ImportError:
        return "unknown"
    return hypothesis.__version__


def _safe_profile_active(directory: pathlib.Path) -> bool:
    # Fail closed: any parent-side fault (unwritable TMPDIR, missing executable)
    # must read as "not active", never as a traceback or a pass.
    try:
        return _profile_active(directory)
    except Exception:  # noqa: BLE001
        return False


def preflight(directory: pathlib.Path) -> int:
    if _safe_profile_active(directory):
        return 0
    print(
        f"hypothesis profile not active (hypothesis {_hypothesis_version()})",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hypothesis profile and preflight for the mutation gate"
    )
    parser.add_argument("command", choices=["write", "preflight"])
    parser.add_argument("directory", type=pathlib.Path)
    args = parser.parse_args(argv)
    if args.command == "write":
        write_sitecustomize(args.directory)
        return 0
    return preflight(args.directory)


if __name__ == "__main__":
    sys.exit(main())
