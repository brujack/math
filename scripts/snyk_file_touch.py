#!/usr/bin/env python3
"""Judge snyk-scan SARIF: fail only on a finding in a file the PR changes.

Reads SARIF on stdin, compares it with the merge ref's changed files and the
tracked files, and prints one verdict. Exit 0 clean, 1 findings, 2 unjudgeable.
Standard library only: it runs as `python3 -I` and imports no sibling module.
"""

import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TextIO
from urllib.parse import unquote

GIT_DIFF_ARGV = [
    "git", "-c", "core.quotePath=false", "diff", "--name-only", "-z",
    "--no-renames", "HEAD^1", "HEAD",
]  # fmt: skip
GIT_LS_FILES_ARGV = ["git", "ls-files", "-z"]
MANIFEST_PATH = ".snyk-files"


class JudgeError(Exception):
    """The input cannot be judged; the message is the exit-2 reason."""


def parse_manifest(text: str) -> dict[str, int]:
    """Parse `.snyk-files`: `<path> <count>` lines, blanks and `#` lines skipped."""
    counts: dict[str, int] = {}
    for raw in text.splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        match = re.fullmatch(r"(\S+) ([0-9]+)", raw)
        if match is None:
            raise JudgeError(f"{MANIFEST_PATH}: malformed line: {raw!r}")
        path = match.group(1)
        if path in counts:
            raise JudgeError(f"{MANIFEST_PATH}: repeated path: {path}")
        counts[path] = int(match.group(2))
    return counts


_MISSING = object()
_LOC_URI = ("physicalLocation", "artifactLocation", "uri")


@dataclass(frozen=True)
class Checkout:
    """What the judge knows about the merge ref's working tree."""

    changed: frozenset[str]
    tracked: tuple[str, ...]  # `git ls-files` order, which Task 2's output follows
    size_of: Callable[[str], int | None]
    read_text: Callable[[str], str]


def _dig(obj: Any, *keys: str | int, default: Any = None) -> Any:
    """Follow keys/indexes through nested dicts and lists; `default` on any miss."""
    for key in keys:
        try:
            obj = obj[key]
        except (KeyError, IndexError, TypeError):
            return default
    return obj


def _text(value: Any) -> str:
    return "?" if value is None else str(value)


def _list_at(obj: Any, key: str) -> list[Any]:
    """The list under `key`: [] when absent, JudgeError when present but not a list."""
    value = _dig(obj, key, default=_MISSING)
    if value is _MISSING:
        return []
    if not isinstance(value, list):
        raise JudgeError(f"SARIF {key} is not a list")
    return value


def _decode(uri: Any) -> str | None:
    """A percent-decoded uri; None (fail closed) when it is not a string."""
    return unquote(uri) if isinstance(uri, str) else None


def _first_uri(res: Any) -> str | None:
    locations = _list_at(res, "locations")
    return _decode(_dig(locations, 0, *_LOC_URI))


def _decoded_uris(res: Any) -> list[str | None]:
    """The first-location uri, then every code-flow step uri that is present."""
    uris = [_first_uri(res)]
    for code_flow in _list_at(res, "codeFlows"):
        for thread in _list_at(code_flow, "threadFlows"):
            for step in _list_at(thread, "locations"):
                raw = _dig(step, "location", *_LOC_URI, default=_MISSING)
                if raw is not _MISSING:
                    uris.append(_decode(raw))
    return uris


def _is_touched(res: Any, checkout: Checkout, tracked: set[str]) -> bool:
    first = _first_uri(res)
    if first is not None and any(c.isspace() for c in first):
        return True
    return any(
        u is None or u in checkout.changed or u not in tracked
        for u in _decoded_uris(res)
    )


def _touched_line(res: Any, checkout: Checkout, tracked: set[str]) -> str:
    uris = list(dict.fromkeys(_decoded_uris(res)))
    hit = [u for u in uris if u is not None and u in checkout.changed]
    start = _dig(res, "locations", 0, "physicalLocation", "region", "startLine")
    line = (
        f"touched: {_text(_dig(res, 'level'))} {_text(_dig(res, 'ruleId'))} "
        f"{_text(_first_uri(res))}:{_text(start)}"
        f" \u2014 {_text(_dig(res, 'message', 'text'))}"
        f" [changed: {', '.join(hit) if hit else 'none'}]"
    )
    for uri in uris:
        if uri is None or uri not in tracked:
            line += f" [untracked uri: {_text(uri)}]"
    return line


