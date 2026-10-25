#!/usr/bin/env python3
"""Run the shared CLI contract matrix against one Python program.

Usage: cli_contract.py <module.py>

The program must define SMOKE_SIZE (int) and LARGE_RUN_THRESHOLD (int or None).
Each case runs the program as a subprocess in a fresh temporary directory with
an open, never-closed stdin pipe, so a program that reads stdin blocks and fails
on the timeout instead of reading end of input as "no".

Exit 0: every case passes; one line goes to stdout.
Exit 1: at least one case fails; each failure is printed, naming its case.
Exit 2: usage error (wrong argument count, missing file, or a program whose
        SMOKE_SIZE/LARGE_RUN_THRESHOLD cannot be read).
"""

import concurrent.futures
import dataclasses
import importlib.util
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable

# Module-level so tests can lower them; a silent stdin reader fails only by timeout.
CASE_TIMEOUT: float = 60
REFUSAL_TIMEOUT: float = 5

# The contract forbids a "?" anywhere on stdout, not only in a trailing prompt:
# a stub that asks a question is indistinguishable from one that reads an answer.
_PROMPT_MARKERS = ("?", "(y/n)")

# Seconds to wait for the pipes to drain after the process group is killed.
_DRAIN_TIMEOUT = 5


class ContractConfigError(Exception):
    """The program under test cannot be loaded or lacks the contract constants."""


@dataclasses.dataclass
class CaseResult:
    returncode: int | None
    stdout: str
    stderr: str
    files: dict[str, str]
    timed_out: bool


def load_constants(path: pathlib.Path) -> tuple[int, int | None]:
    """Import the program and return (SMOKE_SIZE, LARGE_RUN_THRESHOLD)."""
    spec = importlib.util.spec_from_file_location("cli_contract_target", path)
    if spec is None or spec.loader is None:
        raise ContractConfigError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        raise ContractConfigError(
            f"{path.name}: importing to read SMOKE_SIZE/LARGE_RUN_THRESHOLD "
            f"failed: {error!r}"
        ) from error
    smoke = getattr(module, "SMOKE_SIZE", None)
    if not isinstance(smoke, int) or isinstance(smoke, bool):
        raise ContractConfigError(f"{path.name}: SMOKE_SIZE must be an int")
    if not hasattr(module, "LARGE_RUN_THRESHOLD"):
        raise ContractConfigError(f"{path.name}: LARGE_RUN_THRESHOLD is not defined")
    threshold = module.LARGE_RUN_THRESHOLD
    if threshold is not None and (
        not isinstance(threshold, int) or isinstance(threshold, bool)
    ):
        raise ContractConfigError(
            f"{path.name}: LARGE_RUN_THRESHOLD must be an int or None"
        )
    return smoke, threshold


def _read_files(directory: pathlib.Path) -> dict[str, str]:
    return {
        str(item.relative_to(directory)): item.read_text(errors="replace")
        for item in sorted(directory.rglob("*"))
        if item.is_file()
    }


