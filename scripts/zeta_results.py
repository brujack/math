"""Generator for the zeta results page.

Reads the `/usr/bin/time -v` report, the CLI's `out.txt`, the committed
`runs.toml` and a refined zero table. Every bad input raises `ResultsError`
whose message is `"<run id>: <check>"`, so a run is never published on
unverified data. Only after every check passes does it render the matplotlib
SVGs and the static `index.html`, swap the site in atomically and copy each
run's `out.txt` and `err.txt` (binary path reduced) beside it.
"""

# SARIF probe: shift lines (never merged).
#
#

import argparse
import html
import io
import math
import re
import shutil
import stat
import sys
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from types import ModuleType
from typing import Any

import tomllib

HISTOGRAM_BINS = 20
RUN_KEYS = frozenset({"id", "binary_sha", "machine", "date"})
OPTIONAL_RUN_KEYS = frozenset({"note"})
T_TOLERANCE = 1e-9

_ELAPSED_RE = re.compile(r"^(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# A run id names its run-copy directory, so it must be one plain path component.
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
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
    run_id = str(table["id"])
    if _ID_RE.fullmatch(run_id) is None:
        raise ResultsError(
            f"run[{index}]: id {run_id!r} is not ASCII letters, digits, '-' or '_'"
            " starting with a letter or digit"
        )
    sha = str(table["binary_sha"])
    if _SHA_RE.match(sha) is None:
        raise ResultsError(f"{label}: binary_sha is not 40 lowercase hex digits")
    note = table.get("note")
    return RunMeta(
        id=run_id,
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


# N(10^N), the count of zeros with 0 < Im s <= 10^N: OEIS A072080.
PUBLISHED_COUNTS = {2: 29, 3: 649, 4: 10142, 5: 138069, 6: 1747146, 7: 21136125}

BIN_WIDTH = 0.15
S_MAX = 3.0
DISPLAY_FINE_WIDTH = 0.05
DISPLAY_FINE_BINS = 60
DISPLAY_THRESHOLD = 10_000
GRAM_TOLERANCE = 1e-8
_ERF_P = 0.327_591_1
_ERF_A = (0.254_829_592, -0.284_496_736, 1.421_413_741, -1.453_152_027, 1.061_405_429)
_WIGNER_A = 4.0 / math.pi
_GRAM_START = 9.67
_NEWTON_STOP = 1e-7
_NEWTON_MAX = 100


def spacings(m: list[float]) -> list[float]:
    """Normalised gaps between consecutive midpoints, as the CLI computes them."""
    return [(m1 - m0) * math.log(m0 / math.tau) / math.tau for m0, m1 in pairwise(m)]


def as_erf(x: float) -> float:
    """Abramowitz and Stegun 7.1.26, ported from `spacing.rs` `erf`."""
    ax = abs(x)
    t = 1.0 / (1.0 + _ERF_P * ax)
    poly = 0.0
    for c in reversed(_ERF_A):
        poly = (poly + c) * t
    return math.copysign(1.0 - poly * math.exp(-ax * ax), x)


def wigner_pdf(s: float) -> float:
    return 32.0 / (math.pi * math.pi) * s * s * math.exp(-4.0 * s * s / math.pi)


def wigner_cdf(s: float) -> float:
    if s <= 0.0:
        return 0.0
    x = math.sqrt(_WIGNER_A) * s
    return as_erf(x) - 2.0 / math.sqrt(math.pi) * x * math.exp(-_WIGNER_A * s * s)


def poisson_cdf(s: float) -> float:
    return 1 - math.exp(-s)


def ks_distance(d: list[float], cdf: Callable[[float], float]) -> float:
    """Kolmogorov-Smirnov distance of the sample `d` to `cdf`."""
    if not d:
        raise ValueError("KS distance of an empty sample")
    ordered = sorted(d)
    n = float(len(ordered))
    worst = 0.0
    for i, s in enumerate(ordered):
        f = cdf(s)
        worst = max(worst, (i + 1.0) / n - f, f - i / n)
    return worst


def _binned(d: list[float], width: float, bins: int) -> list[int]:
    counts = [0] * bins
    for s in d:
        if 0.0 <= s <= S_MAX:
            counts[min(int(s / width), bins - 1)] += 1
    return counts


def cli_bins(d: list[float]) -> list[int]:
    """The CLI's 20 bins of 0.15 over [0, 3]; gaps outside are dropped."""
    return _binned(d, BIN_WIDTH, HISTOGRAM_BINS)


def display_bins(
    d: list[float], threshold: int = DISPLAY_THRESHOLD
) -> tuple[float, list[int]]:
    """Bin width and counts for the figure: 0.05 wide once `len(d) >= threshold`."""
    if len(d) < threshold:
        return BIN_WIDTH, cli_bins(d)
    return DISPLAY_FINE_WIDTH, _binned(d, DISPLAY_FINE_WIDTH, DISPLAY_FINE_BINS)


def cross_check(run_id: str, d: list[float], out: OutSummary, count: int) -> None:
    """Fail closed unless our gaps, 20 bins and KS equal the CLI's printed values."""
    if not len(d) == count - 1 == out.spacings:
        raise ResultsError(
            f"{run_id}: gap count {len(d)} does not match L - 1 = {count - 1} "
            f"and the CLI's {out.spacings}"
        )
    if out.cli_counts is None or cli_bins(d) != list(out.cli_counts):
        raise ResultsError(f"{run_id}: 20-bin histogram differs from the CLI's")
    ours = f"{ks_distance(d, wigner_cdf):.4f}"
    if ours != out.cli_ks:
        raise ResultsError(f"{run_id}: KS {ours} differs from the CLI's {out.cli_ks}")


def theta(t: float) -> float:
    return (
        (t / 2) * math.log(t / math.tau)
        - t / 2
        - math.pi / 8
        + 1 / (48 * t)
        + 7 / (5760 * t**3)
    )


def _theta_slope(t: float) -> float:
    return 0.5 * math.log(t / math.tau) - 1 / (48 * t * t) - 7 / (1920 * t**4)


def _newton(target: float, start: float) -> float:
    t = start
    for _ in range(_NEWTON_MAX):
        step = (theta(t) - target) / _theta_slope(t)
        t -= step
        if abs(step) < _NEWTON_STOP:
            return t
    raise ResultsError(f"Gram point for theta = {target} did not converge")


def gram_points_upto(limit: float) -> list[float]:
    """Gram points g_-1, g_0, ... up to the last one not above `limit`."""
    points: list[float] = []
    g = _newton(-math.pi, _GRAM_START)
    n = -1
    while g <= limit:
        points.append(g)
        n += 1
        g = _newton(n * math.pi, g + math.pi / _theta_slope(g))
    return points


@dataclass(frozen=True)
class GramStats:
    counts: dict[int, int]
    share: float
    straddles: int


def _gram_counts(m: list[float], gram: list[float]) -> dict[int, int]:
    per_interval = [0] * (len(gram) - 1)
    for value in m:
        i = bisect_right(gram, value) - 1
        if 0 <= i < len(per_interval):
            per_interval[i] += 1
    counts = dict.fromkeys(range(5), 0)
    for zeros in per_interval:
        counts[min(zeros, 4)] += 1
    return counts


def _straddles(table: RefinedTable, gram: list[float]) -> int:
    total = 0
    for a, b in zip(table.a, table.b, strict=True):
        i = bisect_right(gram, a + GRAM_TOLERANCE)
        if i < len(gram) and gram[i] < b - GRAM_TOLERANCE:
            total += 1
    return total


def gram_stats(table: RefinedTable, gram: list[float]) -> GramStats:
    """Zeros per Gram interval [g_{n-1}, g_n) by midpoint, plus strict straddles S."""
    counts = _gram_counts(table.m, gram)
    intervals = max(len(gram) - 1, 0)
    share = counts[1] / intervals if intervals else 0.0
    return GramStats(counts, share, _straddles(table, gram))


# ---------------------------------------------------------------------------
# Rendering, site assembly and the command line.
# ---------------------------------------------------------------------------

MPL_MISSING = "zeta_results: matplotlib missing; run make install-deps"
FIGURE_SIZE = (6, 4)
FONT_PT = 12
SVG_HASH_SALT = "zeta-results"
CURVE_POINTS = 300
CLAIM_TAIL = (
    " re-verified, with certified interval arithmetic, that every nontrivial zero of "
    "ζ(s) with 0 < Im s ≤ 10^N lies on the critical line and is simple, for each N "
    "shown. This is an independent re-computation of a known result, not a new one. "
    "Platt and Trudgian (2021) verified the same property up to 3·10^12, and "
    "Odlyzko's tables give the zeros themselves."
)
POISSON_SENTENCE = (
    "The contrast with Poisson is the lesson: independent points would pile up near "
    "zero gap, while the zeros repel each other. A small KS distance to the Wigner "
    "surmise can still be a statistical rejection at a large gap count, because the "
    "surmise is an approximation and convergence with height is slow."
)
GRAM_DEFINITION = (
    "A Gram point g_n is the solution of θ(t) = nπ, where θ is the Riemann–Siegel "
    "theta function."
)
DELTA_DEFINITION = (
    "The normalised gap is δ_n = (m_(n+1) − m_n)·ln(m_n/2π)/2π, which rescales the "
    "spacings between consecutive zeros to mean 1; m_n is the midpoint of the "
    "certified bracket."
)
GRAM_CAVEAT = (
    "The zero brackets are certified. The Gram points are computed in double "
    "precision, not certified; S counts the brackets with a Gram point strictly "
    "inside, which bounds how much that matters. The zero above the last Gram point "
    "g_K ≤ 10^N falls in no interval."
)
_PAGE_STYLE = (
    "body{font-family:sans-serif;max-width:50rem;margin:1rem auto;padding:0 1rem;"
    "line-height:1.5}img{max-width:100%;height:auto}table{border-collapse:collapse}"
    "th,td{border:1px solid #888;padding:.25rem .5rem;text-align:right}"
    "figcaption{font-size:.85rem;color:#444}figure{margin:1rem 0}"
)
_COMMAND_PATH_RE = re.compile(
    r'(?<=Command being timed: ")(?:.*/)?(?=zeta-[0-9a-f]{7} )'
)


class MatplotlibMissing(ResultsError):
    """matplotlib is not importable; the message is the full user-facing line."""


@dataclass(frozen=True)
class Refined:
    table: RefinedTable
    gaps: list[float]
    ks_wigner: float
    ks_poisson: float
    gram: GramStats


@dataclass(frozen=True)
class RunData:
    meta: RunMeta
    report: TimeReport
    out: OutSummary
    out_text: str
    err_published: str
    refined: Refined | None


def _load_pyplot() -> ModuleType:
    try:
        import matplotlib  # pyright: ignore[reportMissingImports]

        matplotlib.use("Agg")
        from matplotlib import pyplot  # pyright: ignore[reportMissingImports]
    except ImportError as err:
        raise MatplotlibMissing(MPL_MISSING) from err
    return pyplot


def command_text(rep: TimeReport) -> str:
    """The published command line, `zeta <N>[ --refine]`, without any path."""
    return f"zeta {rep.n}" + (" --refine" if rep.refine else "")


def strip_command_path(err_text: str) -> str:
    """Remove the directory prefix of the timed binary's path.

    The binary hash is not checked here; `published_err` does that.
    """
    return _COMMAND_PATH_RE.sub("", err_text)


def published_err(err_text: str, rep: TimeReport, binary_sha: str, run_id: str) -> str:
    """The err.txt to publish; fails closed unless the command line is path-free."""
    stripped = strip_command_path(err_text)
    expected = f'Command being timed: "zeta-{binary_sha[:7]} {command_text(rep)[5:]}"'
    commands = [ln for ln in stripped.splitlines() if "Command being timed" in ln]
    if len(commands) != 1 or commands[0].strip() != expected:
        raise ResultsError(
            f"{run_id}: err.txt must hold exactly one command line, {expected!r}"
        )
    return stripped


def count_verdict(n: int, count: int) -> str:
    """`equal` when `count` is the published N(10^n), else `differs`."""
    return "equal" if PUBLISHED_COUNTS[n] == count else "differs"


def format_elapsed(seconds: float) -> str:
    """Seconds below 60 s, else h:mm:ss (rounded to a whole second)."""
    if seconds < 60:
        return f"{seconds:.2f} s"
    hours, rest = divmod(round(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def _read_text(path: Path, run_id: str) -> str:
    try:
        return path.read_text()
    except OSError as err:
        raise ResultsError(f"{run_id}: cannot read {path.name}") from err


def _analyse_refined(
    run_id: str, directory: Path, rep: TimeReport, out: OutSummary
) -> Refined:
    table = read_refined(directory / f"zeta_1e{rep.n}.txt", run_id, out.count)
    gaps = spacings(table.m)
    cross_check(run_id, gaps, out, out.count)
    return Refined(
        table,
        gaps,
        ks_distance(gaps, wigner_cdf),
        ks_distance(gaps, poisson_cdf),
        gram_stats(table, gram_points_upto(10.0**rep.n)),
    )


def load_run(run_id: str, meta: RunMeta, directory: Path) -> RunData:
    """Read and fully check one run directory."""
    err_text = _read_text(directory / "err.txt", run_id)
    out_text = _read_text(directory / "out.txt", run_id)
    rep = parse_time_report(err_text, run_id)
    check_binary(meta, rep, run_id)
    out = parse_out(out_text, run_id, rep.n, refine=rep.refine)
    refined = _analyse_refined(run_id, directory, rep, out) if rep.refine else None
    err_published = published_err(err_text, rep, meta.binary_sha, run_id)
    return RunData(meta, rep, out, out_text, err_published, refined)


def _check_run_set(metas: dict[str, RunMeta], dirs: dict[str, Path]) -> None:
    for run_id in dirs:
        if run_id not in metas:
            raise ResultsError(f"{run_id}: --run has no runs.toml entry")
    for run_id in metas:
        if run_id not in dirs:
            raise ResultsError(f"{run_id}: runs.toml entry has no --run")


def load_runs(runs_toml: Path, dirs: dict[str, Path]) -> list[RunData]:
    """Check every run; the result is sorted by N, plain before refined, then id."""
    metas = load_runs_toml(runs_toml)
    _check_run_set(metas, dirs)
    runs = [load_run(run_id, metas[run_id], path) for run_id, path in dirs.items()]
    runs.sort(key=lambda r: (r.report.n, r.report.refine, r.meta.id))
    seen: set[tuple[int, bool]] = set()
    for run in runs:
        key = (run.report.n, run.report.refine)
        if key in seen:
            raise ResultsError(
                f"{run.meta.id}: duplicate run of {command_text(run.report)}"
            )
        seen.add(key)
    return runs


def _svg_bytes(plt: ModuleType, fig: Any) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", metadata={"Date": None})
    plt.close(fig)
    return buf.getvalue()


def _gap_figure(plt: ModuleType, rep: TimeReport, data: Refined) -> bytes:
    total = len(data.gaps)
    width, counts = display_bins(data.gaps)
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    centres = [(i + 0.5) * width for i in range(len(counts))]
    heights = [c / (total * width) for c in counts]
    for i, bar in enumerate(
        ax.bar(centres, heights, width=width, color="#9ab", edgecolor="white")
    ):
        bar.set_gid(f"hist-bar-{i}")
    xs = [i * S_MAX / CURVE_POINTS for i in range(CURVE_POINTS + 1)]
    (wigner,) = ax.plot(xs, [wigner_pdf(x) for x in xs], "r-", label="Wigner surmise")
    (poisson,) = ax.plot(xs, [math.exp(-x) for x in xs], "k--", label="Poisson")
    wigner.set_gid("wigner-curve")
    poisson.set_gid("poisson-curve")
    ax.set_xlim(0, S_MAX)
    ax.set_xlabel("normalised gap δ")
    ax.set_ylabel("density")
    ax.set_title(f"Gaps between zeros, N = {rep.n}")
    ax.legend(loc="upper right")
    ax.text(
        0.97,
        0.6,
        f"{total:,} gaps\nKS Wigner {data.ks_wigner:.4f}\nKS Poisson {data.ks_poisson:.4f}",
        transform=ax.transAxes,
        ha="right",
        va="top",
    )
    fig.tight_layout()
    return _svg_bytes(plt, fig)


def _share_figure(plt: ModuleType, refined: list[RunData]) -> bytes:
    ns = [r.report.n for r in refined]
    shares = [r.refined.gram.share for r in refined if r.refined is not None]
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    (line,) = ax.plot(ns, shares, "o-")
    line.set_gid("gram-share-line")
    ax.set_xticks(ns)
    ax.set_ylim(0, 1)
    ax.set_xlabel("N (zeros up to 10^N)")
    ax.set_ylabel("share of Gram intervals with one zero")
    ax.set_title("Gram's law")
    fig.tight_layout()
    return _svg_bytes(plt, fig)


def _text(value: str) -> str:
    return html.escape(value, quote=False)


def _attr(value: str) -> str:
    return html.escape(value, quote=True)


def _table_html(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{_text(h)}</th>" for h in headers)
    body = "\n".join(
        "<tr>" + "".join(f"<td>{_text(c)}</td>" for c in row) + "</tr>" for row in rows
    )
    return (
        '<div style="overflow-x:auto">\n<table>\n'
        f"<tr>{head}</tr>\n{body}\n</table>\n</div>"
    )


def _provenance(run: RunData) -> str:
    meta = run.meta
    return (
        f"command: {command_text(run.report)}; binary commit: {meta.binary_sha[:7]}; "
        f"machine: {meta.machine}; date: {meta.date}"
    )


def _figure_html(src: str, alt: str, provenance: str) -> str:
    return (
        f'<figure>\n<img src="{_attr(src)}" alt="{_attr(alt)}">\n'
        f'<figcaption class="provenance">{_text(provenance)}</figcaption>\n</figure>'
    )


def _counts_html(runs: list[RunData]) -> str:
    rows = [
        [
            str(r.report.n),
            "refine" if r.report.refine else "plain",
            str(r.out.count),
            str(PUBLISHED_COUNTS[r.report.n]),
            count_verdict(r.report.n, r.out.count),
        ]
        for r in runs
    ]
    headers = ["N", "mode", "zeros found L", "published N(10^N)", "result"]
    return (
        "<h2>Verified counts</h2>\n"
        "<p>Published counts: OEIS A072080.</p>\n" + _table_html(headers, rows)
    )


def _gram_html(refined: list[RunData]) -> str:
    rows = [
        [
            str(r.report.n),
            *(str(r.refined.gram.counts[k]) for k in range(5)),
            f"{r.refined.gram.share:.4f}",
            str(r.refined.gram.straddles),
        ]
        for r in refined
        if r.refined is not None
    ]
    headers = [
        "N",
        "0 zeros",
        "1 zero",
        "2 zeros",
        "3 zeros",
        "4+ zeros",
        "exactly one",
        "S",
    ]
    return (
        f"<h2>Gram's law</h2>\n<p>{_text(GRAM_DEFINITION)}</p>\n"
        + _table_html(headers, rows)
        + f"\n<p>{_text(GRAM_CAVEAT)}</p>"
    )


def _runs_html(runs: list[RunData]) -> str:
    machines = {r.meta.machine for r in runs}
    shared = len(machines) == 1
    headers = ["N", "refine", "elapsed", "peak RSS", "binary commit", "date", "note"]
    if not shared:
        headers.insert(0, "machine")
    rows = []
    for r in runs:
        row = [
            str(r.report.n),
            "yes" if r.report.refine else "no",
            format_elapsed(r.report.elapsed_s),
            f"{r.report.peak_rss_kb / 1024:.1f} MiB",
            r.meta.binary_sha[:7],
            r.meta.date,
            r.meta.note or "",
        ]
        rows.append(row if shared else [r.meta.machine, *row])
    machine = f"<p>Machine: {_text(machines.pop())}</p>\n" if shared else ""
    return "<h2>Runs</h2>\n" + machine + _table_html(headers, rows)


def _figures(plt: ModuleType, refined: list[RunData]) -> tuple[str, dict[str, bytes]]:
    files: dict[str, bytes] = {}
    parts = [f"<h2>Gap spacings</h2>\n<p>{_text(DELTA_DEFINITION)}</p>"]
    parts.append(f"<p>{_text(POISSON_SENTENCE)}</p>")
    for r in refined:
        if r.refined is None:
            continue
        name = f"gaps-N{r.report.n}.svg"
        files[name] = _gap_figure(plt, r.report, r.refined)
        alt = (
            f"Histogram of {len(r.refined.gaps):,} normalised gaps for N = {r.report.n} "
            "against the Wigner surmise and the Poisson curve"
        )
        parts.append(_figure_html(name, alt, _provenance(r)))
    return "\n".join(parts), files


def _gram_figure(plt: ModuleType, refined: list[RunData]) -> tuple[str, bytes]:
    name = "gram-share.svg"
    alt = "Share of Gram intervals holding exactly one zero, against N"
    provenance = " | ".join(_provenance(r) for r in refined)
    return _figure_html(name, alt, provenance), _share_figure(plt, refined)


def _page(body: list[str]) -> str:
    footer = (
        '<footer><p><a href="deployed-from.txt">deployed-from.txt</a> names the '
        "commit this page was deployed from.</p></footer>"
    )
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>zeta results</title>\n<style>{_PAGE_STYLE}</style>\n</head>\n<body>\n"
        "<main>\n<h1>zeta results</h1>\n"
        f'<p class="claim"><code>zeta</code>{_text(CLAIM_TAIL)}</p>\n'
        + "\n".join(body)
        + f"\n</main>\n{footer}\n</body>\n</html>\n"
    )


def render_site(plt: ModuleType, runs: list[RunData]) -> dict[str, bytes]:
    """The site as `{relative path: bytes}`; deterministic for the same inputs."""
    refined = [r for r in runs if r.refined is not None]
    body = [_counts_html(runs)]
    files: dict[str, bytes] = {}
    with plt.rc_context({"svg.hashsalt": SVG_HASH_SALT, "font.size": FONT_PT}):
        if refined:
            gap_html, files = _figures(plt, refined)
            gram_html = _gram_html(refined)
            figure_html, share_svg = _gram_figure(plt, refined)
            files["gram-share.svg"] = share_svg
            body += [gap_html, gram_html, figure_html]
    body.append(_runs_html(runs))
    files["index.html"] = _page(body).encode()
    return files


# Empty file at the top of every tree this generator writes; without it a
# non-empty directory is someone else's and must never be replaced or deleted.
# An empty, unmarked directory is accepted as a target: it holds nothing to lose.
MARKER = ".zeta-results"


def _overlaps(a: Path, b: Path) -> bool:
    """True when the resolved paths are equal or one contains the other."""
    return a == b or a in b.parents or b in a.parents


def _canonical(flag: str, path: Path) -> Path:
    """The one path every later check and action uses for this target.

    Checks and actions must share one path object: `os.path.abspath` folds `..`
    textually while the kernel follows symlinks first, so a checked spelling
    could name a different directory than the one swapped. The parent is
    resolved (symlinks, then `..`, as the kernel does) and the leaf appended
    unresolved. A leaf symlink is refused before that, since resolving it
    would hide it. A parent that does not exist resolves non-strictly: its
    existing prefix is resolved and the remainder kept, so a new tree can be
    created beneath it.
    """
    if path.is_symlink():
        raise ResultsError(f"refusing {flag}: {path.name} is a symlink")
    if path.name in ("", ".", ".."):
        raise ResultsError(f"refusing {flag} {str(path)!r}: no directory name")
    canon = path.parent.resolve() / path.name
    cwd = Path.cwd().resolve()
    if canon == cwd or canon in cwd.parents:
        raise ResultsError(f"refusing {flag}: it holds the working directory")
    return canon


def _family(canon: Path) -> list[Path]:
    """The target and the two siblings the swap creates, as the swap names them."""
    return [canon, _sibling(canon, "tmp"), _sibling(canon, "old")]


def _check_inputs(flag: str, canon: Path, inputs: list[Path]) -> None:
    for member in _family(canon):
        for item in inputs:
            if _overlaps(member, item):
                raise ResultsError(
                    f"refusing {flag}: {member.name} overlaps an input ({item.name})"
                )


def _check_symlinks(flag: str, canon: Path) -> None:
    """Refuse a symlink anywhere the swap renames or deletes."""
    for member in _family(canon):
        if member.is_symlink():
            raise ResultsError(f"refusing {flag}: {member.name} is a symlink")


def _has_marker(member: Path) -> bool:
    """True for a regular MARKER file; a symlink does not prove ownership."""
    try:
        return stat.S_ISREG((member / MARKER).lstat().st_mode)
    except OSError:
        return False


def _check_owned(flag: str, member: Path, allow_empty: bool) -> None:
    """Refuse an existing path the generator did not write (no MARKER at its top),
    except an empty directory when `allow_empty`."""
    if not member.exists():
        return
    if not member.is_dir():
        raise ResultsError(f"refusing {flag}: {member.name} is not a directory")
    if _has_marker(member):
        return
    if allow_empty and not any(member.iterdir()):
        return
    raise ResultsError(
        f"refusing {flag}: {member.name} exists and was not written by this generator"
    )


def _check_targets(out: Path, runs_out: Path, inputs: list[Path]) -> tuple[Path, Path]:
    """Refuse targets the swap could destroy; return their canonical paths.

    Covers `.`, `..`, the cwd, an input, a clash, a symlink and any existing
    path the generator did not write. Nothing is created or deleted here. The
    returned paths are the only ones the caller may act on.
    """
    targets = [
        ("--out", _canonical("--out", out)),
        ("--runs-out", _canonical("--runs-out", runs_out)),
    ]
    for flag, canon in targets:
        _check_symlinks(flag, canon)
    out_canon, runs_canon = targets[0][1], targets[1][1]
    if _overlaps(out_canon, runs_canon):
        raise ResultsError("refusing --out and --runs-out: equal or nested")
    if any(_overlaps(a, b) for a in _family(out_canon) for b in _family(runs_canon)):
        raise ResultsError("refusing --out and --runs-out: their .tmp/.old collide")
    resolved = [p.resolve() for p in inputs]
    for flag, canon in targets:
        _check_inputs(flag, canon, resolved)
    for flag, canon in targets:
        target, tmp, old = _family(canon)
        _check_owned(flag, target, allow_empty=True)
        _check_owned(flag, tmp, allow_empty=False)
        _check_owned(flag, old, allow_empty=False)
    return out_canon, runs_canon


def _sibling(path: Path, suffix: str) -> Path:
    return path.with_name(f"{path.name}.{suffix}")


def _recover(final: Path) -> None:
    """Undo a crash between the swap's renames; touch only `<final>.old` and `.tmp`."""
    old, tmp = _sibling(final, "old"), _sibling(final, "tmp")
    if old.exists():
        if final.exists():
            shutil.rmtree(old)
        else:
            old.rename(final)
    if tmp.exists():
        shutil.rmtree(tmp)


def _keep_swap(tmp: Path, final: Path) -> None:
    """Rename the old tree to `.old` and the new one in; restore on failure."""
    old = _sibling(final, "old")
    had_old = final.exists()
    if had_old:
        final.rename(old)
    try:
        tmp.rename(final)
    except OSError:
        if had_old:
            old.rename(final)
        raise


def _undo_swap(tmp: Path, final: Path) -> None:
    old = _sibling(final, "old")
    final.rename(tmp)
    if old.exists():
        old.rename(final)


def _stage(final: Path, files: dict[str, bytes]) -> Path:
    tmp = _sibling(final, "tmp")
    tmp.mkdir(parents=True)
    (tmp / MARKER).write_bytes(b"")
    for name, data in files.items():
        target = tmp / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return tmp


def publish(trees: list[tuple[Path, dict[str, bytes]]]) -> None:
    """Stage every tree, then swap them all in; any failure restores the old ones."""
    staged: list[tuple[Path, Path]] = []
    swapped: list[tuple[Path, Path]] = []
    try:
        for final, files in trees:
            staged.append((_stage(final, files), final))
        for tmp, final in staged:
            _keep_swap(tmp, final)
            swapped.append((tmp, final))
    except OSError:
        for tmp, final in reversed(swapped):
            _undo_swap(tmp, final)
        for final, _ in trees:
            shutil.rmtree(_sibling(final, "tmp"), ignore_errors=True)
        raise
    for _, final in swapped:
        shutil.rmtree(_sibling(final, "old"), ignore_errors=True)


def run_copy_files(runs: list[RunData]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for run in runs:
        files[f"{run.meta.id}/out.txt"] = run.out_text.encode()
        files[f"{run.meta.id}/err.txt"] = run.err_published.encode()
    return files


def _parse_runs(specs: list[str]) -> dict[str, Path]:
    dirs: dict[str, Path] = {}
    for spec in specs:
        run_id, sep, directory = spec.partition("=")
        if not sep or not run_id or not directory:
            raise ResultsError(f"--run {spec!r}: expected <id>=<dir>")
        if run_id in dirs:
            raise ResultsError(f"{run_id}: --run given twice")
        dirs[run_id] = Path(directory)
    return dirs


def _arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the zeta results page.")
    parser.add_argument("--runs-toml", type=Path, required=True)
    parser.add_argument("--run", action="append", default=[], metavar="ID=DIR")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs-out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _arg_parser().parse_args(argv)
    try:
        plt = _load_pyplot()
        dirs = _parse_runs(args.run)
        out, runs_out = _check_targets(
            args.out, args.runs_out, [*dirs.values(), args.runs_toml]
        )
        _recover(out)
        _recover(runs_out)
        runs = load_runs(args.runs_toml, dirs)
        site = render_site(plt, runs)
        publish([(out, site), (runs_out, run_copy_files(runs))])
    except (ResultsError, OSError) as err:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
