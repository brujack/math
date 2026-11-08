#!/usr/bin/env python3
# Vendored from ai-config .claude/scripts/cosmic_ray_prune.py @ 0694f163fbd4. Edit there, re-sync here.
"""Prune a fresh cosmic-ray 8.7.0 session by deleting rows.

Subcommands:
  diff        <session> <diff-file> <module>
  equivalents <session> <toml> (--diff <diff-file> --toml-path <path> | --full-run)

`equivalents` must run on the full fresh session, before `diff` or sharding:
its matching reads row positions and neighbouring lines that other pruning
would have thinned. `core/NumberReplacer` emits two specs per literal site,
identical but for `occurrence`; the lower `occurrence` is the `+1` offset.

Exit codes: 0 success; 1 invalid data (first stderr line starts
`cosmic_ray_prune: `, session left byte-identical); 2 usage.

Standard library only; this module never imports cosmic_ray.
"""

import argparse
import json
import re
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple, TypeVar

import tomllib

PREFIX = "cosmic_ray_prune: "

SCHEMA_8_7_0: dict[str, frozenset[str]] = {
    "work_items": frozenset({"job_id"}),
    "mutation_specs": frozenset(
        {
            "module_path",
            "operator_name",
            "operator_args",
            "occurrence",
            "start_pos_row",
            "start_pos_col",
            "end_pos_row",
            "end_pos_col",
            "definition_name",
            "job_id",
        }
    ),
    "work_results": frozenset(
        {"worker_outcome", "output", "test_outcome", "diff", "job_id"}
    ),
}


