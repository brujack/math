#!/usr/bin/env python3
"""Weakening driver for the per-PR Python mutation gate (spec R7, R8, R12, R17).

`judge --dir <dir> --base <sha> --work <dir> --after-head [--repo <root>]` decides
whether the merge-base test suite of a sub-project can be replayed against head
mutants. `--dir` is a working copy of the sub-project whose basename is the
sub-project's directory in the repo; the module name is that basename with `-`
replaced by `_`.

Exit codes: 0 judgeable (signature at `<work>/base-sig.json`), 1 red (message on
stdout), 2 usage error (including a missing `--after-head`), 3 no base test file at
the merge base (`no base test file: weakening check skipped`), 4 infrastructure
failure (`base suite unjudgeable: infrastructure: <cause>`, a bad `--base` or git
failure, or a malformed signature after the runner exited 0).
"""

import argparse
import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

RUNNER = Path(__file__).resolve().with_name("mutation_base_runner.py")
UNJUDGEABLE = "base suite unjudgeable: "
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
CLASS_SETUP_PREFIXES = ("setUpClass (", "setUpModule (")
FAILED_TEST_PREFIX = "unittest.loader._FailedTest"

Signature = dict[str, Any]


def git(repo: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}
    return subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def git_show(repo: str, base: str, path: str) -> str | None:
    """Content of `path` at `base`, or None when it does not exist there."""
    result = git(repo, "show", f"{base}:{path}")
    return result.stdout if result.returncode == 0 else None


def read_optional(path: Path) -> str | None:
    return path.read_text() if path.is_file() else None


def cosmic_ray_value(text: str | None, key: str) -> object:
    """`[cosmic-ray] <key>` of a toml text; None when absent or unparseable."""
    if text is None:
        return None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    section = data.get("cosmic-ray")
    return section.get(key) if isinstance(section, dict) else None


def r8_message(module: str, head_toml: str | None, base_toml: str | None) -> str | None:
    want = f"python3 -m unittest test_{module}"
    if all(cosmic_ray_value(t, "test-command") == want for t in (head_toml, base_toml)):
        return None
    return f"{UNJUDGEABLE}test-command must be {want}"


def base_timeout(base_toml: str | None) -> float | None:
    value = cosmic_ray_value(base_toml, "timeout")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value)


@dataclass
class Recording:
    """One recorder run: a signature, or `problem` (red) or `infra` (exit 4)."""

    signature: Signature | None = None
    problem: str | None = None
    infra: str | None = None


