"""Input parsing for the zeta results page.

Reads the `/usr/bin/time -v` report, the CLI's `out.txt`, the committed
`runs.toml` and a refined zero table. Every bad input raises `ResultsError`
whose message is `"<run id>: <check>"`, so a run is never published on
unverified data.
"""

import math
import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import tomllib

HISTOGRAM_BINS = 20
RUN_KEYS = frozenset({"id", "binary_sha", "machine", "date"})
OPTIONAL_RUN_KEYS = frozenset({"note"})
T_TOLERANCE = 1e-9

_ELAPSED_RE = re.compile(r"^(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_COMMAND_RE = re.compile(
    r'^\s*Command being timed: "(?:.*/)?zeta-([0-9a-f]{7}) ([2-7])( --refine)?"\s*$',
    re.MULTILINE,
)
_ELAPSED_LINE_RE = re.compile(
    r"^\s*Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)\s*$", re.MULTILINE
)
_RSS_RE = re.compile(
    r"^\s*Maximum resident set size \(kbytes\): (\d+)\s*$", re.MULTILINE
)
_SIGNAL_RE = re.compile(r"^\s*Command terminated by signal (\d+)\s*$", re.MULTILINE)
_EXIT_RE = re.compile(r"^\s*Exit status: (\d+)\s*$", re.MULTILINE)
_VERIFIED_RE = re.compile(
    r"^RH verified: all (\d+) nontrivial zeros with 0 < Im s <= (\d+) "
    r"lie on Re s = 1/2 and are simple$",
    re.MULTILINE,
)
_SPACINGS_RE = re.compile(r"^Spacing histogram: .*, (\d+) spacings$", re.MULTILINE)
_BIN_RE = re.compile(
    r"^\s+\d+\.\d\d-\d+\.\d\d\s+(\d+)\s+\d+\.\d+\s+\d+\.\d+$", re.MULTILINE
)
_KS_RE = re.compile(
    r"^KS distance to the Wigner surmise CDF: (\d+\.\d+)\s*$", re.MULTILINE
)


class ResultsError(Exception):
    """A failed input check; the message is `<run id>: <check>`."""


@dataclass(frozen=True)
class TimeReport:
    n: int
    refine: bool
    binary_hash: str
    elapsed_s: float
    peak_rss_kb: int


@dataclass(frozen=True)
class OutSummary:
    count: int
    spacings: int | None
    cli_counts: tuple[int, ...] | None
    cli_ks: str | None


@dataclass(frozen=True)
class RunMeta:
    id: str
    binary_sha: str
    machine: str
    date: str
    note: str | None


@dataclass(frozen=True)
class RefinedTable:
    a: list[float]
    b: list[float]
    m: list[float]


def parse_elapsed(value: str) -> float:
    """Seconds from `m:ss.ss` or `h:mm:ss`; ValueError on any other shape."""
    match = _ELAPSED_RE.match(value)
    if match is None:
        raise ValueError(f"not an elapsed time: {value!r}")
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + float(seconds)


def _require(
    pattern: re.Pattern[str], text: str, run_id: str, what: str
) -> re.Match[str]:
    match = pattern.search(text)
    if match is None:
        raise ResultsError(f"{run_id}: {what} not found")
    return match


def parse_time_report(text: str, run_id: str) -> TimeReport:
    """Parse a `/usr/bin/time -v` report; the exit status must be 0."""
    command = _require(
        _COMMAND_RE, text, run_id, "command line (zeta-<hash> <N>[ --refine])"
    )
    signal = _SIGNAL_RE.search(text)
    if signal is not None:
        raise ResultsError(f"{run_id}: command terminated by signal {signal.group(1)}")
    status = int(_require(_EXIT_RE, text, run_id, "Exit status").group(1))
    if status != 0:
        raise ResultsError(f"{run_id}: Exit status is {status}, not 0")
    elapsed = _require(
        _ELAPSED_LINE_RE, text, run_id, "Elapsed (wall clock) time"
    ).group(1)
    rss = _require(_RSS_RE, text, run_id, "Maximum resident set size").group(1)
    try:
        elapsed_s = parse_elapsed(elapsed)
    except ValueError as err:
        raise ResultsError(f"{run_id}: bad elapsed time {elapsed!r}") from err
    return TimeReport(
        n=int(command.group(2)),
        refine=command.group(3) is not None,
        binary_hash=command.group(1),
        elapsed_s=elapsed_s,
        peak_rss_kb=int(rss),
    )


def check_binary(meta: RunMeta, rep: TimeReport, run_id: str) -> None:
    """The binary named in the time report must be the one runs.toml records."""
    if rep.binary_hash != meta.binary_sha[:7]:
        raise ResultsError(
            f"{run_id}: binary zeta-{rep.binary_hash} does not match "
            f"binary_sha {meta.binary_sha[:7]}"
        )


