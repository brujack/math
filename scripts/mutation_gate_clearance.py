#!/usr/bin/env python3
"""Signed-trailer clearance for the mutation gate (spec R26, R27, R28).

A commit in the PR range clears a target when it carries a line

    Mutation-Gate-Reviewed: #<pr> <target>: <reason>

with `<pr>` equal to the PR's number, a reason of at least 10 characters, and a signature
that `git verify-commit` accepts against the allowed-signers file. Anything else that
looks like a trailer is reported as `trailer ignored: <commit>: <reason>`.

`check_allowed_signers` is the R28 checker for the allowed-signers file itself.
"""

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

TRAILER_RE = re.compile(r"^Mutation-Gate-Reviewed: #(\d+) ([^\s:]+): (.*)$")
MIN_REASON = 10
KEY_TYPE = "sk-ssh-ed25519@openssh.com"
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
COMMIT_MARK = "\x01"


@dataclass(frozen=True)
class Clearance:
    sha: str
    target: str
    reason: str


def _git(
    repo: Path, args: list[str], signers: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}
    prefix = ["git", "-C", str(repo)]
    if signers is not None:
        prefix += [
            "-c",
            "gpg.format=ssh",
            "-c",
            f"gpg.ssh.allowedSignersFile={signers}",
        ]
    return subprocess.run(
        prefix + args,
        capture_output=True,
        text=True,
        env=env,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def verify(repo: Path, sha: str, signers: Path) -> bool:
    """True when git accepts the commit's ssh signature against `signers`."""
    return _git(repo, ["verify-commit", sha], signers).returncode == 0


def _ignore_reason(repo: Path, sha: str, signers: Path) -> str | None:
    """Why `sha` cannot clear anything, or None when its signature is accepted."""
    if verify(repo, sha, signers):
        return None
    status = _git(repo, ["log", "-1", "--format=%G?", sha], signers).stdout.strip()
    return "unsigned" if status == "N" else "signature not accepted"


def _parse_lines(message: str) -> list[tuple[int, str, str]]:
    """The well-formed trailer lines of a commit message as (pr, target, reason)."""
    found = []
    for line in message.splitlines():
        match = TRAILER_RE.match(line.rstrip())
        if match and len(match.group(3).strip()) >= MIN_REASON:
            found.append((int(match.group(1)), match.group(2), match.group(3).strip()))
    return found


def _commits(repo: Path, base: str, head: str) -> list[tuple[str, str]]:
    """(sha, message) for each commit in base..head, newest first."""
    out = _git(repo, ["log", f"--format={COMMIT_MARK}%H%x00%B", f"{base}..{head}"])
    if out.returncode != 0:
        raise RuntimeError(f"git log {base}..{head} failed: {out.stderr.strip()}")
    records = [r for r in out.stdout.split(COMMIT_MARK) if r]
    return [
        (sha, message) for sha, _, message in (r.partition("\x00") for r in records)
    ]


def _commit_clearances(
    repo: Path, sha: str, message: str, pr: int, signers: Path
) -> tuple[list[Clearance], list[str]]:
    lines = _parse_lines(message)
    if not lines:
        return [], []
    other = [n for n, _, _ in lines if n != pr]
    ignored = [f"trailer ignored: {sha}: names #{n}" for n in dict.fromkeys(other)]
    mine = [(t, r) for n, t, r in lines if n == pr]
    if not mine:
        return [], ignored
    why = _ignore_reason(repo, sha, signers)
    if why is not None:
        return [], [*ignored, f"trailer ignored: {sha}: {why}"]
    return [Clearance(sha, t, r) for t, r in mine], ignored


def trailers(
    repo: Path, base: str, head: str, pr: int, signers: Path
) -> tuple[list[Clearance], list[str]]:
    """Accepted clearances (newest commit first) and the `trailer ignored:` lines."""
    cleared: list[Clearance] = []
    ignored: list[str] = []
    for sha, message in _commits(repo, base, head):
        got, skipped = _commit_clearances(repo, sha, message, pr, signers)
        cleared += got
        ignored += skipped
    return cleared, ignored


def _unchanged(repo: Path, sha: str, head: str, paths: list[str]) -> bool:
    result = _git(repo, ["diff", "--quiet", sha, head, "--", *paths])
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git diff {sha} {head} failed: {result.stderr.strip()}")
    return result.returncode == 0


def cleared_for_dir(
    repo: Path, base: str, head: str, pr: int, directory: str, signers: Path
) -> str | None:
    """R27: the latest clearing commit for `directory` whose module and test file are
    unchanged between it and `head`, or None."""
    module = directory.replace("-", "_")
    paths = [f"{directory}/{module}.py", f"{directory}/test_{module}.py"]
    found, _ = trailers(repo, base, head, pr, signers)
    for clearance in found:
        if clearance.target == directory and _unchanged(
            repo, clearance.sha, head, paths
        ):
            return clearance.sha
    return None


def remedy_command(pr: int, targets: list[str], key: str) -> str:
    """The one command that clears every uncleared target (R26), with the merge note."""
    lines = [
        "git -c gpg.format=ssh -c user.signingkey='key::" + key + "' \\",
        "  commit --allow-empty -S -m 'chore: mutation gate review' \\",
    ]
    lines += [f"  -m 'Mutation-Gate-Reviewed: #{pr} {t}: <reason>' \\" for t in targets]
    lines[-1] = lines[-1].removesuffix(" \\")
    lines.append(
        "After signing, merge master into the branch; do not rebase (a rebase drops the signature)."
    )
    return "\n".join(lines)


def _key_problem(number: int, tokens: list[str]) -> str | None:
    """The R28 problem on one signers line, or None."""
    blobs = [i for i, tok in enumerate(tokens) if i > 0 and tok.startswith("AAAA")]
    if not blobs or blobs[0] < 2:
        return f"line {number}: no key type and key found"
    key_type = tokens[blobs[0] - 1]
    if key_type != KEY_TYPE:
        return f"line {number}: key type {key_type} is not {KEY_TYPE}"
    if "no-touch-required" in " ".join(tokens[1 : blobs[0] - 1]):
        return f"line {number}: no-touch-required is not allowed"
    return None


def check_allowed_signers(text: str) -> list[str]:
    """R28: problems in an allowed-signers file's text (empty list when clean)."""
    problems = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        problem = _key_problem(number, line.split())
        if problem:
            problems.append(problem)
    return problems
