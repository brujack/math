"""Summarise a finished cosmic-ray session as one verdict line.

Usage: cosmic_ray_cell_status.py <session.sqlite> <label> [--out FILE] [--survivors FILE]

Prints `green: <label> — S surviving, T timed out, K jobs` and exits 0, or
`red: <label> — <reason>` and exits 1. A session is red when it has no work
items, the result count differs from the work-item count, or any result is not
worker_outcome NORMAL with test_outcome KILLED or SURVIVED (a NULL is unusable). Survivors and
timeouts (test_outcome KILLED with output 'timeout') are never red.
cosmic-ray stores enum names uppercase; a differently-cased value is red.
--out also writes the line to FILE; --survivors writes one
`<module_path>:<start_pos_row> <operator_name>` line per survivor, sorted (empty
for a red cell, so a stale file never survives). Both files are written via temp
files and renamed only once both writes succeed; the verdict prints after that,
and a write failure turns the verdict red.
"""

import argparse
import contextlib
import os
import pathlib
import sqlite3
import sys
import tempfile

DASH = "—"
# coalesce: a NULL outcome makes the comparison NULL, and NOT NULL is NULL (not true),
# which would let the row slip past the filter and read green.
GOOD_OUTCOMES = (
    "coalesce(worker_outcome = 'NORMAL' AND test_outcome IN ('KILLED', 'SURVIVED'), 0)"
)


def count(conn: sqlite3.Connection, sql: str) -> int:
    return int(conn.execute(sql).fetchone()[0])


def assess(conn: sqlite3.Connection, label: str) -> tuple[bool, str]:
    """Return (is_green, verdict line) for an open session."""
    jobs = count(conn, "SELECT count(*) FROM work_items")
    if jobs == 0:
        return False, f"red: {label} {DASH} no work items"
    unexecuted = count(
        conn,
        "SELECT count(*) FROM work_items w LEFT JOIN work_results r "
        "ON r.job_id = w.job_id WHERE r.job_id IS NULL",
    )
    if unexecuted:
        return False, f"red: {label} {DASH} {unexecuted} work items without a result"
    orphans = count(
        conn,
        "SELECT count(*) FROM work_results r LEFT JOIN work_items w "
        "ON w.job_id = r.job_id WHERE w.job_id IS NULL",
    )
    if orphans:
        return False, f"red: {label} {DASH} {orphans} results without a work item"
    bad = conn.execute(
        "SELECT DISTINCT coalesce(worker_outcome, 'NULL'), coalesce(test_outcome, 'NULL') "
        f"FROM work_results WHERE NOT {GOOD_OUTCOMES} ORDER BY 1, 2"
    ).fetchall()
    if bad:
        pairs = ", ".join(f"{w}/{t}" for w, t in bad)
        return False, f"red: {label} {DASH} unusable outcomes (worker/test): {pairs}"
    survivors = count(
        conn, "SELECT count(*) FROM work_results WHERE test_outcome = 'SURVIVED'"
    )
    timeouts = count(
        conn,
        "SELECT count(*) FROM work_results "
        "WHERE test_outcome = 'KILLED' AND output = 'timeout'",
    )
    return (
        True,
        f"green: {label} {DASH} {survivors} surviving, {timeouts} timed out, {jobs} jobs",
    )


def survivor_lines(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT m.module_path, m.start_pos_row, m.operator_name "
        "FROM work_results r JOIN mutation_specs m USING (job_id) "
        "WHERE r.test_outcome = 'SURVIVED'"
    ).fetchall()
    return sorted(f"{path}:{row} {op}" for path, row, op in rows)


def write_atomically(targets: list[tuple[pathlib.Path, str]]) -> None:
    """Write every (path, text) via a temp file beside it; rename only after all succeed.

    Raises OSError on any failure, having removed every temp file it created.
    """
    staged: list[tuple[str, pathlib.Path]] = []
    try:
        for path, text in targets:
            fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
            staged.append((tmp_name, path))
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
        for tmp_name, path in staged:
            os.replace(tmp_name, path)
    finally:
        for tmp_name, _ in staged:
            with contextlib.suppress(FileNotFoundError):  # already renamed into place
                os.unlink(tmp_name)


def evaluate(session: pathlib.Path, label: str) -> tuple[bool, str, list[str]]:
    """Return (is_green, verdict line, survivor lines); survivors are empty unless green."""
    if not session.is_file():
        return False, f"red: {label} {DASH} no such session file: {session}", []
    try:
        # Read-only: a status check must never alter the session it judges. The URI
        # is percent-encoded so '#', '?' and '%' in the path are not parsed as syntax.
        conn = sqlite3.connect(session.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            green, line = assess(conn, label)
            return green, line, survivor_lines(conn) if green else []
        finally:
            conn.close()
    except sqlite3.Error as err:
        return False, f"red: {label} {DASH} unreadable session: {err}", []


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Summarise a finished cosmic-ray session as one verdict line."
    )
    parser.add_argument("session", type=pathlib.Path)
    parser.add_argument("label")
    parser.add_argument("--out", type=pathlib.Path)
    parser.add_argument("--survivors", type=pathlib.Path)
    args = parser.parse_args(argv)

    green, line, survivors = evaluate(args.session, args.label)
    targets: list[tuple[pathlib.Path, str]] = []
    if args.out is not None:
        targets.append((args.out, line + "\n"))
    if args.survivors is not None:
        targets.append((args.survivors, "".join(f"{s}\n" for s in survivors)))
    try:
        write_atomically(targets)
    except OSError as err:
        print(f"red: {args.label} {DASH} cannot write output files: {err}")
        return 1

    print(line)
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
