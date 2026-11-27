#!/usr/bin/env python3
"""Weakening driver for the per-PR Python mutation gate (spec R7, R8, R12-R15, R17, R19, R27).

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

`replay --dir <work copy> --session <head sqlite> --shard <k>/<n> --planned <a> --base <sha>
--work <dir> [--pr <n>] [--repo <root>]` replays the shard's head survivors under the base
tests (R13), re-runs a timed-out base kill at twice the timeout (R14), prints the weakened
verdict (R15) and checks shard completeness (R19). Exit codes: 0 green, 1 red, 2 usage.
When `--pr` is given and a verified commit clears the dir (R27) only the replay is skipped.

cosmic-ray treats any non-zero exit of the test command as a kill, so the replay runs the
base runner through `compare-wrapper`: it maps runner exit 0 to 0 and 1 to 1, and for any
other runner exit (usage 2, internal error 3, a signal) writes a sentinel file and exits 3.
The driver checks the sentinel after every run and reports `replay failed: runner fault`
for that job, so an infrastructure fault is never counted as a kill.
"""

import argparse
import contextlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib
from cosmic_ray.mutating import mutate_and_test
from cosmic_ray.work_db import WorkDB, use_db
from cosmic_ray.work_item import MutationSpec, TestOutcome, WorkerOutcome, WorkResult

RUNNER = Path(__file__).resolve().with_name("mutation_base_runner.py")
UNJUDGEABLE = "base suite unjudgeable: "
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
CLASS_SETUP_PREFIXES = ("setUpClass (", "setUpModule (")
FAILED_TEST_PREFIX = "unittest.loader._FailedTest"
SIGNERS_PATH = ".github/mutation-gate-allowed-signers"
SIGNERS_PLACEHOLDER = "<key from .github/mutation-gate-allowed-signers>"
TIMEOUT_OUTPUT = "timeout"
TIMEOUT_RERUN_FACTOR = 2
WRAPPER_FAULT_EXIT = 3
SHARD_RE = re.compile(r"^\d+/\d+$")

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


Mutate = Callable[[Sequence[MutationSpec], str, float], WorkResult]


@dataclass(frozen=True)
class Survivor:
    """A head-session job whose mutant the head tests did not kill."""

    job_id: str
    mutations: tuple[MutationSpec, ...]
    diff: str


@dataclass(frozen=True)
class Arm:
    """One test run of a mutant: `failure` set means the run itself failed (red)."""

    killed: bool = False
    timed_out: bool = False
    failure: str | None = None


@dataclass(frozen=True)
class Verdict:
    failure: str | None = None
    weakened: bool = False


@dataclass
class Tally:
    replayed: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)
    weakened: list[Survivor] = field(default_factory=list)


def compare_wrapper(args: argparse.Namespace) -> int:
    """Run the base runner in compare mode; any exit other than 0 or 1 is a runner
    fault: leave a sentinel so the driver can tell it from a kill (exit 1)."""
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, str(RUNNER), "compare", args.sig, args.test]
    code = subprocess.run(
        cmd, env=env, stdin=subprocess.DEVNULL, check=False
    ).returncode
    if code in (0, 1):
        return code
    Path(args.sentinel).write_text(str(code))
    return WRAPPER_FAULT_EXIT


def load_session(path: Path) -> tuple[int, list[Survivor]]:
    """(jobs with results, the survivors among them) of a cosmic-ray session."""
    with use_db(str(path), WorkDB.Mode.open) as db:
        items = {str(item.job_id): item for item in db.work_items}
        results = sorted(
            ((str(job_id), result) for job_id, result in db.results),
            key=lambda pair: pair[0],
        )
    survivors = [
        Survivor(job_id, items[job_id].mutations, result.diff or "")
        for job_id, result in results
        if result.test_outcome == TestOutcome.SURVIVED and job_id in items
    ]
    return len(results), survivors


def arm_from_result(result: WorkResult) -> Arm:
    if result.worker_outcome != WorkerOutcome.NORMAL:
        return Arm(failure=str(result.worker_outcome.value))
    if result.test_outcome not in (TestOutcome.KILLED, TestOutcome.SURVIVED):
        return Arm(failure=str(getattr(result.test_outcome, "value", "no outcome")))
    return Arm(
        killed=result.test_outcome == TestOutcome.KILLED,
        timed_out=result.output == TIMEOUT_OUTPUT,
    )