class PruneError(Exception):
    """Invalid data; `lines[0]` is the reason, the rest are hints."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__(lines[0])
        self.lines = lines


def _fail(reason: str) -> PruneError:
    return PruneError([PREFIX + reason])


def open_session(path: Path) -> sqlite3.Connection:
    """Open an existing session read-write; never creates a file."""
    uri = f"{Path(path).absolute().as_uri()}?mode=rw"
    try:
        return sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise _fail(f"cannot open session {path}: {exc}") from exc


def check_schema(conn: sqlite3.Connection) -> None:
    """Require the exact 8.7.0 column-name set for each of the three tables."""
    for table, expected in SCHEMA_8_7_0.items():
        found = frozenset(r[1] for r in conn.execute(f"PRAGMA table_info({table})"))
        if found != expected:
            missing = sorted(expected - found)
            extra = sorted(found - expected)
            raise _fail(
                f"table {table} does not match cosmic-ray 8.7.0 schema"
                f" (missing {missing}, extra {extra})"
            )


# Literal SQL per table: no table name is ever interpolated into a query.
_COUNT_SQL = {
    "work_items": "SELECT count(*) FROM work_items",
    "mutation_specs": "SELECT count(*) FROM mutation_specs",
    "work_results": "SELECT count(*) FROM work_results",
}


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(_COUNT_SQL[table]).fetchone()[0])


def check_fresh(conn: sqlite3.Connection) -> None:
    """Require an initialised session that has not been executed."""
    for table in ("work_items", "mutation_specs"):
        if _count(conn, table) == 0:
            raise _fail(f"{table} is empty; run cosmic-ray init first")
    if _count(conn, "work_results") != 0:
        raise _fail("work_results is not empty; session has already been executed")


def delete_specs(conn: sqlite3.Connection, job_ids: set[str]) -> None:
    """Delete specs then their work items in one transaction; roll back on error."""
    with conn:
        conn.executemany(
            "DELETE FROM mutation_specs WHERE job_id = ?", [(j,) for j in job_ids]
        )
        conn.executemany(
            "DELETE FROM work_items WHERE job_id = ?", [(j,) for j in job_ids]
        )


# Headers git may emit outside a hunk body, besides `diff --git`, `+++ `, `@@`.
_HEADER_PREFIXES = (
    "--- ",
    "index ",
    "new file mode ",
    "deleted file mode ",
    "similarity index ",
    "dissimilarity index ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
    "old mode ",
    "new mode ",
    "Binary files ",
)

_HUNK_RE = re.compile(r"@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?")


@dataclass
class DiffResult:
    """Changed new-side lines per `+++ b/` path, and those paths in order."""

    changed: dict[str, set[int]] = field(default_factory=dict)
    paths: list[str] = field(default_factory=list)


class _DiffWalker:
    """Count-driven walk of a unified diff: header lines are only recognised
    when both remaining hunk counts are zero, so body text that merely looks
    like a header (`--- x`, `+++ y`) is never mistaken for one."""

    def __init__(self) -> None:
        self.result = DiffResult()
        self._path: str | None = None
        self._old_left = 0
        self._new_left = 0
        self._new_line = 0
        self._after_body = False
        self._seen_plus = False
        self._lineno = 0
        self._hunk_text = ""
        self._hunk_lineno = 0

    def unfinished(self) -> PruneError:
        return _fail(
            f"diff line {self._hunk_lineno}: input ends inside hunk"
            f" {self._hunk_text!r}, whose counts are not exhausted"
        )

    def _refuse(self, reason: str) -> PruneError:
        return _fail(f"diff line {self._lineno}: {reason}")

    def in_body(self) -> bool:
        return self._old_left > 0 or self._new_left > 0

    def feed(self, line: str) -> None:
        self._lineno += 1
        if self.in_body():
            self._body(line)
        else:
            self._header(line)

    def _body(self, line: str) -> None:
        tag = line[:1]
        if tag == "\\":
            return
        if tag == "+":
            self._take(line, old=False, new=True)
            if self._path is not None:
                self.result.changed[self._path].add(self._new_line)
            self._new_line += 1
        elif tag in (" ", ""):
            self._take(line, old=True, new=True)
            self._new_line += 1
        elif tag == "-":
            self._take(line, old=True, new=False)
        else:
            raise self._refuse(f"unexpected character {tag!r} in hunk body: {line!r}")
        self._after_body = not self.in_body()

    def _take(self, line: str, *, old: bool, new: bool) -> None:
        if (old and self._old_left == 0) or (new and self._new_left == 0):
            raise self._refuse(f"hunk body line exceeds the header's counts: {line!r}")
        self._old_left -= old
        self._new_left -= new

    def _header(self, line: str) -> None:
        after_body, self._after_body = self._after_body, False
        if line.startswith("\\"):
            if not after_body:
                raise self._refuse(f"backslash line outside a hunk body: {line!r}")
        elif line.startswith("diff --git "):
            self._path = None
            self._seen_plus = False
        elif line.startswith("+++ "):
            self._file_path(line[4:])
        elif line.startswith("@@"):
            self._hunk(line)
        elif not line.startswith(_HEADER_PREFIXES):
            kind = "empty line" if line == "" else "line"
            raise self._refuse(f"unrecognised {kind} outside a hunk body: {line!r}")

    def _file_path(self, raw: str) -> None:
        path = raw.split("\t", 1)[0]
        self._seen_plus = True
        if path.startswith('"'):
            raise self._refuse(f"quoted path is not supported: {raw!r}")
        if path == "/dev/null":
            self._path = None
        elif path.startswith("b/"):
            self._path = path[2:]
            self.result.paths.append(self._path)
            self.result.changed.setdefault(self._path, set())
        else:
            raise self._refuse(
                f"path lacks the b/ prefix (use --dst-prefix=b/): {raw!r}"
            )

    def _hunk(self, line: str) -> None:
        match = _HUNK_RE.fullmatch(line)
        if match is None:
            raise self._refuse(f"malformed hunk header: {line!r}")
        if not self._seen_plus:
            raise self._refuse(f"hunk header before any +++ line: {line!r}")
        self._hunk_text = line
        self._hunk_lineno = self._lineno
        old, start, new = match.groups()
        self._old_left = 1 if old is None else int(old)
        self._new_left = 1 if new is None else int(new)
        self._new_line = int(start)


def parse_diff(text: str) -> DiffResult:
    """Collect the changed new-side line numbers of every `+++ b/` section.

    Splits on "\\n" only, as git does; str.splitlines() would also split on form
    feeds, lone carriage returns and Unicode separators inside a context line.
    """
    walker = _DiffWalker()
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    for line in lines:
        walker.feed(line)
    if walker.in_body():
        raise walker.unfinished()
    return walker.result


def spec_hits(start: int, end: int, changed: set[int]) -> bool:
    """True when the inclusive row range [start, end] holds a changed line."""
    return any(start <= line <= end for line in changed)


def _read_diff(path: Path) -> str:
    try:
        # Git splits lines on "\n" only; keep "\r", form feeds and the like.
        with path.open(encoding="utf-8", errors="surrogateescape", newline="") as fh:
            return fh.read()
    except OSError as exc:
        raise _fail(f"cannot read diff {path}: {exc}") from exc


def _run_diff(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    module: str = args.module
    result = parse_diff(_read_diff(args.diff_file))
    specs = conn.execute(
        "SELECT job_id, module_path, start_pos_row, end_pos_row FROM mutation_specs"
    ).fetchall()
    modules = sorted({row[1] for row in specs})
    if module not in modules:
        raise PruneError(
            [f"{PREFIX}module {module} matches no module_path in the session", *modules]
        )
    changed = result.changed.get(module, set())
    keep = {
        job
        for job, path, start, end in specs
        if path == module and spec_hits(start, end, changed)
    }
    delete_specs(conn, {row[0] for row in specs} - keep)
    if not changed and result.paths:
        sys.stderr.write(
            "\n".join(
                [f"diff changes nothing in {module}; its +++ b/ paths:", *result.paths]
            )
            + "\n"
        )
    sys.stdout.write(f"kept {len(keep)} of {len(specs)} (lines {len(changed)})\n")
    return 0


_T = TypeVar("_T")
_HEADER = "[[equivalent]]"
_REQUIRED_KEYS = ("operator", "function", "line", "col", "above")
_OPTIONAL_KEYS = ("row", "variant")
_NO_LINE_HINT = (
    "no spec has this line text; the line was edited, so re-author the entry"
    " from the survivor"
)


@dataclass
class Entry:
    """One `[[equivalent]]` table; `index` is its 1-based position."""

    operator: str
    function: str
    line: str
    col: int
    above: str
    row: int | None
    variant: int | None
    reason: str
    index: int


def _typed(table: dict[str, Any], key: str, kind: type[_T], index: int) -> _T:
    value = table[key]
    if not isinstance(value, kind) or isinstance(value, bool):
        raise _fail(f"entry {index}: {key} must be {kind.__name__}, got {value!r}")
    return value


def _entry(table: dict[str, Any], index: int) -> Entry:
    known = {*_REQUIRED_KEYS, *_OPTIONAL_KEYS, "reason"}
    if unknown := sorted(set(table) - known):
        raise _fail(f"entry {index}: unknown key(s) {unknown}")
    if missing := sorted(({*_REQUIRED_KEYS, "reason"}) - set(table)):
        raise _fail(f"entry {index}: missing key(s) {missing}")
    reason = _typed(table, "reason", str, index)
    if not reason.strip():
        raise _fail(f"entry {index}: reason is empty")
    return Entry(
        operator=_typed(table, "operator", str, index),
        function=_typed(table, "function", str, index),
        line=_typed(table, "line", str, index),
        col=_typed(table, "col", int, index),
        above=_typed(table, "above", str, index),
        row=_typed(table, "row", int, index) if "row" in table else None,
        variant=_typed(table, "variant", int, index) if "variant" in table else None,
        reason=reason,
        index=index,
    )


def _own_lines(text_lines: list[str], headers: list[int]) -> list[set[int]]:
    """Per entry: its header and key/value lines, never a blank or comment line."""
    owned: list[set[int]] = []
    for i, start in enumerate(headers):
        stop = headers[i + 1] - 1 if i + 1 < len(headers) else len(text_lines)
        lines = {start}
        for number in range(start + 1, stop + 1):
            stripped = text_lines[number - 1].strip()
            if stripped and not stripped.startswith("#"):
                lines.add(number)
        owned.append(lines)
    return owned


def _header_lines(text_lines: list[str]) -> list[int]:
    """1-based numbers of `[[equivalent]]` lines; any other table-like line fails."""
    headers: list[int] = []
    for number, line in enumerate(text_lines, start=1):
        if line.removesuffix("\r") == _HEADER:
            headers.append(number)
        elif line.lstrip().startswith("["):
            raise _fail(
                f"toml line {number} is not exactly {_HEADER} at column 0: {line!r}"
            )
    return headers


def _parses_to(text: str, expected: dict[str, Any]) -> bool:
    try:
        return tomllib.loads(text) == expected
    except tomllib.TOMLDecodeError:
        return False


def _verify_prefix(text_lines: list[str], headers: list[int]) -> None:
    """Nothing may precede the first header, so a header-like line inside a
    string or an inline array cannot shift the line mapping."""
    first = headers[0] - 1 if headers else len(text_lines)
    # Each line gets "\n" back (split removed it), so a CRLF line ends "\r\n".
    prefix = "".join(line + "\n" for line in text_lines[:first])
    if not _parses_to(prefix, {}):
        raise _fail(f"toml text before the first {_HEADER} holds keys or tables")


def load_entries(path: Path) -> tuple[list[Entry], list[set[int]]]:
    """Parse the toml into entries plus each entry's own (1-based) lines."""
    try:
        # newline="" keeps a bare CR: universal-newline reading would turn it
        # into a line break that git does not count, shifting own-line numbers.
        with path.open(encoding="utf-8", newline="") as handle:
            text = handle.read()
        data = tomllib.loads(text)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise _fail(f"cannot read toml {path}: {exc}") from exc
    tables = data.pop("equivalent", [])
    if data:
        raise _fail(
            f"toml has keys or tables other than [[equivalent]]: {sorted(data)}"
        )
    if not isinstance(tables, list) or not all(isinstance(t, dict) for t in tables):
        raise _fail("toml key `equivalent` must be an array of [[equivalent]] tables")
    text_lines = text.split("\n")
    headers = _header_lines(text_lines)
    if len(headers) != len(tables):
        raise _fail(
            f"toml has {len(headers)} {_HEADER} header lines but {len(tables)}"
            " parsed entries"
        )
    _verify_prefix(text_lines, headers)
    entries = [_entry(table, i) for i, table in enumerate(tables, start=1)]
    return entries, _own_lines(text_lines, headers)