def kill_group(pid: int) -> None:
    """Kill the process group `pid` leads; an already-empty group is the normal case."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def runner_problem(returncode: int, err_path: Path) -> str:
    lines = [line for line in err_path.read_text().splitlines() if line.strip()]
    tail = lines[-1] if lines else "no output"
    return f"base runner exited {returncode}: {tail}"


def valid_signature(data: object) -> bool:
    return isinstance(data, dict) and all(
        isinstance(entry, dict)
        and isinstance(entry.get("outcome"), str)
        and isinstance(entry.get("error"), list)
        and type(entry.get("setup_error")) is bool
        for entry in data.values()
    )


def load_recording(sig_path: Path) -> Recording:
    try:
        data = json.loads(sig_path.read_text())
    except (OSError, ValueError):
        return Recording(infra="malformed base signature")
    if not valid_signature(data):
        return Recording(infra="malformed base signature")
    return Recording(signature=data)


def record(work_dir: Path, test_name: str, sig_path: Path, timeout: float) -> Recording:
    """Run the base runner once in its own process group; stderr goes to a file so a
    descendant that outlives the group cannot hold a pipe open and hang the wait."""
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, str(RUNNER), "record", str(sig_path), test_name]
    err_path = sig_path.with_suffix(".err")
    with (
        err_path.open("w") as err,
        subprocess.Popen(
            cmd,
            cwd=work_dir,
            env=env,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=err,
        ) as proc,
    ):
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_group(proc.pid)
            proc.wait()
            return Recording(problem=f"base suite timed out after {timeout:g}s")
        finally:
            kill_group(proc.pid)
    if proc.returncode != 0:
        return Recording(problem=runner_problem(proc.returncode, err_path))
    return load_recording(sig_path)


def differing_ids(first: Signature, second: Signature) -> list[str]:
    return sorted(
        i for i in first.keys() | second.keys() if first.get(i) != second.get(i)
    )


def class_setup_failed(entry: dict[str, Any]) -> bool:
    return entry["outcome"] == "error"


def signature_problems(
    first: Signature, second: Signature
) -> list[tuple[str, list[str]]]:
    checks = [
        (
            "test file failed to import",
            [i for i in first if i.startswith(FAILED_TEST_PREFIX)],
        ),
        (
            "class or module setUp error",
            [
                i
                for i, e in first.items()
                if i.startswith(CLASS_SETUP_PREFIXES) and class_setup_failed(e)
            ],
        ),
        ("per-test setUp error", [i for i, e in first.items() if e["setup_error"]]),
        ("two recordings differ", differing_ids(first, second)),
    ]
    return [(cause, sorted(ids)) for cause, ids in checks if ids]


def report_red(problems: list[tuple[str, list[str]]]) -> int:
    for cause, ids in problems:
        print(f"{UNJUDGEABLE}{cause}")
        for test_id in ids:
            print(f"  {test_id}")
    return 1


def infra_failure(cause: str) -> int:
    print(f"{UNJUDGEABLE}infrastructure: {cause}")
    return 4


def judge_signatures(work_dir: Path, test_name: str, work: Path, timeout: float) -> int:
    runs: list[Recording] = []
    for number in (1, 2):
        run = record(work_dir, test_name, work / f"base-sig-{number}.json", timeout)
        if run.infra:
            return infra_failure(run.infra)
        if run.problem:
            return report_red([(run.problem, [])])
        runs.append(run)
    first, second = (run.signature or {} for run in runs)
    problems = signature_problems(first, second)
    if problems:
        return report_red(problems)
    (work / "base-sig.json").write_text(json.dumps(first, sort_keys=True))
    print(f"base suite judgeable: {len(first)} tests recorded")
    return 0


def resolve_repo(args: argparse.Namespace) -> str | None:
    if args.repo:
        return args.repo
    result = git(".", "rev-parse", "--show-toplevel")
    return result.stdout.strip() if result.returncode == 0 else None


def judge(args: argparse.Namespace) -> int:
    work_dir = Path(args.dir)
    subdir = work_dir.name
    module = subdir.replace("-", "_")
    repo = resolve_repo(args)
    if repo is None:
        return infra_failure("not inside a git repository (pass --repo)")
    if git(repo, "cat-file", "-e", f"{args.base}^{{commit}}").returncode != 0:
        return infra_failure(f"base {args.base} is not a commit in {repo}")
    base_source = git_show(repo, args.base, f"{subdir}/test_{module}.py")
    if base_source is None:
        print("no base test file: weakening check skipped")
        return 3
    base_toml = git_show(repo, args.base, f"{subdir}/cosmic-ray.toml")
    message = r8_message(module, read_optional(work_dir / "cosmic-ray.toml"), base_toml)
    if message:
        print(message)
        return 1
    if not (work_dir / f"test_{module}.py").is_file():
        print(f"test_{module}.py deleted")
        return 1
    timeout = base_timeout(base_toml)
    if timeout is None:
        print(
            f"{UNJUDGEABLE}merge-base cosmic-ray.toml has no positive numeric timeout"
        )
        return 1
    test_name = f"test_{module}_base.py"
    (work_dir / test_name).write_text(base_source)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    return judge_signatures(work_dir, test_name, work, timeout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    judge_parser = sub.add_parser("judge")
    judge_parser.add_argument("--dir", required=True)
    judge_parser.add_argument("--base", required=True)
    judge_parser.add_argument("--work", required=True)
    judge_parser.add_argument("--repo")
    judge_parser.add_argument("--after-head", action="store_true")
    return parser


def main(argv: list[str]) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exit_request:
        return int(exit_request.code or 0) if isinstance(exit_request.code, int) else 2
    if not args.after_head:
        print(
            "mutation_weakening: judge refuses to run without --after-head",
            file=sys.stderr,
        )
        return 2
    return judge(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