def _parse_refined_out(text: str, run_id: str) -> tuple[int, tuple[int, ...], str]:
    spacings = int(_require(_SPACINGS_RE, text, run_id, "spacing count").group(1))
    counts = tuple(int(c) for c in _BIN_RE.findall(text))
    if len(counts) != HISTOGRAM_BINS:
        raise ResultsError(
            f"{run_id}: expected {HISTOGRAM_BINS} histogram rows, found {len(counts)}"
        )
    ks = _require(_KS_RE, text, run_id, "KS distance line").group(1)
    return spacings, counts, ks


def parse_out(text: str, run_id: str, n: int, *, refine: bool) -> OutSummary:
    """Parse the CLI's stdout; a refined run must also carry its histogram and KS."""
    verified = _require(_VERIFIED_RE, text, run_id, "RH verified line")
    if int(verified.group(2)) != 10**n:
        raise ResultsError(
            f"{run_id}: verified bound {verified.group(2)} is not 10^{n}"
        )
    count = int(verified.group(1))
    if not refine:
        return OutSummary(count, None, None, None)
    spacings, counts, ks = _parse_refined_out(text, run_id)
    return OutSummary(count, spacings, counts, ks)


def _run_from_table(table: dict[str, object], index: int) -> RunMeta:
    label = table["id"] if isinstance(table.get("id"), str) else f"run[{index}]"
    keys = set(table)
    if not RUN_KEYS <= keys or not keys <= RUN_KEYS | OPTIONAL_RUN_KEYS:
        raise ResultsError(
            f"{label}: runs.toml keys {sorted(keys)} are not id, binary_sha, machine, date[, note]"
        )
    for key, value in table.items():
        if not isinstance(value, str):
            raise ResultsError(f"{label}: runs.toml key {key} is not a string")
    sha = str(table["binary_sha"])
    if _SHA_RE.match(sha) is None:
        raise ResultsError(f"{label}: binary_sha is not 40 lowercase hex digits")
    note = table.get("note")
    return RunMeta(
        id=str(table["id"]),
        binary_sha=sha,
        machine=str(table["machine"]),
        date=str(table["date"]),
        note=note if isinstance(note, str) else None,
    )


def load_runs_toml(path: Path) -> dict[str, RunMeta]:
    """Load `[[run]]` tables keyed by id; unknown keys and duplicate ids fail."""
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as err:
        raise ResultsError(f"runs.toml: {err}") from err
    tables = data.get("run")
    if not isinstance(tables, list) or not tables:
        raise ResultsError("runs.toml: no [[run]] tables")
    runs: dict[str, RunMeta] = {}
    for index, table in enumerate(tables):
        if not isinstance(table, dict):
            raise ResultsError(f"runs.toml: run[{index}] is not a table")
        meta = _run_from_table(table, index)
        if meta.id in runs:
            raise ResultsError(f"{meta.id}: duplicate id in runs.toml")
        runs[meta.id] = meta
    return runs


def _table_row(line: str, number: int, run_id: str) -> tuple[float, float]:
    """Validate one data line; return its (a, b) with `t_n` bracket-checked."""
    fields = line.split()
    if len(fields) != 5:
        raise ResultsError(
            f"{run_id}: refined table line {number} has {len(fields)} fields, expected 5"
        )
    if fields[0] != str(number):
        raise ResultsError(f"{run_id}: refined table line {number} is out of order")
    try:
        _, a, b, t, w = (float(f) for f in fields)
    except ValueError as err:
        raise ResultsError(
            f"{run_id}: refined table line {number} has a non-number"
        ) from err
    if not all(math.isfinite(v) for v in (a, b, t, w)):
        raise ResultsError(
            f"{run_id}: refined table line {number} has a non-finite value"
        )
    slack = T_TOLERANCE * abs(t)
    if not a - slack <= t <= b + slack:
        raise ResultsError(
            f"{run_id}: refined table line {number} has t_n outside [a, b]"
        )
    return a, b


def read_refined(path: Path, run_id: str, count: int) -> RefinedTable:
    """Read a refined table; `count` data lines, strictly increasing midpoints."""
    lines = path.read_text().splitlines()
    if not lines or lines[0] != "# n a b t_n w_n":
        raise ResultsError(f"{run_id}: refined table header is not '# n a b t_n w_n'")
    if len(lines) - 1 != count:
        raise ResultsError(
            f"{run_id}: refined table has {len(lines) - 1} lines, expected {count}"
        )
    a_values: list[float] = []
    b_values: list[float] = []
    for number, line in enumerate(lines[1:], start=1):
        a, b = _table_row(line, number, run_id)
        a_values.append(a)
        b_values.append(b)
    mids = [a + (b - a) / 2 for a, b in zip(a_values, b_values, strict=True)]
    if any(y <= x for x, y in pairwise(mids)):
        raise ResultsError(f"{run_id}: bracket midpoints are not strictly increasing")
    return RefinedTable(a_values, b_values, mids)