class _Spec(NamedTuple):
    job_id: str
    module: str
    row: int
    end_row: int
    col: int
    function: str | None
    occurrence: int
    line: str
    above: str


@dataclass
class SourceCache:
    """Per-run caches: source files by path, and specs by operator name."""

    files: dict[str, list[str]] = field(default_factory=dict)
    specs: dict[str, list["_Spec"]] = field(default_factory=dict)


def _source_lines(module_path: str, sources: SourceCache) -> list[str]:
    if module_path not in sources.files:
        try:
            text = Path(module_path).read_text(
                encoding="utf-8", errors="surrogateescape"
            )
        except OSError as exc:
            raise _fail(f"cannot read source {module_path}: {exc}") from exc
        lines = text.split("\n")
        if lines[-1] == "":
            lines.pop()
        sources.files[module_path] = lines
    return sources.files[module_path]


def _line_and_above(lines: list[str], row: int, module_path: str) -> tuple[str, str]:
    if not 1 <= row <= len(lines):
        raise _fail(f"source {module_path} has no line {row}")
    above = ""
    for index in range(row - 2, -1, -1):
        if lines[index].strip():
            above = lines[index].strip()
            break
    return lines[row - 1].strip(), above


def _load_specs(
    conn: sqlite3.Connection, operator: str, sources: SourceCache
) -> list[_Spec]:
    if operator in sources.specs:
        return sources.specs[operator]
    rows = conn.execute(
        "SELECT job_id, module_path, start_pos_row, end_pos_row, start_pos_col,"
        " definition_name, occurrence FROM mutation_specs WHERE operator_name = ?"
        " ORDER BY occurrence, job_id",
        (operator,),
    ).fetchall()
    specs: list[_Spec] = []
    for job_id, module_path, row, end_row, col, function, occurrence in rows:
        line, above = _line_and_above(
            _source_lines(module_path, sources), row, module_path
        )
        specs.append(
            _Spec(
                job_id,
                module_path,
                row,
                end_row,
                col,
                function,
                occurrence,
                line,
                above,
            )
        )
    sources.specs[operator] = specs
    return specs