@dataclass
class Replayer:
    """Runs one survivor under the base runner or the head tests."""

    mutate: Mutate
    base_command: str
    head_command: str
    sentinel: Path
    timeout: float

    def run_arm(self, survivor: Survivor, command: str, timeout: float) -> Arm:
        self.sentinel.unlink(missing_ok=True)
        try:
            result = self.mutate(survivor.mutations, command, timeout)
        except Exception as exc:  # noqa: BLE001 - spec R13: any exception is a red replay
            print(f"mutation_weakening: {type(exc).__name__}: {exc}", file=sys.stderr)
            return Arm(failure="exception")
        if self.sentinel.exists():
            return Arm(failure="runner fault")
        return arm_from_result(result)

    def timeout_rerun(self, survivor: Survivor) -> Verdict:
        """R14: a base kill by timeout counts only if, at twice the timeout, the base
        runner still kills it and the head tests do not."""
        longer = self.timeout * TIMEOUT_RERUN_FACTOR
        head = self.run_arm(survivor, self.head_command, longer)
        base = self.run_arm(survivor, self.base_command, longer)
        failure = head.failure or base.failure
        if failure:
            return Verdict(failure=failure)
        return Verdict(weakened=base.killed and not head.killed)

    def judge(self, survivor: Survivor) -> Verdict:
        base = self.run_arm(survivor, self.base_command, self.timeout)
        if base.failure:
            return Verdict(failure=base.failure)
        if not base.killed:
            return Verdict()
        if base.timed_out:
            return self.timeout_rerun(survivor)
        return Verdict(weakened=True)

    def replay(self, survivors: Iterable[Survivor]) -> Tally:
        tally = Tally()
        for survivor in survivors:
            verdict = self.judge(survivor)
            if verdict.failure:
                tally.failures.append((verdict.failure, survivor.job_id))
                continue
            tally.replayed += 1
            if verdict.weakened:
                tally.weakened.append(survivor)
        return tally


def first_signer_key(text: str | None) -> str:
    """`<type> <base64>` of the first key line of an allowed-signers file."""
    for line in (text or "").splitlines():
        tokens = line.split()
        for index, token in enumerate(tokens):
            if token.startswith(("ssh-", "sk-")) and index + 1 < len(tokens):
                return f"{token} {tokens[index + 1]}"
    return SIGNERS_PLACEHOLDER


def clearing_commit(
    repo: str, args: argparse.Namespace, subdir: str, signers_text: str | None
) -> str | None:
    """R27: the verified commit clearing `subdir`, or None (also when `--pr` is absent)."""
    if args.pr is None or signers_text is None:
        return None
    clearance = clearance_module()
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        signers = Path(tmp) / "allowed-signers"
        signers.write_text(signers_text)
        return clearance.cleared_for_dir(
            Path(repo), args.base, head, args.pr, subdir, signers
        )


def clearance_module() -> Any:
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import mutation_gate_clearance

    return mutation_gate_clearance


def print_weakened(
    tally: Tally, subdir: str, base: str, pr: int | None, key: str
) -> None:
    print(
        f"weakened: {len(tally.weakened)} mutants killed by base tests survive head tests"
    )
    for survivor in tally.weakened:
        spec = survivor.mutations[0]
        print(survivor.job_id)
        print(f"  operator: {spec.operator_name}")
        print(f"  occurrence: {spec.occurrence}")
        print(survivor.diff.rstrip("\n"))
        print(
            f"  repro: make -C {subdir} mutants-weakening BASE={base} JOB={survivor.job_id}"
        )
    if pr is not None:
        print(clearance_module().remedy_command(pr, [subdir], key))


def completeness_line(
    ran: int, planned: int, replayed: int, survivors: int, check_replay: bool
) -> str | None:
    if ran == planned and (replayed == survivors or not check_replay):
        return None
    return (
        f"shard incomplete: ran {ran} of {planned} jobs, "
        f"replayed {replayed} of {survivors} survivors"
    )


