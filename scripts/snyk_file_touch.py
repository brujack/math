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
from collections import Counter
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
COMPARED_EXTS = [".py", ".html", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue"]
# Joined at runtime (not folded to a constant) so no source or .pyc holds the phrase.
_PREFIX = "deep"
_SUPPRESSION_WORDS = f"{_PREFIX}code ignore"
_SUPPRESSION_RE = re.compile(_PREFIX + r"code\s+ignore", re.IGNORECASE)


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


def _require_dict(obj: Any, what: str) -> None:
    if not isinstance(obj, dict):
        raise JudgeError(f"SARIF object holding {what} is not an object")


def _list_at(obj: Any, key: str) -> list[Any]:
    """The list under `key`: [] when absent, JudgeError when present but not a list."""
    _require_dict(obj, key)
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
    """The first-location uri, then every code-flow step uri (None when unusable)."""
    uris = [_first_uri(res)]
    for code_flow in _list_at(res, "codeFlows"):
        for thread in _list_at(code_flow, "threadFlows"):
            for step in _list_at(thread, "locations"):
                _require_dict(step, "a code-flow step")
                uris.append(_decode(_dig(step, "location", *_LOC_URI)))
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


def _header(touched: int, untouched: int, coverage_parts: list[str]) -> str:
    return f"snyk: {touched} touched, {untouched} untouched; " + ", ".join(
        coverage_parts
    )


def _coverage_entry(entry: Any) -> tuple[str, int]:
    """Validate one `properties.coverage` entry; JudgeError when malformed."""
    if not isinstance(entry, dict):
        raise JudgeError("SARIF coverage entry is not an object")
    lang, files = entry.get("lang"), entry.get("files")
    if not isinstance(lang, str):
        raise JudgeError("SARIF coverage entry has a non-string lang")
    if isinstance(files, bool) or not isinstance(files, int) or files < 0:
        raise JudgeError("SARIF coverage entry files is not a non-negative integer")
    return lang, files


def _coverage(runs: list[Any]) -> tuple[dict[str, int], set[str]]:
    """Analysed-file counts per lang summed over all runs, and the SUPPORTED langs."""
    files: dict[str, int] = {}
    supported: set[str] = set()
    for run in runs:
        for entry in run["properties"]["coverage"]:
            lang, count = _coverage_entry(entry)
            files[lang] = files.get(lang, 0) + count
            if entry.get("type") == "SUPPORTED":
                supported.add(lang)
    return files, supported


def _ext(path: str) -> str:
    return os.path.splitext(path)[1]


def _eligible(checkout: Checkout, exts: list[str]) -> list[str]:
    """Tracked regular non-empty files of a compared extension, `ls-files` order."""
    wanted = set(exts)
    eligible = []
    for path in checkout.tracked:
        if _ext(path) not in wanted:
            continue
        size = checkout.size_of(path)
        if size is not None and size > 0:
            eligible.append(path)
    return eligible


def _mismatch_lines(
    exts: list[str], analysed: Mapping[str, int], tracked_count: Mapping[str, int],
    changed: frozenset[str],
) -> list[str]:  # fmt: skip
    lines = []
    for ext in exts:
        a, b = analysed.get(ext, 0), tracked_count.get(ext, 0)
        if a != b:
            hit = sorted(p for p in changed if _ext(p) == ext)
            lines.append(
                f"snyk-scan: Snyk analysed {a} {ext} files but {b} non-empty ones "
                "are tracked; a file is hidden from the scan "
                f"(changed {ext} files: {', '.join(hit) if hit else 'none'})"
            )
    return lines


def _counts_toward_presence(res: Any, tracked: set[str]) -> bool:
    """False for a result touched by an untracked, unusable or whitespace path."""
    uris = _decoded_uris(res)
    first = uris[0]
    if first is not None and any(c.isspace() for c in first):
        return False
    return all(u is not None and u in tracked for u in uris)


def _presence_lines(
    results: list[Any],
    tracked: set[str],
    manifest: Mapping[str, int],
    changed: frozenset[str],
) -> list[str]:
    counts: dict[str, int] = {}
    for res in results:
        if _counts_toward_presence(res, tracked):
            path = _first_uri(res)
            if path is not None:
                counts[path] = counts.get(path, 0) + 1
    lines = []
    for path in sorted(set(counts) | set(manifest)):
        m, n = counts.get(path, 0), manifest.get(path, 0)
        if m != n:
            line = f"snyk-scan: {path} has {m} results; {MANIFEST_PATH} says {n}"
            if path not in changed:
                line += (
                    " (file unchanged by this PR: Snyk drift, a master-side change,"
                    " or an effect of this PR's edits elsewhere)"
                )
            lines.append(line)
    return lines


def _suppression_lines(eligible: list[str], checkout: Checkout) -> list[str]:
    lines = []
    for path in eligible:
        try:
            text = checkout.read_text(path)
        except OSError as exc:
            raise JudgeError(f"cannot read {path}: {exc}") from exc
        if _SUPPRESSION_RE.search(text):
            lines.append(
                f"snyk-scan: {path} contains an inline Snyk suppression "
                f"({_SUPPRESSION_WORDS})"
            )
    return lines


def judge(
    sarif: object, checkout: Checkout, manifest: Mapping[str, int]
) -> tuple[list[str], int]:
    """Return stdout lines and exit code 0 (clean) or 1 (any finding or check)."""
    runs = _validate_runs(sarif)
    tracked = set(checkout.tracked)
    results = [res for run in runs for res in run["results"]]
    touched = [
        _touched_line(res, checkout, tracked)
        for res in results
        if _is_touched(res, checkout, tracked)
    ]
    analysed, supported = _coverage(runs)
    exts = COMPARED_EXTS + sorted(supported - set(COMPARED_EXTS))
    eligible = _eligible(checkout, exts)
    tracked_count = Counter(_ext(p) for p in eligible)
    parts = [f"coverage {e} {analysed.get(e, 0)}/{tracked_count[e]}" for e in exts]
    mismatches = _mismatch_lines(exts, analysed, tracked_count, checkout.changed)
    presence = _presence_lines(results, tracked, manifest, checkout.changed)
    suppressed = _suppression_lines(eligible, checkout)
    lines = [_header(len(touched), len(results) - len(touched), parts)]
    lines += touched + mismatches + presence + suppressed
    if not (touched or mismatches or presence or suppressed):
        return lines, 0
    lines.append(
        f"::error::snyk-scan: {len(touched)} finding(s) in files this PR changes; "
        f"{len(mismatches)} coverage mismatch(es); {len(presence)} presence "
        f"difference(s); {len(suppressed)} suppression(s)"
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
    except json.JSONDecodeError as exc:
        raise JudgeError(f"stdin is not JSON: {exc}") from exc
    except (ValueError, RecursionError) as exc:
        raise JudgeError(f"stdin is not usable JSON: {type(exc).__name__}") from exc


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