def _quote(value: str) -> str:
    """A TOML basic string, so a listed field pastes into the toml unchanged."""
    # json leaves DEL raw, which a TOML basic string forbids.
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")


def _listing(entry: Entry, specs: list[_Spec]) -> list[str]:
    shared = sorted(
        (s for s in specs if s.line == entry.line), key=lambda s: (s.row, s.col)
    )
    if not shared:
        return [_NO_LINE_HINT]
    groups: dict[tuple[object, ...], list[str]] = {}
    for s in sorted(shared, key=lambda s: s.occurrence):
        groups.setdefault((s.function, s.col, s.above, s.row), []).append(s.job_id)
    lines: list[str] = []
    for s in shared:
        group = groups[(s.function, s.col, s.above, s.row)]
        text = (
            f"row {s.row} col {s.col} function {_quote(s.function or '')}"
            f" above {_quote(s.above)}"
        )
        if len(group) > 1:
            text += f" variant {group.index(s.job_id)}"
        lines.append(text)
    return lines


def _five_key(spec: _Spec, entry: Entry) -> bool:
    return (
        spec.function == (entry.function or None)
        and spec.col == entry.col
        and spec.line == entry.line
        and spec.above == entry.above
    )


def _pick_row(
    entry: Entry, matched: list[_Spec], fail: Callable[[str], PruneError]
) -> list[_Spec]:
    rows = sorted({s.row for s in matched})
    if entry.row is None:
        if len(rows) > 1:
            raise fail(f"the match spans rows {rows}; add row")
        return matched
    if len(rows) == 1:
        raise fail(f"row {entry.row} given but the match is on one row ({rows[0]})")
    picked = [s for s in matched if s.row == entry.row]
    if not picked:
        raise fail(f"row {entry.row} selects no spec (match rows {rows})")
    return picked