def _validate_runs(sarif: object) -> list[Any]:
    runs = sarif.get("runs") if isinstance(sarif, dict) else None
    if not isinstance(runs, list) or not runs:
        raise JudgeError("SARIF has no runs")
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("results"), list):
            raise JudgeError("SARIF run has no results list")
        if not isinstance(_dig(run, "properties", "coverage"), list):
            raise JudgeError("SARIF run has no properties.coverage list")
    return runs


def _header(touched: int, untouched: int, coverage: list[str]) -> str:
    return f"snyk: {touched} touched, {untouched} untouched; " + ", ".join(coverage)


def judge(
    sarif: object, checkout: Checkout, manifest: Mapping[str, int]
) -> tuple[list[str], int]:
    """Return stdout lines and exit code 0/1 (Task 1: touch decision only)."""
    runs = _validate_runs(sarif)
    tracked = set(checkout.tracked)
    results = [res for run in runs for res in run["results"]]
    touched = [
        _touched_line(res, checkout, tracked)
        for res in results
        if _is_touched(res, checkout, tracked)
    ]
    # Task 2 supplies the coverage parts (and the manifest checks that use `manifest`).
    lines = [_header(len(touched), len(results) - len(touched), [])]
    lines.extend(touched)
    if not touched:
        return lines, 0
    lines.append(
        f"::error::snyk-scan: {len(touched)} finding(s) in files this PR changes; "
        "0 coverage mismatch(es); 0 presence difference(s); 0 suppression(s)"
    )
    return lines, 1


def default_run_git(argv: list[str]) -> bytes:
    """Run git; any failure becomes a JudgeError."""
    try:
        proc = subprocess.run(argv, capture_output=True, check=False)
    except OSError as exc:
        raise JudgeError(f"cannot run {argv[0]}: {exc}") from exc
    if proc.returncode != 0:
        raise JudgeError(f"{' '.join(argv)} exited {proc.returncode}")
    return proc.stdout


def default_read_manifest() -> str:
    with open(MANIFEST_PATH, encoding="utf-8") as handle:
        return handle.read()


def default_size_of(path: str) -> int | None:
    """Size of a regular file, None for anything else (symlink, directory, missing)."""
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return st.st_size if stat.S_ISREG(st.st_mode) else None


def default_read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _split_nul(raw: bytes) -> list[str]:
    return [p.decode("utf-8") for p in raw.split(b"\0") if p]


def _read_sarif(stdin: TextIO) -> object:
    try:
        return json.load(stdin)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise JudgeError(f"stdin is not JSON: {type(exc).__name__}") from exc


def _read_manifest(read_manifest: Callable[[], str]) -> dict[str, int]:
    try:
        return parse_manifest(read_manifest())
    except FileNotFoundError as exc:
        raise JudgeError(f"{MANIFEST_PATH} is missing") from exc
    except OSError as exc:
        raise JudgeError(f"{MANIFEST_PATH} is unreadable: {exc}") from exc


def main(
    stdin: TextIO,
    run_git: Callable[[list[str]], bytes],
    read_manifest: Callable[[], str],
    size_of: Callable[[str], int | None],
    read_text: Callable[[str], str],
) -> int:
    try:
        sarif = _read_sarif(stdin)
        manifest = _read_manifest(read_manifest)
        checkout = Checkout(
            frozenset(_split_nul(run_git(GIT_DIFF_ARGV))),
            tuple(_split_nul(run_git(GIT_LS_FILES_ARGV))),
            size_of,
            read_text,
        )
        lines, code = judge(sarif, checkout, manifest)
    except (JudgeError, UnicodeDecodeError) as exc:
        print(f"snyk_file_touch: {exc}", file=sys.stderr)
        return 2
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(
        main(
            sys.stdin,
            default_run_git,
            default_read_manifest,
            default_size_of,
            default_read_text,
        )
    )