def _kill_group(proc: subprocess.Popen[str]) -> None:
    """SIGKILL the child's whole process group (it leads its own session)."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_case(
    path: pathlib.Path,
    args: list[str],
    stdin_text: str = "",
    timeout: float | None = None,
) -> CaseResult:
    """Run the program once in a fresh directory with an open stdin pipe.

    stdin_text must stay under the pipe buffer (4096 bytes is always safe): it
    is written before the process starts, so a larger text would block here.
    """
    limit = CASE_TIMEOUT if timeout is None else timeout
    read_end, write_end = os.pipe()
    try:
        # The write end stays open until the process is done: closing it would
        # hand a stdin reader end of input, which is the defect being detected.
        os.write(write_end, stdin_text.encode())
        with tempfile.TemporaryDirectory() as tmp:
            # Own session: workers the program spawns inherit its pipes, so a
            # timeout must kill the group or the drain below waits forever.
            proc = subprocess.Popen(
                [sys.executable, str(path.resolve()), *args],
                stdin=read_end,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=tmp,
                text=True,
                errors="replace",
                start_new_session=True,
            )
            timed_out = False
            try:
                try:
                    stdout, stderr = proc.communicate(timeout=limit)
                except subprocess.TimeoutExpired:
                    _kill_group(proc)
                    stdout, stderr = proc.communicate(timeout=_DRAIN_TIMEOUT)
                    timed_out = True
            except BaseException:
                _kill_group(proc)
                proc.wait()
                raise
            return CaseResult(
                returncode=None if timed_out else proc.returncode,
                stdout=stdout or "",
                stderr=stderr or "",
                files=_read_files(pathlib.Path(tmp)),
                timed_out=timed_out,
            )
    finally:
        os.close(read_end)
        os.close(write_end)


def _longest_line(files: dict[str, str]) -> str:
    lines = [line.strip() for text in files.values() for line in text.splitlines()]
    return max((line for line in lines if line), key=len, default="")


def _stdout_lines(result: CaseResult) -> list[str]:
    return [line.strip() for line in result.stdout.splitlines()]


def _common_problems(result: CaseResult) -> list[str]:
    """Checks shared by every case that runs the program at a valid size."""
    if result.timed_out:
        return ["timed out (a program reading stdin blocks on the open pipe)"]
    problems: list[str] = []
    if result.returncode != 0:
        problems.append(f"exit {result.returncode}, expected 0")
    longest = _longest_line(result.files)
    if not longest:
        problems.append("wrote no non-empty output file")
    for line in _stdout_lines(result):
        if any(marker in line for marker in _PROMPT_MARKERS):
            problems.append(f"stdout line looks like a prompt: {line!r}")
    if longest and longest in _stdout_lines(result):
        problems.append("stdout echoes the longest result line without --show")
    return problems


def _check_quiet(result: CaseResult) -> list[str]:
    return _common_problems(result)


def _check_show(result: CaseResult) -> list[str]:
    if result.timed_out:
        return ["timed out (a program reading stdin blocks on the open pipe)"]
    problems: list[str] = []
    if result.returncode != 0:
        problems.append(f"exit {result.returncode}, expected 0")
    longest = _longest_line(result.files)
    if not longest:
        problems.append("wrote no non-empty output file")
    elif longest not in _stdout_lines(result):
        problems.append("--show did not print the longest result line")
    return problems


def _check_refusal(result: CaseResult) -> list[str]:
    if result.timed_out:
        return ["timed out instead of refusing"]
    problems: list[str] = []
    if result.returncode != 1:
        problems.append(f"exit {result.returncode}, expected 1")
    if "--yes" not in result.stdout + result.stderr:
        problems.append("refusal does not name --yes")
    if result.files:
        problems.append(f"wrote files before confirmation: {sorted(result.files)}")
    return problems


def _check_usage(result: CaseResult) -> list[str]:
    if result.timed_out:
        return ["timed out with no arguments (it must exit 2, not wait on stdin)"]
    if result.returncode != 2:
        return [f"exit {result.returncode}, expected 2"]
    return []


@dataclasses.dataclass
class _Case:
    number: int
    label: str
    args: list[str]
    stdin_text: str
    timeout: float
    check: Callable[[CaseResult], list[str]]


def _build_cases(smoke: int, threshold: int | None) -> list[_Case]:
    size = str(smoke)
    cases = [
        _Case(1, "SIZE", [size], "", CASE_TIMEOUT, _check_quiet),
        _Case(2, "SIZE --show", [size, "--show"], "", CASE_TIMEOUT, _check_show),
        _Case(3, "--smoke", ["--smoke"], "", CASE_TIMEOUT, _check_quiet),
        _Case(4, "y on stdin", [size], "y\n", CASE_TIMEOUT, _check_quiet),
    ]
    if threshold is not None:
        cases.append(
            _Case(
                5,
                "THRESHOLD without --yes",
                [str(threshold)],
                "",
                REFUSAL_TIMEOUT,
                _check_refusal,
            )
        )
    else:
        cases.append(
            _Case(5, "SIZE --yes", [size, "--yes"], "", CASE_TIMEOUT, _check_quiet)
        )
    cases.append(_Case(6, "no arguments", [], "", CASE_TIMEOUT, _check_usage))
    return cases


def run_matrix(path: pathlib.Path) -> list[str]:
    """Run all six cases; return failure messages (empty when conforming)."""
    smoke, threshold = load_constants(path)
    cases = _build_cases(smoke, threshold)

    def execute(case: _Case) -> CaseResult:
        return run_case(path, case.args, case.stdin_text, case.timeout)

    # Cases are independent subprocesses; running them together keeps a program
    # that times out on every case from costing six timeouts in a row.
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(cases)) as pool:
        results = list(pool.map(execute, cases))
    return [
        f"case {case.number} ({case.label}): {problem}"
        for case, result in zip(cases, results, strict=True)
        for problem in case.check(result)
    ]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: cli_contract.py <module.py>", file=sys.stderr)
        return 2
    path = pathlib.Path(args[0])
    if not path.is_file():
        print(f"cli_contract: {path}: no such file", file=sys.stderr)
        return 2
    try:
        failures = run_matrix(path)
    except ContractConfigError as error:
        print(f"cli_contract: {error}", file=sys.stderr)
        return 2
    if failures:
        for failure in failures:
            print(f"cli_contract: {path.name}: {failure}")
        return 1
    print(f"cli_contract: {path.name}: all cases pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