def _pick_variant(
    entry: Entry, matched: list[_Spec], fail: Callable[[str], PruneError]
) -> _Spec:
    count = len(matched)
    if entry.variant is None:
        if count > 1:
            raise fail(f"{count} specs match; add variant (0..{count - 1})")
        return matched[0]
    if count == 1:
        raise fail("variant given but exactly one spec matches")
    if not 0 <= entry.variant < count:
        raise fail(f"variant {entry.variant} out of range (0..{count - 1})")
    return matched[entry.variant]


def _load_specs_for(
    conn: sqlite3.Connection, entry: Entry, sources: SourceCache
) -> list[_Spec]:
    """`_load_specs`, with a source-file failure naming the entry."""
    try:
        return _load_specs(conn, entry.operator, sources)
    except PruneError as exc:
        reason = exc.lines[0].removeprefix(PREFIX)
        raise PruneError(
            [f"{PREFIX}entry {entry.index}: {reason}", *exc.lines[1:]]
        ) from exc


def resolve_entry(
    conn: sqlite3.Connection, entry: Entry, sources: SourceCache
) -> tuple[str, str, int, int]:
    """Resolve an entry to exactly one spec: (job_id, module, start row, end row)."""
    specs = _load_specs_for(conn, entry, sources)

    def fail(reason: str) -> PruneError:
        return PruneError(
            [f"{PREFIX}entry {entry.index}: {reason}", *_listing(entry, specs)]
        )

    matched = [s for s in specs if _five_key(s, entry)]
    if not matched:
        raise fail("matches no spec")
    modules = sorted({s.module for s in matched})
    if len(modules) > 1:
        raise fail(f"the match spans more than one module_path: {modules}")
    chosen = _pick_variant(entry, _pick_row(entry, matched, fail), fail)
    return chosen.job_id, chosen.module, chosen.row, chosen.end_row


def _resolve_all(
    conn: sqlite3.Connection, entries: list[Entry]
) -> list[tuple[str, str, int, int]]:
    """Per entry, in order: (job_id, module, start row, end row); no shared spec."""
    sources = SourceCache()
    owner: dict[str, int] = {}
    resolved: list[tuple[str, str, int, int]] = []
    for entry in entries:
        job_id, module, start, end = resolve_entry(conn, entry, sources)
        if job_id in owner:
            raise _fail(
                f"entry {entry.index} resolves to the same spec as entry"
                f" {owner[job_id]}"
            )
        owner[job_id] = entry.index
        resolved.append((job_id, module, start, end))
    return resolved