def replayer_for(
    args: argparse.Namespace, work_dir: Path, timeout: float, mutate: Mutate
) -> Replayer:
    module = work_dir.name.replace("-", "_")
    work = Path(args.work).resolve()
    base_cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "compare-wrapper",
        "--sentinel",
        str(work / "runner-fault"),
        str(work / "base-sig.json"),
        f"test_{module}_base.py",
    ]
    head_command = cosmic_ray_value(
        read_optional(work_dir / "cosmic-ray.toml"), "test-command"
    )
    return Replayer(
        mutate,
        shlex.join(base_cmd),
        str(head_command),
        work / "runner-fault",
        timeout,
    )


def report_replay(
    args: argparse.Namespace,
    subdir: str,
    tally: Tally,
    ran: int,
    survivors: int,
    key: str,
) -> int:
    for failure, job_id in tally.failures:
        print(f"replay failed: {failure}")
        print(f"  job {job_id}")
    if tally.weakened:
        print_weakened(tally, subdir, args.base, args.pr, key)
    line = completeness_line(ran, args.planned, tally.replayed, survivors, True)
    if line:
        print(line)
    red = tally.failures or tally.weakened or line
    return 1 if red else 0


def report_cleared(ran: int, planned: int) -> int:
    line = completeness_line(ran, planned, 0, 0, False)
    if line is None:
        return 0
    print(line)
    return 1


def replay(args: argparse.Namespace, mutate: Mutate = mutate_and_test) -> int:
    work_dir = Path(args.dir).resolve()
    subdir = work_dir.name
    repo = resolve_repo(args)
    if repo is None:
        return infra_failure("not inside a git repository (pass --repo)")
    try:
        ran, survivors = load_session(Path(args.session).resolve())
    except Exception as exc:  # noqa: BLE001 - an unreadable session is a red shard
        print(f"replay failed: session unreadable: {type(exc).__name__}: {exc}")
        return 1
    signers_text = git_show(repo, args.base, SIGNERS_PATH)
    cleared = clearing_commit(repo, args, subdir, signers_text)
    if cleared:
        print(f"cleared by Mutation-Gate-Reviewed {cleared}")
        return report_cleared(ran, args.planned)
    timeout = base_timeout(git_show(repo, args.base, f"{subdir}/cosmic-ray.toml"))
    if timeout is None:
        print(
            f"{UNJUDGEABLE}merge-base cosmic-ray.toml has no positive numeric timeout"
        )
        return 1
    replayer = replayer_for(args, work_dir, timeout, mutate)
    with contextlib.chdir(work_dir):
        tally = replayer.replay(survivors)
    return report_replay(
        args, subdir, tally, ran, len(survivors), first_signer_key(signers_text)
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    judge_parser = sub.add_parser("judge")
    judge_parser.add_argument("--dir", required=True)
    judge_parser.add_argument("--base", required=True)
    judge_parser.add_argument("--work", required=True)
    judge_parser.add_argument("--repo")
    judge_parser.add_argument("--after-head", action="store_true")
    replay_parser = sub.add_parser("replay")
    replay_parser.add_argument("--dir", required=True)
    replay_parser.add_argument("--session", required=True)
    replay_parser.add_argument("--shard", required=True)
    replay_parser.add_argument("--planned", required=True, type=int)
    replay_parser.add_argument("--base", required=True)
    replay_parser.add_argument("--work", required=True)
    replay_parser.add_argument("--pr", type=int)
    replay_parser.add_argument("--repo")
    wrapper_parser = sub.add_parser("compare-wrapper")
    wrapper_parser.add_argument("--sentinel", required=True)
    wrapper_parser.add_argument("sig")
    wrapper_parser.add_argument("test")
    return parser


def main(argv: list[str], mutate: Mutate = mutate_and_test) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exit_request:
        return int(exit_request.code or 0) if isinstance(exit_request.code, int) else 2
    if args.command == "compare-wrapper":
        return compare_wrapper(args)
    if args.command == "replay":
        if not SHARD_RE.match(args.shard):
            print("mutation_weakening: --shard must be <k>/<n>", file=sys.stderr)
            return 2
        return replay(args, mutate)
    if not args.after_head:
        print(
            "mutation_weakening: judge refuses to run without --after-head",
            file=sys.stderr,
        )
        return 2
    return judge(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