def _refuse_reconfirm(
    entry: Entry, module: str, row: int, diff: DiffResult, toml_path: str
) -> PruneError:
    lines = [
        (
            f"{PREFIX}entry {entry.index} excludes a mutant on a changed line"
            f" ({module}:{row}); re-confirm it in this PR"
        )
    ]
    if toml_path not in diff.paths:
        lines.extend(diff.paths)
    return PruneError(lines)


def _check_reconfirm(
    entries: list[Entry],
    own: list[set[int]],
    resolved: list[tuple[str, str, int, int]],
    diff_file: Path,
    toml_path: str,
) -> int:
    """Require a changed own toml line for each entry on a changed source line.

    Returns R, the number of resolved specs on changed lines.
    """
    diff = parse_diff(_read_diff(diff_file))
    toml_changed = diff.changed.get(toml_path, set())
    on_changed = 0
    for entry, own_lines, (_job, module, start, end) in zip(
        entries, own, resolved, strict=True
    ):
        if Path(module).is_absolute():
            raise _fail(
                f"entry {entry.index} resolves to absolute module_path {module};"
                " --diff paths are relative, so re-confirm cannot see its changes"
            )
        hits = sorted(
            line for line in diff.changed.get(module, set()) if start <= line <= end
        )
        if not hits:
            continue
        on_changed += 1
        if not own_lines & toml_changed:
            raise _refuse_reconfirm(entry, module, hits[0], diff, toml_path)
    return on_changed


def _run_equivalents(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    entries, own = load_entries(args.toml)
    resolved = _resolve_all(conn, entries)
    total = _count(conn, "mutation_specs")
    suffix = ""
    if not args.full_run:
        on_changed = _check_reconfirm(
            entries, own, resolved, args.diff_file, args.toml_path
        )
        suffix = f" (re-confirm: diff, {on_changed} on changed lines)"
    delete_specs(conn, {job_id for job_id, _, _, _ in resolved})
    sys.stdout.write(f"excluded {len(resolved)} of {total}{suffix}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cosmic_ray_prune.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    diff = sub.add_parser("diff", help="keep only mutants on changed lines")
    diff.add_argument("session", type=Path)
    diff.add_argument("diff_file", type=Path)
    diff.add_argument("module")
    diff.set_defaults(handler=_run_diff)
    eq = sub.add_parser("equivalents", help="remove declared equivalent mutants")
    eq.add_argument("session", type=Path)
    eq.add_argument("toml", type=Path)
    eq.add_argument("--full-run", action="store_true")
    eq.add_argument("--diff", dest="diff_file", type=Path)
    eq.add_argument("--toml-path")
    eq.set_defaults(handler=_run_equivalents)
    return parser


def _prepare(path: Path) -> sqlite3.Connection:
    conn = open_session(path)
    try:
        check_schema(conn)
        check_fresh(conn)
    except sqlite3.Error as exc:
        conn.close()
        raise _fail(f"cannot read session {path}: {exc}") from exc
    except PruneError:
        conn.close()
        raise
    return conn


def _dispatch(args: argparse.Namespace) -> int:
    conn = _prepare(args.session)
    try:
        return int(args.handler(conn, args))
    finally:
        conn.close()


def _check_modes(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Exit 2 unless `equivalents` has `--full-run` alone or `--diff` with `--toml-path`.

    argparse cannot express a required pair inside a mutually exclusive group.
    """
    if args.command != "equivalents":
        return
    has_pair = args.diff_file is not None and args.toml_path is not None
    if args.full_run and (args.diff_file is not None or args.toml_path is not None):
        parser.error("--full-run excludes --diff and --toml-path")
    if not args.full_run and not has_pair:
        parser.error("equivalents needs --full-run, or --diff with --toml-path")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _check_modes(parser, args)
    try:
        return _dispatch(args)
    except PruneError as exc:
        sys.stderr.write("\n".join(exc.lines) + "\n")
        return 1
    except sqlite3.Error as exc:
        sys.stderr.write(f"{PREFIX}database error on session {args.session}: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
